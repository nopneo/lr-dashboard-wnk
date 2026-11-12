import sys
from datetime import date, timedelta

import pytest

import audit
import loader
import setup_check
from config import Config
from tests.test_metrics import data


def make_fetch(missing=(), last_delivery=None, grants="GRANT SELECT ON hos.* TO 'ro'@'%'", thai="VDRL"):
    def fetch(sql, args=None):
        s = " ".join(sql.split()).lower()
        if "select version()" in s:
            return [{"v": "10.5.0-MariaDB", "n": "now", "d": "hos"}]
        if "show grants" in s:
            return [{"g": grants}]
        if "information_schema.tables" in s:
            return [{"t": t} for t in setup_check.TABLES if t not in missing]
        if "from labour_lab" in s:
            return [{"name": thai}]
        if "max(labor_date)" in s:
            return [{"d": (last_delivery or date.today()).isoformat()}]
        raise AssertionError("unexpected sql: " + s[:80])
    return fetch


def statuses(rows):
    return {t: s for s, t, _ in rows}


def test_risky_privs_flags_write_rights_only_for_this_db():
    assert setup_check.risky_privs(["GRANT ALL PRIVILEGES ON hos.* TO x"], "hos") == ["ALL PRIVILEGES"]
    assert setup_check.risky_privs(["GRANT SELECT ON hos.* TO x"], "hos") == []
    assert setup_check.risky_privs(["GRANT DELETE ON other.* TO x"], "hos") == []
    assert setup_check.risky_privs(["GRANT SELECT ON *.* TO x WITH GRANT OPTION"], "hos") == ["GRANT OPTION"]


def test_db_checks_all_good():
    rows, ok = setup_check._db_checks(make_fetch())
    assert ok and not [r for r in rows if r[0] == "bad"]


def test_missing_required_table_is_a_bad_row_naming_it():
    rows, ok = setup_check._db_checks(make_fetch(missing=("ipt_labour_lab",)))
    assert not ok
    assert any(s == "bad" and "ipt_labour_lab" in d for s, _, d in rows)


def test_required_tables_cover_everything_the_queries_read():
    needed = {"ipt_pregnancy", "ipt_labour", "ipt_labour_infant", "ipt_labour_lab", "iptdiag", "iptoprt", "ipt",
              "ipt_newborn", "referout", "lab_head", "lab_order", "lab_items", "dchstts", "patient"}
    assert needed <= set(setup_check.TABLES)


def test_write_privileges_are_bad():
    rows, _ = setup_check._db_checks(make_fetch(grants="GRANT ALL PRIVILEGES ON hos.* TO x"))
    assert any(s == "bad" and "สิทธิ์" in t for s, t, _ in rows)


def test_stale_last_delivery_warns():
    rows, ok = setup_check._db_checks(make_fetch(last_delivery=date.today() - timedelta(days=400)))
    assert ok and any(s == "warn" and "คลอดล่าสุด" in t for s, t, _ in rows)


def test_garbled_thai_warns():
    rows, _ = setup_check._db_checks(make_fetch(thai="���???"))
    assert any(s == "warn" and "ภาษาไทย" in t for s, t, _ in rows)


def test_db_unreachable_is_bad_and_stops():
    def boom(sql, args=None):
        raise ConnectionError("refused")
    rows, ok = setup_check._db_checks(boom)
    assert not ok and rows[0][0] == "bad" and "ต่อฐานข้อมูลไม่ได้" in rows[0][1]


def test_data_audit_problems_are_warnings_not_blockers(monkeypatch):
    monkeypatch.setattr(setup_check, "_env_checks", lambda: [])
    monkeypatch.setattr(audit, "audit", lambda d1, d2, cfg: [
        {"key": "k", "title": "รหัสทดสอบ", "status": "bad", "hint": "ตรวจรหัส"}])
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data())
    rows = setup_check.run(fetch=make_fetch(), cfg=Config(), audit=True, days=30)
    mine = [r for r in rows if "รหัสทดสอบ" in r[1]]
    assert mine and mine[0][0] == "warn"


def test_list_check_states(monkeypatch, tmp_path):
    import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "lr.sqlite"))
    monkeypatch.setattr(store, "_ready", False)
    monkeypatch.delenv("LR_SECRET_KEY", raising=False)
    assert setup_check._list_check()[0][0] == "info"
    monkeypatch.setenv("LR_SECRET_KEY", "short")
    assert setup_check._list_check()[0][0] == "warn"
    monkeypatch.setenv("LR_SECRET_KEY", "k" * 40)
    assert setup_check._list_check()[0][0] == "warn"          # เปิดแล้วแต่ยังไม่มีบัญชี
    store.add_user("nurse1", "correct-horse-1", "x")
    assert setup_check._list_check()[0][0] == "ok"


def test_main_exit_code_is_1_when_any_bad(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["setup_check.py", "--no-audit"])
    monkeypatch.setattr(setup_check, "run", lambda **kw: [("ok", "a", "x"), ("bad", "b", "y")])
    assert setup_check.main() == 1
    assert "ต้องแก้" in capsys.readouterr().out


def test_main_exit_code_is_0_with_only_warnings(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["setup_check.py", "--no-audit"])
    monkeypatch.setattr(setup_check, "run", lambda **kw: [("ok", "a", "x"), ("warn", "b", "y")])
    assert setup_check.main() == 0
