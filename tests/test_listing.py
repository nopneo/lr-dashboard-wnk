from datetime import date

import pytest

import listing
import metrics
from tests.test_metrics import CFG, data, delivery, infant


def fixture_data():
    """6 มารดา: a ปกติ · b PPH · c แฝด · d BBA · e Apgar ต่ำ + ทารก LBW · f ตายคลอด"""
    ds = [delivery(x, date(2026, 1, i + 1)) for i, x in enumerate("abcdef")]
    dx = {"a": ["O800"], "b": ["O800", "O721"], "c": ["O800"], "d": ["O800"], "e": ["O800", "O60"], "f": ["Z371"]}
    inf = [infant(1, "a"), infant(2, "b"), infant(3, "c"), infant(3, "c"), infant(4, "d", bba_type="3"),
           infant(5, "e", apgar1=6, weight=2300, apgar5=5), infant(6, "f", infant_icd10="Z371")]
    return data(ds, dx=dx, infants=inf)


# key ในรายชื่อ → (ฟังก์ชันหาตัวเลขเทียบ) · รายชื่อนับ "มารดา (AN)" ส่วน KPI บางตัวนับทารก — fixture นี้มีทารก 1 คน/แม่ ยกเว้นแฝด
@pytest.mark.parametrize("key,expected", [
    ("mothers", 6), ("normal", 3), ("abnormal", 3), ("twins", 1), ("bba", 1), ("still", 1),
    ("apgar1_low", 1), ("pph", 1), ("preterm", 1), ("asphyxia", 1), ("lbw", 1),
])
def test_members_counts(key, expected):
    assert len(listing.members(key, fixture_data(), CFG)) == expected


def test_members_agree_with_kpi_cards():
    d = fixture_data()
    kpi = {r["key"]: r["value"] for r in metrics.kpi_rows(d, CFG)}
    for key in ("mothers", "normal", "abnormal", "twins", "bba", "still", "apgar1_low"):
        assert len(listing.members(key, d, CFG)) == kpi[key], key


def test_members_agree_with_quality_grid():
    d = fixture_data()
    grid = {g["key"]: g["n"] for g in metrics.quality_grid(d, CFG)}
    for key in ("asphyxia", "pph", "preterm", "htn", "prolonged", "fetal_distress", "prom", "lbw"):
        assert len(listing.members(key, d, CFG)) == grid[key], key


def test_unknown_key_returns_none():
    assert listing.members("nope", fixture_data(), CFG) is None


def test_table_rows_have_identifiers_and_dx_only_from_that_mother():
    d = fixture_data()
    ans = listing.members("pph", d, CFG)
    head, rows = listing.table(ans, d, {"b": {"hn": "000123", "name": "นางทดสอบ ตัวอย่าง"}})
    assert head[:4] == ["วันที่คลอด", "HN", "AN", "ชื่อ-สกุล"]
    assert rows == [{"date": date(2026, 1, 2), "hn": "000123", "an": "b", "name": "นางทดสอบ ตัวอย่าง",
                     "dx": "O72, O80"}]


def test_table_missing_name_does_not_crash():
    d = fixture_data()
    _, rows = listing.table(["a"], d, {})
    assert rows[0]["hn"] == "" and rows[0]["name"] == ""
