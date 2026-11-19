"""ป้องกันการย้อนหาตัวบุคคลจากตัวเลขรวมในหน้าสาธารณะ (คนนอก รพ. ที่ไม่ได้ login) — แบบเดียวกับ anc_dashboard

ปัญหา: หน้าแรกเลือกช่วงวันที่เองได้ (28–400 วัน) — เปิดช่วง 28 วันกับ 29 วันที่เริ่มวันเดียวกันแล้วลบกัน
ได้ตัวเลขของวันเดียว คนที่รู้ว่าใครคลอดวันไหนจะรู้ว่าการคลอดนั้นมี PPH / ครรภ์เป็นพิษ / ทารกขาดออกซิเจน ฯลฯ
และหน้ารายปีแสดงจำนวนมารดา HIV / Syphilis / Hep B / สารเสพติด และเด็กตาย ที่อาจเป็น 1–2 รายต่อปี

มาตรการ (เฉพาะหน้าสาธารณะ — เครื่องใน รพ. และผู้ที่ login แล้วเห็นตัวเลขเต็มเหมือนเดิม):
1. ช่วงที่กำหนดเองปัดเป็นเดือนเต็ม: วันเริ่ม = วันที่ 1 · วันสิ้นสุด = สิ้นเดือน (เดือนปัจจุบันถึงวันนี้)
2. ตัวเลขภาวะแทรกซ้อนและแถวอ่อนไหวในหน้ารายปีที่มี 1 ถึง MIN_CELL-1 แสดงเป็น "<5"

LR_PUBLIC_MIN_CELL = ขนาดช่องขั้นต่ำ (ค่าเริ่มต้น 5) · 0 = ปิดมาตรการทั้งหมด (ไม่แนะนำ)
"""

import calendar
import copy
import os
from datetime import date

MIN_CELL = max(int(os.getenv("LR_PUBLIC_MIN_CELL", "5") or 0), 0)

#: แถวในหน้ารายปี (metrics.KPI_KEYS) ที่เป็นข้อมูลสุขภาพอ่อนไหวพิเศษ
SENSITIVE_KPI = {"amph", "alcohol_smoke", "syphilis", "hiv", "hbv", "still", "neo_death7"}


def enabled():
    return MIN_CELL > 0


def label():
    return f"<{MIN_CELL}"


def month_window(d1, d2, today=None):
    """ปัดช่วงเป็นเดือนเต็ม · วันสิ้นสุดไม่เกินวันนี้"""
    today = today or date.today()
    end = d2.replace(day=calendar.monthrange(d2.year, d2.month)[1])
    return d1.replace(day=1), min(end, today)


def _small(n):
    return isinstance(n, int) and not isinstance(n, bool) and 0 < n < MIN_CELL


def count(n):
    """จำนวนนับของเหตุการณ์อ่อนไหว → "<5" ถ้า 1–4"""
    return label() if _small(n) else n


def public_ctx(ctx):
    """สำเนาของ ctx หน้าแรก (ต้นฉบับอาจใช้ร่วมกับเครื่องใน รพ. — ห้ามแก้) ที่ซ่อนช่องเล็กแล้ว"""
    if not enabled():
        return ctx
    c = copy.copy(ctx)
    c["public_privacy"] = True
    c["quality"] = [dict(q, n=count(q.get("n"))) for q in ctx.get("quality") or []]
    c["kpi"] = {k: (dict(r, value=count(r.get("value"))) if k in SENSITIVE_KPI else r)
                for k, r in (ctx.get("kpi") or {}).items()}
    return c


def public_yearly(table):
    """สำเนาตารางรายปีที่ซ่อนแถวอ่อนไหวที่มี 1–4 ราย"""
    if not enabled():
        return table
    t = copy.deepcopy(table)
    t["public_privacy"] = True
    for row in t.get("rows") or []:
        if row.get("key") in SENSITIVE_KPI:
            row["values"] = [count(v) for v in row["values"]]
    return t
