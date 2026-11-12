"""ตรวจความพร้อมก่อนใช้งาน LR Dashboard — รันหลังกรอกค่าฐานข้อมูลใน .env

    python setup_check.py              ตรวจสภาพแวดล้อม + ฐานข้อมูล + Data Audit 90 วันล่าสุด
    python setup_check.py --days 30    ตรวจข้อมูลย้อนหลัง 30 วัน
    python setup_check.py --no-audit   ข้าม Data Audit (เร็วกว่า)
    Docker: docker exec <ชื่อ container> python setup_check.py

อ่านฐานข้อมูลอย่างเดียว ไม่แก้ข้อมูลใน HOSxP · แสดงเฉพาะจำนวนนับ ไม่มีข้อมูลรายคน
ผล ✘ = ต้องแก้ก่อนใช้งาน · ⚠ = ใช้ได้แต่ควรตรวจ · ส่งผลทั้งหมดนี้มาด้วยเมื่อแจ้งปัญหา
"""

import argparse
import importlib
import os
import platform
import re
import sys
import time
from datetime import date, datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

#: ตารางที่แดชบอร์ดอ่าน — ไม่มี = ส่วนที่ใช้ตารางนั้นล้ม
TABLES = ["ipt_pregnancy", "ipt_labour", "ipt_labour_infant", "ipt_labour_lab", "labour_lab", "ipt_newborn", "ipt",
          "iptdiag", "iptoprt", "referout", "lab_head", "lab_order", "lab_items", "dchstts", "patient"]
#: สิทธิ์ที่บัญชีอ่านอย่างเดียวมีได้
SAFE_PRIVS = {"SELECT", "USAGE", "SHOW VIEW"}
#: การคลอดล่าสุดเก่ากว่านี้ (วัน) → เตือน (ไม่ใช่ฐานจริง / replica ไม่อัปเดต) · รพ.เล็กคลอดไม่ถึงวันละราย จึงตั้งไว้กว้าง
STALE_DAYS = 45


def risky_privs(grant_lines, dbname=None):
    """บรรทัดผลของ SHOW GRANTS → สิทธิ์ที่เกินกว่าอ่านอย่างเดียว · นับเฉพาะฐาน dbname และ *.*"""
    out = set()
    for line in grant_lines:
        m = re.match(r"\s*GRANT\s+(.+?)\s+ON\s+(\S+)", line or "", re.I)
        if not m:
            continue
        target = m.group(2).split(".")[0].strip("`'\"")
        if dbname and target not in ("*", dbname):
            continue
        for p in re.sub(r"\(.*?\)", "", m.group(1)).split(","):
            p = p.strip().upper()
            if p and p not in SAFE_PRIVS:
                out.add(p)
        if re.search(r"WITH\s+GRANT\s+OPTION", line, re.I):
            out.add("GRANT OPTION")
    return sorted(out)


def _list_check():
    """หน้ารายชื่อ (มีข้อมูลส่วนบุคคล): ปิด / เปิดแต่กุญแจสั้นหรือยังไม่มีบัญชี / พร้อมใช้"""
    key = os.getenv("LR_SECRET_KEY", "")
    if not key:
        return [("info", "หน้ารายชื่อ", "ปิดไว้ (ไม่ได้ตั้ง LR_SECRET_KEY) — แดชบอร์ดแสดงเฉพาะตัวเลข")]
    if len(key) < 32:
        return [("warn", "หน้ารายชื่อ", "LR_SECRET_KEY สั้นเกินไป — ใช้ python -c \"import secrets; print(secrets.token_hex(32))\"")]
    import store
    try:
        users = [u for u in store.list_users() if u["active"]]
    except Exception as e:                                       # noqa: BLE001
        return [("bad", "หน้ารายชื่อ", f"เปิดฐานข้อมูลผู้ใช้ {store.DB_PATH} ไม่ได้: {type(e).__name__} — ตรวจสิทธิ์เขียนโฟลเดอร์ LR_DATA_DIR")]
    lan = " · เฉพาะใน รพ." if os.getenv("LR_LIST_LAN_ONLY", "0") == "1" else ""
    if not users:
        return [("warn", "หน้ารายชื่อ", "เปิดแล้วแต่ยังไม่มีบัญชี — python manage.py adduser <ชื่อ> --display \"ชื่อ\"")]
    return [("ok", "หน้ารายชื่อ", f"เปิดใช้ · บัญชี {len(users)} คน{lan} · ดูประวัติการเปิดดู: python manage.py audit")]


def _env_checks():
    out = []
    v = sys.version_info
    out.append(("ok" if v >= (3, 10) else "bad", f"Python {platform.python_version()}", "ต้อง 3.10 ขึ้นไป"))
    need = [("flask", "Flask"), ("pymysql", "PyMySQL"), ("dotenv", "python-dotenv"), ("PIL", "Pillow"),
            ("waitress" if os.name == "nt" else "gunicorn", "waitress" if os.name == "nt" else "gunicorn")]
    missing = []
    for mod, pkg in need:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    out.append(("bad", "ไลบรารี Python", "ขาด " + ", ".join(missing) + " — pip install -r requirements.txt")
               if missing else ("ok", "ไลบรารี Python", "ครบตาม requirements.txt"))
    offset = -time.timezone if not time.localtime().tm_isdst else -time.altzone
    out.append(("ok", "เขตเวลา", "UTC+7") if offset == 7 * 3600 else
               ("warn", "เขตเวลา", f"UTC{offset / 3600:+g} ไม่ใช่ Asia/Bangkok — ช่วง 7 วันล่าสุดและปีงบประมาณปัจจุบันจะเพี้ยน"))
    import render
    if os.getenv("LR_EXPORT", "1") == "0":
        out.append(("info", "ส่งออกไฟล์", "ปิดไว้ (LR_EXPORT=0)"))
    else:
        try:
            out.append(("ok", "เบราว์เซอร์สำหรับส่งออก", render.find_browser()))
        except SystemExit:
            out.append(("warn", "เบราว์เซอร์สำหรับส่งออก",
                        "ไม่พบ Chrome/Edge/Chromium — ปุ่มส่งออก JPG/PDF ใช้ไม่ได้ หรือตั้ง LR_EXPORT=0"))
    return out


def _db_checks(fetch):
    out = []
    try:
        r = (fetch("select version() v, now() n, database() d") or [{}])[0]
    except Exception as e:                                       # noqa: BLE001
        out.append(("bad", "ต่อฐานข้อมูลไม่ได้", f"{type(e).__name__}: {str(e)[:160]} — ตรวจ DB_HOST/พอร์ต/firewall/GRANT"))
        return out, False
    dbname = r.get("d")
    out.append(("ok", "ต่อฐานข้อมูลได้", f"{r.get('v')} · ฐาน {dbname}"))

    try:
        rows = fetch("show grants for current_user()")
        risky = risky_privs([next(iter(x.values()), "") for x in rows], dbname)
        out.append(("bad", "สิทธิ์บัญชีฐานข้อมูล", "มีสิทธิ์เกินกว่าอ่านอย่างเดียว: " + ", ".join(risky) +
                    " — ใช้บัญชีที่มีแค่ SELECT") if risky else
                   ("ok", "สิทธิ์บัญชีฐานข้อมูล", f"อ่าน {dbname} ได้อย่างเดียว (SELECT)"))
    except Exception:                                            # noqa: BLE001
        out.append(("info", "สิทธิ์บัญชีฐานข้อมูล", "อ่าน SHOW GRANTS ไม่ได้ — ข้าม"))

    have = {str(x.get("t", "")).lower() for x in
            fetch("select table_name t from information_schema.tables where table_schema = database()")}
    miss = [t for t in TABLES if t not in have]
    out.append(("bad", "ตาราง HOSxP", "ไม่พบ " + ", ".join(miss)) if miss else
               ("ok", "ตาราง HOSxP", f"ครบ {len(TABLES)} ตาราง"))
    if miss:
        return out, False

    names = [str(x.get("name") or "") for x in fetch("select lab_name name from labour_lab limit 30")]
    garbled = any("�" in n or re.search(r"[ÃÂàáâ¡-ÿ]{2,}|\?{3,}", n) for n in names)
    out.append(("warn", "ภาษาไทย", "ชื่อรายการ labour_lab อ่านไม่ออก — ตรวจ charset (HOSxP ใช้ tis620)") if garbled else
               ("ok", "ภาษาไทย", "อ่านชื่อรายการได้"))

    last = (fetch("select max(labor_date) d from ipt_pregnancy where labor_date <= curdate()") or [{}])[0].get("d")
    if not last:
        out.append(("bad", "การคลอดล่าสุด", "ไม่มีข้อมูลใน ipt_pregnancy — งานห้องคลอดต้องบันทึกผ่านระบบ IPD/ห้องคลอดของ HOSxP"))
        return out, False
    age = (date.today() - date.fromisoformat(str(last)[:10])).days
    out.append(("ok" if age <= STALE_DAYS else "warn", "การคลอดล่าสุด",
                f"{last}" + ("" if age <= STALE_DAYS else f" ({age} วันก่อน) — ใช่ฐานข้อมูลที่ใช้งานจริงหรือไม่")))
    return out, True


def _audit(days, cfg):
    import audit as lr_audit
    import loader
    d2 = date.today()
    d1 = d2 - timedelta(days=days - 1)
    try:
        items = lr_audit.audit(d1, d2, cfg)
        comp = lr_audit.completeness(loader.load_data(d1, d2, cfg), cfg)
    except Exception as e:                                       # noqa: BLE001
        return [("bad", "Data Audit", f"ตรวจไม่สำเร็จ: {type(e).__name__}")]
    # ปัญหาข้อมูลเป็น ⚠ (รายละเอียดและวิธีแก้อยู่ที่หน้า /check)
    soft = lambda s: "warn" if s == "bad" else s
    out = [(soft(i["status"]), f"Data Audit: {i['title']}", i["hint"]) for i in items]
    out += [("ok" if x["n"] == 0 else "warn", f"ความครบ: {x['title']}", f"{x['n']}/{x['den']}") for x in comp]
    return out


def run(fetch=None, cfg=None, audit=True, days=90):
    """รายการผลตรวจ [(status, หัวข้อ, รายละเอียด)] · status = ok / warn / bad / info"""
    from config import load_config
    if fetch is None:
        from db import fetch
    cfg = cfg or load_config()
    out = _env_checks()
    out += _list_check()
    db_out, db_ok = _db_checks(fetch)
    out += db_out
    if db_ok and audit:
        out += _audit(days, cfg)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=90, help="ตรวจข้อมูลย้อนหลังกี่วัน (ค่าเริ่มต้น 90, สูงสุด 366)")
    ap.add_argument("--no-audit", action="store_true", help="ข้าม Data Audit")
    args = ap.parse_args()
    print(f"LR Dashboard — ตรวจความพร้อม · {datetime.now():%Y-%m-%d %H:%M} · {platform.platform()}")
    rows = run(audit=not args.no_audit, days=min(366, max(1, args.days)))
    for status, title, detail in rows:
        print(f"  {dict(ok='✔', warn='⚠', bad='✘', info='·')[status]} {title} — {detail}")
    n = {s: sum(1 for x, _, _ in rows if x == s) for s in ("ok", "warn", "bad")}
    print(f"\nสรุป: ✔ {n['ok']} ผ่าน · ⚠ {n['warn']} ควรตรวจ · ✘ {n['bad']} ต้องแก้")
    if n["bad"]:
        print("ยังไม่พร้อมใช้งาน — แก้ข้อ ✘ แล้วรันใหม่")
    elif n["warn"]:
        print("ใช้งานได้ แต่ตัวเลขบางส่วนอาจคลาดเคลื่อน — ตรวจข้อ ⚠ และหน้า /check ก่อนใช้จริง")
    else:
        print("พร้อมใช้งาน — เทียบตัวเลขกับรายงานห้องคลอดเดิม 1–2 สัปดาห์ แล้วตั้ง LR_DATA_AUDITED=1")
    return 1 if n["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
