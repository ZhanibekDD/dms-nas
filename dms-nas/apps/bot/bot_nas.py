"""
Thin NAS wrapper for bot: singleton client + convenience helpers.
Integrates with core/monitoring.py for alert on repeated failures.
"""

import logging
from apps.bot.bot_config import NAS_BASE_URL, NAS_USER, NAS_PASSWORD
from core.nas_client import NASClient
import core.monitoring as mon

logger = logging.getLogger("bot_nas")

_client: NASClient = None


def get_nas() -> NASClient:
    global _client
    if _client is None:
        _client = NASClient(NAS_BASE_URL, NAS_USER, NAS_PASSWORD)
        _client.login()
    return _client


def nas_upload(dest_folder: str, filename: str, file_bytes: bytes) -> bool:
    nas = get_nas()
    try:
        result = nas.upload(dest_folder, filename, file_bytes)
        if result:
            mon.nas_op_ok("upload")
        else:
            mon.nas_op_failed("upload", f"{dest_folder}/{filename}")
        return result
    except Exception as exc:
        logger.error("nas_upload failed: %s", exc)
        try:
            nas.relogin()
            result = nas.upload(dest_folder, filename, file_bytes)
            if result:
                mon.nas_op_ok("upload")
            else:
                mon.nas_op_failed("upload", f"retry failed {dest_folder}/{filename}")
            return result
        except Exception as exc2:
            mon.nas_op_failed("upload", str(exc2))
            return False


def nas_download(file_path: str) -> bytes | None:
    nas = get_nas()
    try:
        content = nas.download(file_path)
        if content is not None:
            mon.nas_op_ok("download")
        else:
            mon.nas_op_failed("download", file_path)
        return content
    except Exception as exc:
        logger.error("nas_download failed: %s", exc)
        try:
            nas.relogin()
            content = nas.download(file_path)
            if content is not None:
                mon.nas_op_ok("download")
            return content
        except Exception as exc2:
            mon.nas_op_failed("download", str(exc2))
            return None


def nas_list_folder(folder_path: str) -> list[dict]:
    nas = get_nas()
    try:
        result = nas.list_folder(folder_path)
        mon.nas_op_ok("list")
        return result
    except Exception as exc:
        logger.warning("nas_list_folder %s: %s", folder_path, exc)
        return []


def nas_create_folder(parent: str, name: str) -> bool:
    return get_nas().create_folder(parent, name)


def build_inbox_path(object_name: str, doc_type: str) -> str:
    return f"/{object_name}/_INBOX/{doc_type}"


def build_finance_path(object_name: str, finance_type: str) -> str:
    return f"/{object_name}/Финансы/{finance_type}"
