from datetime import date

import loader
import queries
from config import Config, fy_range

CFG = Config()


def _patch(monkeypatch, **over):
    base = {
        "deliveries": [{"an": "A1", "labor_date": date(2026, 9, 30), "ym": "2026-09", "twin": 0, "is_abort": 0}],
        "delivery_dx": [{"an": "A1", "icd10": "O800"}, {"an": "A1", "icd10": "Z370"}],
        "delivery_ops": [{"an": "A1", "icd9": "7359"}],
        "infants": [{"ipt_labour_id": 1, "an": "A1"}],
        "lab_results": [{"an": "A1", "lab_key": "hiv", "result": "neg"}],
        "lr_refers": [{"ym": "2026-09", "n": 2}],
    }
    base.update(over)
    seen = {}
    for name, rows in base.items():
        def fn(d1, d2, cfg, _n=name, _r=rows):
            seen[_n] = (d1, d2)
            if isinstance(_r, Exception):
                raise _r
            return _r
        monkeypatch.setattr(queries, name, fn)
    return seen


def test_load_data_shapes(monkeypatch):
    d1, d2 = fy_range(2569)
    seen = _patch(monkeypatch)
    data = loader.load_data(d1, d2, CFG)
    assert data["dx_by_an"] == {"A1": {"O800", "Z370"}}
    assert data["ops_by_an"] == {"A1": {"7359"}}
    assert data["labs"][0]["lab_key"] == "hiv"
    assert data["refers"] == [{"ym": "2026-09", "n": 2}]
    assert data["errors"] == []
    # ช่วงปิดหัวท้ายส่งถึงทุก query (ขอบปีงบ 30 ก.ย. / 1 ต.ค.)
    assert all(v == (date(2025, 10, 1), date(2026, 9, 30)) for v in seen.values())


def test_one_failing_source_does_not_break_others(monkeypatch):
    _patch(monkeypatch, infants=RuntimeError("db down"))
    data = loader.load_data(date(2025, 10, 1), date(2026, 9, 30), CFG)
    assert data["infants"] == []
    assert data["errors"] == ["infants"]
    assert len(data["deliveries"]) == 1
