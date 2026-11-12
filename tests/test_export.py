import pytest

import app as lr_app
import render


@pytest.fixture
def client(monkeypatch):
    lr_app._export_cache = lr_app.TTLCache(maxsize=4)
    return lr_app.app.test_client()


def test_export_renders_print_url_and_returns_attachment(client, monkeypatch):
    seen = {}

    def fake_render(fmt, url, out_path):
        seen.update(fmt=fmt, url=url)
        open(out_path, "wb").write(b"\xff\xd8fakejpg")

    monkeypatch.setattr(render, "render_to", fake_render)
    r = client.get("/export.jpg?fy=2569")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data.startswith(b"\xff\xd8")
    assert "print=1" in seen["url"] and "fy=2569" in seen["url"]
    assert "attachment" in r.headers["Content-Disposition"] and "lr_2569" in r.headers["Content-Disposition"]


@pytest.mark.parametrize("fmt", ["exe", "html", "gif"])
def test_export_rejects_unknown_formats(client, fmt):
    assert client.get(f"/export.{fmt}").status_code == 404


def test_export_disabled_by_env(client, monkeypatch):
    monkeypatch.setattr(lr_app, "EXPORT_ENABLED", False)
    assert client.get("/export.jpg").status_code == 404


def test_export_failure_returns_500_json_not_traceback(client, monkeypatch):
    def boom(fmt, url, out):
        raise RuntimeError("no chrome")

    monkeypatch.setattr(render, "render_to", boom)
    r = client.get("/export.pdf")
    assert r.status_code == 500 and "no chrome" not in r.get_data(as_text=True)
