"""
Synology DSM File Station API client.
All NAS operations go through this module.
Logical paths only: /Обмен, /Днепр  — never /volume1/...
"""

import time
import logging
from typing import Optional
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("nas_client")


class NASError(Exception):
    pass


class NASClient:
    """Thread-safe, retry-capable Synology FileStation client."""

    def __init__(self, base_url: str, username: str, password: str, retries: int = 3):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.retries = retries
        self._sid: Optional[str] = None
        self._token: Optional[str] = None
        self._session = requests.Session()
        self._session.verify = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, params: dict, timeout: int = 30) -> dict:
        last_err: Exception = RuntimeError("no attempts")
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._session.get(self.base_url, params=params, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                if data.get("success"):
                    return data.get("data") or {}
                err = data.get("error", {})
                code = err.get("code", "?")
                last_err = NASError(f"API error {code} | {params.get('api')}.{params.get('method')}")
                logger.warning("NAS attempt %d/%d error %s: %s.%s",
                               attempt, self.retries, code,
                               params.get("api"), params.get("method"))
                if attempt < self.retries:
                    time.sleep(attempt)
            except NASError:
                if attempt < self.retries:
                    time.sleep(attempt)
            except Exception as exc:
                last_err = exc
                logger.warning("NAS attempt %d/%d exception: %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(attempt)
        raise last_err

    def _auth_params(self) -> dict:
        if not self._sid:
            self.login()
        return {"_sid": self._sid, "SynoToken": self._token or ""}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> None:
        data = self._get({
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": self.username,
            "passwd": self.password,
            "session": "FileStation",
            "format": "sid",
        })
        self._sid = data["sid"]
        self._token = data.get("synotoken", "")
        logger.info("NAS login OK sid=...%s", self._sid[-6:] if self._sid else "?")

    def logout(self) -> None:
        if not self._sid:
            return
        try:
            self._get({**self._auth_params(),
                       "api": "SYNO.API.Auth", "version": "1",
                       "method": "logout", "session": "FileStation"})
        except Exception:
            pass
        self._sid = None
        self._token = None

    def relogin(self) -> None:
        self._sid = None
        self._token = None
        self.login()

    # ------------------------------------------------------------------
    # File Station operations
    # ------------------------------------------------------------------

    def list_shares(self) -> list[dict]:
        data = self._get({
            **self._auth_params(),
            "api": "SYNO.FileStation.List",
            "version": "2",
            "method": "list_share",
            "additional": "real_path,time,perm",
        })
        return data.get("shares", [])

    def list_folder(self, folder_path: str, offset: int = 0, limit: int = 200) -> list[dict]:
        data = self._get({
            **self._auth_params(),
            "api": "SYNO.FileStation.List",
            "version": "2",
            "method": "list",
            "folder_path": folder_path,
            "offset": offset,
            "limit": limit,
            "additional": "real_path,size,time,type",
        })
        return data.get("files", [])

    def create_folder(self, parent_path: str, name: str) -> bool:
        try:
            self._get({
                **self._auth_params(),
                "api": "SYNO.FileStation.CreateFolder",
                "version": "2",
                "method": "create",
                "folder_path": parent_path,
                "name": name,
                "force_parent": "true",
            })
            logger.info("NAS CreateFolder %s/%s", parent_path, name)
            return True
        except NASError as exc:
            # code 414 = already exists → idempotent
            if "414" in str(exc):
                return True
            logger.error("NAS CreateFolder failed %s/%s: %s", parent_path, name, exc)
            return False

    def upload(self, dest_folder: str, filename: str,
               file_bytes: bytes, overwrite: bool = True) -> bool:
        """Multipart POST — tokens must be in URL query string, not form body."""
        auth = self._auth_params()
        url = (
            f"{self.base_url}"
            f"?api=SYNO.FileStation.Upload&version=2&method=upload"
            f"&_sid={auth['_sid']}&SynoToken={auth['SynoToken']}"
        )
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._session.post(
                    url,
                    data={
                        "path": dest_folder,
                        "create_parents": "true",
                        "overwrite": "true" if overwrite else "false",
                    },
                    files={"file": (filename, file_bytes)},
                    timeout=180,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("success"):
                    logger.info("NAS Upload %s → %s", filename, dest_folder)
                    return True
                err_code = data.get("error", {}).get("code", "?")
                logger.warning("NAS Upload attempt %d error %s", attempt, err_code)
                if attempt < self.retries:
                    time.sleep(attempt)
            except Exception as exc:
                logger.warning("NAS Upload attempt %d exception: %s", attempt, exc)
                if attempt < self.retries:
                    time.sleep(attempt)
        return False

    def download(self, file_path: str, timeout: int = 180) -> Optional[bytes]:
        auth = self._auth_params()
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._session.get(
                    self.base_url,
                    params={
                        **auth,
                        "api": "SYNO.FileStation.Download",
                        "version": "2",
                        "method": "download",
                        "path": file_path,
                        "mode": "download",
                    },
                    timeout=timeout,
                    stream=True,
                )
                resp.raise_for_status()
                content = resp.content
                logger.info("NAS Download %s (%d bytes)", file_path, len(content))
                return content
            except Exception as exc:
                logger.warning("NAS Download attempt %d exception: %s", attempt, exc)
                if attempt < self.retries:
                    time.sleep(attempt)
        return None

    def delete(self, path: str) -> bool:
        try:
            self._get({
                **self._auth_params(),
                "api": "SYNO.FileStation.Delete",
                "version": "2",
                "method": "delete",
                "path": path,
            })
            logger.info("NAS Delete %s", path)
            return True
        except Exception as exc:
            logger.error("NAS Delete failed %s: %s", path, exc)
            return False

    def copy_move(self, src_path: str, dest_folder: str,
                  move: bool = False, timeout_sec: int = 120) -> bool:
        """Start async CopyMove task and poll until done."""
        try:
            data = self._get({
                **self._auth_params(),
                "api": "SYNO.FileStation.CopyMove",
                "version": "3",
                "method": "start",
                "path": src_path,
                "dest_folder_path": dest_folder,
                "overwrite": "true",
                "remove_src": "true" if move else "false",
            })
            task_id = data.get("taskid", "")
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                time.sleep(2)
                status = self._get({
                    **self._auth_params(),
                    "api": "SYNO.FileStation.CopyMove",
                    "version": "3",
                    "method": "status",
                    "taskid": task_id,
                })
                if status.get("finished"):
                    op = "Move" if move else "Copy"
                    logger.info("NAS %s done %s → %s", op, src_path, dest_folder)
                    return True
            logger.warning("NAS CopyMove timeout %s → %s", src_path, dest_folder)
            return False
        except Exception as exc:
            logger.error("NAS CopyMove failed: %s", exc)
            return False

    def rename(self, folder_path: str, old_name: str, new_name: str) -> bool:
        try:
            self._get({
                **self._auth_params(),
                "api": "SYNO.FileStation.Rename",
                "version": "2",
                "method": "rename",
                "path": f"{folder_path}/{old_name}",
                "name": new_name,
            })
            logger.info("NAS Rename %s/%s → %s", folder_path, old_name, new_name)
            return True
        except Exception as exc:
            logger.error("NAS Rename failed: %s", exc)
            return False

    def path_exists(self, path: str) -> bool:
        """Check if a path exists on NAS by trying to list its parent."""
        parts = path.rsplit("/", 1)
        if len(parts) < 2:
            return False
        parent, name = parts
        try:
            files = self.list_folder(parent, limit=500)
            return any(f.get("name") == name for f in files)
        except Exception:
            return False
