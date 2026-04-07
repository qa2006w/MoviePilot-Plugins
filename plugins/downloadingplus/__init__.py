from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType, SystemConfigKey
from app.db.systemconfig_oper import SystemConfigOper
from app.modules.qbittorrent.qbittorrent import Qbittorrent
from typing import Any, List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class DownloadingPlus(_PluginBase):
    plugin_name = "下載狀態增強"
    plugin_desc = "增強 /downloading 指令，顯示速率、剩餘時間、已下載大小"
    plugin_icon = "download.png"
    plugin_version = "1.8"
    plugin_author = "DEDE"
    author_url = ""
    plugin_config_prefix = "downloadingplus_"
    plugin_order = 20
    auth_level = 1

    _enabled = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
        else:
            self._enabled = True

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/dlstatus",
                "event": EventType.PluginAction,
                "desc": "查看下載詳細狀態",
                "category": "下載",
                "data": {"action": "dlstatus"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    @eventmanager.register(EventType.PluginAction)
    def handle(self, event: Event):
        if not self._enabled:
            return
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "dlstatus":
            return

        channel = event_data.get("channel")
        userid = event_data.get("user")
        source = event_data.get("source")

        def fmt_size(b):
            if b >= 1024**3:
                return f"{b/1024**3:.2f} GB"
            elif b >= 1024**2:
                return f"{b/1024**2:.1f} MB"
            return f"{b/1024:.0f} KB"

        def fmt_speed(b):
            if b >= 1024**2:
                return f"{b/1024**2:.1f} MB/s"
            elif b >= 1024:
                return f"{b/1024:.0f} KB/s"
            return f"{b} B/s"

        def fmt_eta(s):
            if s < 0 or s >= 8640000:
                return "未知"
            h, r = divmod(s, 3600)
            m, sec = divmod(r, 60)
            if h > 0:
                return f"{h}時{m}分"
            elif m > 0:
                return f"{m}分{sec}秒"
            return f"{sec}秒"

        try:
            db = SystemConfigOper()
            downloaders = db.get(SystemConfigKey.Downloaders) or []
            qb_config = None
            for d in downloaders:
                if d.get("type") == "qbittorrent" and d.get("enabled"):
                    qb_config = d.get("config", {})
                    break

            if not qb_config:
                self.post_message(channel=channel, title="❌ 找不到 qBittorrent 設定", userid=userid, source=source)
                return

            qb = Qbittorrent(
                host=qb_config.get("host"),
                username=qb_config.get("username"),
                password=qb_config.get("password")
            )
            torrents, error = qb.get_torrents(status="downloading")

            if error:
                self.post_message(channel=channel, title="❌ 無法連接 qBittorrent", userid=userid, source=source)
                return

            if not torrents:
                self.post_message(channel=channel, title="✅ 目前沒有下載中的任務", userid=userid, source=source)
                return

            title = f"📥 下載中（共 {len(torrents)} 個任務）"
            lines = []

            for i, torrent in enumerate(torrents, 1):
                name = torrent.get("name", "未知")
                size = torrent.get("size", 0)
                downloaded = torrent.get("downloaded", 0)
                progress = torrent.get("progress", 0) * 100
                dlspeed = torrent.get("dlspeed", 0)
                eta = torrent.get("eta", -1)

                bar_len = 10
                filled = int(bar_len * progress / 100)
                bar = "█" * filled + "░" * (bar_len - filled)

                line = (
                    f"{'─'*28}\n"
                    f"🎬 {i}. {name[:38]}{'...' if len(name)>38 else ''}\n"
                    f"[{bar}] {progress:.1f}%\n"
                    f"📦 {fmt_size(downloaded)} / {fmt_size(size)}\n"
                    f"⚡ ↓ {fmt_speed(dlspeed)}\n"
                    f"⏱ 剩餘：{fmt_eta(eta)}"
                )
                lines.append(line)

            self.post_message(
                channel=channel,
                title=title,
                text="\n".join(lines),
                userid=userid,
                source=source
            )

        except Exception as e:
            logger.error(f"DownloadingPlus error: {e}")
            self.post_message(channel=channel, title=f"❌ 發生錯誤：{str(e)}", userid=userid, source=source)

    def get_form(self) -> Tuple[List, Dict]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "啟用插件",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ], {"enabled": True}

    def get_page(self) -> List[dict]:
        return []

    def stop_service(self):
        pass
