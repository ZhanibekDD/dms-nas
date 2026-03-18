"""
Approval / rejection workflow.
All actions are idempotent — repeating with same result is safe.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("svc.approvals")


def approve_doc(db, nas, upload_id: int, reviewer_id: int) -> dict:
    """
    Approve document: copy NAS file _INBOX → _APPROVED, update DB.
    Returns {"ok": True} or {"ok": False, "error": "..."}
    """
    row = db.get_upload(upload_id)
    if not row:
        return {"ok": False, "error": "upload not found"}

    if row["review_status"] == "approved":
        logger.info("Approve idempotent upload_id=%d", upload_id)
        return {"ok": True, "idempotent": True}

    src_path: str = row["nas_path"]
    # Build approved destination: replace _INBOX with _APPROVED
    dest_folder = src_path.rsplit("/", 1)[0].replace("/_INBOX/", "/_APPROVED/", 1)
    if "/_INBOX/" not in dest_folder:
        dest_folder = dest_folder + "_approved"

    ok = nas.copy_move(src_path, dest_folder, move=False)
    if not ok:
        logger.error("Approve copy failed upload_id=%d src=%s dest=%s", upload_id, src_path, dest_folder)
        return {"ok": False, "error": "NAS copy failed"}

    db.set_review_status(upload_id, "approved", reviewer_id)
    db.audit(reviewer_id, "approve", "upload", upload_id,
             f"approved {src_path} → {dest_folder}")
    logger.info("Approved upload_id=%d by user=%d", upload_id, reviewer_id)
    return {"ok": True}


def reject_doc(db, nas, upload_id: int, reviewer_id: int, reason: str) -> dict:
    """
    Reject document: copy NAS file _INBOX → _REJECTED, update DB.
    """
    row = db.get_upload(upload_id)
    if not row:
        return {"ok": False, "error": "upload not found"}

    if row["review_status"] == "rejected":
        db.set_review_status(upload_id, "rejected", reviewer_id, reason)
        return {"ok": True, "idempotent": True}

    src_path: str = row["nas_path"]
    dest_folder = src_path.rsplit("/", 1)[0].replace("/_INBOX/", "/_REJECTED/", 1)
    if "/_INBOX/" not in dest_folder:
        dest_folder = dest_folder + "_rejected"

    ok = nas.copy_move(src_path, dest_folder, move=False)
    if not ok:
        logger.error("Reject copy failed upload_id=%d", upload_id)
        return {"ok": False, "error": "NAS copy failed"}

    db.set_review_status(upload_id, "rejected", reviewer_id, reason)
    db.audit(reviewer_id, "reject", "upload", upload_id,
             f"rejected {src_path}: {reason}")
    logger.info("Rejected upload_id=%d by user=%d reason=%s", upload_id, reviewer_id, reason)
    return {"ok": True, "uploader_id": row["telegram_id"]}
