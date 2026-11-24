"""หน้าสาธารณะ (คนนอก รพ. ไม่ได้ login) ต้องไม่ให้ย้อนหาภาวะ/ผลตรวจของการคลอดรายคนจากตัวเลขรวม"""
from datetime import date

import pytest

import app as lr_app
import loader
import metrics
import privacy
from tests.test_app import client, fake_data  # noqa: F401  (fixture)

PUBLIC = {"REMOTE_ADDR": "8.8.8.8"}
LAN = {"REMOTE_ADDR": "192.168.1.5"}


@pytest.fixture
def ranges(monkeypatch):
    calls = []

    def fake(d1, d2, cfg):
        calls.append((d1, d2))
        return fake_data()
    monkeypatch.setattr(loader, "load_data", fake)
    return calls


def test_lan_keeps_exact_custom_range(client, ranges):
    client.get("/?d1=2026-01-05&d2=2026-02-01", environ_base=LAN)
    assert ranges[-1] == (date(2026, 1, 5), date(2026, 2, 1))


def test_public_custom_range_snapped_to_months(client, ranges):
    # ช่วง 28 วันกับ 29 วันที่เริ่มวันเดียวกัน → หลังปัดได้ช่วงเดียวกัน ลบหาตัวเลขรายวันไม่ได้
    client.get("/?d1=2026-01-05&d2=2026-02-01", environ_base=PUBLIC)
    client.get("/?d1=2026-01-05&d2=2026-02-02", environ_base=PUBLIC)
    assert ranges[-2] == ranges[-1] == (date(2026, 1, 1), date(2026, 2, 28))


def test_public_fiscal_year_unchanged(client, ranges):
    from config import fy_range
    client.get("/?fy=2569", environ_base=PUBLIC)
    assert ranges[0] == fy_range(2569)


def test_public_quality_small_cells_hidden(client, ranges):
    lan = client.get("/?fy=2569", environ_base=LAN).get_data(as_text=True)
    pub = client.get("/?fy=2569", environ_base=PUBLIC).get_data(as_text=True)
    assert "ข้อมูลสาธารณะ" in pub and "ข้อมูลสาธารณะ" not in lan
    assert "&lt;5<small> ราย</small>" in pub
    assert "&lt;5<small> ราย</small>" not in lan


def test_public_ctx_does_not_mutate_original():
    ctx = {"quality": [{"key": "pph", "n": 1, "den": 2}], "kpi": {"hiv": {"key": "hiv", "value": 1}}}
    out = privacy.public_ctx(ctx)
    assert out["quality"][0]["n"] == "<5" and out["kpi"]["hiv"]["value"] == "<5"
    assert ctx["quality"][0]["n"] == 1 and ctx["kpi"]["hiv"]["value"] == 1


def test_public_yearly_sensitive_rows(client, monkeypatch):
    table = {"years": [2568, 2569], "errors": [[], []],
             "rows": [{"key": "hiv", "label": "มารดา HIV", "values": [1, 0]},
                      {"key": "mothers", "label": "จำนวนมารดาที่คลอด", "values": [3, 4]},
                      {"key": "still", "label": "เด็กเกิดไร้ชีพ", "values": [None, 7]}]}
    monkeypatch.setattr(metrics, "yearly_table", lambda *a, **k: table)
    pub = client.get("/yearly", environ_base=PUBLIC).get_data(as_text=True)
    lan = client.get("/yearly", environ_base=LAN).get_data(as_text=True)
    assert "ข้อมูลสาธารณะ" in pub and "&lt;5" in pub and "ข้อมูลสาธารณะ" not in lan
    t = privacy.public_yearly(table)
    assert t["rows"][0]["values"] == ["<5", 0]          # HIV 1 → <5 · 0 คงไว้
    assert t["rows"][1]["values"] == [3, 4]             # จำนวนคลอดไม่อ่อนไหว
    assert t["rows"][2]["values"] == [None, 7]
    assert table["rows"][0]["values"] == [1, 0]          # ไม่แก้ต้นฉบับ


def test_public_flag_from_loopback(client, ranges):
    client.get("/?d1=2026-01-05&d2=2026-02-01&public=1", environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert ranges[-1] == (date(2026, 1, 1), date(2026, 2, 28))


def test_export_public_flag_and_separate_cache(client, ranges, monkeypatch):
    seen = []

    def fake_render(fmt, url, out):
        seen.append(url)
        open(out, "wb").write(b"x")
    monkeypatch.setattr(lr_app.render, "render_to", fake_render)
    monkeypatch.setattr(lr_app, "EXPORT_ENABLED", True)
    lr_app._export_cache._data.clear()
    assert client.get("/export.png?fy=2569", environ_base=LAN).status_code == 200
    assert client.get("/export.png?fy=2569", environ_base=PUBLIC).status_code == 200
    assert len(seen) == 2 and "public=1" not in seen[0] and "public=1" in seen[1]


def test_month_window():
    assert privacy.month_window(date(2026, 1, 5), date(2026, 2, 1), today=date(2026, 6, 1)) == \
        (date(2026, 1, 1), date(2026, 2, 28))
    assert privacy.month_window(date(2026, 6, 3), date(2026, 6, 9), today=date(2026, 6, 10)) == \
        (date(2026, 6, 1), date(2026, 6, 10))


def test_disabled_with_zero(client, ranges, monkeypatch):
    monkeypatch.setattr(privacy, "MIN_CELL", 0)
    client.get("/?d1=2026-01-05&d2=2026-02-01", environ_base=PUBLIC)
    assert ranges[-1] == (date(2026, 1, 5), date(2026, 2, 1))
