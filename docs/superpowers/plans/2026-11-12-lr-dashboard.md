# LR Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แอป Flask อ่านอย่างเดียว แสดงตัวชี้วัดห้องคลอด รพ.วังน้ำเขียว (หน้าหลัก + ตารางรายปี 13 แถว + Data Audit) จาก HOSxP

**Architecture:** โครงเดียวกับ `E:\App\Hos 212\ANC_dashboard` — `queries.py` (SQL ล้วน รับรหัสจาก config) → `loader.py` (รวมผล) → `metrics.py` (ฟังก์ชันบริสุทธิ์ ทดสอบโดยไม่ต่อฐาน) → `app.py` + templates · `audit.py` ใช้ queries ชุดเดียวกันกับหน้าหลัก ไฟล์กลาง (`cache.py`, `db.py`, `store.py`, `manage.py`, `render.py`, ส่วน PrefixMiddleware/login/CSRF ของ `app.py`) **คัดลอกจาก ANC แล้วเปลี่ยน prefix `ANC_`→`LR_`** ไม่เขียนใหม่

**Tech Stack:** Python 3 · Flask ≥3.1.1 · PyMySQL · python-dotenv · Pillow · openpyxl · pytest · gunicorn/waitress (requirements.txt คัดจาก ANC)

**Spec:** `docs/superpowers/specs/2026-11-12-lr-dashboard-design.md`

## Global Constraints

- ปีงบประมาณ = 1 ต.ค.–30 ก.ย. แสดงเป็น พ.ศ. · ปีงบปัจจุบัน = 2570 (เริ่ม 2026-10-01)
- **ห้ามเขียนรหัสตายตัวใน SQL** — ทุกรหัสมาจาก `Config` (env prefix `LR_`) ส่งเป็นพารามิเตอร์ · `%` ตัวอักษรใน SQL เขียน `%%` (ตามกติกา `db.py`)
- ฐาน HOSxP เก็บ tis-620 · session อ่านอย่างเดียว (`SET SESSION TRANSACTION READ ONLY`)
- หน้าหลัก/ส่งออก = **จำนวนนับเท่านั้น** ไม่มีข้อมูลรายคน · `/check` เปิดเฉพาะ LAN · รายชื่อหลัง login
- ตัวชี้วัดที่ไม่มีข้อมูลในฐาน = `None` แสดง "ไม่มีข้อมูล" **ห้ามแสดงเป็น 0**
- รหัสผ่านผู้ใช้ `generate_password_hash(pw, method="pbkdf2:sha256")` · ห้ามเก็บรหัสในไฟล์ · `.env` ไม่ลงชุดแจก
- แถบ "ตัวเลขยังไม่ได้ตรวจกับข้อมูลของโรงพยาบาลนี้" จนกว่า `LR_DATA_AUDITED=1` หรือกดยืนยันใน `/check` (localStorage) · ห้ามติดในไฟล์ส่งออก/โหมดพิมพ์
- ใช้ชื่อ/โลโก้ รพ.วังน้ำเขียว (ไม่ใช้ของ รพ. ใน mockup)
- ยอดคลอดรายปีงบฐานจริง 2565–2569 ต้องได้ **92 / 85 / 92 / 72 / 78**
- รัน test: `python -m pytest tests -q` (ที่ `E:\App\Hos 212\LR_dashboard`) · test ห้ามต่อฐานจริง

## Review Focus

ข้อที่ spec เงียบแต่มักพัง (แต่ละข้อมี test ใน task ที่ระบุ):

1. **ผลแล็บ "Non-reactive" มีคำว่า reactive อยู่ข้างใน** — ต้องเป็นลบ ไม่ใช่บวก (Task 3)
2. **Apgar เป็น NULL** — ต้องไม่ถูกนับเป็น ≤ 7 และไม่ทำ Python ล้ม (Task 3)
3. **แฝด** — แม่นับ 1 เด็กนับ 2 · ไม่นับซ้ำในตัวหารร้อยละ (Task 3)
4. **ช่วงที่ไม่มีการคลอด** (ปีงบเพิ่งเริ่ม มี 6 ราย / ช่วงว่าง) — ร้อยละหารศูนย์ต้องไม่ล้ม กราฟว่างแสดง "—" (Task 3, 5)
5. **แหล่งข้อมูลไม่ตรงกัน** (มีแถว `ipt_pregnancy` แต่ไม่มีเด็ก หรือกลับกัน; รายแท้งปนมา) — กระทบยอดต้องแสดงส่วนต่างตรง ๆ ไม่เลือกให้เงียบ ๆ (Task 4)
6. **คลอดวันที่ 30 ก.ย./1 ต.ค.** — ขอบปีงบ ช่วงวันที่ปิดหัวท้าย (Task 2)

## โครงสร้างไฟล์

```
LR_dashboard/
  config.py      Config (รหัสทั้งหมด) · load_config(env) · fy_range · fy_of · fy_options
  db.py cache.py                 คัดลอกจาก ANC (prefix LR_)
  queries.py     SQL → list[dict]
  loader.py      load_data(d1, d2, cfg) → dict (รวมผล queries)
  metrics.py     ฟังก์ชันบริสุทธิ์: kpi_rows, monthly, quality_grid, yearly_table, classify_result
  audit.py       audit(d1, d2, cfg) → list[item] · reconcile(d1, d2, cfg)
  app.py         routes + PrefixMiddleware + login/CSRF (คัดจาก ANC)
  store.py manage.py listing.py  ผู้ใช้/รายชื่อ (คัดจาก ANC)
  render.py      ส่งออก JPG/PDF (คัดจาก ANC)
  setup_check.py build_dist.py
  templates/ (dashboard yearly check list login) · static/style.css
  tests/ docs/ INSTALL.md README.md CHANGELOG.md SECURITY.md LICENSE NOTICE.md Dockerfile .env.example
  .github/ISSUE_TEMPLATE/bug_report.yml
```

(`loader.py` เพิ่มจากโครงใน spec เพื่อให้ `app.py` และ `audit.py` ใช้ชุดข้อมูลเดียวกัน — ANC เก็บไว้ใน app.py)

---

### Task 0: Scaffold + config

**Files:**
- Create: `config.py`, `db.py`, `cache.py`, `requirements.txt`, `.env.example`, `LICENSE`, `NOTICE.md`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_db.py`
- `db.py`/`cache.py`/`requirements.txt`/`LICENSE`/`NOTICE.md`: คัดจาก `ANC_dashboard` (เปลี่ยน `ANC_`→`LR_`)

**Interfaces:**
- Produces: `db.fetch(sql, args=None) -> list[dict]` · `db.fetch_one` · `db.num(v, default=0)` (ตาม ANC) · `cache.TTLCache`
- Produces: `config.Config` (frozen dataclass) ฟิลด์ ค่าเริ่มต้น และ env:

| field | default | env |
|---|---|---|
| `normal_icd` | `("O80",)` | `LR_NORMAL_ICD` |
| `cs_icd9` | `("74",)` (prefix) | `LR_CS_ICD9` |
| `forceps_icd9` / `forceps_icd10` | `("720","721","722","723","724")` / `("O810","O811","O812","O813")` | `LR_FORCEPS_ICD9/_ICD10` |
| `vacuum_icd9` / `vacuum_icd10` | `("727",)` / `("O814",)` | `LR_VACUUM_ICD9/_ICD10` |
| `breech_icd9` / `breech_icd10` | `("725",)` / `("O830","O831")` | `LR_BREECH_ICD9/_ICD10` |
| `stillbirth_icd10` | `("P95","Z371","Z373","Z374","Z376")` | `LR_STILLBIRTH_ICD10` |
| `dead_dchstts` | `("08","09")` | `LR_DEAD_DCHSTTS` |
| `bba_types` | `("3",)` | `LR_BBA_TYPES` |
| `apgar1_max` | `7` | `LR_APGAR1_MAX` |
| `asphyxia_apgar5` / `asphyxia_icd10` | `7` (Apgar5 < 7) / `("P21",)` | `LR_ASPHYXIA_APGAR5/_ICD10` |
| `lbw_grams` | `2500` | `LR_LBW_GRAMS` |
| `dx_pph` `dx_preterm` `dx_htn` `dx_prolonged` `dx_fetal_distress` `dx_prom` | `("O72",)` `("O60",)` `("O13","O14","O15","O16")` `("O63",)` `("O68",)` `("O42",)` | `LR_DX_*` |
| `syphilis_labs` `hiv_labs` `hbv_labs` `amph_labs` | `()` (ว่าง = เลือกจากชื่อ ดู Task 1 step 1) | `LR_LAB_SYPHILIS` ฯลฯ |
| `refer_dx_prefix` | `("O",)` | `LR_REFER_DX_PREFIX` |

- Produces: `load_config(env=os.environ) -> Config` · `fy_range(fy_be: int) -> tuple[date, date]` · `fy_of(d: date) -> int` (พ.ศ.) · `fy_options(today=None, n=6) -> list[int]` (ใหม่→เก่า)

- [ ] **Step 1:** `git init` ใน `LR_dashboard` (โฟลเดอร์ยังไม่เป็น repo · ไม่ตั้ง remote) · คัดไฟล์กลางจาก ANC แล้วแทน `ANC_`→`LR_` (`grep -n "ANC" db.py cache.py` ต้องไม่เหลือ)
- [ ] **Step 2: Write failing tests** `tests/test_config.py` — `fy_range(2570) == (date(2026,10,1), date(2027,9,30))` · `fy_range(2565) == (date(2021,10,1), date(2022,9,30))` · `fy_of(date(2026,9,30)) == 2569` · `fy_of(date(2026,10,1)) == 2570` · `fy_options(date(2026,11,12))[0] == 2570` · `load_config({}).normal_icd == ("O80",)` · `load_config({"LR_NORMAL_ICD": "o80, O81"}).normal_icd == ("O80","O81")` (trim + upper) · `load_config({"LR_APGAR1_MAX": "6"}).apgar1_max == 6`
  `tests/test_db.py` — `db.num("3") == 3` · `db.num(None) == 0` · `db.num("") == 0` · `db._bind("a in %(x)s", {"x": ("a","b")})` ได้ `"a in ('a','b')"`
- [ ] **Step 3: Run** `python -m pytest tests/test_config.py tests/test_db.py -q` → FAIL (`config` ไม่มี)
- [ ] **Step 4: Implement** `config.py` ตามตาราง (ใช้ helper `_list`, `_num` แบบ ANC `config.py`) · `tests/conftest.py` ตั้ง `LR_HOSPITAL_NAME="โรงพยาบาลทดสอบ"`, `LR_SECRET_KEY=""` และเพิ่ม repo root เข้า `sys.path`
- [ ] **Step 5: Run** ชุดเดียวกัน → PASS · `git add . && git commit -m "feat: scaffold, config, fiscal-year helpers"`

---

### Task 1: queries.py + บันทึก schema

**Files:**
- Create: `queries.py`, `docs/schema-notes.md`, `tests/test_queries.py`

**Interfaces:**
- Consumes: `db.fetch`, `config.Config`
- Produces (ทุกฟังก์ชัน `(d1: date, d2: date, cfg: Config) -> list[dict]` ช่วงปิดหัวท้าย `between d1 and d2`):
  - `deliveries` — คีย์ `an, labor_date, ym ('YYYY-MM'), twin (0/1), is_abort (0/1)` จาก `ipt_pregnancy`
  - `delivery_dx` — `an, icd10` (distinct ต่อ AN, ไม่มีจุด) จาก `iptdiag`
  - `delivery_ops` — `an, icd9` จาก `iptoprt`
  - `infants` — `ipt_labour_id, an, birth_date, ym, weight, apgar1, apgar5, dchstts, dead (bool), bba_type, labor_ba_id, infant_icd10, days_to_dch (int|None)` (นิยาม dead ตาม spec แถว 6; `days_to_dch = datediff(ipt.dchdate, birth_date)` ผ่าน `infant_an`)
  - `lab_results` — `an, lab_key ('syphilis'|'hiv'|'hbv'|'amph'), result` (text ดิบ)
  - `lr_refers` — `ym, n` จำนวนส่งต่อที่มี Dx ขึ้นต้นด้วย `cfg.refer_dx_prefix` (นิยามละเอียดยืนยันใน Task 6)
  - `recent_counts(today: date, cfg) -> dict` — `{"days7": int}` จำนวนคลอด 7 วันล่าสุด

- [ ] **Step 1: ตรวจ schema (read-only, นับ/คอลัมน์เท่านั้น)** ด้วย `hosdb` (สกิล `hosxp-db`): คอลัมน์ของ `ipt_labour_lab`, `labour_lab`, `ipt_newborn`, `referout`, `iptoprt` · เก็บชื่อคอลัมน์ที่ใช้จริงและวิธีจับคู่ผลแล็บใน `docs/schema-notes.md` (ห้ามมีข้อมูลรายคน) · ถ้า `ipt_labour_lab` จับ VDRL/Anti-HIV/HBsAg ด้วยรหัส `labour_lab` ให้ตั้งค่าเริ่มต้นของ `*_labs` ใน `config.py` ให้เป็นรหัสนั้น
- [ ] **Step 2: Write failing test** `tests/test_queries.py` โดย monkeypatch `db.fetch` ให้เก็บ `(sql, args)`: ทุกฟังก์ชัน (a) ส่ง `d1`,`d2` ใน args (b) **ไม่มีรหัส Dx/ICD ตัวอักษรใน sql** — ค้น regex `r"'[OPZ]\d{2}"` และ `r"'\d{2}'"` ต้องไม่เจอ (c) `infants(...)` ส่ง `cfg.dead_dchstts` และ `cfg.bba_types` เป็นสมาชิกใน args · `deliveries` สร้าง sql ที่กรอง `is_abort = 0` ได้ด้วย args (ไม่ใช่ตัวอักษรใน sql)
- [ ] **Step 3: Run** `python -m pytest tests/test_queries.py -q` → FAIL
- [ ] **Step 4: Implement** `queries.py` ตาม Interfaces · ใช้ `ipt_pregnancy.labor_date` เป็นวันของการคลอด · `ym` = `date_format(..., '%%Y-%%m')`
- [ ] **Step 5: Run** → PASS · commit `feat: queries`

---

### Task 2: loader + ตัวนับ 13 แถว (metrics แกนกลาง)

**Files:**
- Create: `loader.py`, `metrics.py`, `tests/test_metrics.py`, `tests/test_loader.py`

**Interfaces:**
- Consumes: ฟังก์ชันของ Task 1
- Produces: `loader.load_data(d1, d2, cfg) -> dict` คีย์ `deliveries, dx_by_an (dict[str, set[str]]), ops_by_an (dict[str, set[str]]), infants, labs, refers` (แต่ละแหล่งถูกห่อด้วย try → ล้มแหล่งไหนได้ `[]` + ใส่ชื่อใน `data["errors"]` แล้วหน้าเว็บขึ้นเตือน)
- Produces: `metrics.KPI_KEYS` ลำดับตาม spec §4: `("mothers","normal","abnormal","cs","forceps","vacuum","breech","twins","bba","babies","live","still","neo_death7","apgar1_low","amph","alcohol_smoke","syphilis","hiv","hbv")`
- Produces: `metrics.kpi_rows(data: dict, cfg: Config) -> list[dict]` แต่ละแถว `{"key","label","value": int|None,"status":"ok"|"nodata"}` · `mothers` นับ `deliveries` ที่ `is_abort==0` · `normal` = AN ที่มี Dx ใน `cfg.normal_icd` และไม่มี Dx ภาวะแทรกซ้อน/ไม่มีหัตถการ cs/forceps/vacuum/breech · `abnormal = mothers - normal` · `twins` นับแม่ (`twin==1` หรือเด็ก ≥2 ต่อ `ipt_labour_id`) · `babies = len(infants)` · `still` จาก Dx `cfg.stillbirth_icd10` · `live = babies - still` · `apgar1_low` นับ `apgar1 is not None and apgar1 <= cfg.apgar1_max` · `alcohol_smoke` = `value None, status "nodata"` จนกว่า Task 6 จะพบแหล่ง
- Produces: `metrics.pct(n, d) -> float | None` (`None` เมื่อ `d` เป็น 0/None)

- [ ] **Step 1: Write failing tests** (`tests/test_metrics.py`, ข้อมูลจำลองเป็น dict ล้วน):
  - 3 การคลอด: AN a (Dx O80), b (Dx O80+O72), c (Dx O80 + ops 727) → `mothers==3`, `normal==1`, `abnormal==2`, `vacuum==1`
  - แท้ง 1 แถว (`is_abort=1`) → ไม่เข้า `mothers`
  - **ขอบปีงบ:** `deliveries` ที่ `labor_date` = `date(2026,9,30)` และ `date(2026,10,1)` → `fy_of` ต่างกัน และ `kpi_rows` ของช่วง `fy_range(2569)` นับเฉพาะอันแรก (ทดสอบที่ `test_loader.py` ว่า `load_data` ส่ง d1/d2 ปิดหัวท้ายไปที่ queries)
  - `pct(1, 0) is None` · `pct(1, 4) == 25.0`
- [ ] **Step 2: Run** `python -m pytest tests/test_metrics.py tests/test_loader.py -q` → FAIL
- [ ] **Step 3: Implement** `loader.load_data` และ `metrics.kpi_rows`/`pct` ตามด้านบน (ยังไม่ทำแถว lab/สุรา — ให้ `status "nodata"` ชั่วคราว ทำใน Task 3)
- [ ] **Step 4: Run** → PASS · commit `feat: loader and core KPI rows`

---

### Task 3: ตัวชี้วัดเด็ก/แล็บ/คุณภาพ/รายเดือน/รายปี

**Files:**
- Modify: `metrics.py`
- Test: `tests/test_metrics_outcomes.py`

**Interfaces:**
- Produces: `metrics.classify_result(text: str | None) -> "pos" | "neg" | "unclear"`
- Produces: `metrics.monthly(data: dict, cfg: Config, months: list[str]) -> list[dict]` คีย์ `{"ym","normal","complicated","referred"}` (`referred` มาจาก `data["refers"]` ไม่รวมในยอดคลอด)
- Produces: `metrics.quality_grid(data, cfg) -> list[dict]` `{"key","label","n","den"}` สำหรับ: `asphyxia` (Apgar5 < `asphyxia_apgar5` หรือ ICD `asphyxia_icd10` หรือ `labor_ba_id` ไม่ว่าง) · `pph` · `preterm` · `htn` · `prolonged` · `fetal_distress` · `prom` · `lbw` (`weight < lbw_grams` ต่อเด็กที่ไม่ตาย) · `refer`
- Produces: `metrics.yearly_table(loader: Callable[[date, date], dict], years: list[int], cfg) -> dict` → `{"years": [...], "rows": [{"key","label","values": [int|None,...]}]}` (เรียก `loader(*fy_range(fy))` ต่อปี)
- Produces: `metrics.rate_per_thousand(n, den) -> float | None`

- [ ] **Step 1: Write failing tests:**
  - `classify_result("Non-reactive") == "neg"` · `("NON REACTIVE") == "neg"` · `("Reactive") == "pos"` · `("Positive") == "pos"` · `("Negative") == "neg"` · `("") == "unclear"` · `(None) == "unclear"` · `("Inconclusive") == "unclear"` · `("พบ") == "unclear"`   ← **Review Focus #1**
  - `infants` 3 ราย Apgar1 = `[7, None, 8]` → `apgar1_low` = 1 และไม่เกิด `TypeError`  ← **#2**
  - แม่ 1 ราย เด็ก 2 ราย (`ipt_labour_id` เดียวกัน) → `twins==1`, `babies==2`, `mothers==1`  ← **#3**
  - `data` ว่างทั้งหมด → `kpi_rows` ทุกแถว `value` เป็น 0 สำหรับแถวที่นับได้ (ไม่ใช่ None) · `quality_grid` ไม่ล้ม · `monthly(data, cfg, ["2026-10"]) == [{"ym":"2026-10","normal":0,"complicated":0,"referred":0}]`  ← **#4**
  - ผล lab: เด็ก/แม่ที่ผล "Reactive" ของ `syphilis` 1 ราย "Non-reactive" 2 ราย → `syphilis==1` · ไม่มีแถว `labs` ของ `hiv` เลย → `hiv` `status=="nodata"` (ไม่ใช่ 0)
  - `rate_per_thousand(25, 1000) == 25.0` · `rate_per_thousand(1, 0) is None`
- [ ] **Step 2: Run** `python -m pytest tests/test_metrics_outcomes.py -q` → FAIL
- [ ] **Step 3: Implement** ตาม Interfaces · `classify_result`: normalize (lower, ตัดช่องว่าง/ขีด) แล้วตรวจกลุ่ม "ลบ" (`non`/`neg`/`ไม่พบ`/`nr`) **ก่อน** กลุ่ม "บวก" · เติมแถว `amph/syphilis/hiv/hbv` ใน `kpi_rows` ให้ `nodata` เมื่อไม่มีแถว `labs` ของ key นั้น
- [ ] **Step 4: Run** `python -m pytest tests -q` → PASS · commit `feat: outcome, lab, quality, monthly, yearly metrics`

---

### Task 4: audit.py (Data Audit + กระทบยอด)

**Files:**
- Create: `audit.py`, `tests/test_audit.py`

**Interfaces:**
- Consumes: `db.fetch`, `config.Config`, `queries.*`
- Produces: `audit.audit(d1, d2, cfg) -> list[dict]` item `{"key","title","app_uses","found":[{"code","name","n"}],"status":"ok"|"warn"|"bad","env","hint"}` ครอบคลุมทุกรหัสใน `Config` (normal/cs/forceps/vacuum/breech/stillbirth/dead_dchstts/bba/apgar/asphyxia/dx_*/lab keys) — รูปแบบเดียวกับ `check._item` ของ ANC
- Produces: `audit.reconcile(d1, d2, cfg) -> dict` `{"sources": {"ipt_pregnancy": n, "ipt_labour_infant_mothers": n, "labor": n, "icd_o80_o84": n}, "max_diff": int, "status": "ok"|"warn"}` · `warn` เมื่อ `max_diff > 5% ของค่ามากสุด` หรือ > 3 ราย
- Produces: `audit.completeness(data, cfg) -> list[dict]` สัดส่วน Apgar ที่ว่าง / เด็กที่ไม่มีแถวแม่ / แม่ที่ไม่มีแถวเด็ก

- [ ] **Step 1: Write failing tests** (monkeypatch `db.fetch`): `reconcile` แหล่งตรงกันหมด (78,78,78,77) → `status=="ok"` · แหล่งหนึ่งเป็น 120 ที่เหลือ 80 → `status=="warn"` และ `sources` คงค่าทุกแหล่ง **ไม่ถูกเลือกทิ้ง**  ← **#5** · `audit` ทุก item มี `env` ขึ้นต้น `LR_` และ `app_uses` ไม่ว่าง · แหล่งหนึ่ง `db.fetch` ยก exception → item นั้น `status=="bad"` และ item อื่นยังอยู่ (ใช้ guard แบบ `check._guard`)
- [ ] **Step 2: Run** `python -m pytest tests/test_audit.py -q` → FAIL
- [ ] **Step 3: Implement** — คัดโครง `_item/_guard/_found/audit` จาก `ANC_dashboard/check.py` แล้วแทนรายการเป็นของ LR · `reconcile` นับ 4 แหล่งตาม spec §2
- [ ] **Step 4: Run** → PASS · commit `feat: data audit and reconciliation`

---

### Task 5: app.py + templates + สไตล์

**Files:**
- Create: `app.py`, `templates/dashboard.html`, `templates/yearly.html`, `templates/check.html`, `static/style.css`, `tests/test_app.py`
- คัดจาก ANC: `PrefixMiddleware`, `_security_headers`, `thai_date`, `fy_options` helper, `_from_lan/_check_allowed`, ส่วนแถบเตือน/`_audit_flags`

**Interfaces:**
- Consumes: `loader.load_data`, `metrics.*`, `audit.*`, `cache.TTLCache`
- Produces routes: `GET /` (query `fy`, `d1`, `d2`) · `GET /yearly` · `GET /check` (LAN เท่านั้น มิฉะนั้น 403/404 ตาม ANC) · `GET /healthz` → `200 ok`
- Produces: `app.build_context(d1, d2) -> dict` (ส่งให้ template: `kpi`, `cards` (mothers/normal/complicated/referred + `pct_vs_prev`), `monthly`, `quality`, `recent`, `errors`, `audited: bool`)
- แบบ: ใช้สกิล `design-taste-frontend`/`impeccable` ตอนทำ CSS · โทนน้ำเงิน–ฟ้า (ตามแนว mockup) · การ์ด 4 ใบ + กราฟแท่งซ้อน (SVG inline) + โดนัท + ตาราง 9 ช่อง · ใช้โลโก้ `E:\App\Hos 212\logo.png`/`logo2.jpg` ผ่านไฟล์ใน `static/img/` · โดนัท/กราฟต้องมีข้อความ "ส่งต่อ ไม่นับเป็นคลอดที่ รพ." ใต้ตัวอย่าง

- [ ] **Step 1: Write failing tests** (Flask test client, monkeypatch `loader.load_data` ให้คืนข้อมูลจำลอง):
  - `GET /healthz` → 200 · `GET /` → 200 และมีข้อความ "ตัวเลขยังไม่ได้ตรวจ" เมื่อไม่ตั้ง `LR_DATA_AUDITED` · ตั้ง `LR_DATA_AUDITED=1` → ไม่มีข้อความนั้น
  - `GET /?fy=2569` ใช้ช่วง `fy_range(2569)` (ตรวจ d1/d2 ที่ส่งให้ `load_data`) · `fy` ผิดรูป (`abc`, `1999`) → ใช้ปีงบปัจจุบัน ไม่ 500
  - ข้อมูลว่าง (ไม่มีการคลอด) → 200 · HTML ไม่มี `NaN`/`None`/`ZeroDivision` · ตัวชี้วัดที่ `nodata` แสดง "ไม่มีข้อมูล"  ← **#4**
  - `/check` จาก IP นอก LAN → ไม่ 200 · จาก `127.0.0.1` → 200
  - หน้า `/` ไม่มีรายชื่อ/HN/AN (ตรวจ regex `\bAN\d`/`HN` ไม่ปรากฏเมื่อข้อมูลจำลองมี `an="6900001"`)
- [ ] **Step 2: Run** `python -m pytest tests/test_app.py -q` → FAIL
- [ ] **Step 3: Implement** `app.py` + templates ตาม Interfaces · cache ผลต่อ `(d1,d2)` ด้วย `TTLCache` (TTL 300 วินาที เหมือน ANC) · `LR_DATA_AUDITED` อ่านจาก env · หน้า `/yearly` ใช้ `metrics.yearly_table(..., years=fy_options()[:5][::-1])`
- [ ] **Step 4: Run** `python -m pytest tests -q` → PASS
- [ ] **Step 5: ตรวจบนเบราว์เซอร์** — เริ่ม dev server ด้วย `preview_start` ต่อฐานจริงแบบอ่านอย่างเดียว (ผ่าน `.env` ของผู้ใช้ที่ผู้ใช้สร้างเอง — ห้ามให้ Claude พิมพ์รหัส) หรือโหมด fixture (`LR_FAKE_DATA=1` โหลด JSON ตัวอย่างจาก `tests/fixtures/`) · ถ่ายภาพ desktop + มือถือ 375px · ตรวจไม่มี overflow แนวนอน · commit `feat: web app`

---

### Task 6: ยืนยันกับฐานจริง + ปิดประเด็นเปิดใน spec §9

**Files:**
- Modify: `config.py` (ค่าเริ่มต้นที่ยืนยันแล้ว), `metrics.py` (แถว `alcohol_smoke`, การ์ด "ส่งต่อ"), `docs/schema-notes.md`, spec §9
- Test: `tests/test_metrics_outcomes.py` (เพิ่ม)

- [ ] **Step 1: กระทบยอดจริง (read-only ผ่าน `hosdb`)** รัน `audit.reconcile` ของ `fy_range(fy)` สำหรับ 2565–2569 → ต้องได้ `ipt_pregnancy` = 92/85/92/72/78 (ตัดแท้งแล้ว) · ถ้าไม่ตรง ให้หาสาเหตุ (ห้ามปรับตัวเลขให้ตรง) แล้วบันทึกใน `docs/schema-notes.md`
- [ ] **Step 2: ปิด 5 ข้อใน spec §9** ด้วยการนับอย่างเดียว: (1) `infant_delivery_type_id` ที่พบจริง ว่า '3' แปลว่าอะไรใน รพ. นี้ (2) `infant_dchstts` 03/04/05 และ `ipt_newborn.dead` ตรงกับเด็กตายจริงกี่ราย (3) หาแหล่งสุรา/บุหรี่ใน `kips_lr_labour_record`/ANC screen — ถ้าไม่เจอปล่อย `nodata` และบันทึก (4) รูปแบบผลใน `ipt_labour_lab` (5) นิยาม "ส่งต่อจาก LR" จาก `referout` → ปรับ `queries.lr_refers`
- [ ] **Step 3: Write failing test** สำหรับค่าที่เปลี่ยน (เช่น `Config` default ใหม่ หรือ `classify_result` ต่อรูปแบบผลจริงที่พบ — ใช้ค่าตัวอย่างที่ไม่ระบุตัวบุคคล) → FAIL → แก้ → PASS
- [ ] **Step 4:** อัปเดต spec §9 เป็น "ยืนยันแล้ว: …" · `python -m pytest tests -q` ผ่านทั้งหมด · commit `feat: confirm codes against live data`

---

### Task 7: รายชื่อหลัง login + ส่งออก

**Files:**
- Create: `store.py`, `manage.py`, `listing.py`, `render.py`, `templates/login.html`, `templates/list.html`, `tests/test_store.py`, `tests/test_list_auth.py`
- Modify: `app.py` (เพิ่ม `/login`, `/logout`, `/list/<key>`, `/export.<fmt>`)

**Interfaces:**
- คัดจาก ANC: `store.add_user/check_login/get_user/...` · `manage.py` (CLI สร้างผู้ใช้) · `render.render_to(fmt, url, out_path)`
- Produces: `listing.rows(key: str, d1, d2, cfg) -> list[dict]` สำหรับ key ในกลุ่ม `normal|abnormal|twins|bba|still|neo_death7|apgar1_low|pph|asphyxia` (คอลัมน์: วันที่, HN, AN, หมายเหตุ — มีเฉพาะหลัง login)
- `LR_SECRET_KEY` ว่าง = ปิดหน้ารายชื่อ/login ทั้งหมด (แดชบอร์ดตัวเลขยังใช้ได้)

- [ ] **Step 1: Write failing tests** (ตามแบบ `ANC_dashboard/tests/test_list_auth.py`): ไม่ login → `/list/normal` redirect ไป `/login` · ไม่ตั้ง `LR_SECRET_KEY` → `/list/normal` 404 · login ผิดเกินกำหนด → 429 · รหัสผ่านใหม่ verify ผ่านด้วย `pbkdf2:sha256` (`store.add_user` แล้ว `check_login` ได้ผู้ใช้) · POST ไม่มี CSRF → 400 · `/export.jpg` ไม่มีข้อความแถบเตือน "ยังไม่ได้ตรวจ" (ตรวจ HTML ที่ใช้เรนเดอร์ส่งออกที่มี `?print=1`)
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** (คัดจาก ANC; `store` ใช้ไฟล์ SQLite `data/lr_users.db` เหมือน ANC `store.py`) · **Step 4: Run** `python -m pytest tests -q` → PASS · commit `feat: login-gated lists and export`

---

### Task 8: setup_check + เอกสาร + ชุดแจก

**Files:**
- Create: `setup_check.py`, `build_dist.py`, `INSTALL.md`, `README.md`, `CHANGELOG.md`, `SECURITY.md`, `Dockerfile`, `.dockerignore`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `tests/test_setup_check.py`, `tests/test_docs.py`

**Interfaces:**
- `setup_check.run(fetch=None, cfg=None, audit=True, days=90) -> list[tuple[str, str, str]]` (`(ระดับ ✔/⚠/✘, หัวข้อ, รายละเอียด)`) · `setup_check.main()` → exit 1 เมื่อมี ✘ · ตรวจ: Python/ไลบรารี · เขตเวลา · Chrome (ถ้ามีส่งออก) · ต่อ DB ได้ · สิทธิ์ read-only (`risky_privs`) · ตารางที่ใช้ครบ (`ipt_pregnancy, ipt_labour, ipt_labour_infant, ipt_labour_lab, iptdiag, iptoprt, ipt, ipt_newborn, referout`) · ภาษาไทยอ่านได้ · visit ล่าสุด + Data Audit

- [ ] **Step 1: Write failing tests:** `setup_check.run` กับ `fetch` ปลอมที่ตารางขาด `ipt_labour_lab` → มีแถว ✘ ระบุชื่อตาราง · ทุกอย่างผ่านด้วย `fetch` ปลอม → ไม่มี ✘ · `risky_privs(["GRANT ALL PRIVILEGES ON hos.* TO ..."])` ไม่ว่าง (คัดจาก ANC) · `tests/test_docs.py`: `INSTALL.md` มีหัวข้อ "ก่อนนำไปใช้" · มีคำว่า `LR_DATA_AUDITED` · `bug_report.yml` มีช่องแนบผล `setup_check` และ checkbox "ไม่มีข้อมูลผู้ป่วย" · `build_dist.FILES` ทุกไฟล์มีอยู่จริงและไม่มี `.env`
- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** — `INSTALL.md` ข้อ 0 ตาม CLAUDE.md: ขั้นตอนตรวจ → ทดลองคู่รายงานเดิม 1–2 สัปดาห์ → ตั้ง `LR_DATA_AUDITED=1` · MIT ไม่มีการรับประกัน · วิธีแจ้งปัญหา · `build_dist.py` คัดจาก ANC (ข้ามโลโก้ รพ. และ `.env`)
- [ ] **Step 4: Run** `python -m pytest tests -q` → PASS · commit `docs: setup check, install guide, distribution`

---

### Task 9: Deploy (ต้องให้ผู้ใช้สั่งและให้รหัส SSH/DB เอง)

**Files:** ไม่เพิ่มโค้ด — ใช้สกิล `wnkhos-deploy` · `deploy_ssh.py` คัดจาก ANC/ipt ถ้าต้องใช้

- [ ] **Step 1: ถามผู้ใช้ก่อนทุกครั้ง** (การเปิดเว็บภายนอก/แก้ `ssl.conf` เป็นงานที่ย้อนยาก): ยืนยัน sub-path `/lr/`, พอร์ตว่าง (ตรวจจริงบนเซิร์ฟเวอร์), ผู้ใช้ให้รหัสเอง
- [ ] **Step 2:** deploy ตามสกิล (`/opt/lr_dashboard` + `.venv` + `.env` chmod 600 + systemd gunicorn + ProxyPass **ก่อน** `ProxyPass / http://127.0.0.1:3000/` · `cp` backup → `httpd -t` → reload) · ตรวจ `GET /lr/healthz` = 200 และเปิด `/lr/check` จากนอก LAN ต้องไม่ผ่าน
- [ ] **Step 3:** รัน `python setup_check.py` บนเซิร์ฟเวอร์ · บันทึกผลใน `CHANGELOG.md` · commit `chore: deploy notes`
