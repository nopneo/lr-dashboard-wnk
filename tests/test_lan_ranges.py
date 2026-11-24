"""IP ภายในระบุช่วงเอง — ไม่ใช้ ip.is_private ที่นับช่วงสาธารณะบางช่วง (198.18/15, 203.0.113/24) เป็น private"""
import pytest

import app as app_mod


@pytest.mark.parametrize("ip, lan", [
    ("192.168.11.5", True), ("10.1.2.3", True), ("172.20.0.1", True), ("127.0.0.1", True), ("::1", True),
    ("198.18.0.1", False), ("203.0.113.7", False), ("100.64.1.1", False), ("8.8.8.8", False),
    ("172.32.0.1", False), ("::ffff:192.168.1.1", True), ("::ffff:8.8.8.8", False), ("junk", False)])
def test_from_lan_explicit_ranges(ip, lan):
    with app_mod.app.test_request_context("/", environ_base={"REMOTE_ADDR": ip}):
        assert app_mod._from_lan() is lan


def test_lan_nets_still_counts_hospital_public_ip(monkeypatch):
    monkeypatch.setattr(app_mod, "LAN_NETS", app_mod._nets("203.0.113.10"))
    with app_mod.app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.10"}):
        assert app_mod._from_lan() is True


def test_cloudflare_request_from_private_looking_ip_is_public():
    h = {"X-Forwarded-For": "10.0.0.5, 162.158.1.1", "CF-Connecting-IP": "10.0.0.5"}
    with app_mod.app.test_request_context("/", headers=h, environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert app_mod._from_lan() is False
