import pytest

import store


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "lr.sqlite"))
    monkeypatch.setattr(store, "_ready", False)


def test_add_user_and_check_login():
    store.add_user("nurse1", "correct-horse-1", "พยาบาล LR")
    u = store.check_login("nurse1", "correct-horse-1")
    assert u and u["display"] == "พยาบาล LR"


def test_password_hashed_with_pbkdf2_sha256_not_plain():
    store.add_user("nurse1", "correct-horse-1", "x")
    with store.conn() as c:
        h = c.execute("select pw_hash from users").fetchone()[0]
    assert h.startswith("pbkdf2:sha256") and "correct-horse-1" not in h


def test_wrong_password_and_unknown_user():
    store.add_user("nurse1", "correct-horse-1", "x")
    assert store.check_login("nurse1", "nope") is None
    assert store.check_login("ghost", "correct-horse-1") is None


def test_disabled_user_cannot_login_or_load():
    store.add_user("nurse1", "correct-horse-1", "x")
    uid = store.check_login("nurse1", "correct-horse-1")["id"]
    assert store.set_active("nurse1", False) == 1
    assert store.check_login("nurse1", "correct-horse-1") is None
    assert store.get_user(uid) is None


def test_set_password():
    store.add_user("nurse1", "old-password-1", "x")
    store.set_password("nurse1", "new-password-2")
    assert store.check_login("nurse1", "old-password-1") is None
    assert store.check_login("nurse1", "new-password-2")


def test_audit_log_and_failures_by_user_and_ip():
    for _ in range(3):
        store.log("nurse1", "login_fail", ip="10.0.0.5")
    store.log("other", "login_fail", ip="10.0.0.5")
    store.log("nurse1", "view_list", "k=normal", ip="10.0.0.5")
    assert store.recent_failures("nurse1", "10.0.0.5", 15) == (3, 4)
    rows = store.audit(username="nurse1", limit=10)
    assert rows[0]["action"] == "view_list" and len(rows) == 4


def test_duplicate_username_rejected():
    store.add_user("nurse1", "correct-horse-1", "x")
    with pytest.raises(Exception):
        store.add_user("nurse1", "another-pass-9", "y")
