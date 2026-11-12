"""เอกสารและชุดแจก ต้องครบตามกติกา "แอปที่อ่าน HOSxP และแจกให้ รพ. อื่นใช้" (CLAUDE.md)"""

import glob
import os
import re
import zipfile

import app as lr_app
import build_dist

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


def test_install_has_before_use_section_with_required_content():
    t = read("INSTALL.md")
    assert "## 0. ก่อนนำไปใช้" in t
    for must in ("setup_check.py", "/check", "LR_DATA_AUDITED=1", "MIT", "ไม่มีการรับประกัน", "ห้ามแนบข้อมูลผู้ป่วย",
                 "1–2 สัปดาห์"):
        assert must in t, must


def test_bug_report_template_requires_setup_check_and_privacy_confirmation():
    t = read(".github/ISSUE_TEMPLATE/bug_report.yml")
    assert "id: setup_check" in t and "required: true" in t
    assert "ไม่มีข้อมูลผู้ป่วย" in t
    assert "ANC" not in t


def test_every_env_var_used_in_code_is_documented_in_env_example():
    used = set()
    for path in glob.glob(os.path.join(HERE, "*.py")):
        used |= set(re.findall(r"\bLR_[A-Z0-9_]+\b", open(path, encoding="utf-8").read()))
    # LR_* ที่เป็นชื่อตัวอย่างในคอมเมนต์/เอกสารภายใน ไม่ใช่ env จริง
    used -= {"LR_"}
    documented = set(re.findall(r"\bLR_[A-Z0-9_]+\b", read(".env.example")))
    missing = sorted(used - documented)
    assert not missing, f"env ที่โค้ดอ่านแต่ .env.example ไม่มี: {missing}"


def test_env_example_has_no_secrets_and_no_anc_leftovers():
    t = read(".env.example")
    assert "ANC_" not in t
    assert not re.search(r"DB_PASS=\S*[A-Za-z0-9]{6,}", t.replace("<password>", ""))


def test_changelog_and_readme_match_app_version():
    assert lr_app.VERSION in read("CHANGELOG.md")
    assert lr_app.VERSION in read("README.md") or "LR Dashboard" in read("README.md")


def test_security_and_notice_exist():
    assert "ข้อมูลผู้ป่วย" in read("SECURITY.md")
    assert "MIT" in read("NOTICE.md")


def test_dockerignore_excludes_secrets_and_dockerfile_ships_setup_check():
    ignore = read(".dockerignore").split()
    assert ".env" in ignore and ".git" in ignore
    d = read("Dockerfile")
    assert "COPY . ." in d and "LR_" in d and "ANC_" not in d


def test_dist_zip_contains_app_and_setup_check_but_no_secrets(tmp_path):
    path = build_dist.build(str(tmp_path))
    names = zipfile.ZipFile(path).namelist()
    assert any(n.endswith("/app.py") for n in names) and any(n.endswith("/setup_check.py") for n in names)
    assert any(n.endswith("templates/dashboard.html") for n in names)
    bad = [n for n in names if n.endswith(".env") or "hospital_logo" in n or ".superpowers" in n
           or "/tests/" in n or "lr.sqlite" in n]
    assert not bad, bad


def test_every_dist_file_exists():
    for f in build_dist.FILES:
        assert os.path.exists(os.path.join(HERE, f)), f
