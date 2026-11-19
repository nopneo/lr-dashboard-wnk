"""สร้างชุดติดตั้งสำหรับโรงพยาบาลอื่น → dist/lr_dashboard-<version>.zip

ใส่เฉพาะไฟล์กลาง ไม่มี .env / บัญชีผู้ใช้ / โลโก้ของ รพ.ผู้พัฒนา / tests
"""

import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["app.py", "audit.py", "cache.py", "charts.py", "config.py", "db.py", "listing.py", "loader.py", "manage.py", "privacy.py",
         "metrics.py", "queries.py", "render.py", "store.py", "setup_check.py", "build_dist.py",
         "requirements.txt", ".env.example", "README.md", "INSTALL.md", "SECURITY.md", "CHANGELOG.md",
         "Dockerfile", ".dockerignore", "LICENSE", "NOTICE.md",
         ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/config.yml"]
DIRS = ["templates", "static", "docs"]
SKIP = {os.path.join("static", "img", "hospital_logo.png")}
SKIP_PARTS = ("__pycache__", os.sep + "superpowers" + os.sep)


def build(out_dir=None):
    version = re.search(r'VERSION = "([^"]+)"', open(os.path.join(HERE, "app.py"), encoding="utf-8").read())[1]
    out_dir = out_dir or os.path.join(HERE, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"lr_dashboard-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(os.path.join(HERE, f), f"lr_dashboard/{f}")
        for d in DIRS:
            for root, _, names in os.walk(os.path.join(HERE, d)):
                for n in sorted(names):
                    full = os.path.join(root, n)
                    rel = os.path.relpath(full, HERE)
                    if rel in SKIP or any(p in rel for p in SKIP_PARTS):
                        continue
                    z.write(full, "lr_dashboard/" + rel.replace(os.sep, "/"))
    return out


def main():
    out = build()
    print(out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
