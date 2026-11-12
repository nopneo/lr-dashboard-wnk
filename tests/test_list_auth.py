import pytest

import app as lr_app
import loader
import queries
import store
from tests.test_app import fake_data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "lr.sqlite"))
    monkeypatch.setattr(store, "_ready", False)
    monkeypatch.setattr(lr_app.app, "secret_key", "test-secret-key")
    monkeypatch.setattr(loader, "load_data", lambda d1, d2, cfg: fake_data())
    monkeypatch.setattr(queries, "case_names", lambda ans: {"6900001": {"hn": "000777", "name": "นางทดสอบ ตัวอย่าง"}})
    store.add_user("nurse1", "correct-horse-1", "พยาบาล LR")
    return lr_app.app.test_client()


def csrf(client, path="/login"):
    client.get(path)
    with client.session_transaction() as s:
        s["csrf"] = "tok"
    return "tok"


def do_login(client, user="nurse1", pw="correct-horse-1", next_=None):
    tok = csrf(client)
    url = "/login" + (f"?next={next_}" if next_ else "")
    return client.post(url, data={"username": user, "password": pw, "csrf": tok})


def test_lists_and_login_disabled_without_secret_key(monkeypatch):
    monkeypatch.setattr(lr_app.app, "secret_key", None)
    c = lr_app.app.test_client()
    assert c.get("/list").status_code == 404
    assert c.get("/login").status_code == 404


def test_list_requires_login_and_redirects_with_next(client):
    r = client.get("/list/normal")
    assert r.status_code == 302 and "/login?next=" in r.headers["Location"]


def test_login_then_list_shows_identifiers_and_is_not_cached(client):
    assert do_login(client).status_code == 302
    r = client.get("/list/normal")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "6900001" in html and "000777" in html
    assert r.headers["Cache-Control"] == "no-store"


def test_wrong_password_shows_error_and_logs_failure(client):
    r = do_login(client, pw="wrong")
    assert r.status_code == 200 and "ไม่ถูกต้อง" in r.get_data(as_text=True)
    assert store.recent_failures("nurse1", None, 15)[0] == 1


def test_lockout_after_too_many_failures(client):
    for _ in range(lr_app.LOGIN_MAX_USER):
        do_login(client, pw="wrong")
    assert do_login(client).status_code == 429          # แม้ใส่รหัสถูก ก็ถูกกันชั่วคราว


def test_login_post_without_csrf_rejected(client):
    client.get("/login")
    r = client.post("/login", data={"username": "nurse1", "password": "correct-horse-1"})
    assert r.status_code == 400


@pytest.mark.parametrize("bad", ["//evil.example", "https://evil.example", "/\\evil.example"])
def test_open_redirect_blocked(client, bad):
    r = do_login(client, next_=bad)
    assert r.status_code == 302 and "evil" not in r.headers["Location"]


def test_view_is_written_to_audit_log(client):
    do_login(client)
    client.get("/list/pph")
    actions = [(a["action"], a["detail"]) for a in store.audit("nurse1")]
    assert any(a == "view_list" and "k=pph" in (d or "") for a, d in actions)


def test_unknown_list_key_404(client):
    do_login(client)
    assert client.get("/list/not-a-key").status_code == 404


def test_logout_requires_csrf_and_clears_session(client):
    do_login(client)
    assert client.post("/logout", data={}).status_code == 400
    client.get("/list")                      # หน้าที่แสดงปุ่มออกจากระบบ สร้าง CSRF token ให้
    with client.session_transaction() as s:
        tok = s["csrf"]
    assert client.post("/logout", data={"csrf": tok}).status_code == 302
    assert client.get("/list/normal").status_code == 302


def test_main_page_never_shows_identifiers_even_when_logged_in(client):
    do_login(client)
    html = client.get("/").get_data(as_text=True)
    assert "6900001" not in html and "000777" not in html


def test_session_cookie_has_own_name_and_is_httponly(client):
    r = do_login(client)
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "lr_session=" in cookies and "HttpOnly" in cookies and "SameSite=Lax" in cookies
