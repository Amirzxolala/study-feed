import asyncio, json, os, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import mocks
SRC = Path(__file__).resolve().parent.parent; mocks.start(18091)
root = Path(tempfile.mkdtemp()); shutil.copytree(SRC / "agent", root / "agent"); (root / "data").mkdir()
os.environ.update(AGENT_ROOT=str(root), TG_API_BASE="http://127.0.0.1:18091", LLM_BASE_URL="http://127.0.0.1:18091/v1", LLM_MODEL="m", LLM_KEYS="k2", AGENT_FAST="1", TG_OWNER_ID="111")
os.environ.pop("TG_BOT_TOKEN", None)
sys.path.insert(0, str(SRC / "agent")); import agent as A; from channels import ChannelSource

class F:  # فایل
    def __init__(s, n, size, mime): s.name, s.size, s.mime_type = n, size, mime
class M:
    def __init__(s, id, text, date_i, media=None, f=None, grouped=None, photo=None):
        s.id, s.message, s.media, s.file, s.grouped_id, s.photo, s.web_preview = id, text, media, f, grouped, photo, None
        s.date = datetime.fromtimestamp(1790000000 + date_i, timezone.utc)
class Fake:
    calls = []
    def __init__(s, msgs): s.msgs = msgs; s.sent = []
    async def connect(s): pass
    async def disconnect(s): pass
    async def is_user_authorized(s): return True
    async def get_entity(s, u):
        if u == "nochannel": raise ValueError("no such")
        class E: title = "کانال آزمون"
        return E()
    async def iter_messages(s, ent, limit=None, min_id=0, reverse=False):
        Fake.calls.append((limit, min_id, reverse))
        L = [m for m in s.msgs if m.id > min_id]
        L = sorted(L, key=lambda m: m.id, reverse=not reverse)[:limit]
        for m in L: yield m
    async def download_media(s, m, file=None): return b"BLOB" + str(m.id).encode()
    async def send_message(s, *a, **k): s.sent.append(a)

msgs = [M(i, f"ثبت‌نام کنکور مرحله {i}", i) for i in range(1, 15)]
msgs.append(M(20, "جدول امتحانات", 20, media=1, f=F("t.pdf", 100, "application/pdf")))
msgs.append(M(21, "", 21, media=1, f=F("huge.zip", 99_000_000, "application/zip")))
fk = Fake(msgs)
cfg = {"first_run_limit": 3, "per_run_limit": 40, "channels": [{"username": "@exams", "name": "کانال آزمون"}, {"username": "nochannel"}]}
ok = 0
def check(c, m):
    global ok; print(("✅ " if c else "❌ ") + m); ok += 1
    if not c: raise SystemExit(1)
feed = A.run([ChannelSource(client=fk, cfg=cfg)])
it = feed["items"]
check(len(it) == 2, f"اولین بار فقط ۳ پیام آخر دیده شد (یکی‌شان فایل بدون متن و بزرگ بود) ({len(it)})")
check(all(x["origin"] == "telegram" and x["source"] == "کانال آزمون" for x in it), "منبع = نام کانال")
check(any(x["link"] == "https://t.me/exams/20" for x in it), "لینک پیام اصلی ساخته شد")
pdf = next(x for x in it if x["files"]); check(pdf["files"][0]["name"] == "t.pdf" and (root / pdf["files"][0]["path"]).read_bytes() == b"BLOB20", "فایل کانال دانلود و ذخیره شد")
check(not any("huge" in json.dumps(x) for x in it), "فایل خیلی بزرگ دانلود نشد")
check(fk.sent == [], "هیچ پیامی ارسال نشد (فقط خواندن)")
st = json.loads((root / "data/state.json").read_text("utf-8")); check(st["channels"]["exams"] == 21, "آخرین شناسه‌ی پیام ذخیره شد")
# اجرای دوم: فقط پیام‌های جدید
fk.msgs.append(M(22, "ثبت‌نام کنکور تازه", 22)); n = len(it)
feed = A.run([ChannelSource(client=fk, cfg=cfg)])
check(len(feed["items"]) == n + 1, "اجرای دوم فقط پیام جدید را آورد")
check(Fake.calls[-1][1] == 21 and Fake.calls[-1][2] is True, "درخواست با min_id درست")
print(f"\n{ok} تست کانال موفق")
