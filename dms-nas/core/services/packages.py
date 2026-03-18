"""
Document package builder: ZIP + summary.md from NAS files.
"""

import io
import logging
import zipfile
from datetime import datetime

logger = logging.getLogger("svc.packages")

MAX_ZIP_BYTES = 50 * 1024 * 1024  # 50 MB


def build_package(nas, db, telegram_id: int, object_name: str,
                  period: str, doc_types: list[str]) -> dict:
    """
    Download matching files from NAS and build a ZIP in-memory.
    Returns {"ok": True, "zip_bytes": bytes, "summary": str, "count": int}
    or      {"ok": False, "error": "..."}
    """
    collected: list[dict] = []

    for doc_type in doc_types:
        folder = f"/{object_name}/_APPROVED/{doc_type}"
        try:
            files = nas.list_folder(folder)
        except Exception:
            try:
                folder = f"/{object_name}/_INBOX/{doc_type}"
                files = nas.list_folder(folder)
            except Exception:
                continue

        for f in files:
            if f.get("isdir"):
                continue
            name: str = f.get("name", "")
            if period and period.lower() not in name.lower():
                continue
            collected.append({"path": f"{folder}/{name}", "name": name, "type": doc_type})

    if not collected:
        return {"ok": False, "error": "Файлы не найдены по заданным критериям"}

    zip_buf = io.BytesIO()
    summary_lines = [
        f"# Пакет документов",
        f"Объект: {object_name}",
        f"Период: {period or 'все'}",
        f"Типы: {', '.join(doc_types)}",
        f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Файлов: {len(collected)}",
        "",
        "## Состав",
    ]

    total_bytes = 0
    added = 0

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in collected:
            content = nas.download(item["path"])
            if content is None:
                summary_lines.append(f"- ❌ {item['type']}/{item['name']} (ошибка загрузки)")
                continue
            total_bytes += len(content)
            if total_bytes > MAX_ZIP_BYTES:
                summary_lines.append(f"⚠️ Достигнут лимит 50 МБ, остальные файлы пропущены")
                break
            arc_name = f"{item['type']}/{item['name']}"
            zf.writestr(arc_name, content)
            summary_lines.append(f"- ✅ {arc_name}")
            added += 1

        summary_text = "\n".join(summary_lines)
        zf.writestr("summary.md", summary_text.encode("utf-8"))

    zip_bytes = zip_buf.getvalue()

    zip_nas_path = f"/{object_name}/_PACKAGES/{object_name}_{period or 'all'}_{datetime.now():%Y%m%d_%H%M}.zip"
    nas.upload(f"/{object_name}/_PACKAGES",
               f"{object_name}_{period or 'all'}_{datetime.now():%Y%m%d_%H%M}.zip",
               zip_bytes)

    db.log_package(telegram_id, object_name, period, doc_types, zip_nas_path, added)
    logger.info("Package built obj=%s period=%s files=%d bytes=%d",
                object_name, period, added, len(zip_bytes))

    return {
        "ok": True,
        "zip_bytes": zip_bytes,
        "summary": summary_text,
        "count": added,
        "zip_name": f"{object_name}_{period or 'all'}.zip",
    }
