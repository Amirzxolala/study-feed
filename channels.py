"""
حالت دوم: خواندن کانال‌های عمومی با حساب تلگرام خودت (Telethon). فقط خواندن؛ هیچ پیامی ارسال نمی‌شود.
نیاز: TG_API_ID, TG_API_HASH (از my.telegram.org)، TG_SESSION (با make_session.py یک بار روی کامپیوتر خودت بساز)
فهرست کانال‌ها در agent/channels.json
"""
import asyncio, json, os
from datetime import timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def clamp(s, n):
    s = str(s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


class ChannelSource:
    def __init__(self, client=None, cfg=None, max_bytes=None):
        self.cfg = cfg or json.loads((HERE / "channels.json").read_text("utf-8"))
        self.client = client
        self.max_bytes = max_bytes or int(os.environ.get("MAX_FILE_MB", "10")) * 1024 * 1024

    def _make_client(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])

    def fetch(self, st):
        return asyncio.run(self._fetch(st)), []

    async def _fetch(self, st):
        out = []
        cl = self.client or self._make_client()
        await cl.connect()
        try:
            if not await cl.is_user_authorized():
                raise RuntimeError("نشست تلگرام معتبر نیست؛ make_session.py را دوباره اجرا کن")
            cur = st.setdefault("channels", {})
            for ch in self.cfg["channels"]:
                uname = ch["username"].lstrip("@")
                try:
                    ent = await cl.get_entity(uname)
                except Exception as e:
                    print("[agent] کانال پیدا نشد:", uname, e)
                    continue
                last = cur.get(uname)
                if last is None:   # اولین بار: فقط چند پیام آخر، نه کل تاریخچه
                    msgs = [m async for m in cl.iter_messages(ent, limit=self.cfg.get("first_run_limit", 10))][::-1]
                else:
                    msgs = [m async for m in cl.iter_messages(ent, min_id=last, limit=self.cfg.get("per_run_limit", 40), reverse=True)]
                title = ch.get("name") or getattr(ent, "title", uname)
                for m in msgs:
                    cur[uname] = max(cur.get(uname) or 0, m.id)
                    text = (getattr(m, "message", None) or getattr(m, "text", "") or "").strip()
                    files = []
                    if getattr(m, "media", None) is not None and not getattr(m, "web_preview", None):
                        size = getattr(getattr(m, "file", None), "size", 0) or 0
                        name = getattr(getattr(m, "file", None), "name", None) or ("photo.jpg" if getattr(m, "photo", None) else "file")
                        mime = getattr(getattr(m, "file", None), "mime_type", "") or ("image/jpeg" if getattr(m, "photo", None) else "")
                        if size <= self.max_bytes:
                            blob = await cl.download_media(m, file=bytes)
                            if blob:
                                files.append({"fid": f"ch{uname}{m.id}", "blob": blob, "name": name, "mime": mime, "size": len(blob)})
                    if not text and not files:
                        continue
                    d = m.date.astimezone(timezone.utc) if getattr(m, "date", None) else None
                    out.append({
                        "key": f"ch:{uname}:{m.id}", "chat_id": f"ch:{uname}", "mid": m.id, "user_id": "", "chat_type": "channel", "kind": "channel",
                        "date": d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else "", "text": text, "files": files,
                        "group": f"ch{uname}{m.grouped_id}" if getattr(m, "grouped_id", None) else None,
                        "source": clamp(title, 60), "link": f"https://t.me/{uname}/{m.id}", "trusted": True,
                    })
        finally:
            await cl.disconnect()
        return out
