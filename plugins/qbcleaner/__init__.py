import re
from typing import Any, List, Dict, Tuple, Optional
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.log import logger
from app.plugins import _PluginBase
import httpx


class QbCleaner(_PluginBase):
    plugin_name = "上傳115後清理qBit"
    plugin_desc = "115上傳完成後，自動刪除qBittorrent中對應的種子與文件"
    plugin_icon = "https://raw.githubusercontent.com/honmashironeko/PublicFiles/main/icons/qbittorrent.png"
    plugin_version = "1.2"
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
    _only_u115: bool = True

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._qb_url = config.get("qb_url", "").rstrip("/")
            self._qb_username = config.get("qb_username", "")
            self._qb_password = config.get("qb_password", "")
            self._delete_files = config.get("delete_files", True)
            self._only_u115 = config.get("only_u115", True)

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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "only_u115",
                                            "label": "僅115上傳成功時刪除",
                                            "hint": "關閉後，任何整理完成都會觸發刪除",
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
                                            "text": "插件使用 download_hash 精確對應 qBittorrent 種子並刪除，無需比對文件名。建議開啟「同時刪除本地文件」以釋放 /downloads/ 空間。",
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
            "only_u115": True,
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

    def _delete_by_hash(self, torrent_hash: str) -> bool:
        try:
            with httpx.Client(follow_redirects=True) as client:
                if not self._qb_login(client):
                    return False
                resp = client.post(
                    f"{self._qb_url}/api/v2/torrents/delete",
                    data={
                        "hashes": torrent_hash,
                        "deleteFiles": "true" if self._delete_files else "false",
                    },
                    timeout=10,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"【QbCleaner】刪除種子失敗: {e}")
            return False

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

        # 判斷是否為115上傳
        if self._only_u115:
            target_item = getattr(transferinfo, "target_item", None)
            dest_storage = str(getattr(target_item, "storage", "")) if target_item else ""
            if "u115" not in dest_storage.lower() and "115" not in dest_storage.lower():
                logger.debug(f"【QbCleaner】非115目標，跳過: {dest_storage}")
                return

        # 用 download_hash 直接刪除
        download_hash = event_data.get("download_hash")
        if not download_hash:
            logger.warn("【QbCleaner】無 download_hash，無法刪除種子")
            return

        logger.info(f"【QbCleaner】開始刪除種子 hash: {download_hash}")
        if self._delete_by_hash(download_hash):
            logger.info(
                f"【QbCleaner】已刪除種子 {download_hash}"
                + ("（含本地文件）" if self._delete_files else "（保留本地文件）")
            )
        else:
            logger.error(f"【QbCleaner】刪除種子失敗: {download_hash}")

    def stop_service(self):
        pass
