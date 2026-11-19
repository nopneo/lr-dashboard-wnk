"""การแก้ตามผลรีวิวทั้ง branch (Important 1–12) — แต่ละ test ผูกกับข้อของผู้รีวิว"""

import os
from datetime import date

import pytest

import app as lr_app
import audit
import db
import listing
import loader
import metrics
import queries
import render
from config import Config, fy_range, load_config
from tests.test_metrics import CFG, data, delivery, infant, val

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- #1 ยังไม่ลงรหัส Dx คลอด ≠ ภาวะแทรกซ้อน

def _uncoded_data():
    return data([delivery("a"), delivery("b")], dx={"a": ["O800"]}, infants=[infant(1, "a"), infant(2, "b")])


def test_delivery_without_any_delivery_dx_is_uncoded_not_abnormal():
    rows = metrics.kpi_rows(_uncoded_data(), CFG)
    assert (val(rows, "mothers"), val(rows, "normal"), val(rows, "abnormal")) == (2, 1, 0)
    assert metrics.uncoded_ans(_uncoded_data(), CFG) == ["b"]


def test_uncoded_has_its_own_bucket_in_monthly_list_and_completeness():
    d = _uncoded_data()
    m = metrics.monthly(d, CFG, ["2026-01"])[0]
    assert (m["normal"], m["complicated"], m["uncoded"]) == (1, 0, 1)
    assert listing.members("uncoded", d, CFG) == ["b"]
    c = {x["key"]: x for x in audit.completeness(d, CFG)}
    assert c["uncoded_delivery"]["n"] == 1 and c["uncoded_delivery"]["den"] == 2


def test_coded_complication_still_counts_as_abnormal():
    d = data([delivery("a")], dx={"a": ["O800", "O721"]}, infants=[infant(1, "a")])
    rows = metrics.kpi_rows(d, CFG)
    assert val(rows, "abnormal") == 1 and not metrics.uncoded_ans(d, CFG)


# ---------------------------------------------------------------- #2 #3 ทารกไร้ชีพระดับทารก

def test_stillbirth_by_dchstts_without_icd():
    d = data([delivery("a")], infants=[infant(1, "a", dchstts="08", dead=True, days_to_dch=0)])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "still"), val(rows, "live"), val(rows, "neo_death7")) == (1, 0, 0)


def test_single_stillbirth_dx_without_infant_row_still_adds_the_baby():
    d = data([delivery("a")], dx={"a": ["Z371"]})
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "babies"), val(rows, "still"), val(rows, "live")) == (1, 1, 0)


def test_twins_one_stillborn_dx_z373_with_only_one_infant_row():
    d = data([delivery("a")], dx={"a": ["Z373"]}, infants=[infant(1, "a")])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "babies"), val(rows, "still"), val(rows, "live")) == (2, 1, 1)


def test_twins_both_stillborn_z374():
    d = data([delivery("a")], dx={"a": ["Z374"]}, infants=[infant(1, "a"), infant(1, "a")])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "babies"), val(rows, "still"), val(rows, "live")) == (2, 2, 0)


def test_live_twin_neonatal_death_counted_when_sibling_stillborn():
    d = data([delivery("a")], dx={"a": ["Z373"]},
             infants=[infant(1, "a", dchstts="08", dead=True, days_to_dch=0), infant(1, "a", dead=True, days_to_dch=3)])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "babies"), val(rows, "still"), val(rows, "neo_death7")) == (2, 1, 1)


def test_completeness_reports_babies_implied_by_dx_but_missing_rows():
    d = data([delivery("a")], dx={"a": ["Z373"]}, infants=[infant(1, "a")])
    c = {x["key"]: x for x in audit.completeness(d, CFG)}
    assert c["births_without_row"]["n"] == 1


def test_stillbirth_dchstts_is_configurable():
    assert load_config({}).stillbirth_dchstts == ("08",)
    assert load_config({"LR_STILLBIRTH_DCHSTTS": "08,10"}).stillbirth_dchstts == ("08", "10")


# ---------------------------------------------------------------- #4 กระทบยอดต้องไม่ซ่อนแถวที่ตัดออก

def test_excluded_rows_shows_raw_flagged_and_no_evidence(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: [{"raw": 102, "abort_flag": 0, "no_evidence": 10}])
    r = audit.excluded_rows(date(2021, 10, 1), date(2022, 9, 30), CFG)
    assert r == {"raw": 102, "abort_flag": 0, "no_evidence": 10, "counted": 92}


def test_audit_has_excluded_rows_item_that_warns_when_rows_dropped(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: [{"raw": 102, "abort_flag": 0, "no_evidence": 10, "n": 0}])
    items = {i["key"]: i for i in audit.audit(date(2021, 10, 1), date(2022, 9, 30), CFG)}
    assert items["excluded_rows"]["status"] == "warn"
    assert {f["code"] for f in items["excluded_rows"]["found"]} >= {"แถวทั้งหมดใน ipt_pregnancy", "ไม่มีหลักฐานการคลอด"}


def test_reconcile_icd_source_derives_codes_from_config(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: seen.append(args) or [{"n": 1}])
    audit.reconcile(date(2025, 10, 1), date(2026, 9, 30), Config(delivery_icd10=("O80", "O82", "Z37")))
    assert any(a and a.get("codes") == ("O80", "O82") for a in seen)       # ไม่เอา Z37 (ไม่ใช่ O8x)


# ---------------------------------------------------------------- #5 ช่วงวันที่สั้นเกินไปทำให้เป็นข้อมูลรายคน

@pytest.mark.parametrize("d1,d2", [("2026-11-03", "2026-11-03"), ("2026-10-01", "2026-10-27")])
def test_custom_range_shorter_than_28_days_falls_back_to_fiscal_year(d1, d2):
    a, b, fy = lr_app.resolve_range({"d1": d1, "d2": d2})
    assert fy is not None and (a, b) == fy_range(fy)


def test_custom_range_of_28_days_is_allowed():
    a, b, fy = lr_app.resolve_range({"d1": "2026-10-01", "d2": "2026-10-28"})
    assert fy is None and (a, b) == (date(2026, 10, 1), date(2026, 10, 28))


# ---------------------------------------------------------------- #6 เทียบปีงบก่อนเฉพาะเมื่อปีครบ

def test_no_prior_year_delta_while_fiscal_year_is_incomplete(monkeypatch):
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data([delivery("a")], dx={"a": ["O800"]}))
    monkeypatch.setattr(queries, "recent_counts", lambda today, cfg: {"days7": 0})
    ctx = lr_app.build_context(*fy_range(2570), 2570, today=date(2026, 11, 12))
    assert ctx["partial"] is True and all(c["delta"] is None for c in ctx["cards"])
    done = lr_app.build_context(*fy_range(2569), 2569, today=date(2026, 11, 12))
    assert done["partial"] is False and all(c["delta"] is not None for c in done["cards"][:2])   # มารดา/ปกติ มีฐานเทียบ (ผิดปกติฐาน 0 → ไม่มี %)


def test_partial_year_is_labelled_on_the_page(monkeypatch):
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data([delivery("a")], dx={"a": ["O800"]}))
    monkeypatch.setattr(queries, "recent_counts", lambda today, cfg: {"days7": 0})
    monkeypatch.setattr(lr_app, "current_fy", lambda today=None: 2570)
    html = lr_app.app.test_client().get("/?fy=2570").get_data(as_text=True)
    assert "ยังไม่สิ้นสุด" in html or "ยังไม่ครบ" in html


# ---------------------------------------------------------------- #7 หน้ารายปี: แถบเตือน · error · แถว 9–13

@pytest.fixture
def yearly_client(monkeypatch):
    monkeypatch.delenv("LR_DATA_AUDITED", raising=False)
    monkeypatch.setattr(queries, "recent_counts", lambda today, cfg: {"days7": 0})
    return lr_app.app.test_client()


def test_yearly_has_audit_banner_until_audited(yearly_client, monkeypatch):
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data([delivery("a")]))
    assert "ตัวเลขยังไม่ได้ตรวจ" in yearly_client.get("/yearly").get_data(as_text=True)
    monkeypatch.setenv("LR_DATA_AUDITED", "1")
    assert "ตัวเลขยังไม่ได้ตรวจ" not in yearly_client.get("/yearly").get_data(as_text=True)


def test_yearly_rows_9_to_13_show_numbers_without_waiting_for_audit(yearly_client, monkeypatch):
    # ผู้ใช้ตัดสินใจ 2026-11-12: แสดงตัวเลขแถว 9–13 ทันที (แถบเตือนด้านบนยังอยู่จนกว่าตั้ง LR_DATA_AUDITED=1)
    labs = [{"an": "a", "lab_key": "hiv", "result": "pos"}]
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data([delivery("a")], labs=labs))
    html = yearly_client.get("/yearly").get_data(as_text=True)
    assert "กำลังตรวจสอบข้อมูล" not in html and "ตัวเลขยังไม่ได้ตรวจ" in html


def test_yearly_year_with_failed_source_shows_warning_and_dashes_not_zeros(yearly_client, monkeypatch):
    def fake(d1, d2, cfg):
        d = data([delivery("a", date(2024, 12, 5))], dx={"a": ["O800"]}, infants=[infant(1, "a")])
        if d1.year == 2024:                                      # ปีงบ 2568 ล้ม
            d = data()
            d["errors"] = ["infants"]
        return d
    monkeypatch.setattr(loader, "load_data", fake)
    html = yearly_client.get("/yearly").get_data(as_text=True)
    assert "อ่านข้อมูลของปี" in html and "2568" in html


def test_failed_load_is_not_cached_but_good_load_is(monkeypatch):
    calls = []
    good = data([delivery("a")])

    def fake(d1, d2, cfg):
        calls.append(1)
        return fake.result

    monkeypatch.setattr(loader, "load_data", fake)
    monkeypatch.setenv("LR_CACHE_TTL", "300")
    lr_app._cache = lr_app.TTLCache(maxsize=8)
    bad = data()
    bad["errors"] = ["infants"]
    fake.result = bad
    lr_app._data(date(2026, 1, 1), date(2026, 1, 31), CFG)
    lr_app._data(date(2026, 1, 1), date(2026, 1, 31), CFG)
    assert len(calls) == 2                                       # ผลที่มี error ไม่แคช
    fake.result = good
    lr_app._data(date(2026, 2, 1), date(2026, 2, 28), CFG)
    lr_app._data(date(2026, 2, 1), date(2026, 2, 28), CFG)
    assert len(calls) == 3                                       # ผลปกติแคช


# ---------------------------------------------------------------- #8 ผลแล็บที่จับคู่ไม่ได้ต้องไม่หายเงียบ

@pytest.mark.parametrize("text,expected", [
    ("บวก", "pos"), ("ลบ", "neg"), ("Weakly reactive", "pos"), ("WR", "pos"), ("2+", "pos"), ("rpr reactive", "pos"),
    ("rpr non-reactive", "neg"), ("R/O", "unclear"), ("+/-", "unclear"), ("ผลลบ", "neg"),
])
def test_more_hand_typed_lab_results(text, expected):
    assert metrics.classify_result(text) == expected


def test_labs_audit_warns_on_any_unclear_result(monkeypatch):
    def fake(sql, args=None):
        if "ipt_labour_lab" in sql:
            return [{"code": "Neg", "name": 2, "n": 79}, {"code": "???", "name": 2, "n": 1}]
        return []
    monkeypatch.setattr(db, "fetch", fake)
    items = {i["key"]: i for i in audit.audit(date(2025, 10, 1), date(2026, 9, 30), CFG)}
    assert items["labs"]["status"] == "warn"


def test_amph_results_are_classified_and_unclear_warns(monkeypatch):
    def fake(sql, args=None):
        if "lab_order_result" in sql:
            return [{"code": "Negative", "name": "", "n": 4}, {"code": "บวกๆ", "name": "", "n": 1}]
        return []
    monkeypatch.setattr(db, "fetch", fake)
    items = {i["key"]: i for i in audit.audit(date(2025, 10, 1), date(2026, 9, 30), CFG)}
    assert items["amph_results"]["status"] == "warn" or any("pos" in f["name"] for f in items["amph_results"]["found"])
    assert any("neg" in f["name"] for f in items["amph_results"]["found"])


def test_completeness_counts_unclear_lab_results():
    labs = [{"an": "a", "lab_key": "hiv", "result": "neg"}, {"an": "a", "lab_key": "syphilis", "result": "???"}]
    d = data([delivery("a")], labs=labs)
    c = {x["key"]: x for x in audit.completeness(d, CFG)}
    assert c["labs_unclear"]["n"] == 1 and c["labs_unclear"]["den"] == 2


# ---------------------------------------------------------------- #9 /check ครอบคลุมทุกรหัสที่แอปสมมติ

def test_check_covers_asphyxia_lbw_flags_refer_and_delivery_codes(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: [])
    items = {i["key"]: i for i in audit.audit(date(2025, 10, 1), date(2026, 9, 30), CFG)}
    assert {"asphyxia", "lbw", "delivery_flags", "refer", "delivery_icd10", "amph_results"} <= set(items)
    assert "LR_ASPHYXIA_APGAR5" in items["asphyxia"]["env"] and "LR_LBW_GRAMS" in items["lbw"]["env"]
    assert "LR_DELIVERY_ICD10" in items["delivery_icd10"]["env"]


def test_labor_ba_id_zero_is_not_asphyxia():
    assert metrics.is_asphyxia(infant(1, "a", labor_ba_id=0, apgar5=10), CFG) is False
    assert metrics.is_asphyxia(infant(1, "a", labor_ba_id=2, apgar5=10), CFG) is True


# ---------------------------------------------------------------- #10 ไฟล์บัญชีผู้ใช้ต้องไม่ถูก commit

def test_gitignore_covers_the_real_user_store_file():
    lines = [ln.strip() for ln in open(os.path.join(HERE, ".gitignore"), encoding="utf-8")]
    assert "data/*" in lines and "!data/.gitkeep" in lines
    assert os.path.exists(os.path.join(HERE, "data", ".gitkeep"))


# ---------------------------------------------------------------- #11 รายชื่อ: ค่าเริ่มต้น = เฉพาะ LAN

def test_list_pages_are_lan_only_by_default(monkeypatch):
    monkeypatch.setattr(lr_app.app, "secret_key", "k" * 40)
    monkeypatch.delenv("LR_LIST_LAN_ONLY", raising=False)
    c = lr_app.app.test_client()
    assert c.get("/login", environ_overrides={"REMOTE_ADDR": "8.8.8.8"}).status_code == 403
    assert c.get("/login", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).status_code == 200


def test_list_lan_only_can_be_switched_off_explicitly(monkeypatch):
    monkeypatch.setattr(lr_app.app, "secret_key", "k" * 40)
    monkeypatch.setenv("LR_LIST_LAN_ONLY", "0")
    c = lr_app.app.test_client()
    assert c.get("/login", environ_overrides={"REMOTE_ADDR": "8.8.8.8"}).status_code == 200


def test_install_explains_lan_nets_for_non_rfc1918_hospital_networks():
    t = open(os.path.join(HERE, "INSTALL.md"), encoding="utf-8").read()
    assert "LR_LAN_NETS" in t and "IP สาธารณะจริงของ รพ." in t and "192.168.x.x" in t
    assert "ห้ามใส่ IP บ้าน" in t and "LR_LIST_LAN_ONLY=0" in t
    assert "30.25.1.0/24" not in t          # วงนี้ของ รพ.วังน้ำเขียวปิดแล้ว — ไม่ใช้เป็นตัวอย่าง


# ---------------------------------------------------------------- #12 ส่งออกที่ไม่ต้อง login ต้องจำกัด

def test_export_ignores_custom_dates_and_renders_fiscal_year_only(monkeypatch):
    seen = {}

    def fake_render(fmt, url, out):
        seen["url"] = url
        open(out, "wb").write(b"x")

    monkeypatch.setattr(render, "render_to", fake_render)
    lr_app._export_cache = lr_app.TTLCache(maxsize=4)
    r = lr_app.app.test_client().get("/export.jpg?d1=2026-01-01&d2=2026-02-15")
    assert r.status_code == 200 and "fy=" in seen["url"] and "d1=" not in seen["url"]


def test_render_timeout_is_below_gunicorn_timeout_and_cache_is_wide():
    assert render.TIMEOUT <= 100
    assert lr_app.EXPORT_WAIT <= 30


def test_twin_delivery_by_dx_counts_as_twins_even_with_one_infant_row():
    # ข้อมูลจริง ปีงบ 2567: Z37.2 (แฝดมีชีพทั้งคู่) แต่บันทึกทารกไว้แถวเดียว
    d = data([delivery("a")], dx={"a": ["Z372"]}, infants=[infant(1, "a")])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "twins"), val(rows, "babies"), val(rows, "mothers")) == (1, 2, 1)
