#!/usr/bin/env python3
"""
ایجنت جمع‌آوری مطالب از تلگرام برای اپ.
اجرا:  python agent/agent.py            (یک بار اجرا می‌شود و تمام می‌شود؛ مناسب GitHub Actions)
بدون وابستگی اجباری (فقط کتابخانه‌ی استاندارد). برای خواندن PDF اختیاری: pip install pypdf
"""
import base64, hashlib, json, os, re, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", Path(__file__).resolve().parent.parent))
CFG = json.loads((ROOT / "agent" / "config.json").read_text("utf-8"))
INSTR = (ROOT / "agent" / "instructions.md").read_text("utf-8")
DATA = ROOT / "data"
FEED_P, STATE_P = DATA / "feed.json", DATA / "state.json"
INBOX = ROOT / "inbox"
CATS = {c["id"]: c for c in CFG["categories"]}
TG_BASE = os.environ.get("TG_API_BASE", "https://api.telegram.org").rstrip("/")
TOKEN = os.environ.get("TG_BOT_TOKEN", "")
OWNER = str(os.environ.get("TG_OWNER_ID", "")).strip()
ALLOWED_CHATS = {x.strip() for x in re.split(r"[,\s]+", os.environ.get("TG_ALLOWED_CHATS", "")) if x.strip()}
ALLOWED_USERS = {OWNER} | {x.strip() for x in re.split(r"[,\s]+", os.environ.get("TG_ALLOWED_USERS", "")) if x.strip()}
ALLOWED_USERS.discard("")


def log(*a):
    print("[agent]", *a, flush=True)


# ------------------------------------------------------------------ HTTP
def http(method, url, body=None, headers=None, timeout=60, raw=False):
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            return b if raw else json.loads(b.decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        txt = ""
        try:
            txt = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        raise HTTPFail(e.code, txt)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise HTTPFail(0, str(e))


class HTTPFail(Exception):
    def __init__(self, code, text=""):
        super().__init__(f"HTTP {code} {text}")
        self.code, self.text = code, text


def tg(method, **params):
    r = http("POST", f"{TG_BASE}/bot{TOKEN}/{method}", params)
    if not r.get("ok"):
        raise HTTPFail(r.get("error_code", 0), r.get("description", ""))
    return r["result"]


# ------------------------------------------------------------------ LLM
class LLMUnavailable(Exception):
    pass


def llm_profiles():
    """هر پروفایل: base_url, model, keys[]. از LLM_CONFIG (JSON) یا سه متغیر ساده."""
    raw = os.environ.get("LLM_CONFIG", "").strip()
    if raw:
        cfg = json.loads(raw)
        return cfg if isinstance(cfg, list) else [cfg]
    keys = [k for k in re.split(r"[,\s]+", os.environ.get("LLM_KEYS", os.environ.get("LLM_KEY", ""))) if k]
    return [{
        "base_url": os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "model": os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
        "keys": keys,
    }]


class LLM:
    def __init__(self):
        self.profiles = llm_profiles()
        self.dead = set()      # (profile_idx, key_idx) که در این اجرا محدود/نامعتبر شدند
        self.no_vision = set()  # پروفایل‌هایی که تصویر را قبول نکردند
        self.used = None

    def _call(self, pi, ki, messages):
        p = self.profiles[pi]
        url = p["base_url"].rstrip("/") + "/chat/completions"
        body = {"model": p["model"], "messages": messages, "temperature": 0.2}
        if p.get("json_mode", False):
            body["response_format"] = {"type": "json_object"}
        r = http("POST", url, body, {"Authorization": "Bearer " + p["keys"][ki]}, timeout=90)
        return r["choices"][0]["message"]["content"]

    def ask(self, system, user_text, images=()):
        last = None
        for pi, p in enumerate(self.profiles):
            for ki in range(len(p.get("keys", []))):
                if (pi, ki) in self.dead:
                    continue
                use_img = bool(images) and pi not in self.no_vision and p.get("vision", True)
                for attempt in range(3):
                    content = user_text
                    if use_img:
                        content = [{"type": "text", "text": user_text}] + [
                            {"type": "image_url", "image_url": {"url": u}} for u in images]
                    msgs = [{"role": "system", "content": system}, {"role": "user", "content": content}]
                    try:
                        out = self._call(pi, ki, msgs)
                        self.used = {"model": p["model"], "key": ki + 1}
                        return out
                    except HTTPFail as e:
                        last = e
                        t = (e.text or "").lower()
                        if use_img and e.code in (400, 415, 422) and ("image" in t or "vision" in t or "content" in t):
                            self.no_vision.add(pi)
                            use_img = False
                            continue
                        if e.code in (429, 402, 403) or "quota" in t or "insufficient" in t:
                            log(f"کلید {ki+1} از پروفایل {p['model']} محدود شد → کلید بعدی")
                            self.dead.add((pi, ki))
                            break
                        if e.code in (401, 400) and ("key" in t or e.code == 401):
                            log(f"کلید {ki+1} از پروفایل {p['model']} نامعتبر است")
                            self.dead.add((pi, ki))
                            break
                        if e.code in (0, 500, 502, 503, 504):
                            time.sleep(min(2 ** attempt, 4) if not os.environ.get("AGENT_FAST") else 0)
                            continue
                        raise
                    except (KeyError, IndexError, ValueError) as e:
                        last = e
                        break
        raise LLMUnavailable(str(last))


def extract_json(s):
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no json")
    return json.loads(s[i:j + 1])


def clamp(s, n):
    s = str(s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def build_system():
    lines = "\n".join(f'- {c["id"]}: {c["name"]} ({c["hint"]})' for c in CFG["categories"])
    return INSTR + "\n\nفهرست دسته‌ها (category باید دقیقاً یکی از این شناسه‌ها باشد):\n" + lines


def validate(raw):
    """خروجی مدل را سخت‌گیرانه پاک‌سازی می‌کند؛ هر چیز غیرمجاز به صف تایید می‌رود."""
    cat = raw.get("category")
    ok_cat = cat in CATS
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence", 0))))
    except Exception:
        conf = 0.0
    rel = raw.get("reliability")
    if rel not in ("official", "reported", "unverified"):
        rel = "unverified"
    ed = raw.get("event_date")
    if not (isinstance(ed, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ed)):
        ed = None
    tags = [clamp(t, 24) for t in (raw.get("tags") or []) if isinstance(t, str)][:5]
    return {
        "relevant": raw.get("relevant") is not False,
        "cat": cat if ok_cat else "notice",
        "title": clamp(raw.get("title"), 90), "summary": clamp(raw.get("summary"), 300),
        "body": clamp(raw.get("body"), 3000), "tags": tags, "reliability": rel, "event_date": ed,
        "confidence": conf if ok_cat else min(conf, 0.3),
    }


# ------------------------------------------------------------------ ذخیره‌سازی
def load_json(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def save_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(p)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(n):
    n = re.sub(r"[^\w.\-؀-ۿ]+", "_", n or "file").strip("._") or "file"
    return n[:80]


# ------------------------------------------------------------------ دریافت از تلگرام
def norm_message(m, kind):
    """یک پیام تلگرام را به ساختار ساده تبدیل می‌کند."""
    chat = m.get("chat", {})
    frm = m.get("from", {}) or {}
    files = []
    if m.get("document"):
        d = m["document"]
        files.append({"fid": d["file_id"], "name": d.get("file_name") or "file", "mime": d.get("mime_type", ""), "size": d.get("file_size", 0)})
    if m.get("photo"):
        ph = max(m["photo"], key=lambda x: x.get("file_size", 0) or x.get("width", 0))
        files.append({"fid": ph["file_id"], "name": "photo.jpg", "mime": "image/jpeg", "size": ph.get("file_size", 0)})
    for k, nm in (("video", "video.mp4"), ("audio", "audio.mp3"), ("voice", "voice.ogg")):
        if m.get(k):
            v = m[k]
            files.append({"fid": v["file_id"], "name": v.get("file_name") or nm, "mime": v.get("mime_type", ""), "size": v.get("file_size", 0)})
    src = chat.get("title") or chat.get("username") or "تلگرام"
    fo = m.get("forward_origin") or {}
    if fo.get("chat", {}).get("title"):
        src = fo["chat"]["title"]
    elif fo.get("sender_user_name"):
        src = fo["sender_user_name"]
    elif m.get("forward_from_chat", {}).get("title"):
        src = m["forward_from_chat"]["title"]
    link = ""
    uname = (fo.get("chat") or chat).get("username")
    mid_f = fo.get("message_id") or m["message_id"]
    if uname:
        link = f"https://t.me/{uname}/{mid_f}"
    return {
        "key": f'{chat.get("id")}:{m["message_id"]}', "chat_id": chat.get("id"), "mid": m["message_id"],
        "user_id": str(frm.get("id", "")), "chat_type": chat.get("type"), "kind": kind,
        "date": datetime.fromtimestamp(m.get("date", time.time()), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "text": (m.get("text") or m.get("caption") or "").strip(), "files": files,
        "group": m.get("media_group_id"), "source": clamp(src, 60), "link": link,
    }


def is_allowed(msg):
    """فقط چت‌های مجاز (گروه/کانال خصوصی خودت) یا گفتگوی خصوصی با خودت. پیام‌های کانال‌خوانی (trusted) هم مجازند."""
    if msg.get("trusted") or str(msg["chat_id"]) in ALLOWED_CHATS:
        return True
    return msg["chat_type"] == "private" and msg["user_id"] in ALLOWED_USERS


def download(msg_file, dest_dir):
    """فایل را از تلگرام می‌گیرد (حداکثر max_file_mb). برمی‌گرداند: (مسیر نسبی یا None، سبب)."""
    lim = CFG["max_file_mb"] * 1024 * 1024
    if msg_file.get("size") and msg_file["size"] > lim:
        return None, "big"
    try:
        if msg_file.get("blob") is not None:      # حالت کانال‌ها: فایل از قبل دریافت شده
            blob = msg_file["blob"]
        else:
            info = tg("getFile", file_id=msg_file["fid"])
            blob = http("GET", f'{TG_BASE}/file/bot{TOKEN}/{info["file_path"]}', raw=True, timeout=120)
    except HTTPFail as e:
        return None, f"err:{e.code}"
    if len(blob) > lim:
        return None, "big"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = safe_name(msg_file["name"])
    p = dest_dir / name
    p.write_bytes(blob)
    return p, "ok"


def file_text(p, mime):
    """متن قابل‌استخراج از فایل (برای کمک به هوش مصنوعی)."""
    try:
        ext = p.suffix.lower()
        if ext in (".txt", ".md", ".csv", ".json") or mime.startswith("text/"):
            return p.read_text("utf-8", "ignore")[:6000]
        if ext == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(str(p))
            return "\n".join((pg.extract_text() or "") for pg in r.pages[:8])[:6000]
    except Exception as e:
        log("خواندن متن فایل ناموفق:", p.name, e)
    return ""


def hash_text(t):
    t = re.sub(r"\s+", " ", t).strip().lower()
    return hashlib.sha1(t.encode()).hexdigest()[:16] if len(t) >= 20 else ""


def hint_category(text):
    """هشتگ دستی مثل #konkur یا #روش_مطالعه، دسته را اجباری می‌کند."""
    for tag in re.findall(r"#([\w؀-ۿ]+)", text or ""):
        t = tag.lower().replace("_", " ")
        for c in CFG["categories"]:
            if t == c["id"] or t == c["name"].replace("‌", " ").lower() or t == c["name"].lower():
                return c["id"]
    return None


# ------------------------------------------------------------------ پردازش
def process(msg, feed, st, llm):
    keys = msg.get("keys") or [msg["key"]]
    iid = "i" + hashlib.sha1(keys[0].encode()).hexdigest()[:10]
    item = {
        "id": iid, "origin": "telegram", "date": msg["date"], "source": msg["source"], "link": msg["link"],
        "files": [], "status": "pending", "notified": False, "tries": 0, "msgkeys": keys,
        "chat_id": msg["chat_id"], "mid": msg["mid"], "created": now_iso(),
    }
    text = msg["text"]
    extra, images, notes = [], [], []
    for f in msg["files"]:
        p, why = download(f, DATA / "files" / iid)
        if not p:
            notes.append(f'فایل «{f["name"]}» ' + ("بزرگ‌تر از سقف بود و ذخیره نشد" if why == "big" else "دریافت نشد"))
            continue
        rel = p.relative_to(ROOT).as_posix()
        kind = "img" if f["mime"].startswith("image/") else "pdf" if p.suffix.lower() == ".pdf" else "file"
        item["files"].append({"name": f["name"], "path": rel, "type": kind, "size": p.stat().st_size})
        t = file_text(p, f["mime"])
        if t:
            extra.append(f'--- متن فایل «{f["name"]}» ---\n{t}')
        if kind == "img" and CFG.get("vision") and p.stat().st_size < 3_500_000:
            images.append(f'data:{f["mime"] or "image/jpeg"};base64,' + base64.b64encode(p.read_bytes()).decode())
    item["_input"] = "\n\n".join(x for x in [f'منبع: {msg["source"]}', f'متن پیام:\n{text}' if text else "(بدون متن)", *extra, *notes] if x)
    item["_images"] = images[:3]
    item["_text"] = text
    return item


def classify(item, llm):
    forced = hint_category(item["_text"])
    try:
        out = llm.ask(build_system(), item["_input"], item["_images"])
        v = validate(extract_json(out))
        item["ai"] = llm.used
    except LLMUnavailable as e:
        log("هوش مصنوعی در دسترس نبود:", e)
        item["status"], item["tries"], item["ai_failed"] = "pending", item["tries"] + 1, True
        first = (item["_text"].strip().splitlines() or ["بدون عنوان"])[0]
        item.update(cat=forced or "notice", title=clamp(first, 90), summary="", body=clamp(item["_text"], 3000),
                    tags=[], reliability="unverified", confidence=0.0, event_date=None)
        return item
    except ValueError:
        v = {"relevant": True, "cat": forced or "notice", "title": clamp((item["_text"].splitlines() or ["بدون عنوان"])[0], 90),
             "summary": "", "body": clamp(item["_text"], 3000), "tags": [], "reliability": "unverified", "event_date": None, "confidence": 0.0}
    item.pop("ai_failed", None)
    if forced:
        v["cat"], v["confidence"], v["relevant"] = forced, 1.0, True
    for k in ("cat", "title", "summary", "body", "tags", "reliability", "event_date", "confidence"):
        item[k] = v[k]
    item["section"] = CATS[item["cat"]]["section"]
    if not v["relevant"]:
        item["status"] = "rejected"
    elif v["confidence"] >= CFG["confidence_threshold"] and v["title"]:
        item["status"] = "published"
    else:
        item["status"] = "pending"
    return item


def finalize(item):
    item["section"] = CATS.get(item.get("cat"), CATS["notice"])["section"]
    for k in ("_input", "_images", "_text"):
        item.pop(k, None)
    return item


# ------------------------------------------------------------------ پیام‌ها به مالک
def reply(msg, text):
    if not CFG.get("reply_to_sender") or msg["chat_type"] == "channel":
        return
    try:
        tg("sendMessage", chat_id=msg["chat_id"], text=text, reply_to_message_id=msg["mid"])
    except HTTPFail as e:
        log("ارسال پاسخ ناموفق:", e)


def notify_review(item):
    if not OWNER or item.get("notified"):
        return
    c = CATS.get(item["cat"], {})
    txt = (f'🔎 نیاز به تایید\nدسته‌ی پیشنهادی: {c.get("emoji","")} {c.get("name","")} ({item["confidence"]:.0%})\n'
           f'عنوان: {item["title"]}\n\n{clamp(item.get("summary") or item.get("body"), 400)}')
    if item.get("ai_failed"):
        txt = "⚠️ هوش مصنوعی در دسترس نبود؛ بعداً دوباره تلاش می‌شود.\n\n" + txt
    rows = [[{"text": "✅ تایید", "callback_data": f"ap:{item['id']}"}, {"text": "❌ رد", "callback_data": f"rj:{item['id']}"}]]
    # دکمه‌ی عوض‌کردن دسته (۲ تا در هر ردیف)
    cb = [{"text": f'{c["emoji"]} {c["name"]}', "callback_data": f'ct:{item["id"]}:{c["id"]}'} for c in CFG["categories"]]
    rows += [cb[i:i + 2] for i in range(0, len(cb), 2)]
    try:
        tg("sendMessage", chat_id=OWNER, text=txt, reply_markup={"inline_keyboard": rows})
        item["notified"] = True
    except HTTPFail as e:
        log("ارسال درخواست تایید ناموفق:", e)


def handle_callback(cb, feed):
    uid = str(cb["from"]["id"])
    if uid not in ALLOWED_USERS:
        tg("answerCallbackQuery", callback_query_id=cb["id"], text="اجازه نداری")
        return
    parts = (cb.get("data") or "").split(":")
    act, iid = parts[0], parts[1] if len(parts) > 1 else ""
    item = next((x for x in feed["items"] if x["id"] == iid), None)
    if not item:
        tg("answerCallbackQuery", callback_query_id=cb["id"], text="این مورد پیدا نشد")
        return
    if act == "ap":
        item["status"] = "published"
        out = "تایید شد ✅"
    elif act == "rj":
        item["status"] = "rejected"
        out = "رد شد ❌"
    elif act == "ct" and len(parts) > 2 and parts[2] in CATS:
        item["cat"], item["section"] = parts[2], CATS[parts[2]]["section"]
        item["status"] = "published"
        out = f"منتشر شد در «{CATS[parts[2]]['name']}» ✅"
    else:
        out = "نامعتبر"
    item["reviewed"] = now_iso()
    tg("answerCallbackQuery", callback_query_id=cb["id"], text=out)
    try:
        m = cb.get("message") or {}
        tg("editMessageText", chat_id=m["chat"]["id"], message_id=m["message_id"], text=f'{item["title"]}\n\n{out}')
    except Exception:
        pass


# ------------------------------------------------------------------ inbox (آپلود دستی از اپ)
def read_inbox(feed, llm):
    n = 0
    if not INBOX.exists():
        return 0
    for p in sorted(INBOX.glob("*.json")):
        try:
            d = json.loads(p.read_text("utf-8"))
            iid = "m" + hashlib.sha1(p.name.encode()).hexdigest()[:10]
            if any(x["id"] == iid for x in feed["items"]):
                p.unlink()
                continue
            item = {"id": iid, "origin": "manual", "date": d.get("date") or now_iso(), "source": clamp(d.get("source") or "دستی", 60),
                    "link": clamp(d.get("link"), 300), "files": [], "created": now_iso(), "tries": 0,
                    "local_id": clamp(d.get("local_id"), 40)}
            for f in (d.get("files") or [])[:5]:
                raw = base64.b64decode(f.get("b64", ""))
                if len(raw) > CFG["max_file_mb"] * 1024 * 1024:
                    continue
                dest = DATA / "files" / iid
                dest.mkdir(parents=True, exist_ok=True)
                fp = dest / safe_name(f.get("name"))
                fp.write_bytes(raw)
                item["files"].append({"name": f.get("name", "file"), "path": fp.relative_to(ROOT).as_posix(),
                                      "type": f.get("type", "file"), "size": len(raw)})
            if d.get("cat") in CATS and d.get("title"):
                item.update(cat=d["cat"], title=clamp(d["title"], 90), summary=clamp(d.get("summary"), 300),
                            body=clamp(d.get("body") or d.get("text"), 3000), tags=[], reliability=d.get("reliability", "reported"),
                            event_date=None, confidence=1.0, status="published")
            else:
                item.update(_input=(d.get("text") or d.get("title") or ""), _images=[], _text=d.get("text") or "", status="pending")
                classify(item, llm)
            feed["items"].append(finalize(item))
            p.unlink()
            n += 1
        except Exception as e:
            log("inbox ناموفق:", p.name, e)
    return n


# ------------------------------------------------------------------ اجرای اصلی
def run(sources=None):
    DATA.mkdir(exist_ok=True)
    feed = load_json(FEED_P, {"version": 1, "items": []})
    st = load_json(STATE_P, {"offset": 0, "seen": [], "hashes": []})
    llm = LLM()
    new = 0
    seen, hashes = set(st["seen"]), set(st["hashes"])

    # ۱) بازپردازش مواردی که قبلاً هوش مصنوعی در دسترس نبود
    for it in feed["items"]:
        if it.get("ai_failed") and it.get("tries", 0) < CFG["llm_retries_per_item"]:
            it["_input"], it["_images"], it["_text"] = (it.get("body") or it.get("title", "")), [], it.get("body", "")
            classify(it, llm)
            if not it.get("ai_failed"):
                it["notified"] = False
            finalize(it)

    # ۲) پیام‌های جدید
    msgs, callbacks = [], []
    if sources is None:
        sources = [BotSource()] if TOKEN else []
    for s in sources:
        m, c = s.fetch(st)
        msgs += m
        callbacks += c
    for cb in callbacks:
        try:
            handle_callback(cb, feed)
        except Exception as e:
            log("callback ناموفق:", e)

    # دستورها و فیلتر
    todo = []
    for m in msgs:
        if m["key"] in seen:
            continue
        seen.add(m["key"])
        if not is_allowed(m):
            log("پیام از فرستنده‌ی غیرمجاز نادیده گرفته شد:", m["chat_id"], m["user_id"])
            continue
        if m["text"].startswith("/") and not m["files"]:
            cmd = m["text"].split()[0].split("@")[0]
            pend = sum(1 for x in feed["items"] if x["status"] == "pending")
            if cmd in ("/start", "/help"):
                reply(m, "سلام! هر متن، فایل، عکس یا پیام فورواردی که اینجا بفرستی، در اجرای بعدی (هر یک ساعت) دسته‌بندی می‌شه و می‌ره تو اپ.\nبرای دسته‌ی دستی هشتگ بزن؛ مثلاً #konkur یا #روش_مطالعه.\n/status وضعیت رو نشون می‌ده.")
            elif cmd == "/status":
                reply(m, f'در اپ: {sum(1 for x in feed["items"] if x["status"]=="published")} مورد • در انتظار تایید: {pend}')
            continue
        todo.append(m)

    # ادغام آلبوم‌ها (چند عکس/فایل با یک media_group_id یک مورد می‌شوند)
    merged, gidx = [], {}
    for m in todo:
        g = m.get("group")
        if g and g in gidx:
            cur = merged[gidx[g]]
            cur["text"] = "\n".join(t for t in (cur["text"], m["text"]) if t)
            cur["files"] = cur["files"] + m["files"]
            cur.setdefault("keys", [cur["key"]]).append(m["key"])
        else:
            if g:
                gidx[g] = len(merged)
            merged.append(dict(m))
    for m in merged:
        if not m["text"] and not m["files"]:
            continue
        h = hash_text(m["text"])
        if h and h in hashes:
            log("تکراری (متن مشابه) رد شد")
            continue
        item = process(m, feed, st, llm)
        classify(item, llm)
        if h and item["status"] != "rejected":
            hashes.add(h)
        finalize(item)
        feed["items"].append(item)
        new += 1
        label = {"published": f'✅ ثبت شد: «{item["title"]}» در {CATS[item["cat"]]["name"]}',
                 "pending": "🔎 مطمئن نبودم؛ برات درخواست تایید فرستادم.", "rejected": "این مورد به درد اپ نمی‌خورد؛ نادیده گرفتم."}[item["status"]]
        reply(m, label)

    new += read_inbox(feed, llm)

    # ۳) درخواست تایید برای موارد pending
    for it in feed["items"]:
        if it["status"] == "pending":
            notify_review(it)

    # ۴) پاک‌سازی و ذخیره
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CFG["keep_rejected_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    feed["items"] = [x for x in feed["items"] if not (x["status"] == "rejected" and x.get("created", "") < cutoff)]
    feed["items"].sort(key=lambda x: x.get("date", ""), reverse=True)
    dropped = feed["items"][CFG["max_items"]:]
    feed["items"] = feed["items"][:CFG["max_items"]]
    for d in dropped:
        for f in d.get("files", []):
            try:
                (ROOT / f["path"]).unlink()
            except Exception:
                pass
    feed.update(version=1, updated=now_iso(), categories=[{k: c[k] for k in ("id", "name", "emoji", "section")} for c in CFG["categories"]])
    save_json(FEED_P, feed)
    st["seen"], st["hashes"] = sorted(seen)[-3000:], sorted(hashes)[-3000:]
    save_json(STATE_P, st)
    log(f"تمام شد: {new} مورد جدید، کل {len(feed['items'])}")
    return feed


class BotSource:
    """خواندن پیام‌های جدید ربات با getUpdates (آفست در state ذخیره می‌شود)."""

    def fetch(self, st):
        msgs, cbs = [], []
        while True:
            ups = tg("getUpdates", offset=st.get("offset", 0), limit=100, timeout=0,
                     allowed_updates=["message", "channel_post", "callback_query"])
            if not ups:
                break
            for u in ups:
                st["offset"] = u["update_id"] + 1
                if "callback_query" in u:
                    cbs.append(u["callback_query"])
                for k in ("message", "channel_post"):
                    if k in u:
                        msgs.append(norm_message(u[k], k))
            if len(ups) < 100:
                break
        return msgs, cbs


if __name__ == "__main__":
    if not TOKEN and "--no-bot" not in sys.argv:
        log("TG_BOT_TOKEN تنظیم نشده")
    extra = []
    if os.environ.get("TG_SESSION"):
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from channels import ChannelSource
            extra.append(ChannelSource())
        except Exception as e:
            log("حالت کانال‌ها فعال نشد:", e)
    run(([BotSource()] if TOKEN else []) + extra)
