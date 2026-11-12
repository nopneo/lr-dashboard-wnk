# ความปลอดภัย — LR Dashboard

| เรื่อง | มาตรการ |
|---|---|
| ข้อมูลส่วนบุคคล | หน้าภาพรวม, `/yearly`, ไฟล์ส่งออก JPG/PNG/PDF และหน้า `/check` แสดงเฉพาะจำนวนนับ ไม่มี HN / ชื่อ / เลขบัตร / AN — ข้อมูลผู้ป่วยต้องไม่ออกนอกเครือข่ายโรงพยาบาล |
| หน้ารายชื่อ `/list` | มีชื่อ/HN/AN — ต้อง login บัญชีรายคน (pbkdf2:sha256) · ล็อกเมื่อรหัสผิด 10 ครั้ง/ชื่อ หรือ 30 ครั้ง/IP ใน 15 นาที · CSRF · cookie `lr_session` HttpOnly/SameSite=Lax (+Secure เมื่อ `LR_COOKIE_SECURE=1`) · session 8 ชม. · `Cache-Control: no-store` · audit log ทุกการ login/เปิดดู (`python manage.py audit`) · ไม่ตั้ง `LR_SECRET_KEY` = ปิดทั้งหมด · `LR_LIST_LAN_ONLY=1` = เฉพาะใน รพ. |
| หน้า `/check` | เปิดเฉพาะเครื่องใน LAN (IP ภายใน หรือ `LR_LAN_NETS`) · ผ่าน Cloudflare ต้องเป็น IP ใน `LR_LAN_NETS` · `LR_CHECK_OPEN=1` เปิดทุกที่ (ไม่แนะนำ) |
| SQL | ช่วงวันที่ต้องเป็นวันที่จริง (ช่วงเองสูงสุด 400 วัน) · รหัสทุกตัวส่งเป็นพารามิเตอร์ ไม่มีรหัสตายตัวใน SQL |
| ฐานข้อมูล | บัญชีอ่านอย่างเดียว + `SET SESSION TRANSACTION READ ONLY` + timeout (`LR_DB_TIMEOUT`) · `setup_check.py` ขึ้น ✘ ถ้าบัญชีมีสิทธิ์เขียนบนฐาน HOSxP |
| ภาระฐานข้อมูล | แคชผลคำนวณ `LR_CACHE_TTL` (300 วินาที) |
| ส่งออกไฟล์ | ทีละงานทั้งเครื่อง · chromium เปิดได้เฉพาะ `127.0.0.1` · ปิดได้ด้วย `LR_EXPORT=0` |
| Header | nosniff, Referrer-Policy, X-Frame-Options, CSP (โหลดได้เฉพาะจากเว็บตัวเอง) · `X-Forwarded-Prefix` รับเฉพาะ path ภายใน |
| ความลับ | รหัสฐานข้อมูลและ `LR_SECRET_KEY` อยู่ใน `.env` (chmod 600/640) · บัญชีผู้ใช้ใน `data/` — ไม่อยู่ใน repo/zip/image |

รายงานช่องโหว่: แจ้งผู้พัฒนาโดยตรง (ช่องทางท้ายหน้าแดชบอร์ด) ไม่เปิดเป็น issue สาธารณะ
