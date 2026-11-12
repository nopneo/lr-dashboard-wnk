from datetime import date

import pytest

import metrics
from config import Config

CFG = Config()


def delivery(an, d=date(2026, 1, 5), twin=0, abort=0):
    return {"an": an, "labor_date": d, "ym": d.strftime("%Y-%m"), "twin": twin, "is_abort": abort}


def infant(lid, an, **kw):
    r = {"ipt_labour_id": lid, "an": an, "birth_date": date(2026, 1, 5), "ym": "2026-01", "weight": 3000,
         "apgar1": 9, "apgar5": 10, "dchstts": "05", "dead": False, "bba_type": "1", "labor_ba_id": None,
         "infant_icd10": None, "days_to_dch": 3}
    r.update(kw)
    return r


def data(deliveries=(), dx=None, ops=None, infants=(), labs=(), refers=(), substance=()):
    return {"deliveries": list(deliveries), "dx_by_an": {k: set(v) for k, v in (dx or {}).items()},
            "ops_by_an": {k: set(v) for k, v in (ops or {}).items()}, "infants": list(infants),
            "labs": list(labs), "refers": list(refers), "substance": list(substance), "errors": []}


def val(rows, key):
    return {r["key"]: r for r in rows}[key]["value"]


def test_row_order_matches_spec():
    keys = tuple(r["key"] for r in metrics.kpi_rows(data(), CFG))
    assert keys == metrics.KPI_KEYS
    assert keys[:3] == ("mothers", "normal", "abnormal")


def test_normal_vs_abnormal_with_complication_and_vacuum():
    d = data([delivery("a"), delivery("b"), delivery("c")],
             dx={"a": ["O800"], "b": ["O800", "O721"], "c": ["O800"]},
             ops={"c": ["7270"]})
    rows = metrics.kpi_rows(d, CFG)
    assert val(rows, "mothers") == 3
    assert val(rows, "normal") == 1          # a เท่านั้น
    assert val(rows, "abnormal") == 2        # b มี PPH (O72), c มีสุญญากาศ 72.7
    assert val(rows, "vacuum") == 1


def test_abort_rows_excluded_from_mothers():
    d = data([delivery("a"), delivery("x", abort=1)], dx={"a": ["O800"]})
    assert val(metrics.kpi_rows(d, CFG), "mothers") == 1


def test_cs_forceps_breech_counts():
    d = data([delivery("a"), delivery("b"), delivery("c")],
             ops={"a": ["7401"], "b": ["7220"]}, dx={"c": ["O830"]})
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "cs"), val(rows, "forceps"), val(rows, "breech")) == (1, 1, 1)


def test_babies_live_still_and_apgar():
    d = data([delivery("a"), delivery("b")], dx={"b": ["Z371"]},
             infants=[infant(1, "a", apgar1=7), infant(2, "b", apgar1=9)])
    rows = metrics.kpi_rows(d, CFG)
    assert val(rows, "babies") == 2
    assert val(rows, "still") == 1 and val(rows, "live") == 1
    assert val(rows, "apgar1_low") == 1      # 7 ≤ 7 นับ


def test_bba_counts_infants_with_configured_type():
    d = data([delivery("a")], infants=[infant(1, "a", bba_type="3"), infant(2, "a", bba_type="1")])
    assert val(metrics.kpi_rows(d, CFG), "bba") == 1


def test_neonatal_death_within_7_days_excludes_stillbirth():
    d = data([delivery("a"), delivery("b"), delivery("c")], dx={"c": ["Z371"]},
             infants=[infant(1, "a", dead=True, days_to_dch=5), infant(2, "b", dead=True, days_to_dch=20),
                      infant(3, "c", dead=True, days_to_dch=0)])
    assert val(metrics.kpi_rows(d, CFG), "neo_death7") == 1


def test_pct():
    assert metrics.pct(1, 4) == 25.0
    assert metrics.pct(1, 0) is None
    assert metrics.pct(1, None) is None


def test_unsourced_rows_are_nodata_not_zero():
    rows = {r["key"]: r for r in metrics.kpi_rows(data(), CFG)}
    assert rows["alcohol_smoke"]["value"] is None and rows["alcohol_smoke"]["status"] == "nodata"
    assert rows["amph"]["status"] == "nodata"


def test_null_dx_and_ops_codes_do_not_crash():
    # ข้อมูลจริง: iptdiag.icd10 / iptoprt.icd9 บางแถวเป็น NULL หรือว่าง
    d = data([delivery("a")], dx={"a": [None, "", "O800"]}, ops={"a": [None, ""]})
    rows = metrics.kpi_rows(d, CFG)
    assert val(rows, "mothers") == 1 and val(rows, "normal") == 1
