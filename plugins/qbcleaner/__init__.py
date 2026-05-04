import re
from typing import Any, List, Dict, Tuple, Optional
from pathlib import Path
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.log import logger
from app.plugins import _PluginBase
import httpx


class QbCleaner(_PluginBase):
    plugin_name = "上傳115後清理qBit"
    plugin_desc = "115上傳完成後，自動刪除qBittorrent中對應的種子與文件"
    plugin_icon = "https://raw.githubusercontent.com/honmashironeko/PublicFiles/main/icons/qbittorrent.png"
    plugin_version = "1.4"
    plugin_author = "qa2006w"
    author_url = "https://github.com/qa2006w"
    plugin_config_prefix = "qbcleaner_"
    plugin_order = 99
    auth_level = 1

    _enabled: bool = False
    _qb_url: str = ""
    _qb_username: str = ""
    _qb_password: str = ""
    _delete_files: bool = True

    # 緩存：文件名（不含副檔名）→ qBit hash
    # 第一次整理（本地→待上傳）時記錄，第二次（待上傳→115）時使用
    _hash_cache: Dict[str, str] = {}

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._qb_url = config.get("qb_url", "").rstrip("/")
            self._qb_username = config.get("qb_username", "")
            self._qb_password = config.get("qb_password", "")
            self._delete_files = config.get("delete_files", True)
        self._hash_cache = {}

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "啟用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delete_files",
                                            "label": "同時刪除本地文件",
                                            "hint": "刪除種子的同時也刪除 /downloads/ 中的原始文件",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "qb_url",
                                            "label": "qBittorrent 網址",
                                            "placeholder": "http://127.0.0.1:8081",
                                            "hint": "qBittorrent WebUI 地址，含 http:// 與 port",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "qb_username",
                                            "label": "qBittorrent 帳號",
                                            "placeholder": "admin",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "qb_password",
                                            "label": "qBittorrent 密碼",
                                            "placeholder": "adminadmin",
                                            "type": "password",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "第一次整理（本地→待上傳）時記錄 hash，第二次整理（待上傳→115）完成後自動刪除對應 qBit 種子。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "qb_url": "",
            "qb_username": "",
            "qb_password": "",
            "delete_files": True,
        }

    def get_page(self) -> List[dict]:
        return []

    def _qb_login(self, client: httpx.Client) -> bool:
        try:
            resp = client.post(
                f"{self._qb_url}/api/v2/auth/login",
                data={"username": self._qb_username, "password": self._qb_password},
                timeout=10,
            )
            if resp.text == "Ok.":
                return True
            logger.error(f"【QbCleaner】qBittorrent 登入失敗: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"【QbCleaner】qBittorrent 連線失敗: {e}")
            return False

    def _delete_torrent(self, torrent_hash: str, torrent_name: str = ""):
        try:
            with httpx.Client(follow_redirects=True) as client:
                if not self._qb_login(client):
                    return
                resp = client.post(
                    f"{self._qb_url}/api/v2/torrents/delete",
                    data={
                        "hashes": torrent_hash,
                        "deleteFiles": "true" if self._delete_files else "false",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info(
                        f"【QbCleaner】已刪除種子: {torrent_name or torrent_hash}"
                        + ("（含本地文件）" if self._delete_files else "（保留本地文件）")
                    )
                else:
                    logger.error(f"【QbCleaner】刪除種子失敗: {torrent_name or torrent_hash}")
        except Exception as e:
            logger.error(f"【QbCleaner】刪除種子失敗: {e}")

    def _get_file_key(self, transferinfo) -> Optional[str]:
        """取得文件名（不含副檔名）作為緩存 key"""
        try:
            fileitem = getattr(transferinfo, "fileitem", None)
            if not fileitem:
                return None
            path = getattr(fileitem, "path", None) or getattr(fileitem, "name", None)
            if not path:
                return None
            return Path(str(path)).stem  # 不含副檔名的文件名
        except Exception:
            return None

    def _is_u115_target(self, transferinfo) -> bool:
        """判斷目標是否為 115"""
        target_item = getattr(transferinfo, "target_item", None)
        dest_storage = str(getattr(target_item, "storage", "")) if target_item else ""
        return "u115" in dest_storage.lower() or "115" in dest_storage.lower()

    @eventmanager.register(EventType.TransferComplete)
    def on_transfer_complete(self, event: Event):
        if not self._enabled:
            return

        event_data = event.event_data
        if not event_data:
            return

        transferinfo = event_data.get("transferinfo")
        if not transferinfo:
            return

        download_hash = event_data.get("download_hash")
        file_key = self._get_file_key(transferinfo)

        if not file_key:
            return

        if self._is_u115_target(transferinfo):
            # 第二次整理：目標是 115，上傳完成，刪除種子
            cached_hash = self._hash_cache.get(file_key)
            if cached_hash:
                logger.info(f"【QbCleaner】115上傳完成，刪除種子: {file_key} (hash={cached_hash})")
                self._delete_torrent(cached_hash, file_key)
                # 清除緩存
                del self._hash_cache[file_key]
            else:
                logger.debug(f"【QbCleaner】115上傳完成但無緩存hash，跳過: {file_key}")
        else:
            # 第一次整理：目標是本地，記錄 hash
            if download_hash:
                self._hash_cache[file_key] = download_hash
                logger.info(f"【QbCleaner】記錄 hash 緩存: {file_key} → {download_hash}")
            else:
                logger.debug(f"【QbCleaner】第一次整理無 hash，跳過緩存: {file_key}")

    def stop_service(self):
        self._hash_cache = {}
