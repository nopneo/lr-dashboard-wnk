from datetime import date

import pytest

import metrics
from config import Config, fy_range
from tests.test_metrics import CFG, data, delivery, infant, val

MONTHS = ["2026-10", "2026-11"]


@pytest.mark.parametrize("text,expected", [
    ("Non-reactive", "neg"), ("NON REACTIVE", "neg"), ("Non reactive", "neg"), ("NR", "neg"), ("�NR", "neg"),
    ("neg", "neg"), ("Neg", "neg"), ("Negative", "neg"), ("-ve", "neg"), ("ไม่พบ", "neg"),
    ("Reactive", "pos"), ("Positive", "pos"), ("pos", "pos"), ("+ve", "pos"), ("R", "pos"), ("พบ", "pos"),
    ("์NR", "neg"), ("ืneg", "neg"), ("ื์NR", "neg"), ("ืำNR", "neg"),   # ตัวผันภาษาไทยนำหน้าจากแป้นพิมพ์
    ("1:8", "pos"), ("1 : 16", "pos"),                                                        # titer VDRL = reactive
    ("", "unclear"), (None, "unclear"), ("Inconclusive", "unclear"), ("รอผล", "unclear"),
])
def test_classify_result(text, expected):
    assert metrics.classify_result(text) == expected


def test_apgar_null_not_counted_and_no_crash():
    d = data([delivery("a")], infants=[infant(1, "a", apgar1=7), infant(2, "a", apgar1=None), infant(3, "a", apgar1=8)])
    assert val(metrics.kpi_rows(d, CFG), "apgar1_low") == 1


def test_twins_mother_once_babies_twice():
    d = data([delivery("a")], infants=[infant(1, "a"), infant(1, "a")])
    rows = metrics.kpi_rows(d, CFG)
    assert (val(rows, "mothers"), val(rows, "twins"), val(rows, "babies")) == (1, 1, 2)


def test_twin_denominator_not_double_counted():
    d = data([delivery("a", twin=1)], infants=[infant(1, "a"), infant(1, "a")])
    assert val(metrics.kpi_rows(d, CFG), "twins") == 1


def test_empty_period_everything_zero_or_none_never_crash():
    d = data()
    rows = metrics.kpi_rows(d, CFG)
    assert val(rows, "mothers") == 0 and val(rows, "babies") == 0
    assert metrics.pct(0, 0) is None
    assert metrics.monthly(d, CFG, MONTHS)[0] == {"ym": "2026-10", "normal": 0, "complicated": 0, "uncoded": 0, "referred": 0}
    assert all(isinstance(g["n"], int) for g in metrics.quality_grid(d, CFG))


def test_lab_positive_not_confused_with_non_reactive():
    labs = [{"an": "a", "lab_key": "syphilis", "result": "Reactive"},
            {"an": "b", "lab_key": "syphilis", "result": "Non-reactive"},
            {"an": "c", "lab_key": "syphilis", "result": "Non-reactive"}]
    d = data([delivery("a"), delivery("b"), delivery("c")], labs=labs)
    assert val(metrics.kpi_rows(d, CFG), "syphilis") == 1


def test_lab_without_rows_is_nodata_not_zero():
    rows = {r["key"]: r for r in metrics.kpi_rows(data([delivery("a")]), CFG)}
    assert rows["hiv"]["value"] is None and rows["hiv"]["status"] == "nodata"


def test_lab_only_counts_each_mother_once():
    labs = [{"an": "a", "lab_key": "hiv", "result": "pos"}, {"an": "a", "lab_key": "hiv", "result": "pos"}]
    d = data([delivery("a")], labs=labs)
    assert val(metrics.kpi_rows(d, CFG), "hiv") == 1


def test_monthly_splits_normal_complicated_and_refers():
    d = data([delivery("a", date(2026, 10, 3)), delivery("b", date(2026, 10, 9)), delivery("c", date(2026, 11, 2))],
             dx={"a": ["O800"], "b": ["O800", "O60"], "c": ["O800"]},
             refers=[{"ym": "2026-10", "n": 2}])
    m = metrics.monthly(d, CFG, MONTHS)
    assert m[0] == {"ym": "2026-10", "normal": 1, "complicated": 1, "uncoded": 0, "referred": 2}
    assert m[1] == {"ym": "2026-11", "normal": 1, "complicated": 0, "uncoded": 0, "referred": 0}


def test_quality_grid_counts():
    d = data([delivery("a"), delivery("b"), delivery("c")],
             dx={"a": ["O800", "O721"], "b": ["O800", "O60"], "c": ["O800", "O140"]},
             infants=[infant(1, "a", apgar5=5), infant(2, "b", weight=2400), infant(3, "c", weight=2400, dead=True)])
    g = {x["key"]: x for x in metrics.quality_grid(d, CFG)}
    assert g["asphyxia"]["n"] == 1 and g["pph"]["n"] == 1 and g["preterm"]["n"] == 1 and g["htn"]["n"] == 1
    assert g["lbw"]["n"] == 1 and g["lbw"]["den"] == 2          # ทารกตายไม่อยู่ในตัวหาร LBW


def test_rate_per_thousand():
    assert metrics.rate_per_thousand(25, 1000) == 25.0
    assert metrics.rate_per_thousand(1, 0) is None


def test_yearly_table_calls_loader_per_fiscal_year():
    calls = []

    def fake_loader(d1, d2):
        calls.append((d1, d2))
        return data([delivery("a")] * (d1.year % 5))

    t = metrics.yearly_table(fake_loader, [2568, 2569], CFG)
    assert calls == [fy_range(2568), fy_range(2569)]
    assert t["years"] == [2568, 2569]
    assert [r["key"] for r in t["rows"]] == list(metrics.KPI_KEYS)
    mothers = next(r for r in t["rows"] if r["key"] == "mothers")
    assert len(mothers["values"]) == 2
