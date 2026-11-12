"""ตั้งค่าร่วมของ test — ไม่ต่อฐานข้อมูลจริง"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LR_HOSPITAL_NAME", "โรงพยาบาลทดสอบ")
os.environ["LR_SECRET_KEY"] = ""          # ไม่ให้ .env ของเครื่องเปิดหน้ารายชื่อ
os.environ["LR_DATA_AUDITED"] = ""
os.environ["LR_CACHE_TTL"] = "0"          # ไม่แคชใน test
