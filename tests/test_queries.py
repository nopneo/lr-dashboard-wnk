import re
from datetime import date

import pytest

import db
import queries
from config import Config

D1, D2 = date(2025, 10, 1), date(2026, 9, 30)
CFG = Config()


class _Calls(list):
    fake = None


@pytest.fixture
def calls(monkeypatch):
    log = _Calls()

    def fake(sql, args=None):
        log.append((sql, args))
        return fake.rows

    fake.rows = []
    monkeypatch.setattr(db, "fetch", fake)
    log.fake = fake
    return log


FUNCS = ["deliveries", "delivery_dx", "delivery_ops", "infants", "lab_results", "lr_refers"]


@pytest.mark.parametrize("name", FUNCS)
def test_range_passed_as_params(calls, name):
    getattr(queries, name)(D1, D2, CFG)
    sql, args = calls[0]
    assert args["d1"] == D1 and args["d2"] == D2


@pytest.mark.parametrize("name", FUNCS)
def test_no_hardcoded_codes_in_sql(calls, name):
    getattr(queries, name)(D1, D2, CFG)
    sql = calls[0][0]
    assert not re.search(r"'[OPZ]\d{2}", sql), "รหัส ICD-10 ตายตัวใน SQL"
    assert not re.search(r"'\d{2,3}'", sql), "รหัสตัวเลขตายตัวใน SQL"


def test_infants_passes_config_codes(calls):
    queries.infants(D1, D2, Config(dead_dchstts=("08",), bba_types=("3", "4")))
    args = calls[0][1]
    assert args["dead"] == ("08",)
    assert args["bba"] == ("3", "4")


def test_infants_typed_rows(calls):
    calls.fake.rows = [{"ipt_labour_id": "5", "an": "A1", "birth_date": date(2026, 10, 1), "ym": "2026-10",
                        "weight": "2900", "apgar1": None, "apgar5": "9", "dchstts": "09", "dead": "N",
                        "bba_type": "3", "labor_ba_id": None, "infant_icd10": None, "days_to_dch": "2"}]
    (r,) = queries.infants(D1, D2, CFG)
    assert r["ipt_labour_id"] == 5 and r["weight"] == 2900
    assert r["apgar1"] is None and r["apgar5"] == 9
    assert r["dead"] is True            # dchstts 09 อยู่ใน dead_dchstts
    assert r["bba_type"] == "3" and r["days_to_dch"] == 2


def test_deliveries_typed_rows_and_abort_flag(calls):
    calls.fake.rows = [{"an": "A1", "labor_date": "2026-09-30", "ym": "2026-09", "twin": "1", "is_abort": "0"},
                       {"an": "A2", "labor_date": date(2026, 10, 1), "ym": "2026-10", "twin": None, "is_abort": "1"}]
    a, b = queries.deliveries(D1, D2, CFG)
    assert a["labor_date"] == date(2026, 9, 30) and a["twin"] == 1 and a["is_abort"] == 0
    assert b["twin"] == 0 and b["is_abort"] == 1


def test_lab_query_never_sends_empty_in_list(calls):
    queries.lab_results(D1, D2, Config(syphilis_labs=(), hiv_labs=(), hbv_labs=()))
    args = calls[0][1]
    for k in ("syph", "hiv", "hbv"):
        assert len(args[k]) >= 1, f"{k}: in () ทำให้ SQL ผิด"


def test_lab_results_rows_carry_lab_key(calls):
    calls.fake.rows = [{"an": "A1", "lab_key": "hiv", "result": "Non-reactive"}]
    assert queries.lab_results(D1, D2, CFG) == [{"an": "A1", "lab_key": "hiv", "result": "Non-reactive"}]


def test_refers_uses_prefix_params(calls):
    queries.lr_refers(D1, D2, Config(refer_dx_prefix=("O", "Z3")))
    args = calls[0][1]
    assert "O%" in args.values() and "Z3%" in args.values()


def test_recent_counts_window(calls):
    calls.fake.rows = [{"n": "4"}]
    assert queries.recent_counts(date(2026, 11, 12), CFG) == {"days7": 4}
    args = calls[0][1]
    assert args["d1"] == date(2026, 11, 6) and args["d2"] == date(2026, 11, 12)


def test_null_or_blank_codes_dropped(calls):
    calls.fake.rows = [{"an": "A1", "icd10": None}, {"an": "A1", "icd10": ""}, {"an": "A1", "icd10": "O800"}]
    assert queries.delivery_dx(D1, D2, CFG) == [{"an": "A1", "icd10": "O800"}]
    calls.fake.rows = [{"an": "A1", "icd9": None}, {"an": "A1", "icd9": "7270"}]
    assert queries.delivery_ops(D1, D2, CFG) == [{"an": "A1", "icd9": "7270"}]
