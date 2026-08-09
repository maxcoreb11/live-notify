"""
Telegram Live-Stream Reminder Bot
==================================
อ่านตารางถ่ายทอดสดจาก schedule.json แล้วส่งข้อความแจ้งเตือนเข้ากลุ่ม/แชท Telegram
ล่วงหน้าตามเวลาที่กำหนด (LEAD_MINUTES) เพื่อให้พนักงานเตรียมตัวก่อนไลฟ์

ออกแบบมาให้รันบน GitHub Actions (ไม่ต้องมีคอมพิวเตอร์/เซิร์ฟเวอร์ของตัวเอง):
    - อ่านค่า BOT_TOKEN / CHAT_ID / LEAD_MINUTES จาก environment variables
      (มาจาก GitHub Actions secrets) เป็นหลัก
    - ถ้าไม่มี env vars จะ fallback ไปอ่านจาก config.json (ไว้ใช้ทดสอบในเครื่องตัวเอง)

สคริปต์นี้ไม่ต้องรันค้าง (ไม่ใช่ long-running process) — เรียกทุกครั้งแล้วจบ
เหมาะกับ scheduled workflow ที่รันทุก 5 นาที
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from banner import generate_banner

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_PATH = os.path.join(BASE_DIR, "schedule.json")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH = os.path.join(BASE_DIR, "notify_bot.log")

BANGKOK = ZoneInfo("Asia/Bangkok")

# กราซพีเรียด: GitHub Actions cron รันจริงทุก ~5 นาที และบางช่วงอาจดีเลย์เพิ่ม
# อีกหลายนาทีถ้าคิวของ GitHub ยาว จึงตั้งช่วงนี้ให้กว้างพอ (นาที) เพื่อไม่ให้พลาดแจ้งเตือน
GRACE_MINUTES = 20

# ─────────────────────────────────────────────────────────────
#  ปุ่มใต้ข้อความ (แก้ตรงนี้ได้เลย)
# ─────────────────────────────────────────────────────────────
# ปุ่มเดียวใต้ทุกข้อความ — ลิงก์ไลฟ์ของช่องเรา
# ต้องเป็นลิงก์ (URL) เท่านั้น ปุ่มแบบกดแล้วบอทตอบกลับใช้ไม่ได้กับระบบนี้
# ตั้งเป็น None ถ้าไม่อยากให้มีปุ่มเลย
LIVE_BUTTON = {"text": "รับชมถ่ายทอดสด", "url": "https://t.me/u800live?livestream"}


def build_keyboard(event: dict):
    """สร้างปุ่มใต้ข้อความ คืนค่า None ถ้าไม่มีปุ่มเลย"""
    if not LIVE_BUTTON:
        return None
    return {"inline_keyboard": [[LIVE_BUTTON]]}


def log(msg: str):
    line = f"[{datetime.now(BANGKOK).isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path, required=True):
    if not os.path.exists(path):
        if required:
            log(f"ERROR: ไม่พบไฟล์ {path}")
            sys.exit(1)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_schedule(events):
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def send_telegram_photo(bot_token: str, chat_id: str, photo_path: str, caption: str,
                        reply_markup=None) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo_file:
            files = {"photo": photo_file}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
            if reply_markup:
                # ส่งแบบ multipart ต้องแปลงปุ่มเป็นข้อความ JSON ก่อน
                data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            resp = requests.post(url, data=data, files=files, timeout=30)
        if resp.status_code == 200:
            return True
        log(f"ERROR: Telegram sendPhoto ตอบกลับ {resp.status_code}: {resp.text}")
        return False
    except requests.RequestException as e:
        log(f"ERROR: ส่งรูปไม่สำเร็จ: {e}")
        return False


def send_telegram_message(bot_token: str, chat_id: str, text: str, reply_markup=None) -> bool:
    """สำรอง: ส่งข้อความล้วน ใช้เมื่อสร้าง/ส่งรูปแบนเนอร์ไม่สำเร็จ"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return True
        log(f"ERROR: Telegram API ตอบกลับ {resp.status_code}: {resp.text}")
        return False
    except requests.RequestException as e:
        log(f"ERROR: ส่งข้อความไม่สำเร็จ: {e}")
        return False


def format_caption(event: dict, lead_minutes: int) -> str:
    if lead_minutes == 0:
        header = "🔴 *กำลังจะเริ่มไลฟ์ตอนนี้!*"
    else:
        header = f"⏰ *แจ้งเตือนล่วงหน้า {lead_minutes} นาที*"
    lines = [
        header,
        f"📌 *{event['title']}*",
        f"🏷️ ประเภท: {event['category']}",
        f"🆚 {event['detail']}",
        f"📅 วัน{event['day_th']}ที่ {event['date']}",
        f"🕒 เวลาไทย: {event['time']} น.",
    ]
    # ฟิลด์เสริมจากตาราง Excel — ใส่เฉพาะรายการที่มีข้อมูล
    if event.get("channel"):
        free_tv = f" ({event['free_tv']})" if event.get("free_tv") else ""
        lines.append(f"📺 ดูที่: {event['channel']}{free_tv}")
    if event.get("club"):
        lines.append(f"👤 ผู้รับผิดชอบ: {event['club']}")
    lines.append("\n_เตรียมทีมให้พร้อมสำหรับการถ่ายทอด/ตัดคลิปนะครับ_")
    return "\n".join(lines)


def load_settings():
    """อ่านการตั้งค่า: env vars (GitHub Actions secrets) ก่อน ถ้าไม่มีค่อย fallback ไป config.json"""
    bot_token = os.environ.get("BOT_TOKEN", "")
    chat_id = os.environ.get("CHAT_ID", "")
    lead_env = os.environ.get("LEAD_MINUTES", "")

    if lead_env:
        lead_minutes_list = [int(x.strip()) for x in lead_env.split(",") if x.strip() != ""]
    else:
        lead_minutes_list = None

    if not bot_token or not chat_id or lead_minutes_list is None:
        config = load_json(CONFIG_PATH, required=False) or {}
        bot_token = bot_token or config.get("bot_token", "")
        chat_id = chat_id or config.get("chat_id", "")
        if lead_minutes_list is None:
            lead_minutes_list = config.get("lead_minutes", [30])

    return bot_token, chat_id, lead_minutes_list


def main():
    bot_token, chat_id, lead_minutes_list = load_settings()

    if not bot_token or bot_token.startswith("YOUR_"):
        log("ERROR: ยังไม่ได้ตั้งค่า BOT_TOKEN (env var หรือ config.json)")
        sys.exit(1)
    if not chat_id or str(chat_id).startswith("YOUR_"):
        log("ERROR: ยังไม่ได้ตั้งค่า CHAT_ID (env var หรือ config.json)")
        sys.exit(1)

    events = load_json(SCHEDULE_PATH)
    now = datetime.now(BANGKOK)
    changed = False

    for event in events:
        try:
            event_dt = datetime.strptime(
                f"{event['date']} {event['time']}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=BANGKOK)
        except ValueError:
            continue  # เวลารูปแบบไม่ถูกต้อง ข้าม

        notified_leads = event.setdefault("notified_leads", [])

        for lead in lead_minutes_list:
            if lead in notified_leads:
                continue
            trigger_time = event_dt - timedelta(minutes=lead)
            # ถึงเวลาแจ้งเตือนแล้ว (อยู่ในช่วง trigger_time ถึง trigger_time+GRACE)
            if trigger_time <= now <= trigger_time + timedelta(minutes=GRACE_MINUTES):
                caption = format_caption(event, lead)
                keyboard = build_keyboard(event)
                sent = False
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        banner_path = generate_banner(event, lead, tmp.name)
                    sent = send_telegram_photo(bot_token, chat_id, banner_path, caption, keyboard)
                    os.remove(banner_path)
                except Exception as e:
                    log(f"WARNING: สร้างรูปแบนเนอร์ไม่สำเร็จ ({e}) จะส่งเป็นข้อความล้วนแทน")
                if not sent:
                    sent = send_telegram_message(bot_token, chat_id, caption, keyboard)
                if sent:
                    notified_leads.append(lead)
                    changed = True
                    log(f"ส่งแจ้งเตือนสำเร็จ: {event['title']} ({event['detail']}) lead={lead}min")

    if changed:
        save_schedule(events)


if __name__ == "__main__":
    main()
