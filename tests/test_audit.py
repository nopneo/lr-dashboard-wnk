from datetime import date

import pytest

import audit
import db
from config import Config
from tests.test_metrics import data, delivery, infant

D1, D2 = date(2025, 10, 1), date(2026, 9, 30)
CFG = Config()


def route(monkeypatch, table_rows=None, boom=None):
    table_rows = table_rows or {}

    def fake(sql, args=None):
        if boom and boom in sql:
            raise RuntimeError("db error")
        for key, rows in table_rows.items():
            if key in sql:
                return rows
        return []

    monkeypatch.setattr(db, "fetch", fake)


def test_reconcile_agreeing_sources_ok(monkeypatch):
    route(monkeypatch, {"from ipt_pregnancy": [{"n": 78}], "from ipt_labour_infant": [{"n": 78}],
                        "from labor ": [{"n": 78}], "from iptdiag": [{"n": 77}]})
    r = audit.reconcile(D1, D2, CFG)
    assert r["status"] == "ok" and r["max_diff"] == 1


def test_reconcile_mismatch_warns_and_keeps_every_source(monkeypatch):
    route(monkeypatch, {"from ipt_pregnancy": [{"n": 120}], "from ipt_labour_infant": [{"n": 80}],
                        "from labor ": [{"n": 80}], "from iptdiag": [{"n": 79}]})
    r = audit.reconcile(D1, D2, CFG)
    assert r["status"] == "warn" and r["max_diff"] == 41
    assert r["sources"] == {"ipt_pregnancy": 120, "ipt_labour_infant_mothers": 80, "labor": 80, "icd_delivery": 79}


def test_audit_items_have_env_and_app_uses(monkeypatch):
    route(monkeypatch)
    items = audit.audit(D1, D2, CFG)
    assert len(items) >= 8
    for it in items:
        assert it["env"].startswith("LR_") or (it["key"] == "alcohol_smoke" and it["env"] == "—"), it["key"]
        assert it["app_uses"], it["key"]
        assert it["status"] in ("ok", "warn", "bad")


def test_one_failing_item_does_not_stop_the_rest(monkeypatch):
    route(monkeypatch, boom="ipt_labour_lab")
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert items["labs"]["status"] == "bad"
    assert "normal_icd" in items and items["normal_icd"]["status"] != "bad"


def test_unconfigured_source_is_flagged_not_silent(monkeypatch):
    route(monkeypatch)
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert items["alcohol_smoke"]["status"] == "warn"


def test_dead_dchstts_warns_when_configured_codes_absent(monkeypatch):
    route(monkeypatch, {"from ipt_labour_infant": [{"code": "05", "n": 79}]})
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert items["dead_dchstts"]["status"] == "warn"


def test_completeness_counts_orphans_and_missing_apgar():
    d = data([delivery("a"), delivery("b")], infants=[infant(1, "a", apgar1=None), infant(2, "z")])
    c = {x["key"]: x for x in audit.completeness(d, CFG)}
    assert c["mothers_without_infant"]["n"] == 1
    assert c["infants_without_mother"]["n"] == 1
    assert c["apgar1_missing"]["n"] == 1 and c["apgar1_missing"]["den"] == 2


def test_reconcile_pregnancy_source_uses_delivery_evidence(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: seen.append((sql, args)) or [{"n": 1}])
    audit.reconcile(D1, D2, CFG)
    sql, args = next((s, a) for s, a in seen if "from ipt_pregnancy" in s)
    assert args["deliv"] == CFG.delivery_icd10 and "ipt_labour_infant" in sql


def test_dead_dchstts_ok_when_master_confirms_codes_even_if_unseen(monkeypatch):
    route(monkeypatch, {"from ipt_labour_infant": [{"code": "05", "n": 79}],
                        "from dchstts": [{"code": "08", "name": "Dead Still Birth"}, {"code": "09", "name": "Dead"}]})
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert items["dead_dchstts"]["status"] == "ok"


def test_stillbirth_item_groups_icd_at_four_chars(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "fetch", lambda sql, args=None: seen.append(sql) or [])
    audit.audit(D1, D2, CFG)
    still = [s for s in seen if "iptdiag" in s and "codes" in s and ", 4)" in s]
    assert still, "stillbirth ต้องจัดกลุ่ม 4 ตัวอักษร (Z37.1 ≠ Z37.0)"


def test_amph_item_lists_candidate_lab_items(monkeypatch):
    route(monkeypatch, {"from lab_items": [{"code": "139", "name": "Methamphetamine", "n": 0}]})
    items = {i["key"]: i for i in audit.audit(D1, D2, CFG)}
    assert items["amph"]["found"] and items["amph"]["env"] == "LR_LAB_AMPH"
