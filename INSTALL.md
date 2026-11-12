# ติดตั้ง LR Dashboard สำหรับโรงพยาบาลที่ใช้ HOSxP

แดชบอร์ดงานห้องคลอดแบบเว็บ (Flask) อ่านข้อมูลสดจากฐานข้อมูล HOSxP (MariaDB/MySQL) **อ่านอย่างเดียว**
นิยามตัวชี้วัดดู [README.md](README.md)

**ขั้นตอนโดยย่อ:** ติดตั้ง (ข้อ 2 หรือ 3) → ใส่ค่าฐานข้อมูลใน `.env` → **`python setup_check.py`**
→ เปิดหน้า **`/check`** จากเครื่องในโรงพยาบาล → ตั้งรหัส `LR_*` ตามที่หน้านั้นแจ้ง (ข้อ 5)
→ เทียบตัวเลขกับรายงานห้องคลอดเดิม 1–2 สัปดาห์ → `LR_DATA_AUDITED=1`

## 0. ก่อนนำไปใช้ — อ่านก่อนติดตั้ง

โปรแกรมนี้แจกฟรีจากโรงพยาบาลวังน้ำเขียว ทดสอบกับข้อมูลจริงของ รพ.วังน้ำเขียว (คลอดปีละราว 80 ราย ไม่มีผ่าท้อง/คีม/สุญญากาศใน รพ.)
แต่ **HOSxP ของแต่ละโรงพยาบาลบันทึกและตั้งรหัสไม่เหมือนกัน** (รหัส Dx คลอดปกติ รหัสหัตถการ ความหมายของ
`infant_dchstts` / `infant_delivery_type_id` รายการ lab VDRL/Anti-HIV/HBsAg/Amphetamine การบันทึกทารกใน `ipt_labour_infant` …)
ถ้าไม่ตรง แดชบอร์ดยังแสดงตัวเลขได้ตามปกติ **แต่ตัวเลขจะเพี้ยนจากความจริงโดยไม่มีข้อความเตือน**
ผู้ที่นำไปใช้จึงต้องตรวจข้อมูลของตัวเองก่อนนำตัวเลขไปรายงานหรือตัดสินใจ

| # | ทำอะไร | เครื่องมือ |
|---|---|---|
| 1 | ตรวจสภาพแวดล้อม: Python ไลบรารี เขตเวลา Chrome การเชื่อมต่อฐานข้อมูล สิทธิ์อ่านอย่างเดียว ตารางที่ต้องใช้ ภาษาไทย การคลอดล่าสุด | `python setup_check.py` |
| 2 | Data Audit: รหัสที่แอปใช้ เทียบกับรหัสและจำนวนในข้อมูลจริง + ค่า `LR_*` ที่ควรตั้ง · **กระทบยอดจำนวนคลอด 4 แหล่ง** · ความครบของข้อมูลทารก/Apgar | หน้า **`/check`** (ข้อ 5) |
| 3 | ทดลองใช้คู่กับรายงานเดิมของห้องคลอด **อย่างน้อย 1–2 สัปดาห์** — เทียบจำนวนคลอด คลอดปกติ/ผิดปกติ เด็กเกิดมีชีพ และยอดส่งต่อ | แดชบอร์ด + รายงานเดิม |
| 4 | ตรวจแล้วตัวเลขตรง → ตั้ง `LR_DATA_AUDITED=1` (ซ่อนแถบเตือน “ตัวเลขยังไม่ได้ตรวจกับข้อมูลของโรงพยาบาลนี้”) | `.env` |

**เงื่อนไขการใช้:** สัญญาอนุญาต MIT ([LICENSE](LICENSE)) — ใช้ แก้ไข แจกต่อได้ โดยคงข้อความลิขสิทธิ์ไว้ ·
โปรแกรมให้ “ตามสภาพ” **ไม่มีการรับประกัน** ความถูกต้องของตัวเลขในโรงพยาบาลของท่าน เป็นความรับผิดชอบของผู้นำไปใช้ (ข้อ 1–4) ·
ส่วนประกอบของผู้อื่นดู [NOTICE.md](NOTICE.md)

**แจ้งปัญหา:** รัน `python setup_check.py` แล้วแก้ข้อ ✘ ก่อน — ถ้ายังไม่หาย แจ้งผู้พัฒนา (ช่องทางท้ายหน้าแดชบอร์ด)
หรือเปิด issue ของ repo นี้ตามแบบฟอร์ม พร้อมผลของ `setup_check.py` และเวอร์ชันที่ใช้ —
**ห้ามแนบข้อมูลผู้ป่วย** (HN ชื่อ เลขบัตร) หรือรหัสผ่าน

## 1. สิ่งที่ต้องมี

- เครื่องที่ต่อถึงฐานข้อมูล HOSxP ได้ (แนะนำ Slave/Replica)
- Python 3.10 ขึ้นไป · Chrome/Edge/Chromium ถ้าจะใช้ปุ่มส่งออก JPG/PDF
- บัญชีฐานข้อมูล **SELECT อย่างเดียว** (แอปตั้ง session เป็น READ ONLY ให้อีกชั้น)
- งานห้องคลอดบันทึกผ่านระบบ IPD/ห้องคลอดของ HOSxP (`ipt_pregnancy`, `ipt_labour`, `ipt_labour_infant`)

```sql
CREATE USER 'lr_ro'@'<ip เครื่องแอป>' IDENTIFIED BY '<รหัสผ่านยาว>';
GRANT SELECT ON hos.* TO 'lr_ro'@'<ip เครื่องแอป>';
```

## 2. ติดตั้งบน Linux

```bash
sudo mkdir -p /opt/lr_dashboard && sudo cp -r . /opt/lr_dashboard && cd /opt/lr_dashboard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env      # แล้วแก้ DB_HOST / DB_USER / DB_PASS
.venv/bin/python setup_check.py
```

`/etc/systemd/system/lr-dashboard.service`

```ini
[Unit]
Description=LR Dashboard
After=network.target
[Service]
WorkingDirectory=/opt/lr_dashboard
EnvironmentFile=/opt/lr_dashboard/.env
ExecStart=/opt/lr_dashboard/.venv/bin/gunicorn --bind 0.0.0.0:5400 --workers 2 --threads 8 --timeout 120 app:app
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now lr-dashboard && curl -s localhost:5400/healthz    # ต้องได้ ok
```

แก้ `.env` บน production: `cp -p .env .env.bak` → แก้ → `chown/chmod --reference=.env.bak .env` → restart → ตรวจ `/healthz`
(`sed -i` ทำให้เจ้าของไฟล์เปลี่ยน แอปอ่านไม่ได้แล้วล่ม)

## 3. ติดตั้งบน Windows

`py -m venv .venv` → `.venv\Scripts\pip install -r requirements.txt` → คัดลอก `.env.example` เป็น `.env` →
`.venv\Scripts\python setup_check.py` → รันด้วย `.venv\Scripts\waitress-serve --port=5400 app:app`
(ตั้งเป็น Windows Service ด้วย NSSM หรือ Task Scheduler)

## 4. ตั้งค่า (.env)

ดูคำอธิบายทุกค่าใน [.env.example](.env.example) — ค่าที่ต้องมี: `DB_HOST DB_NAME DB_USER DB_PASS`

### หน้ารายชื่อ (ไม่บังคับ — มีข้อมูลผู้ป่วย)

1. สร้างกุญแจ: `python -c "import secrets; print(secrets.token_hex(32))"` ใส่ `LR_SECRET_KEY` (ไม่ตั้ง = ปิดหน้ารายชื่อทั้งหมด)
2. สร้างบัญชีรายคน: `python manage.py adduser <ชื่อ> --display "ชื่อที่แสดง"`
3. ดูประวัติการเปิดดู (PDPA): `python manage.py audit` · แนะนำ `LR_LIST_LAN_ONLY=1`

## 5. ปรับให้ตรงกับข้อมูลของโรงพยาบาล (หน้า `/check`)

เปิด `http://<เครื่องแอป>:5400/check` จากเครื่องในโรงพยาบาล (ผ่านอินเทอร์เน็ตเปิดไม่ได้ ยกเว้นตั้ง `LR_CHECK_OPEN=1`)

| รายการ | ดูอะไร | ถ้าไม่ตรงทำอะไร |
|---|---|---|
| **กระทบยอดจำนวนการคลอด** | ยอดจาก `ipt_pregnancy` เทียบ `ipt_labour_infant` · `labor` · ICD O80–O84 | ส่วนต่างมาก → หาสาเหตุก่อนใช้ตัวเลข (แถวรอคลอด/แท้ง/ไม่มีบันทึกทารก) · ปรับ `LR_DELIVERY_ICD10` |
| Dx ที่พบในการคลอด | รหัสคลอดปกติ (O80) ตรงกับที่ รพ. ใช้หรือไม่ | ตั้ง `LR_NORMAL_ICD` |
| หัตถการระหว่างคลอด | รหัสผ่าท้อง/คีม/สุญญากาศ/ท่าก้น | ตั้ง `LR_CS_ICD9` ฯลฯ (รพ.ที่ไม่ทำจะเป็น 0 — ถูกต้อง) |
| สถานะจำหน่ายทารก / ประเภทการคลอดของทารก | รหัสเสียชีวิต (`LR_DEAD_DCHSTTS`) และ BBA (`LR_BBA_TYPES`) | ตรวจความหมายของรหัสใน รพ. |
| ผลแล็บตอนคลอด | VDRL/Anti-HIV/HBsAg ใน `ipt_labour_lab` และผลพิมพ์มือที่จับไม่ได้ (“ไม่ชัด”) | ตั้ง `LR_LAB_SYPHILIS/HIV/HBV` |
| Amphetamine | รายการ lab ที่ชื่อคล้ายและจำนวนที่ส่งตรวจ | ตั้ง `LR_LAB_AMPH` |
| สุรา/บุหรี่ของมารดา | ไม่มีแหล่งในฐาน → “ไม่มีข้อมูล” | บันทึกในระบบแล้วแจ้งผู้พัฒนาเพื่อเพิ่มแหล่ง |

แก้ `.env` แล้ว restart บริการ แล้วเปิด `/check` ซ้ำ จนไม่มีรายการ ⚠ ที่ไม่เข้าใจ

## 6. เปิดผ่าน reverse proxy (sub-path)

แอปรองรับ `X-Forwarded-Prefix` / `X-Forwarded-Proto` — Apache ตัวอย่าง (แทรกก่อนบรรทัด catch-all `ProxyPass /`):

```apache
RequestHeader set X-Forwarded-Prefix "/lr"
ProxyPass        /lr/ http://127.0.0.1:5400/
ProxyPassReverse /lr/ http://127.0.0.1:5400/
```

แก้ `ssl.conf` ทุกครั้ง: `cp` เก็บ backup → `httpd -t` → ผ่านค่อย `systemctl reload httpd` (ไม่ผ่านให้คืน backup ทันที)

## 7. Docker

```bash
docker build -t lr-dashboard .                       # ไม่มี chromium (ปุ่มส่งออกปิด)
docker build --target export -t lr-dashboard-export .  # มี chromium
docker run -p 8080:8080 --env-file .env lr-dashboard
docker exec <ชื่อ container> python setup_check.py
```
