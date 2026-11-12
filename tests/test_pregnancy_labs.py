"""แถว 9–13 ของตารางรายปี — ดึงผล lab ตลอดการตั้งครรภ์ (แบบ ANC dashboard) + ข้อ 17 ของแบบคัดกรองครรภ์เสี่ยง"""

import re
from datetime import date

import pytest

import audit
import db
import listing
import loader
import metrics
import queries
from config import Config, load_config
from tests.test_metrics import CFG, data, delivery, val

D1, D2 = date(2025, 10, 1), date(2026, 9, 30)

LAB_ITEMS = [{"code": 366, "name": "TPHA"}, {"code": 365, "name": "VDRL ครั้งที่ 1"}, {"code": 355, "name": "HBs Ag"},
             {"code": 361, "name": "Anti-HIV (ELI)"}, {"code": 1978, "name": "Anti-HIV (rapid test)"},
             {"code": 77, "name": "Ampicillin"}, {"code": 139, "name": "Methamphetamine"}]


# ---------------------------------------------------------------- config

def test_new_config_fields_and_env():
    c = load_config({})
    assert (c.syphilis_items, c.hiv_items, c.hbv_items) == ((), (), ())          # ว่าง = เลือกจากชื่อรายการ lab
    assert c.substance_items == ("17",)                                         # ข้อ 17 "ติดยาเสพติด ติดสุรา"
    assert (c.lab_window_before, c.lab_window_after) == (300, 7)
    e = load_config({"LR_LAB_HIV_ITEMS": "361, 1978", "LR_SUBSTANCE_FORM_ITEMS": "17,18", "LR_LAB_WINDOW_BEFORE": "280"})
    assert e.hiv_items == ("361", "1978") and e.substance_items == ("17", "18") and e.lab_window_before == 280


# ---------------------------------------------------------------- เลือกรหัส lab จากชื่อ (เหมือน ANC)

def test_lab_item_codes_picked_by_name(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: LAB_ITEMS)
    got = queries.lab_item_codes(Config(amph_labs=()))
    assert set(got["syphilis"]) == {"365", "366"} and set(got["hbv"]) == {"355"} and set(got["hiv"]) == {"361", "1978"}
    assert set(got["amph"]) == {"139"}
    assert "77" not in {c for v in got.values() for c in v}            # Ampicillin ไม่ใช่ Amphetamine


def test_configured_codes_win_and_skip_the_name_lookup(monkeypatch):
    def boom(sql, args=None):
        raise AssertionError("ตั้งรหัสครบแล้ว ไม่ควรอ่าน lab_items")
    monkeypatch.setattr(db, "fetch", boom)
    got = queries.lab_item_codes(Config(syphilis_items=("1",), hiv_items=("2",), hbv_items=("3",), amph_labs=("4",)))
    assert got == {"syphilis": ("1",), "hiv": ("2",), "hbv": ("3",), "amph": ("4",)}


# ---------------------------------------------------------------- ผล lab ตลอดการตั้งครรภ์

def test_pregnancy_labs_use_hn_window_and_map_codes_to_tests(monkeypatch):
    seen = []

    def fake(sql, args=None):
        seen.append((sql, args))
        if "from lab_items" in sql:
            return LAB_ITEMS
        return [{"an": "A1", "code": "366", "result": "Reactive"}, {"an": "A2", "code": "139", "result": "neg"},
                {"an": "A3", "code": "999", "result": "ไม่เกี่ยว"}]

    monkeypatch.setattr(db, "fetch", fake)
    rows = queries.pregnancy_lab_results(D1, D2, Config(amph_labs=()))
    assert rows == [{"an": "A1", "lab_key": "syphilis", "result": "Reactive"},
                    {"an": "A2", "lab_key": "amph", "result": "neg"}]
    sql, args = seen[-1]
    assert "lab_head" in sql and "lh.hn" in sql and args["before"] == 300 and args["after"] == 7
    assert {"366", "365"} <= set(args["codes"])
    assert not re.search(r"'\d{2,3}'", sql)


def test_pregnancy_labs_never_send_empty_in_list(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: seen.append(args) or [])
    queries.pregnancy_lab_results(D1, D2, Config(syphilis_items=("1",), hiv_items=("2",), hbv_items=("3",), amph_labs=()))
    assert all(len(a["codes"]) >= 1 for a in seen if a and "codes" in a)


# ---------------------------------------------------------------- ข้อ 17 แบบคัดกรองครรภ์เสี่ยง

def test_substance_flags_typed_and_parameterised(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: seen.append((sql, args)) or
                        [{"an": "A1", "flag": "1"}, {"an": "A2", "flag": "0"}])
    assert queries.substance_flags(D1, D2, CFG) == [{"an": "A1", "flag": 1}, {"an": "A2", "flag": 0}]
    sql, args = seen[0]
    assert "person_anc_classifying" in sql and args["items"] == ("17",) and args["before"] == 300
    assert not re.search(r"'\d{2,3}'", sql)


# ---------------------------------------------------------------- loader

def test_loader_merges_both_lab_sources_and_substance(monkeypatch):
    base = {"deliveries": [], "delivery_dx": [], "delivery_ops": [], "infants": [], "lr_refers": [],
            "lab_results": [{"an": "A1", "lab_key": "hiv", "result": "neg"}],
            "pregnancy_lab_results": [{"an": "A1", "lab_key": "syphilis", "result": "Reactive"}],
            "substance_flags": [{"an": "A1", "flag": 1}]}
    for name, rows in base.items():
        monkeypatch.setattr(queries, name, lambda d1, d2, cfg, _r=rows: _r)
    d = loader.load_data(D1, D2, CFG)
    assert {(r["lab_key"], r["result"]) for r in d["labs"]} == {("hiv", "neg"), ("syphilis", "Reactive")}
    assert d["substance"] == [{"an": "A1", "flag": 1}] and d["errors"] == []


def test_loader_pregnancy_lab_failure_keeps_delivery_labs_and_reports_error(monkeypatch):
    base = {"deliveries": [], "delivery_dx": [], "delivery_ops": [], "infants": [], "lr_refers": [],
            "lab_results": [{"an": "A1", "lab_key": "hiv", "result": "neg"}], "substance_flags": []}
    for name, rows in base.items():
        monkeypatch.setattr(queries, name, lambda d1, d2, cfg, _r=rows: _r)

    def boom(d1, d2, cfg):
        raise RuntimeError("timeout")

    monkeypatch.setattr(queries, "pregnancy_lab_results", boom)
    d = loader.load_data(D1, D2, CFG)
    assert d["errors"] == ["pregnancy_lab_results"] and [r["lab_key"] for r in d["labs"]] == ["hiv"]


# ---------------------------------------------------------------- metrics

def test_positive_found_in_pregnancy_labs_counts_even_if_delivery_lab_negative():
    labs = [{"an": "a", "lab_key": "syphilis", "result": "Non-reactive"},         # ตอนคลอด
            {"an": "a", "lab_key": "syphilis", "result": "Reactive titer 1:8"}]   # ตอนฝากครรภ์
    assert val(metrics.kpi_rows(data([delivery("a")], labs=labs), CFG), "syphilis") == 1


def test_amph_is_zero_not_no_data_when_someone_was_tested():
    rows = {r["key"]: r for r in metrics.kpi_rows(data([delivery("a")], labs=[{"an": "a", "lab_key": "amph", "result": "Negative"}]), CFG)}
    assert rows["amph"]["value"] == 0 and rows["amph"]["status"] == "ok"


def test_substance_row_counts_flagged_mothers_only():
    d = data([delivery("a"), delivery("b"), delivery("x", abort=1)], substance=[
        {"an": "a", "flag": 1}, {"an": "b", "flag": 0}, {"an": "x", "flag": 1}])
    rows = {r["key"]: r for r in metrics.kpi_rows(d, CFG)}
    assert rows["alcohol_smoke"]["value"] == 1 and rows["alcohol_smoke"]["status"] == "ok"


def test_substance_row_is_no_data_when_no_mother_matched_an_anc_record():
    rows = {r["key"]: r for r in metrics.kpi_rows(data([delivery("a")]), CFG)}
    assert rows["alcohol_smoke"]["value"] is None and rows["alcohol_smoke"]["status"] == "nodata"


def test_label_is_honest_that_smoking_is_not_included():
    assert "ไม่รวมบุหรี่" in metrics.LABELS["alcohol_smoke"]


# ---------------------------------------------------------------- lists

def test_lists_for_lab_positives_and_substance():
    d = data([delivery("a"), delivery("b"), delivery("c")],
             labs=[{"an": "a", "lab_key": "hiv", "result": "positive"}, {"an": "b", "lab_key": "hiv", "result": "neg"},
                   {"an": "c", "lab_key": "amph", "result": "pos"}],
             substance=[{"an": "b", "flag": 1}, {"an": "c", "flag": 0}])
    assert listing.members("hiv", d, CFG) == ["a"] and listing.members("amph", d, CFG) == ["c"]
    assert listing.members("substance", d, CFG) == ["b"] and listing.members("syphilis", d, CFG) == []


def test_list_counts_equal_kpi_counts_for_rows_9_to_13():
    d = data([delivery("a"), delivery("b")], labs=[{"an": "a", "lab_key": "hbv", "result": "pos"}],
             substance=[{"an": "b", "flag": 1}])
    kpi = {r["key"]: r["value"] for r in metrics.kpi_rows(d, CFG)}
    assert len(listing.members("hbv", d, CFG)) == kpi["hbv"] and len(listing.members("substance", d, CFG)) == kpi["alcohol_smoke"]


# ---------------------------------------------------------------- /check

def test_check_has_pregnancy_labs_and_substance_items(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: [])
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert "pregnancy_labs" in items and "LR_LAB_HIV_ITEMS" in items["pregnancy_labs"]["env"]
    assert items["alcohol_smoke"]["env"] == "LR_SUBSTANCE_FORM_ITEMS" and items["alcohol_smoke"]["status"] == "warn"
    assert "ไม่รวมบุหรี่" in (items["alcohol_smoke"]["hint"] + items["alcohol_smoke"]["title"])


def test_pregnancy_labs_item_ok_when_each_test_has_results(monkeypatch):
    def fake(sql, args=None):
        if "count(distinct" in sql and "lab_items" in sql:
            return [{"code": c, "name": n, "n": 5} for c, n in
                    (("366", "TPHA"), ("355", "HBs Ag"), ("361", "Anti-HIV"), ("139", "Methamphetamine"))]
        if "from lab_items" in sql:
            return LAB_ITEMS
        return []
    monkeypatch.setattr(db, "fetch", fake)
    items = {i["key"]: i for i in audit.audit(D1, D2, Config(amph_labs=()))}
    assert items["pregnancy_labs"]["status"] == "ok"
