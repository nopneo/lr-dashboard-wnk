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
- Python 3.9 ขึ้นไป · Chrome/Edge/Chromium ถ้าจะใช้ปุ่มส่งออก JPG/PDF
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
# ไม่ใช้ root: ผู้ใช้ของแอปเอง (useradd -r -s /sbin/nologin lr) · เขียนได้เฉพาะ data/ (ฐาน login + audit log)
# ไม่ใช่ root แล้ว chromium (ปุ่มส่งออก) เปิด sandbox ของตัวเองได้
User=lr
Group=lr
WorkingDirectory=/opt/lr_dashboard
EnvironmentFile=/opt/lr_dashboard/.env
Environment=HOME=/var/lib/lr
StateDirectory=lr
# ฟังเฉพาะ 127.0.0.1 หลัง Apache — ห้าม 0.0.0.0 (เครื่องใน LAN จะ login ผ่าน http ตรงโดยไม่เข้ารหัส)
ExecStart=/opt/lr_dashboard/.venv/bin/gunicorn --bind 127.0.0.1:5400 --workers 2 --threads 8 --timeout 120 app:app
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/lr_dashboard/data
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
CapabilityBoundingSet=
[Install]
WantedBy=multi-user.target
```

สิทธิ์ไฟล์: `chown root:lr .env && chmod 640 .env` · `chown -R lr:lr data && chmod 700 data` (ไฟล์ใน data/ เป็น 600)

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
3. ดูประวัติการเปิดดู (PDPA): `python manage.py audit`
4. **หน้ารายชื่อเปิดได้เฉพาะเครื่องใน รพ. เป็นค่าเริ่มต้น** (ข้อมูลผู้ป่วยต้องไม่ออกอินเทอร์เน็ต) — แอปรู้ว่าเครื่องไหน “อยู่ใน รพ.” ดังนี้
   - เข้าตรงหรือผ่าน proxy ใน รพ.: ที่อยู่ส่วนตัวตาม RFC1918 (`192.168.x.x`, `10.x.x.x`, `172.16–31.x.x`) นับเป็น LAN อยู่แล้ว **ไม่ต้องตั้งค่า**
   - เข้าผ่าน Cloudflare: นับเฉพาะ IP ใน `LR_LAN_NETS` — ใส่ **IP สาธารณะจริงของ รพ.** (IP คงที่ที่เครื่องใน รพ. ออกอินเทอร์เน็ต เช่น `LR_LAN_NETS=203.0.113.10`)
     ถ้า รพ. ใช้วง IP ภายในที่ไม่ใช่ RFC1918 ให้ใส่วงนั้นเพิ่ม (หลายค่าคั่นด้วยจุลภาค)
   - **ห้ามใส่ IP บ้าน/มือถือ** — IP แบบนี้เปลี่ยนเรื่อย ๆ ถ้า ISP เอาไปให้คนอื่น คนนั้นจะถูกนับเป็นคนใน รพ. ทันที
     ทดสอบจากนอก รพ. ให้ login แทน (login แล้วเห็นตัวเลขจริงและรายชื่อได้) — ต้องตั้ง `LR_LIST_LAN_ONLY=0` ด้วย ไม่งั้นหน้า login เองก็เปิดจากนอก รพ. ไม่ได้ (403)
   - **แนะนำ: ทางเข้าภายในด้วยโดเมนย่อยที่ชี้ IP ภายใน** (ข้อ 6.1) — เจ้าหน้าที่เปิดหน้ารายชื่อผ่านทางนี้ แอปเห็น IP จริงของเครื่อง (`192.168.x.x`)
     จึงไม่ต้องพึ่ง `LR_LAN_NETS` และคนนอกเข้าไม่ถึงตั้งแต่ระดับเครือข่าย (ใช้จากนอก รพ. ต้องผ่าน VPN ของ รพ.)
5. ใช้ HTTPS ผ่าน proxy → ตั้ง `LR_COOKIE_SECURE=1`

## 5. ปรับให้ตรงกับข้อมูลของโรงพยาบาล (หน้า `/check`)

เปิด `http://<เครื่องแอป>:5400/check` จากเครื่องในโรงพยาบาล (เครื่องที่ใช้ IP ส่วนตัวเช่น `192.168.x.x` เปิดได้เลย · ผ่าน Cloudflare ต้องใส่ IP สาธารณะจริงของ รพ. ใน `LR_LAN_NETS` · ผ่านอินเทอร์เน็ตจากที่อื่นเปิดไม่ได้ ยกเว้นตั้ง `LR_CHECK_OPEN=1`)

| รายการ | ดูอะไร | ถ้าไม่ตรงทำอะไร |
|---|---|---|
| **กระทบยอดจำนวนการคลอด** | ยอดจาก `ipt_pregnancy` เทียบ `ipt_labour_infant` · `labor` · ICD O80–O84 | ส่วนต่างมาก → หาสาเหตุก่อนใช้ตัวเลข (แถวรอคลอด/แท้ง/ไม่มีบันทึกทารก) · ปรับ `LR_DELIVERY_ICD10` |
| Dx ที่พบในการคลอด | รหัสคลอดปกติ (O80) ตรงกับที่ รพ. ใช้หรือไม่ | ตั้ง `LR_NORMAL_ICD` |
| หัตถการระหว่างคลอด | รหัสผ่าท้อง/คีม/สุญญากาศ/ท่าก้น | ตั้ง `LR_CS_ICD9` ฯลฯ (รพ.ที่ไม่ทำจะเป็น 0 — ถูกต้อง) |
| สถานะจำหน่ายทารก / ประเภทการคลอดของทารก | รหัสเสียชีวิต (`LR_DEAD_DCHSTTS`) และ BBA (`LR_BBA_TYPES`) | ตรวจความหมายของรหัสใน รพ. |
| ผลแล็บตอนคลอด | VDRL/Anti-HIV/HBsAg ใน `ipt_labour_lab` และผลพิมพ์มือที่จับไม่ได้ (“ไม่ชัด”) | ตั้ง `LR_LAB_SYPHILIS/HIV/HBV` |
| ผล lab ตลอดการตั้งครรภ์ | รายการ lab ที่เลือกจากชื่อ (VDRL/TPHA, Anti-HIV, HBsAg, Methamphetamine) และจำนวนมารดาที่ตรวจ | ตั้ง `LR_LAB_SYPHILIS_ITEMS` / `LR_LAB_HIV_ITEMS` / `LR_LAB_HBV_ITEMS` / `LR_LAB_AMPH` |
| Amphetamine | รายการ lab ที่ชื่อคล้ายและจำนวนที่ส่งตรวจ | ตั้ง `LR_LAB_AMPH` |
| สุรา/ยาเสพติดของมารดา | ข้อ 17 ของแบบคัดกรองครรภ์เสี่ยง ANC และจำนวนมารดาที่จับคู่ทะเบียนได้ (ไม่รวมบุหรี่ — ไม่มีแหล่งในฐาน) | ตั้ง `LR_SUBSTANCE_FORM_ITEMS` ให้ตรงกับข้อใน `person_anc_classifying_item` |

แก้ `.env` แล้ว restart บริการ แล้วเปิด `/check` ซ้ำ จนไม่มีรายการ ⚠ ที่ไม่เข้าใจ

## 6. เปิดผ่าน reverse proxy (sub-path)

แอปรองรับ `X-Forwarded-Prefix` / `X-Forwarded-Proto` — Apache ตัวอย่าง (แทรกก่อนบรรทัด catch-all `ProxyPass /`):

```apache
RequestHeader set X-Forwarded-Prefix "/lr"
ProxyPass        /lr/ http://127.0.0.1:5400/
ProxyPassReverse /lr/ http://127.0.0.1:5400/
```

แก้ `ssl.conf` ทุกครั้ง: `cp` เก็บ backup → `httpd -t` → ผ่านค่อย `systemctl reload httpd` (ไม่ผ่านให้คืน backup ทันที)

### 6.1 ทางเข้าภายใน รพ. (โดเมนย่อยที่ชี้ IP ภายใน — แนะนำสำหรับหน้ารายชื่อ)

ทางสาธารณะ (เช่น `https://<โดเมน รพ.>/lr/` ผ่าน Cloudflare) ให้คนนอกเห็นเฉพาะตัวเลขรวม · ทางเข้าภายในเป็นโดเมนย่อยอีกชื่อที่ DNS ชี้ไป **IP ภายใน** ของเครื่องแอป
เบราว์เซอร์ในโรงพยาบาลจึงต่อตรงถึงเครื่องแอป ไม่ผ่าน Cloudflare/อินเทอร์เน็ต — Apache ส่ง IP จริงของเครื่องเจ้าหน้าที่ (`192.168.x.x`) ต่อให้แอป
แอปนับเป็นเครื่องใน รพ. เอง (เห็นตัวเลขเต็มและหน้ารายชื่อหลัง login) และจากอินเทอร์เน็ตเปิดไม่ได้เพราะ IP ภายในใช้จากข้างนอกไม่ได้

**ตัวอย่าง รพ.วังน้ำเขียว:** `https://lan.wnkhos.go.th/lr/` (DNS → `192.168.11.40`) · หน้าแรก `https://lan.wnkhos.go.th/` มีลิงก์ระบบภายในทุกตัว

1. **DNS:** เพิ่ม A record เช่น `lan` → IP ภายในของเครื่องแอป · ใน Cloudflare ต้องเป็น **DNS only (เมฆสีเทา)** — เปิด proxy (เมฆสีส้ม) แล้วใช้ไม่ได้
   (resolver/เราเตอร์บางรุ่นมี DNS rebinding protection ที่ไม่ตอบ IP ภายใน — ทดสอบจากเครื่องใน รพ. ทั้ง DNS ของ ISP และ 8.8.8.8)
2. **ใบรับรอง:** Let's Encrypt แบบ HTTP-01 ออกให้ไม่ได้ (ข้างนอกเข้าถึง IP ภายในไม่ได้) — ใช้ DNS-01 ผ่าน Cloudflare (ฟรี ต่ออายุอัตโนมัติ):
   ```bash
   dnf install certbot python3-certbot-dns-cloudflare        # หรือ apt install python3-certbot-dns-cloudflare
   # /root/.secrets/cloudflare.ini (chmod 600): dns_cloudflare_api_token = <token สิทธิ์ Zone:DNS:Edit เฉพาะโดเมนนี้>
   certbot certonly --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/cloudflare.ini -d lan.<โดเมน รพ.>
   ```
3. **Apache:** vhost แยก (เช่น `/etc/httpd/conf.d/zz-lan-443.conf`) จำกัดให้เฉพาะ IP ภายใน แล้วส่งต่อแบบเดียวกับข้อ 6:
   ```apache
   <VirtualHost *:443>
       ServerName lan.<โดเมน รพ.>
       SSLEngine on
       SSLCertificateFile    /etc/letsencrypt/live/lan.<โดเมน รพ.>/fullchain.pem
       SSLCertificateKeyFile /etc/letsencrypt/live/lan.<โดเมน รพ.>/privkey.pem
       <Location />
           Require ip 192.168.0.0/16 10.0.0.0/8 172.16.0.0/12 127.0.0.1
       </Location>
       ProxyPreserveHost On
       RequestHeader set X-Forwarded-Proto "https"
       ProxyPass        /lr/ http://127.0.0.1:5400/
       ProxyPassReverse /lr/ http://127.0.0.1:5400/
       <Location /lr/>
           RequestHeader set X-Forwarded-Prefix /lr
       </Location>
       RedirectMatch ^/lr$ /lr/
   </VirtualHost>
   ```
   `httpd -t` ผ่านแล้วค่อย `systemctl reload httpd`
4. **`.env`:** คง `LR_LIST_LAN_ONLY=1` · `LR_LAN_NETS` เหลือเฉพาะ IP สาธารณะจริงของ รพ. (ถ้ายังให้เปิดผ่าน Cloudflare จากใน รพ. ได้) หรือเว้นว่าง · ตั้ง `LR_COOKIE_SECURE=1`
5. **ทดสอบ:** จากเครื่องใน รพ. เปิด `https://lan.<โดเมน รพ.>/lr/` แล้วต้องไม่มีแถบ 🔒 "ข้อมูลสาธารณะ" และเปิดหน้า login ได้ ·
   จากมือถือที่ใช้เน็ตมือถือ (ปิด Wi-Fi/VPN) ต้องเปิดไม่ได้ · ใช้จากนอก รพ. ให้ต่อ VPN ของ รพ. (ห้ามเพิ่ม IP บ้านใน `LR_LAN_NETS`)

## 7. Docker

```bash
docker build -t lr-dashboard .                       # ไม่มี chromium (ปุ่มส่งออกปิด)
docker build --target export -t lr-dashboard-export .  # มี chromium
docker run -p 8080:8080 --env-file .env lr-dashboard
docker exec <ชื่อ container> python setup_check.py
```
