"""
DMS-NAS Telegram Bot — All sprints (1-7) in one file.
Entry point: python -m apps.bot.bot  (from dms-nas/ root)
"""

import asyncio
import io
import json
import logging
import os
import sys
import warnings
from datetime import datetime, date

# Подавить per_message предупреждения — наш дизайн per_chat/per_user, это intentional
warnings.filterwarnings(
    "ignore",
    message=".*per_message=False.*CallbackQueryHandler.*",
    category=UserWarning,
)

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── path bootstrap ─────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.bot.bot_config import (
    BOT_TOKEN, DOC_TYPES, FINANCE_TYPES, FINANCE_TRANSITIONS,
    ROLE_PERMISSIONS, ROLE_LABELS, DEFAULT_CHECKLIST, NAS_ROOT_SHARES,
    EXPIRY_HOUR,
)
import apps.bot.bot_db as db
import apps.bot.bot_nas as nas_helper
from core.services import approvals, expiry as expiry_svc, finance as fin_svc
from core.services import packages as pkg_svc, reports as rep_svc
from core.utils import file_hash, category_from_doc_type

# ── Logging (Sprint 8: RotatingFileHandler) ────────────────────────────────────
from logging.handlers import RotatingFileHandler as _RFH

_fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
_stream_h = logging.StreamHandler()
_stream_h.setFormatter(_fmt)
_file_h = _RFH("bot.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
_file_h.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_stream_h, _file_h])

# Подавить HTTP-запросы httpx и telegram network spam
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("telegram.vendor.ptb_urllib3").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("bot")

import core.monitoring as mon

# ── Path store: решает Button_data_invalid (лимит 64 байта в callback_data) ────
# Telegram не принимает длинные пути — храним здесь, передаём короткий ID
_PATH_STORE: dict[str, str] = {}   # id → full_path
_PATH_REV:   dict[str, str] = {}   # full_path → id
_PATH_SEQ = [0]                    # счётчик в списке чтобы менять из вложенных ф-й


def _pid(path: str) -> str:
    """Сохранить путь и вернуть короткий числовой ID."""
    if path in _PATH_REV:
        return _PATH_REV[path]
    pid = str(_PATH_SEQ[0])
    _PATH_SEQ[0] += 1
    _PATH_STORE[pid] = path
    _PATH_REV[path] = pid
    return pid


def _pget(pid: str) -> str:
    """Получить полный путь по ID."""
    return _PATH_STORE.get(pid, "/")

# ── Conversation states ────────────────────────────────────────────────────────
(
    # Upload
    UPL_OBJ, UPL_TYPE, UPL_SECTION, UPL_FILE,
    # Find
    FIND_BROWSE,
    # Approve
    APR_LIST, APR_ACTION, APR_REASON,
    # Expiry
    EXP_MENU, EXP_ADD_TITLE, EXP_ADD_OBJ, EXP_ADD_DATE,
    # Photo report
    PHO_OBJ, PHO_CL, PHO_ITEM,
    # Package
    PKG_OBJ, PKG_PERIOD, PKG_TYPES, PKG_CONFIRM,
    # Finance
    FIN_MENU, FIN_ADD_OBJ, FIN_ADD_TYPE, FIN_ADD_FILE, FIN_ADD_AMT, FIN_ADD_CP,
    FIN_STATUS_DOC, FIN_STATUS_NEW,
    # Create object
    CRE_NAME, CRE_CONFIRM,
    # Search
    SRC_QUERY,
    # Problems
    PRB_LIST, PRB_ADD_DOC, PRB_ADD_LABEL, PRB_ADD_DESC,
    # Admin
    ADM_SET_ROLE_USER, ADM_SET_ROLE_VALUE,
    # Admin: object access
    ADM_OBJ_ACTION, ADM_OBJ_SELECT_USER, ADM_OBJ_SELECT_OBJ,
) = range(39)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _user(update: Update):
    return update.effective_user


def _uid(update: Update) -> int:
    return _user(update).id


def _has(update: Update, perm: str) -> bool:
    user = db.get_user(_uid(update))
    if not user or not user["is_active"]:
        return False
    return perm in ROLE_PERMISSIONS.get(user["role"], [])


def _role(update: Update) -> str:
    user = db.get_user(_uid(update))
    return user["role"] if user else "viewer"


def _kb(rows: list[list[str]], one_time: bool = True) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=one_time)


def _ik(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=data) for label, data in row]
        for row in rows
    ])


def _objects_from_nas() -> list[str]:
    """List top-level objects from all known NAS shares."""
    objects: list[str] = []
    for share in NAS_ROOT_SHARES:
        items = nas_helper.nas_list_folder(share)
        for item in items:
            if item.get("isdir"):
                objects.append(item["name"])
    if not objects:
        objects = ["Днепр", "Обмен"]
    return objects


async def _main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = _uid(update)
    user = db.get_user(uid)
    if not user or not user["is_active"]:
        await update.effective_message.reply_text(
            "⛔ Вы не зарегистрированы. Отправьте /start"
        )
        return

    role = user["role"]
    perms = ROLE_PERMISSIONS.get(role, [])
    rows = []
    if "upload"       in perms: rows.append(["📤 Загрузить документ"])
    if "find"         in perms: rows.append(["📂 Найти документ"])
    if "approve"      in perms: rows.append(["✅ На проверке"])
    if "expiry"       in perms: rows.append(["⏰ Сроки"])
    if "photo_report" in perms: rows.append(["📸 Фотоотчёт"])
    if "package"      in perms: rows.append(["📦 Пакет документов"])
    if "finance"      in perms: rows.append(["💰 Финансы"])
    if "problems"     in perms: rows.append(["⚠️ Проблемы"])
    if "search"       in perms: rows.append(["🔍 Поиск"])
    if "my_uploads"   in perms: rows.append(["📋 Мои загрузки"])
    if "create_object" in perms: rows.append(["🏗️ Создать объект"])
    if "manage_users" in perms:
        rows.append(["👥 Пользователи"])
        rows.append(["🔑 Доступ к объектам"])

    label = ROLE_LABELS.get(role, role)
    await update.effective_message.reply_text(
        f"👷 DMS-NAS | {label}\nВыберите действие:",
        reply_markup=_kb(rows, one_time=False),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 12: OCR background helper
# ──────────────────────────────────────────────────────────────────────────────

def _run_ocr_background(file_bytes: bytes, filename: str,
                        upload_id: int, doc_id: int) -> None:
    """Launch OCR in a daemon thread so it doesn't block the bot."""
    import threading
    def _worker():
        try:
            from core.services.ocr import run_ocr
            result = run_ocr(file_bytes, filename)
            if result["ok"] and result.get("raw_text"):
                db.create_ocr_result(upload_id, doc_id, result)
                logger.info("OCR saved for upload_id=%d doc_id=%d conf=%d%%",
                            upload_id, doc_id, result["confidence"])
        except Exception as exc:
            logger.warning("OCR background error: %s", exc)
    threading.Thread(target=_worker, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
# /start — registration
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _user(update)
    db.upsert_user(u.id, u.username or "", u.full_name or "")
    user = db.get_user(u.id)
    if not user["is_active"]:
        await update.message.reply_text("⛔ Ваш аккаунт отключён. Обратитесь к администратору.")
        return
    await update.message.reply_text(
        f"👋 Добро пожаловать в DMS-NAS!\n"
        f"Роль: *{ROLE_LABELS.get(user['role'], user['role'])}*",
        parse_mode=ParseMode.MARKDOWN,
    )
    await _main_menu(update, context)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _main_menu(update, context)


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 1 — UPLOAD
# ──────────────────────────────────────────────────────────────────────────────

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "upload"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    objects = _objects_from_nas()
    context.user_data["upload_objects"] = objects
    rows = [[o] for o in objects] + [["❌ Отмена"]]
    await update.effective_message.reply_text(
        "📂 Выберите объект:", reply_markup=_kb(rows)
    )
    return UPL_OBJ


async def upload_got_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END

    context.user_data["upload_obj"] = update.message.text
    rows = [[t] for t in DOC_TYPES] + [["❌ Отмена"]]
    await update.message.reply_text("📁 Тип документа:", reply_markup=_kb(rows))
    return UPL_TYPE


async def upload_got_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END

    context.user_data["upload_type"] = update.message.text
    await update.message.reply_text(
        "📝 Укажите участок/раздел (или отправьте «-» чтобы пропустить):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return UPL_SECTION


async def upload_got_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sec = update.message.text.strip()
    context.user_data["upload_section"] = "" if sec == "-" else sec
    await update.message.reply_text(
        "📎 Отправьте файл, фото или видео:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return UPL_FILE


async def upload_got_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    uid = _uid(update)

    # Determine file object and original filename
    if msg.document:
        tg_file = msg.document
        filename = tg_file.file_name or f"doc_{datetime.now():%Y%m%d_%H%M%S}"
    elif msg.photo:
        tg_file = msg.photo[-1]
        filename = f"photo_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    elif msg.video:
        tg_file = msg.video
        filename = getattr(tg_file, "file_name", None) or f"video_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    else:
        await msg.reply_text("⚠️ Отправьте файл, фото или видео.")
        return UPL_FILE

    obj  = context.user_data.get("upload_obj", "")
    typ  = context.user_data.get("upload_type", "Другое")
    sec  = context.user_data.get("upload_section", "")

    await msg.reply_text("⏳ Загружаю на NAS…")

    file_obj = await context.bot.get_file(tg_file.file_id)
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    file_bytes = buf.getvalue()

    dest_folder = nas_helper.build_inbox_path(obj, typ)
    ok = nas_helper.nas_upload(dest_folder, filename, file_bytes)

    if ok:
        nas_path = f"{dest_folder}/{filename}"
        fhash = file_hash(file_bytes)
        fsize = len(file_bytes)

        # Sprint 11: Document Registry — дедупликация по SHA-256
        existing = db.find_document_by_hash(fhash)
        if existing:
            doc_id = existing["id"]
            dedup_note = f"\n♻️ Файл уже в реестре (doc #{doc_id})"
        else:
            doc_id = db.create_document(
                object_name=obj,
                category=category_from_doc_type(typ),
                doc_type=typ,
                nas_path=nas_path,
                original_filename=filename,
                file_hash=fhash,
                file_size=fsize,
                created_by=uid,
            )
            dedup_note = f"\n📋 Реестр doc #{doc_id}"

        upload_id = db.log_upload(uid, filename, nas_path, typ, obj, sec, doc_id=doc_id)
        db.audit(uid, "upload", "upload", upload_id, f"{obj}/{typ}/{filename}")

        # Sprint 12: OCR — запускаем в фоне для PDF и изображений
        ocr_note = ""
        if not existing:  # не запускаем OCR для дубликатов
            _run_ocr_background(file_bytes, filename, upload_id, doc_id)
            ocr_note = "\n🔍 OCR запущен — результат появится в веб-панели"

        await msg.reply_text(
            f"✅ Загружено!\n"
            f"Объект: {obj}\nТип: {typ}\n"
            f"Путь: `{nas_path}`"
            f"{dedup_note}{ocr_note}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await msg.reply_text("❌ Ошибка загрузки на NAS. Попробуйте позже.")

    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 1 — FIND / NAS Browser
# ──────────────────────────────────────────────────────────────────────────────

async def find_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "find"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    context.user_data["find_path"] = "/"
    await _show_folder(update, context, "/")
    return FIND_BROWSE


async def _show_folder(update: Update, context: ContextTypes.DEFAULT_TYPE, path: str):
    if path == "/":
        items = [{"name": s.lstrip("/"), "isdir": True, "path": s}
                 for s in NAS_ROOT_SHARES]
    else:
        raw = nas_helper.nas_list_folder(path)
        items = []
        for f in raw:
            items.append({
                "name": f.get("name", ""),
                "isdir": f.get("isdir", False),
                "path": f"{path}/{f.get('name', '')}".replace("//", "/"),
            })

    # Пути кириллицей могут превышать лимит 64 байта — используем короткие ID
    if not items:
        parent = path.rsplit("/", 1)[0] or "/"
        markup = _ik([[("⬆️ Назад", f"fd|{_pid(parent)}")]])
        text = f"📂 `{path}` — пусто"
    else:
        buttons = []
        for item in items[:20]:
            icon = "📁" if item["isdir"] else "📄"
            cb = f"fd|{_pid(item['path'])}" if item["isdir"] else f"fl|{_pid(item['path'])}"
            # Обрезаем имя чтобы кнопка не была слишком длинной
            label = f"{icon} {item['name'][:40]}"
            buttons.append([(label, cb)])

        nav = []
        if path != "/":
            parent = path.rsplit("/", 1)[0] or "/"
            nav.append(("⬆️ Назад", f"fd|{_pid(parent)}"))
        nav.append(("🏠 Главная", f"fd|{_pid('/')}"))
        nav.append(("❌ Закрыть", "fc"))
        buttons.append(nav)
        markup = _ik(buttons)
        text = f"📂 `{path}`\n{len(items)} элементов"

    msg = update.effective_message
    if msg.text:
        await msg.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        try:
            await msg.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.effective_chat.send_message(text, reply_markup=markup,
                                                     parse_mode=ParseMode.MARKDOWN)


async def find_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    # fd|<id> — перейти в папку
    if data.startswith("fd|"):
        pid = data[3:]
        path = _pget(pid)
        context.user_data["find_path"] = path
        await _show_folder(update, context, path)
        return FIND_BROWSE

    # fl|<id> — скачать файл
    if data.startswith("fl|"):
        pid = data[3:]
        path = _pget(pid)
        await query.edit_message_text(f"⏳ Скачиваю…")
        content = nas_helper.nas_download(path)
        if content:
            filename = path.rsplit("/", 1)[-1]
            await update.effective_chat.send_document(
                document=io.BytesIO(content),
                filename=filename,
                caption=f"📄 {filename}",
            )
        else:
            await update.effective_chat.send_message("❌ Не удалось скачать файл")
        return FIND_BROWSE

    if data == "fc":
        await query.edit_message_text("Просмотр завершён.")
        await _main_menu(update, context)
        return ConversationHandler.END

    return FIND_BROWSE


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 2 — EXPIRY / DEADLINES
# ──────────────────────────────────────────────────────────────────────────────

async def expiry_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "expiry"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    uid = _uid(update)
    items = db.list_expiry_for_user(uid)
    text = "⏰ *Ваши сроки:*\n\n"
    today = date.today()
    for it in items:
        try:
            exp = date.fromisoformat(it["expires_at"])
            delta = (exp - today).days
            if delta < 0:
                status_icon = "🔴"
            elif delta <= 1:
                status_icon = "🟠"
            elif delta <= 7:
                status_icon = "🟡"
            else:
                status_icon = "🟢"
        except Exception:
            status_icon = "⚪"
            delta = "?"
        text += f"{status_icon} [{it['id']}] {it['title']}\n"
        text += f"   Объект: {it['object_name']}  |  Срок: {it['expires_at']}  |  Осталось: {delta} д.\n\n"

    if not items:
        text += "_Нет активных сроков_"

    rows = [["➕ Добавить срок"], ["❌ Отмена"]]
    await update.effective_message.reply_text(
        text, reply_markup=_kb(rows), parse_mode=ParseMode.MARKDOWN
    )
    return EXP_MENU


async def expiry_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text
    if txt == "➕ Добавить срок":
        await update.message.reply_text(
            "✏️ Введите название документа/срока:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EXP_ADD_TITLE
    await _main_menu(update, context)
    return ConversationHandler.END


async def expiry_add_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["exp_title"] = update.message.text.strip()
    objects = _objects_from_nas()
    rows = [[o] for o in objects] + [["❌ Отмена"]]
    await update.message.reply_text("📂 Объект:", reply_markup=_kb(rows))
    return EXP_ADD_OBJ


async def expiry_add_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    context.user_data["exp_obj"] = update.message.text
    await update.message.reply_text(
        "📅 Введите дату истечения (ГГГГ-ММ-ДД):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return EXP_ADD_DATE


async def expiry_add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    try:
        date.fromisoformat(raw)
    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат. Пример: 2025-12-31")
        return EXP_ADD_DATE

    uid = _uid(update)
    item_id = db.add_expiry(
        uid,
        context.user_data["exp_title"],
        context.user_data["exp_obj"],
        raw,
    )
    await update.message.reply_text(f"✅ Срок #{item_id} добавлен: {raw}")
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 3 — APPROVE / REJECT
# ──────────────────────────────────────────────────────────────────────────────

async def approve_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "approve"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    pending = db.list_pending_uploads(limit=10)
    if not pending:
        await update.effective_message.reply_text(
            "✅ Нет документов на проверке.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _main_menu(update, context)
        return ConversationHandler.END

    context.user_data["pending_list"] = [dict(r) for r in pending]
    context.user_data["pending_idx"] = 0
    await _show_pending_card(update, context)
    return APR_ACTION


async def _show_pending_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lst = context.user_data.get("pending_list", [])
    idx = context.user_data.get("pending_idx", 0)
    if idx >= len(lst):
        await update.effective_message.reply_text("✅ Все документы просмотрены.")
        await _main_menu(update, context)
        return

    item = lst[idx]
    text = (
        f"📋 *Документ {idx+1}/{len(lst)}*\n"
        f"ID: `{item['id']}`\n"
        f"Файл: {item['filename']}\n"
        f"Объект: {item['object_name']}\n"
        f"Тип: {item['doc_type']}\n"
        f"Загрузил: {item.get('full_name', '?')} ({item.get('role', '?')})\n"
        f"Дата: {item['uploaded_at'][:16]}\n"
        f"Путь: `{item['nas_path']}`"
    )
    markup = _ik([
        [("✅ Утвердить", f"apr_ok|{item['id']}"),
         ("❌ Отклонить", f"apr_no|{item['id']}")],
        [("⬇️ Скачать", f"apr_dl|{_pid(item['nas_path'])}"),
         ("⏭ Следующий", "apr_next")],
        [("🏠 Меню", "apr_exit")],
    ])
    msg = update.effective_message
    try:
        await msg.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.effective_chat.send_message(text, reply_markup=markup,
                                                 parse_mode=ParseMode.MARKDOWN)


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("apr_ok|"):
        upload_id = int(data.split("|")[1])
        uid = _uid(update)
        result = approvals.approve_doc(db, nas_helper.get_nas(), upload_id, uid)
        if result["ok"]:
            row = db.get_upload(upload_id)
            uploader_id = row["telegram_id"] if row else None
            await query.edit_message_text(f"✅ Документ #{upload_id} утверждён!")
            if uploader_id:
                try:
                    await context.bot.send_message(
                        uploader_id,
                        f"✅ Ваш документ *{row['filename']}* утверждён!",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass
        else:
            await query.edit_message_text(f"❌ Ошибка: {result['error']}")
        context.user_data["pending_idx"] = context.user_data.get("pending_idx", 0) + 1
        await _show_pending_card(update, context)
        return APR_ACTION

    if data.startswith("apr_no|"):
        upload_id = int(data.split("|")[1])
        context.user_data["reject_upload_id"] = upload_id
        await query.edit_message_text("💬 Укажите причину отклонения:")
        return APR_REASON

    if data.startswith("apr_dl|"):
        pid = data.split("|", 1)[1]
        path = _pget(pid)
        await query.edit_message_text("⏳ Скачиваю…")
        content = nas_helper.nas_download(path)
        if content:
            fname = path.rsplit("/", 1)[-1]
            await update.effective_chat.send_document(io.BytesIO(content), filename=fname)
        else:
            await update.effective_chat.send_message("❌ Не удалось скачать")
        await _show_pending_card(update, context)
        return APR_ACTION

    if data == "apr_next":
        context.user_data["pending_idx"] = context.user_data.get("pending_idx", 0) + 1
        await _show_pending_card(update, context)
        return APR_ACTION

    if data == "apr_exit":
        await query.edit_message_text("Проверка завершена.")
        await _main_menu(update, context)
        return ConversationHandler.END

    return APR_ACTION


async def approve_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    upload_id = context.user_data.get("reject_upload_id")
    uid = _uid(update)
    result = approvals.reject_doc(db, nas_helper.get_nas(), upload_id, uid, reason)
    if result["ok"]:
        uploader_id = result.get("uploader_id")
        await update.message.reply_text(f"❌ Документ #{upload_id} отклонён.")
        if uploader_id:
            try:
                row = db.get_upload(upload_id)
                await context.bot.send_message(
                    uploader_id,
                    f"❌ Ваш документ *{row['filename']}* отклонён.\n"
                    f"Причина: {reason}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
    else:
        await update.message.reply_text(f"⚠️ Ошибка: {result['error']}")

    context.user_data["pending_idx"] = context.user_data.get("pending_idx", 0) + 1
    await _show_pending_card(update, context)
    return APR_ACTION


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 4 — PHOTO REPORT
# ──────────────────────────────────────────────────────────────────────────────

async def photo_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "photo_report"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    objects = _objects_from_nas()
    rows = [[o] for o in objects] + [["❌ Отмена"]]
    await update.effective_message.reply_text("📂 Выберите объект:", reply_markup=_kb(rows))
    return PHO_OBJ


async def photo_got_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    context.user_data["pho_obj"] = update.message.text

    checklists = db.list_checklists()
    if checklists:
        rows = [[f"[{cl['id']}] {cl['name']}"] for cl in checklists]
        rows.append(["📝 Стандартный чек-лист"])
    else:
        rows = [["📝 Стандартный чек-лист"]]
    rows.append(["❌ Отмена"])
    await update.message.reply_text("📋 Выберите чек-лист:", reply_markup=_kb(rows))
    return PHO_CL


async def photo_got_cl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text
    if txt == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END

    if txt == "📝 Стандартный чек-лист":
        items = DEFAULT_CHECKLIST
        cl_id = None
    else:
        try:
            cl_id = int(txt.split("]")[0].strip("["))
            row = db.get_checklist(cl_id)
            items = json.loads(row["items"]) if row else DEFAULT_CHECKLIST
        except Exception:
            items = DEFAULT_CHECKLIST
            cl_id = None

    context.user_data["pho_items"] = items
    context.user_data["pho_cl_id"] = cl_id
    context.user_data["pho_idx"] = 0

    uid = _uid(update)
    report = rep_svc.start_report(db, uid, context.user_data["pho_obj"], cl_id)
    context.user_data["pho_report_id"] = report["report_id"]

    await _ask_photo_item(update, context)
    return PHO_ITEM


async def _ask_photo_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = context.user_data["pho_items"]
    idx = context.user_data["pho_idx"]
    if idx >= len(items):
        rep_svc.finish_report(db, context.user_data["pho_report_id"])
        await update.effective_message.reply_text(
            "✅ Фотоотчёт завершён! Все фото сохранены на NAS.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _main_menu(update, context)
        return

    item = items[idx]
    rows = [["⏭ Пропустить"], ["❌ Завершить"]]
    await update.effective_message.reply_text(
        f"📸 Пункт {idx+1}/{len(items)}: *{item}*\nОтправьте фото:",
        reply_markup=_kb(rows),
        parse_mode=ParseMode.MARKDOWN,
    )


async def photo_got_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    items = context.user_data["pho_items"]
    idx = context.user_data["pho_idx"]

    if msg.text == "⏭ Пропустить":
        context.user_data["pho_idx"] += 1
        await _ask_photo_item(update, context)
        return PHO_ITEM

    if msg.text == "❌ Завершить":
        rep_svc.finish_report(db, context.user_data["pho_report_id"])
        await msg.reply_text("✅ Фотоотчёт сохранён.", reply_markup=ReplyKeyboardRemove())
        await _main_menu(update, context)
        return ConversationHandler.END

    if not msg.photo:
        await msg.reply_text("⚠️ Отправьте фото.")
        return PHO_ITEM

    await msg.reply_text(f"⏳ Сохраняю фото {idx+1}…")
    file_obj = await context.bot.get_file(msg.photo[-1].file_id)
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    file_bytes = buf.getvalue()

    result = rep_svc.save_report_item(
        db, nas_helper.get_nas(),
        context.user_data["pho_report_id"],
        idx, items[idx], file_bytes, "photo.jpg",
    )
    if result["ok"]:
        # Sprint 11: register photo in document registry with SHA-256
        try:
            fhash   = file_hash(file_bytes)
            fsize   = len(file_bytes)
            obj_name = context.user_data.get("pho_obj", "")
            existing = db.find_document_by_hash(fhash)
            if not existing:
                db.create_document(
                    object_name=obj_name,
                    category="photo",
                    doc_type="Фотоотчёт",
                    nas_path=result.get("nas_path", ""),
                    original_filename=result["filename"],
                    file_hash=fhash,
                    file_size=fsize,
                    created_by=_uid(update),
                )
        except Exception as _e:
            logger.warning("Registry error for photo: %s", _e)
        await msg.reply_text(f"✅ {result['filename']} сохранено")
    else:
        await msg.reply_text(f"⚠️ Ошибка: {result['error']}")

    context.user_data["pho_idx"] += 1
    await _ask_photo_item(update, context)
    return PHO_ITEM


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 5 — PACKAGES
# ──────────────────────────────────────────────────────────────────────────────

async def package_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "package"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    objects = _objects_from_nas()
    rows = [[o] for o in objects] + [["❌ Отмена"]]
    await update.effective_message.reply_text("📂 Объект:", reply_markup=_kb(rows))
    return PKG_OBJ


async def pkg_got_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    context.user_data["pkg_obj"] = update.message.text
    await update.message.reply_text(
        "📅 Период (например: 2025-12 или оставьте «-» для всех):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PKG_PERIOD


async def pkg_got_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    p = update.message.text.strip()
    context.user_data["pkg_period"] = "" if p == "-" else p

    rows = [[t] for t in DOC_TYPES] + [["✅ Все типы"], ["❌ Отмена"]]
    context.user_data["pkg_selected_types"] = []
    await update.message.reply_text(
        "📁 Выберите тип документа (можно несколько — по одному; «✅ Все типы» для всех):",
        reply_markup=_kb(rows),
    )
    return PKG_TYPES


async def pkg_got_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text
    if txt == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    if txt == "✅ Все типы":
        context.user_data["pkg_selected_types"] = DOC_TYPES
    elif txt in DOC_TYPES:
        if txt not in context.user_data["pkg_selected_types"]:
            context.user_data["pkg_selected_types"].append(txt)
        await update.message.reply_text(
            f"Добавлено: {txt}\nВыбрано: {', '.join(context.user_data['pkg_selected_types'])}\n"
            f"Нажмите «✅ Готово» или выберите ещё.",
            reply_markup=_kb([[t] for t in DOC_TYPES] + [["✅ Готово"], ["❌ Отмена"]]),
        )
        return PKG_TYPES

    selected = context.user_data["pkg_selected_types"]
    if not selected:
        await update.message.reply_text("⚠️ Выберите хотя бы один тип.")
        return PKG_TYPES

    obj = context.user_data["pkg_obj"]
    period = context.user_data["pkg_period"]
    markup = _ik([
        [("✅ Сформировать", "pkg_do"), ("❌ Отмена", "pkg_cancel")]
    ])
    await update.message.reply_text(
        f"📦 Параметры пакета:\n"
        f"Объект: {obj}\nПериод: {period or 'все'}\n"
        f"Типы: {', '.join(selected)}",
        reply_markup=markup,
    )
    return PKG_CONFIRM


async def pkg_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "pkg_cancel":
        await query.edit_message_text("Отменено.")
        await _main_menu(update, context)
        return ConversationHandler.END

    await query.edit_message_text("⏳ Формирую пакет… Это может занять несколько минут.")
    uid = _uid(update)
    result = pkg_svc.build_package(
        nas_helper.get_nas(), db, uid,
        context.user_data["pkg_obj"],
        context.user_data["pkg_period"],
        context.user_data["pkg_selected_types"],
    )
    if result["ok"]:
        await update.effective_chat.send_document(
            document=io.BytesIO(result["zip_bytes"]),
            filename=result["zip_name"],
            caption=f"📦 Пакет: {result['count']} файлов\n{result['summary'][:500]}",
        )
    else:
        await update.effective_chat.send_message(f"❌ {result['error']}")

    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 5 — CREATE OBJECT
# ──────────────────────────────────────────────────────────────────────────────

async def create_object_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "create_object"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "🏗️ Введите название нового объекта (латиница, без пробелов — лучше транслит):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CRE_NAME


async def create_got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip().replace(" ", "_")
    context.user_data["new_obj_name"] = name
    markup = _ik([
        [("✅ Создать", "cre_do"), ("❌ Отмена", "cre_cancel")]
    ])
    await update.message.reply_text(
        f"Будет создан объект *{name}* со стандартной структурой папок на NAS.",
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN,
    )
    return CRE_CONFIRM


async def create_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cre_cancel":
        await query.edit_message_text("Отменено.")
        await _main_menu(update, context)
        return ConversationHandler.END

    name = context.user_data["new_obj_name"]
    await query.edit_message_text(f"⏳ Создаю структуру папок для «{name}»…")
    created = rep_svc.create_object_structure(nas_helper.get_nas(), name)
    db.audit(_uid(update), "create_object", "object", 0, f"object={name} folders={len(created)}")
    await update.effective_chat.send_message(
        f"✅ Объект *{name}* создан!\nСоздано папок: {len(created)}",
        parse_mode=ParseMode.MARKDOWN,
    )
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 5 — QUICK SEARCH
# ──────────────────────────────────────────────────────────────────────────────

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "search"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "🔍 Введите поисковый запрос (имя файла, объект, тип):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SRC_QUERY


async def search_got_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.message.text.strip()
    results = db.search_uploads(q)
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.")
    else:
        lines = [f"🔍 Найдено: {len(results)}\n"]
        for r in results[:15]:
            status_map = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
            icon = status_map.get(r["review_status"], "⚪")
            lines.append(
                f"{icon} `[{r['id']}]` {r['filename']}\n"
                f"   {r['object_name']} / {r['doc_type']} — {r['uploaded_at'][:10]}"
            )
        buttons = []
        for r in results[:10]:
            buttons.append([(f"⬇️ #{r['id']} {r['filename'][:30]}",
                             f"sl|{_pid(r['nas_path'])}")])
        buttons.append([("❌ Закрыть", "sc")])
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=_ik(buttons),
            parse_mode=ParseMode.MARKDOWN,
        )
    return SRC_QUERY


async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith("sl|"):
        pid = query.data[3:]
        path = _pget(pid)
        await query.edit_message_text("⏳ Скачиваю…")
        content = nas_helper.nas_download(path)
        if content:
            fname = path.rsplit("/", 1)[-1]
            await update.effective_chat.send_document(io.BytesIO(content), filename=fname)
        else:
            await update.effective_chat.send_message("❌ Не удалось скачать")
        return SRC_QUERY

    await query.edit_message_text("Поиск завершён.")
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 6 — FINANCE
# ──────────────────────────────────────────────────────────────────────────────

async def finance_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "finance"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    uid = _uid(update)
    role = _role(update)
    docs = db.list_finance_docs(telegram_id=uid if role not in ["admin", "pto"] else None,
                                limit=20)
    text = "💰 *Финансовые документы:*\n\n"
    for d in docs:
        status_icons = {
            "черновик": "📝", "на_проверке": "⏳",
            "утверждён": "✅", "отклонён": "❌", "оплачен": "💳",
        }
        icon = status_icons.get(d["status"], "⚪")
        text += (
            f"{icon} [{d['id']}] {d['filename']}\n"
            f"   {d['object_name']} / {d['doc_type']} | {d['status']}"
        )
        if d["amount"]:
            text += f" | {d['amount']:.2f} грн"
        text += f"\n"

    if not docs:
        text += "_Нет документов_"

    rows = [
        ["➕ Добавить финдок"],
        ["🔄 Изменить статус"],
        ["📊 Экспорт CSV"],
        ["❌ Закрыть"],
    ]
    await update.effective_message.reply_text(
        text, reply_markup=_kb(rows), parse_mode=ParseMode.MARKDOWN
    )
    return FIN_MENU


async def finance_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text
    if txt == "➕ Добавить финдок":
        objects = _objects_from_nas()
        rows = [[o] for o in objects] + [["❌ Отмена"]]
        await update.message.reply_text("📂 Объект:", reply_markup=_kb(rows))
        return FIN_ADD_OBJ

    if txt == "🔄 Изменить статус":
        await update.message.reply_text(
            "Введите ID документа:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return FIN_STATUS_DOC

    if txt == "📊 Экспорт CSV":
        csv_text = fin_svc.export_csv(db)
        buf = io.BytesIO(csv_text.encode("utf-8-sig"))
        await update.message.reply_document(
            document=buf,
            filename=f"finance_{datetime.now():%Y%m%d}.csv",
            caption="📊 Экспорт финансовых документов",
        )
        return FIN_MENU

    await _main_menu(update, context)
    return ConversationHandler.END


async def fin_add_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    context.user_data["fin_obj"] = update.message.text
    rows = [[t] for t in FINANCE_TYPES] + [["❌ Отмена"]]
    await update.message.reply_text("📁 Тип документа:", reply_markup=_kb(rows))
    return FIN_ADD_TYPE


async def fin_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END
    context.user_data["fin_type"] = update.message.text
    await update.message.reply_text(
        "📎 Отправьте файл документа:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return FIN_ADD_FILE


async def fin_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    if msg.document:
        tg_file = msg.document
        filename = tg_file.file_name or f"findoc_{datetime.now():%Y%m%d_%H%M%S}"
    elif msg.photo:
        tg_file = msg.photo[-1]
        filename = f"findoc_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    else:
        await msg.reply_text("⚠️ Отправьте файл или фото.")
        return FIN_ADD_FILE

    context.user_data["fin_filename"] = filename
    context.user_data["fin_file_id"] = tg_file.file_id

    await msg.reply_text(
        "💴 Введите сумму (число) или «-» чтобы пропустить:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return FIN_ADD_AMT


async def fin_add_amt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    try:
        amt = float(raw.replace(",", ".")) if raw != "-" else None
    except ValueError:
        await update.message.reply_text("⚠️ Введите число или «-»")
        return FIN_ADD_AMT
    context.user_data["fin_amount"] = amt
    await update.message.reply_text("🏢 Введите контрагента или «-»:")
    return FIN_ADD_CP


async def fin_add_cp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cp = update.message.text.strip()
    context.user_data["fin_cp"] = "" if cp == "-" else cp

    await update.message.reply_text("⏳ Загружаю на NAS…")
    uid = _uid(update)

    file_obj = await context.bot.get_file(context.user_data["fin_file_id"])
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    file_bytes = buf.getvalue()

    obj = context.user_data["fin_obj"]
    typ = context.user_data["fin_type"]
    filename = context.user_data["fin_filename"]
    dest = nas_helper.build_finance_path(obj, typ)
    ok = nas_helper.nas_upload(dest, filename, file_bytes)

    if ok:
        nas_path = f"{dest}/{filename}"
        fhash = file_hash(file_bytes)
        fsize = len(file_bytes)

        # Sprint 11: Document Registry
        existing = db.find_document_by_hash(fhash)
        if existing:
            registry_doc_id = existing["id"]
        else:
            registry_doc_id = db.create_document(
                object_name=obj,
                category="finance",
                doc_type=typ,
                nas_path=nas_path,
                original_filename=filename,
                file_hash=fhash,
                file_size=fsize,
                created_by=uid,
            )

        doc_id = db.add_finance_doc(
            uid, obj, typ, filename, nas_path,
            context.user_data["fin_amount"],
            context.user_data["fin_cp"],
            doc_id=registry_doc_id,
        )
        db.audit(uid, "finance_upload", "finance_doc", doc_id, nas_path)
        await update.message.reply_text(
            f"✅ Финдок #{doc_id} загружен!\n"
            f"Статус: черновик\nПуть: `{nas_path}`\n"
            f"📋 Реестр doc #{registry_doc_id}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Ошибка загрузки на NAS")

    await _main_menu(update, context)
    return ConversationHandler.END


async def fin_status_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        doc_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Введите число — ID документа")
        return FIN_STATUS_DOC

    doc = db.get_finance_doc(doc_id)
    if not doc:
        await update.message.reply_text("❌ Документ не найден")
        return FIN_STATUS_DOC

    context.user_data["fin_status_doc_id"] = doc_id
    current = doc["status"]
    allowed_next = FINANCE_TRANSITIONS.get(current, [])
    if not allowed_next:
        await update.message.reply_text(f"Документ в финальном статусе: {current}")
        await _main_menu(update, context)
        return ConversationHandler.END

    rows = [[s] for s in allowed_next] + [["❌ Отмена"]]
    await update.message.reply_text(
        f"Документ #{doc_id}: *{doc['filename']}*\n"
        f"Текущий статус: {current}\nВыберите новый статус:",
        reply_markup=_kb(rows),
        parse_mode=ParseMode.MARKDOWN,
    )
    return FIN_STATUS_NEW


async def fin_status_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Отмена":
        await _main_menu(update, context)
        return ConversationHandler.END

    new_status = update.message.text.strip()
    doc_id = context.user_data["fin_status_doc_id"]
    uid = _uid(update)
    role = _role(update)

    result = fin_svc.change_status(db, doc_id, new_status, uid, role)
    if result["ok"]:
        await update.message.reply_text(
            f"✅ Статус документа #{doc_id} → *{new_status}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text(f"❌ {result['error']}")

    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Problems registry
# ──────────────────────────────────────────────────────────────────────────────

async def problems_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "problems"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    items = db.list_problems(status="open")
    text = "⚠️ *Открытые проблемы:*\n\n"
    for it in items:
        text += (
            f"[{it['id']}] 🏷 {it['label']}\n"
            f"   {it['description'][:80]}\n"
            f"   Создал: {it.get('full_name','?')} | {it['created_at'][:10]}\n\n"
        )
    if not items:
        text += "_Нет открытых проблем_"

    rows = [["➕ Добавить проблему"], ["❌ Закрыть"]]
    await update.effective_message.reply_text(
        text, reply_markup=_kb(rows), parse_mode=ParseMode.MARKDOWN
    )
    return PRB_LIST


async def problems_list_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "➕ Добавить проблему":
        await update.message.reply_text(
            "ID документа (или «-» без привязки):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return PRB_ADD_DOC
    await _main_menu(update, context)
    return ConversationHandler.END


async def problems_add_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    context.user_data["prb_doc_id"] = None if txt == "-" else int(txt) if txt.isdigit() else None
    LABELS = ["❗ Критично", "⚠️ Важно", "ℹ️ Информация", "🔧 Требует исправления"]
    rows = [[l] for l in LABELS]
    await update.message.reply_text("🏷 Выберите метку:", reply_markup=_kb(rows))
    return PRB_ADD_LABEL


async def problems_add_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["prb_label"] = update.message.text
    await update.message.reply_text(
        "📝 Опишите проблему:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PRB_ADD_DESC


async def problems_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = _uid(update)
    prob_id = db.add_problem(
        uid,
        context.user_data["prb_label"],
        update.message.text,
        context.user_data.get("prb_doc_id"),
    )
    db.audit(uid, "add_problem", "problem", prob_id)
    await update.message.reply_text(
        f"✅ Проблема #{prob_id} зарегистрирована.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# My uploads today
# ──────────────────────────────────────────────────────────────────────────────

async def my_uploads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _has(update, "my_uploads"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return
    uid = _uid(update)
    rows = db.list_uploads_today(uid)
    if not rows:
        await update.effective_message.reply_text(
            "📋 Сегодня загрузок нет.", reply_markup=ReplyKeyboardRemove()
        )
    else:
        text = f"📋 *Мои загрузки сегодня ({len(rows)}):*\n\n"
        for r in rows:
            status_icons = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
            icon = status_icons.get(r["review_status"], "⚪")
            text += f"{icon} {r['filename']} — {r['object_name']}/{r['doc_type']}\n"
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    await _main_menu(update, context)


# ──────────────────────────────────────────────────────────────────────────────
# Admin — manage users
# ──────────────────────────────────────────────────────────────────────────────

async def admin_users_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _has(update, "manage_users"):
        await update.effective_message.reply_text("⛔ Нет доступа")
        return ConversationHandler.END

    users = db.list_users()
    text = "👥 *Пользователи:*\n\n"
    for u in users:
        active = "✅" if u["is_active"] else "🚫"
        text += (
            f"{active} [{u['telegram_id']}] {u['full_name']} "
            f"(@{u['username'] or '—'}) — {ROLE_LABELS.get(u['role'], u['role'])}\n"
        )
    rows = [["✏️ Изменить роль"], ["❌ Закрыть"]]
    await update.effective_message.reply_text(
        text, reply_markup=_kb(rows), parse_mode=ParseMode.MARKDOWN
    )
    return ADM_SET_ROLE_USER


async def admin_set_role_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ Закрыть":
        await _main_menu(update, context)
        return ConversationHandler.END
    if update.message.text == "✏️ Изменить роль":
        await update.message.reply_text(
            "Введите Telegram ID пользователя:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ADM_SET_ROLE_USER
    try:
        target_id = int(update.message.text.strip())
        context.user_data["adm_target_id"] = target_id
        rows = [[r] for r in ROLE_LABELS.keys()]
        await update.message.reply_text(
            f"Выберите роль для {target_id}:",
            reply_markup=_kb(rows),
        )
        return ADM_SET_ROLE_VALUE
    except ValueError:
        await update.message.reply_text("⚠️ Введите числовой Telegram ID")
        return ADM_SET_ROLE_USER


async def admin_set_role_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text.strip()
    if role not in ROLE_LABELS:
        await update.message.reply_text("⚠️ Неизвестная роль")
        return ADM_SET_ROLE_VALUE
    target_id = context.user_data["adm_target_id"]
    db.set_user_role(target_id, role)
    db.audit(_uid(update), "set_role", "user", target_id,
             f"role→{role}")
    await update.message.reply_text(
        f"✅ Роль пользователя {target_id} → *{ROLE_LABELS[role]}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Admin: object-level access management (/grant & /revoke)
# ──────────────────────────────────────────────────────────────────────────────

async def admin_obj_access_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show submenu for object access management (triggered by keyboard button)."""
    if not _is_admin(_uid(update)):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    rows = db.list_all_object_accesses()
    summary = ""
    if rows:
        groups: dict = {}
        for uid_val, obj in rows:
            groups.setdefault(uid_val, []).append(obj)
        summary = "\n".join(
            f"👤 {uid_val}: " + ", ".join(objs)
            for uid_val, objs in groups.items()
        )
        summary = f"\n\n*Текущие права:*\n{summary}"
    await update.message.reply_text(
        f"🔑 *Управление доступом к объектам*{summary}\n\n"
        "Команды:\n"
        "• /grant — выдать доступ\n"
        "• /revoke — отозвать доступ\n"
        "• /listaccess — показать все права",
        parse_mode=ParseMode.MARKDOWN,
    )


async def admin_obj_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /grant and /revoke commands."""
    if not _is_admin(_uid(update)):
        await update.message.reply_text("⛔ Только для администраторов.")
        return ConversationHandler.END
    cmd = update.message.text.strip().lstrip("/").lower()  # "grant" or "revoke"
    context.user_data["adm_obj_cmd"] = cmd
    await update.message.reply_text(
        f"{'🔓 Выдать' if cmd == 'grant' else '🔒 Отозвать'} доступ к объекту.\n\n"
        "Введите Telegram ID пользователя (число):",
        reply_markup=ReplyKeyboardMarkup(
            [["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return ADM_OBJ_SELECT_USER


async def admin_obj_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)
    if not text.isdigit():
        await update.message.reply_text("⚠️ Введите числовой Telegram ID.")
        return ADM_OBJ_SELECT_USER
    context.user_data["adm_obj_uid"] = int(text)
    # Предложим существующие объекты из базы
    objects = db.get_all_objects()  # returns list of str
    if objects:
        kb = [[o] for o in objects[:20]]  # max 20 строк
        kb.append(["❌ Отмена"])
        markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите объект или введите вручную:", reply_markup=markup)
    else:
        await update.message.reply_text(
            "Введите название объекта:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True),
        )
    return ADM_OBJ_SELECT_OBJ


async def admin_obj_select_obj(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "❌ Отмена":
        return await cancel(update, context)
    obj_name = text
    uid      = context.user_data["adm_obj_uid"]
    cmd      = context.user_data["adm_obj_cmd"]
    if cmd == "grant":
        db.grant_object_access(uid, obj_name)
        db.audit(_uid(update), "grant_object", "user", uid, f"object={obj_name}")
        await update.message.reply_text(
            f"✅ Пользователю *{uid}* выдан доступ к объекту *{obj_name}*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        db.revoke_object_access(uid, obj_name)
        db.audit(_uid(update), "revoke_object", "user", uid, f"object={obj_name}")
        await update.message.reply_text(
            f"✅ У пользователя *{uid}* отозван доступ к объекту *{obj_name}*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove(),
        )
    await _main_menu(update, context)
    return ConversationHandler.END


async def admin_list_accesses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command /listaccess — показывает все права доступа к объектам."""
    if not _is_admin(_uid(update)):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    rows = db.list_all_object_accesses()
    if not rows:
        await update.message.reply_text("Прав объектного доступа не найдено.")
        return
    lines = ["*Права доступа к объектам:*\n"]
    current_uid = None
    for uid_val, obj in rows:
        if uid_val != current_uid:
            current_uid = uid_val
            lines.append(f"\n👤 *{uid_val}*:")
        lines.append(f"  • {obj}")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Generic cancel
# ──────────────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    await _main_menu(update, context)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Text router: main menu buttons → conversation starters
# ──────────────────────────────────────────────────────────────────────────────

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    routes = {
        "📤 Загрузить документ": upload_start,
        "📂 Найти документ": find_start,
        "✅ На проверке": approve_start,
        "⏰ Сроки": expiry_start,
        "📸 Фотоотчёт": photo_report_start,
        "📦 Пакет документов": package_start,
        "💰 Финансы": finance_start,
        "⚠️ Проблемы": problems_start,
        "🔍 Поиск": search_start,
        "📋 Мои загрузки": my_uploads,
        "🏗️ Создать объект": create_object_start,
        "👥 Пользователи": admin_users_start,
        "🔑 Доступ к объектам": admin_obj_access_menu,
    }
    handler = routes.get(txt)
    if handler:
        return await handler(update, context)
    await update.message.reply_text(
        "Используйте кнопки меню или /menu",
        reply_markup=ReplyKeyboardRemove(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Scheduler — daily expiry reminder at 09:00
# ──────────────────────────────────────────────────────────────────────────────

def _make_send_fn(app):
    def send_fn(telegram_id: int, text: str):
        asyncio.get_event_loop().create_task(
            app.bot.send_message(telegram_id, text)
        )
    return send_fn


# ──────────────────────────────────────────────────────────────────────────────
# Application setup
# ──────────────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation: Upload ──────────────────────────────────────────────────
    upload_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📤 Загрузить документ$"), upload_start)],
        states={
            UPL_OBJ:     [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_got_obj)],
            UPL_TYPE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_got_type)],
            UPL_SECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_got_section)],
            UPL_FILE:    [MessageHandler(
                filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.TEXT,
                upload_got_file
            )],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Find ────────────────────────────────────────────────────
    find_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📂 Найти документ$"), find_start)],
        states={
            FIND_BROWSE: [CallbackQueryHandler(find_callback, pattern="^(fd|fl|fc)")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Approve ─────────────────────────────────────────────────
    approve_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ На проверке$"), approve_start)],
        states={
            APR_ACTION: [CallbackQueryHandler(approve_callback, pattern="^apr_")],
            APR_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, approve_reject_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Expiry ──────────────────────────────────────────────────
    expiry_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⏰ Сроки$"), expiry_start)],
        states={
            EXP_MENU:      [MessageHandler(filters.TEXT & ~filters.COMMAND, expiry_menu_choice)],
            EXP_ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, expiry_add_title)],
            EXP_ADD_OBJ:   [MessageHandler(filters.TEXT & ~filters.COMMAND, expiry_add_obj)],
            EXP_ADD_DATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, expiry_add_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Photo report ────────────────────────────────────────────
    photo_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📸 Фотоотчёт$"), photo_report_start)],
        states={
            PHO_OBJ:  [MessageHandler(filters.TEXT & ~filters.COMMAND, photo_got_obj)],
            PHO_CL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, photo_got_cl)],
            PHO_ITEM: [MessageHandler(filters.PHOTO | filters.TEXT, photo_got_item)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Package ─────────────────────────────────────────────────
    pkg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📦 Пакет документов$"), package_start)],
        states={
            PKG_OBJ:     [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_got_obj)],
            PKG_PERIOD:  [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_got_period)],
            PKG_TYPES:   [MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_got_type)],
            PKG_CONFIRM: [CallbackQueryHandler(pkg_confirm_callback, pattern="^pkg_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Finance ─────────────────────────────────────────────────
    finance_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Финансы$"), finance_start)],
        states={
            FIN_MENU:       [MessageHandler(filters.TEXT & ~filters.COMMAND, finance_menu_choice)],
            FIN_ADD_OBJ:    [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_add_obj)],
            FIN_ADD_TYPE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_add_type)],
            FIN_ADD_FILE:   [MessageHandler(
                filters.Document.ALL | filters.PHOTO | filters.TEXT, fin_add_file
            )],
            FIN_ADD_AMT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_add_amt)],
            FIN_ADD_CP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_add_cp)],
            FIN_STATUS_DOC: [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_status_doc)],
            FIN_STATUS_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, fin_status_new)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Create object ───────────────────────────────────────────
    create_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🏗️ Создать объект$"), create_object_start)],
        states={
            CRE_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, create_got_name)],
            CRE_CONFIRM: [CallbackQueryHandler(create_confirm_callback, pattern="^cre_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Search ──────────────────────────────────────────────────
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Поиск$"), search_start)],
        states={
            SRC_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_got_query),
                CallbackQueryHandler(search_callback, pattern="^(sl|sc)"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Problems ────────────────────────────────────────────────
    problems_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚠️ Проблемы$"), problems_start)],
        states={
            PRB_LIST:      [MessageHandler(filters.TEXT & ~filters.COMMAND, problems_list_choice)],
            PRB_ADD_DOC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, problems_add_doc)],
            PRB_ADD_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, problems_add_label)],
            PRB_ADD_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, problems_add_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Admin users ─────────────────────────────────────────────
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👥 Пользователи$"), admin_users_start)],
        states={
            ADM_SET_ROLE_USER:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_role_user)],
            ADM_SET_ROLE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_role_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Conversation: Admin object access ─────────────────────────────────────
    admin_obj_conv = ConversationHandler(
        entry_points=[
            CommandHandler("grant",  admin_obj_start),
            CommandHandler("revoke", admin_obj_start),
        ],
        states={
            ADM_OBJ_SELECT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_obj_select_user)],
            ADM_OBJ_SELECT_OBJ:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_obj_select_obj)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Register all handlers ─────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("listaccess", admin_list_accesses))
    app.add_handler(upload_conv)
    app.add_handler(find_conv)
    app.add_handler(approve_conv)
    app.add_handler(expiry_conv)
    app.add_handler(photo_conv)
    app.add_handler(pkg_conv)
    app.add_handler(finance_conv)
    app.add_handler(create_conv)
    app.add_handler(search_conv)
    app.add_handler(problems_conv)
    app.add_handler(admin_conv)
    app.add_handler(admin_obj_conv)
    app.add_handler(
        MessageHandler(filters.Regex("^📋 Мои загрузки$"), my_uploads)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # ── Global error handler ──────────────────────────────────────────────────
    async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        err = context.error
        logger.error("Update %s caused error: %s", update, err, exc_info=err)
        # Уведомить пользователя об ошибке если возможно
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Произошла ошибка. Попробуйте ещё раз или нажмите /menu"
                )
            except Exception:
                pass

    app.add_error_handler(_error_handler)

    return app


async def main_async():
    app = build_app()

    # ── Configure monitoring — know admin IDs ─────────────────────────────────
    def _get_admin_ids() -> list[int]:
        try:
            users = db.list_users()
            return [u["telegram_id"] for u in users
                    if u["role"] == "admin" and u["is_active"]]
        except Exception:
            return []

    mon.configure(BOT_TOKEN, _get_admin_ids)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler()

    # Expiry reminders at 09:00
    def _run_expiry():
        try:
            expiry_svc.check_and_send_reminders(db, _make_send_fn(app))
        except Exception as exc:
            mon.alert_scheduler_error("expiry_reminders", exc)

    scheduler.add_job(_run_expiry, trigger="cron", hour=EXPIRY_HOUR, minute=0)

    # Daily DB backup at 02:00
    def _run_backup():
        from core.backup import run_backup
        from apps.bot.bot_config import DB_PATH
        try:
            nas = nas_helper.get_nas()
            result = run_backup(DB_PATH, nas)
            if not result["ok"]:
                mon.alert_backup_failed(result.get("error", "unknown"))
            else:
                logger.info("Backup OK: %s (%d bytes)",
                            result["filename"], result["bytes"])
        except Exception as exc:
            mon.alert_backup_failed(str(exc))

    scheduler.add_job(_run_backup, trigger="cron", hour=2, minute=0)

    # Weekly backup on Sunday at 03:00
    def _run_weekly():
        from core.backup import run_weekly_backup
        from apps.bot.bot_config import DB_PATH
        try:
            nas = nas_helper.get_nas()
            run_weekly_backup(DB_PATH, nas)
        except Exception as exc:
            mon.alert_backup_failed(f"weekly: {exc}")

    scheduler.add_job(_run_weekly, trigger="cron", day_of_week="sun", hour=3, minute=0)

    # Sprint 13: Weekly digest to admins on Monday at 09:00
    def _run_weekly_digest():
        from core.services.notify import send_weekly_digest
        from datetime import date, timedelta
        try:
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            # Collect stats
            uploads_week   = len(db.get_uploads_since(week_ago))
            approved_week  = len(db.get_uploads_since(week_ago, status="approved"))
            rejected_week  = len(db.get_uploads_since(week_ago, status="rejected"))
            fin_rows       = db.list_finance_docs()
            fin_total      = len(fin_rows)
            fin_paid       = sum(1 for r in fin_rows if r.get("status") == "оплачен")
            expiry_rows    = db.list_expiry_items()
            today_s        = date.today().isoformat()
            expiry_active  = sum(1 for e in expiry_rows if e.get("status") == "active")
            expiry_overdue = sum(
                1 for e in expiry_rows
                if e.get("status") == "active" and e.get("expires_at", "9999") < today_s
            )
            open_probs = len(db.list_problems(status="open"))
            stats = {
                "uploads_week":  uploads_week,
                "approved_week": approved_week,
                "rejected_week": rejected_week,
                "fin_total":     fin_total,
                "fin_paid":      fin_paid,
                "expiry_active": expiry_active,
                "expiry_overdue": expiry_overdue,
                "open_problems": open_probs,
            }
            # Send to all admin users
            admin_ids = db.get_users_by_role("admin")
            tids = [u["telegram_id"] for u in admin_ids if u.get("telegram_id")]
            if tids:
                send_weekly_digest(tids, stats)
                logger.info("Weekly digest sent to %d admins", len(tids))
        except Exception as exc:
            logger.error("Weekly digest error: %s", exc)

    scheduler.add_job(_run_weekly_digest, trigger="cron", day_of_week="mon", hour=9, minute=0)

    scheduler.start()

    logger.info("Bot starting…")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Keep running until interrupted
        await asyncio.Event().wait()


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
