"""یک بار روی کامپیوتر/گوشی خودت اجرا کن (pip install telethon) تا رشته‌ی نشست ساخته شود؛ آن را در Secrets با نام TG_SESSION بگذار.
هشدار: هر کسی این رشته را داشته باشد به حساب تلگرامت دسترسی دارد. جایی منتشرش نکن."""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
api_id = int(input("api_id: ")); api_hash = input("api_hash: ").strip()
with TelegramClient(StringSession(), api_id, api_hash) as c:
    print("\nTG_SESSION =\n" + c.session.save())
