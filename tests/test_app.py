from datetime import date

import pytest

import app as lr_app
import audit
import loader
import queries
from config import fy_range
from tests.test_metrics import data, delivery, infant


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("LR_DATA_AUDITED", raising=False)
    monkeypatch.setattr(queries, "recent_counts", lambda today, cfg: {"days7": 2})
    return lr_app.app.test_client()


def fake_data(**kw):
    base = dict(deliveries=[delivery("6900001", date(2026, 1, 5)), delivery("6900002", date(2026, 2, 5))],
                dx={"6900001": ["O800"], "6900002": ["O800", "O721"]}, infants=[infant(1, "6900001")])
    base.update(kw)
    return data(**base)


@pytest.fixture
def loaded(monkeypatch):
    calls = []

    def fake(d1, d2, cfg):
        calls.append((d1, d2))
        return fake_data()

    monkeypatch.setattr(loader, "load_data", fake)
    return calls


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_data(as_text=True).strip() == "ok"


def test_index_ok_and_banner_until_audited(client, loaded, monkeypatch):
    html = client.get("/").get_data(as_text=True)
    assert "ตัวเลขยังไม่ได้ตรวจ" in html
    monkeypatch.setenv("LR_DATA_AUDITED", "1")
    assert "ตัวเลขยังไม่ได้ตรวจ" not in client.get("/").get_data(as_text=True)


def test_banner_hidden_in_print_mode(client, loaded):
    assert "ตัวเลขยังไม่ได้ตรวจ" not in client.get("/?print=1").get_data(as_text=True)


def test_fy_param_selects_fiscal_year_range(client, loaded):
    client.get("/?fy=2569")
    assert loaded[0] == fy_range(2569)


@pytest.mark.parametrize("bad", ["abc", "1999", "99999", ""])
def test_bad_fy_falls_back_without_error(client, loaded, bad):
    r = client.get(f"/?fy={bad}")
    assert r.status_code == 200
    assert loaded[0] == fy_range(lr_app.current_fy())


def test_empty_period_renders_without_none_or_nan(client, monkeypatch):
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: data())
    html = client.get("/").get_data(as_text=True)
    assert "None" not in html and "NaN" not in html and "ZeroDivision" not in html


def test_index_has_no_patient_identifiers(client, loaded):
    html = client.get("/").get_data(as_text=True)
    assert "6900001" not in html and "6900002" not in html


def test_load_error_shows_warning_not_500(client, monkeypatch):
    d = fake_data()
    d["errors"] = ["infants"]
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: d)
    r = client.get("/")
    assert r.status_code == 200 and "infants" in r.get_data(as_text=True)


def test_yearly_lists_13_style_rows_and_nodata_text(client, loaded):
    html = client.get("/yearly").get_data(as_text=True)
    assert "จำนวนมารดาที่คลอด" in html and "ไม่มีข้อมูล" in html     # hiv/amph ไม่มีแหล่ง
    assert len(loaded) >= 6                                         # โหลดย้อนหลัง 6 ปีงบ (ครอบคลุม 5 ปีที่ผ่านมา + ปีปัจจุบัน)
    assert f"ปี {lr_app.current_fy() - 5}" in html


def test_check_blocked_outside_lan_and_open_inside(client, loaded, monkeypatch):
    monkeypatch.setattr(audit, "audit", lambda d1, d2, cfg: [
        {"key": "k", "title": "รหัสทดสอบ", "app_uses": "O80", "found": [{"code": "O80", "name": "", "n": 3}],
         "status": "ok", "env": "LR_NORMAL_ICD", "hint": ""}])
    monkeypatch.setattr(audit, "reconcile", lambda d1, d2, cfg: {"sources": {"a": 1}, "max_diff": 0, "status": "ok"})
    out = client.get("/check", environ_overrides={"REMOTE_ADDR": "8.8.8.8"})
    assert out.status_code in (403, 404)
    ok = client.get("/check", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert ok.status_code == 200 and "รหัสทดสอบ" in ok.get_data(as_text=True)


def test_prefix_header_rewrites_links(client, loaded):
    html = client.get("/", headers={"X-Forwarded-Prefix": "/lr"}).get_data(as_text=True)
    assert 'href="/lr/yearly"' in html


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_donut_explains_that_total_includes_referred(client, loaded):
    html = client.get("/").get_data(as_text=True)
    assert "รวมส่งต่อ" in html          # ตัวเลขกลางวงรวมผู้ส่งต่อที่ไม่ได้คลอดที่ รพ. — ต้องบอกให้ชัด


def test_print_mode_states_the_period_since_toolbar_is_hidden(client, loaded):
    html = client.get("/?fy=2569&print=1").get_data(as_text=True)
    assert "ปีงบประมาณ 2569" in html and "1 ตุลาคม 2568" in html and "30 กันยายน 2569" in html
    assert "<select" not in html
