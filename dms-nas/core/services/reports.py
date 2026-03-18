"""
Photo report workflow: checklists → step-by-step photo collection.
"""

import logging
from datetime import datetime

logger = logging.getLogger("svc.reports")

DEFAULT_CHECKLIST = [
    "Общий вид объекта",
    "Фундамент / основание",
    "Несущие конструкции",
    "Кровля",
    "Фасад",
    "Внутренние работы",
    "Инженерные системы",
    "Благоустройство",
]


def start_report(db, telegram_id: int, object_name: str,
                 checklist_id: int = None) -> dict:
    """Create a new in-progress photo report. Returns report row."""
    report_date = datetime.now().strftime("%Y-%m-%d")
    nas_folder = f"/{object_name}/ФотоОтчет/{report_date}"
    report_id = db.create_report(telegram_id, object_name, checklist_id, report_date, nas_folder)
    logger.info("Report started id=%d obj=%s user=%d", report_id, object_name, telegram_id)
    return {"report_id": report_id, "nas_folder": nas_folder, "report_date": report_date}


def save_report_item(db, nas, report_id: int, item_index: int,
                     item_name: str, file_bytes: bytes,
                     original_filename: str) -> dict:
    """Save one photo for a checklist item. Filename: 01_ОбщийВид.jpg"""
    report = db.get_report(report_id)
    if not report:
        return {"ok": False, "error": "report not found"}

    ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else "jpg"
    safe_name = item_name.replace(" ", "_").replace("/", "-")
    filename = f"{item_index + 1:02d}_{safe_name}.{ext}"
    dest_folder = report["nas_folder"]

    ok = nas.upload(dest_folder, filename, file_bytes)
    if not ok:
        return {"ok": False, "error": "NAS upload failed"}

    nas_path = f"{dest_folder}/{filename}"
    db.add_report_item(report_id, item_index, item_name, nas_path)
    logger.info("Report item saved report_id=%d item=%d name=%s", report_id, item_index, item_name)
    return {"ok": True, "nas_path": nas_path, "filename": filename}


def finish_report(db, report_id: int) -> bool:
    db.finish_report(report_id)
    logger.info("Report finished id=%d", report_id)
    return True


def create_object_structure(nas, object_name: str) -> list[str]:
    """
    Create full folder structure for a new construction object.
    Returns list of created paths.
    """
    from apps.bot.bot_config import OBJECT_TEMPLATE
    created = []
    root = f"/{object_name}"
    for rel_path in OBJECT_TEMPLATE:
        parts = rel_path.split("/")
        current = root
        for part in parts:
            ok = nas.create_folder(current, part)
            full = f"{current}/{part}"
            if ok:
                created.append(full)
            current = full
    logger.info("Object structure created: %s (%d folders)", object_name, len(created))
    return created
