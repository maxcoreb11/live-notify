"""
Banner Generator
=================
สร้างรูปแบนเนอร์แจ้งเตือนไลฟ์ (PNG) แบบไดนามิก โดยใส่ชื่อคู่แข่งขัน/เวลา/ประเภทกีฬา
ลงในรูปโดยตรง เพื่อแนบไปกับข้อความ Telegram (sendPhoto)

ไม่พึ่งพาไฟล์รูปภายนอกระหว่างรัน (ฟอนต์ถูก commit ไว้ใน assets/fonts/)
"""

import os
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")

# ฟอนต์ Kanit ไม่มีกราฟิก emoji สี ถ้าปล่อยไว้จะกลายเป็นกล่องสี่เหลี่ยม (tofu)
# จึงกรองอักขระที่ไม่ใช่ไทย/อังกฤษ/ตัวเลข/เครื่องหมายพื้นฐานออกก่อนวาด
_ALLOWED_CHARS = re.compile(r"[^A-Za-z0-9\u0E00-\u0E7F\s\.,!?\-:;()/+|&%'\"]")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _ALLOWED_CHARS.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()

WIDTH, HEIGHT = 1200, 630  # ขนาดมาตรฐานรูปลิงก์/แบนเนอร์ social

# สีประจำแต่ละประเภทกีฬา (พื้นหลัง gradient เข้ม + สีเน้น)
CATEGORY_THEME = {
    "ONE": {"bg": (20, 10, 10), "accent": (255, 61, 0), "label": "ONE CHAMPIONSHIP"},
    "UFC": {"bg": (10, 10, 10), "accent": (218, 41, 28), "label": "UFC"},
    "VNL": {"bg": (8, 16, 28), "accent": (0, 174, 239), "label": "VOLLEYBALL NATIONS LEAGUE"},
    "บอลโลก": {"bg": (6, 20, 12), "accent": (0, 209, 96), "label": "FIFA WORLD CUP 2026"},
    "วอลเลย์บอล U18": {"bg": (8, 16, 28), "accent": (0, 174, 239), "label": "วอลเลย์บอล U18"},
    "บอล": {"bg": (8, 18, 14), "accent": (34, 197, 94), "label": "FOOTBALL"},
    "SEA V Cup": {"bg": (10, 14, 26), "accent": (255, 193, 7), "label": "SEA V CUP 2026"},
    "มวยไทย": {"bg": (22, 10, 6), "accent": (255, 122, 0), "label": "มวยไทย"},
}
DEFAULT_THEME = {"bg": (12, 12, 18), "accent": (255, 200, 0), "label": "LIVE SPORT"}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _draw_gradient_bg(draw: ImageDraw.ImageDraw, base_rgb, accent_rgb):
    """ไล่สีพื้นหลังจากมืดด้านบนไปโทนสีเน้นแบบเข้มด้านล่าง"""
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(base_rgb[0] + (accent_rgb[0] * 0.15 - base_rgb[0]) * t)
        g = int(base_rgb[1] + (accent_rgb[1] * 0.15 - base_rgb[1]) * t)
        b = int(base_rgb[2] + (accent_rgb[2] * 0.15 - base_rgb[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def generate_banner(event: dict, lead_minutes: int, out_path: str) -> str:
    """สร้างรูป PNG แล้วบันทึกที่ out_path, คืนค่า out_path"""
    theme = CATEGORY_THEME.get(event.get("category", ""), DEFAULT_THEME)
    bg, accent, cat_label = theme["bg"], theme["accent"], theme["label"]

    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw, bg, accent)

    # แถบเน้นสีด้านบน + ด้านล่าง
    draw.rectangle([(0, 0), (WIDTH, 14)], fill=accent)
    draw.rectangle([(0, HEIGHT - 14), (WIDTH, HEIGHT)], fill=accent)

    # ป้ายมุมซ้ายบน: สถานะ (LIVE SOON / LIVE NOW)
    status_font = _font("Kanit-Bold.ttf", 34)
    status_text = "🔴 LIVE NOW" if lead_minutes == 0 else f"⏰ อีก {lead_minutes} นาทีถ่ายทอดสด"
    status_text = status_text.replace("🔴 ", "").replace("⏰ ", "")  # emoji ตัดออก (ฟอนต์ไม่รองรับสี)
    pad = 24
    badge_w = draw.textlength(status_text, font=status_font) + pad * 2
    badge_h = 56
    draw.rounded_rectangle(
        [(50, 40), (50 + badge_w, 40 + badge_h)], radius=28,
        fill=accent if lead_minutes == 0 else (255, 255, 255, 30), outline=accent, width=2
    )
    text_color = (255, 255, 255) if lead_minutes == 0 else accent
    draw.text((50 + pad, 40 + 10), status_text, font=status_font, fill=text_color)

    # ป้ายประเภทกีฬา มุมขวาบน
    cat_font = _font("Kanit-Medium.ttf", 28)
    cat_w = draw.textlength(cat_label, font=cat_font)
    draw.text((WIDTH - 50 - cat_w, 52), cat_label, font=cat_font, fill=(230, 230, 230))

    # ชื่อรายการ (title) กลางเรื่อง
    title_font = _font("Kanit-Bold.ttf", 46)
    title_lines = _wrap_text(draw, _clean_text(event.get("title", "")), title_font, WIDTH - 140)
    y = 190
    for line in title_lines[:2]:
        lw = draw.textlength(line, font=title_font)
        draw.text(((WIDTH - lw) / 2, y), line, font=title_font, fill=(200, 200, 200))
        y += 58

    # คู่แข่งขัน (detail) — ตัวใหญ่สุด เด่นสุด
    detail_font = _font("Kanit-ExtraBold.ttf", 62)
    detail_clean = _clean_text(event.get("detail", ""))
    # ตัดส่วนเสริมท้ายๆ ที่คั่นด้วย "|" ออก เพื่อให้คู่แข่งขันหลักเด่นและไม่ล้นรูป
    detail_main = detail_clean.split("|")[0].strip()
    detail_lines = _wrap_text(draw, detail_main, detail_font, WIDTH - 100)
    y += 20
    for line in detail_lines[:2]:
        lw = draw.textlength(line, font=detail_font)
        # เงาตัวอักษรให้อ่านง่ายบนพื้นไล่สี
        draw.text(((WIDTH - lw) / 2 + 3, y + 3), line, font=detail_font, fill=(0, 0, 0))
        draw.text(((WIDTH - lw) / 2, y), line, font=detail_font, fill=(255, 255, 255))
        y += 76

    # เวลาไทย ด้านล่าง เด่นด้วยสีเน้น
    time_font = _font("Kanit-Bold.ttf", 44)
    time_text = f"เวลาไทย {event.get('time', '')} น.  |  วัน{event.get('day_th', '')}ที่ {event.get('date', '')}"
    tw = draw.textlength(time_text, font=time_font)
    draw.text(((WIDTH - tw) / 2, HEIGHT - 130), time_text, font=time_font, fill=accent)

    # แถบชื่อช่อง ล่างสุด
    brand_font = _font("Kanit-Medium.ttf", 26)
    brand_text = "11 PRO NO FAKE"
    bw = draw.textlength(brand_text, font=brand_font)
    draw.text(((WIDTH - bw) / 2, HEIGHT - 66), brand_text, font=brand_font, fill=(180, 180, 180))

    img.save(out_path, "PNG")
    return out_path
