"""ติดตั้ง LR Dashboard ขึ้นเซิร์ฟเวอร์ รพ.วังน้ำเขียว ผ่าน SSH (paramiko)

เข้าเครื่องด้วย SSH key (ดีฟอลต์ ~/.ssh/wnk-app) — ไม่ต้องพิมพ์รหัสผ่านและไม่ฝังความลับลงไฟล์ใด ๆ
.env สร้างบนเซิร์ฟเวอร์จาก /opt/ipd/.env (บัญชี HOSxP อ่านอย่างเดียวชุดเดียวกัน) — รหัส DB ไม่ผ่านเครื่องนี้เลย

    set PYTHONIOENCODING=utf-8      (PowerShell: $env:PYTHONIOENCODING="utf-8")
    python deploy_ssh.py            # SSH_HOST / SSH_USER / SSH_KEY ตั้งทับได้ด้วย env

รันซ้ำได้ปลอดภัย (idempotent) — .env เดิมไม่ถูกเขียนทับ, ssl.conf แก้เฉพาะครั้งแรก
แก้ ssl.conf ตามกฎบังคับ: backup → แก้ → httpd -t → ผ่านค่อย reload (ไม่ผ่านคืน backup)
หน้ารายชื่อ (มีข้อมูลผู้ป่วย) ปิดไว้ — ไม่ตั้ง LR_SECRET_KEY · เปิดเองภายหลังตาม INSTALL.md
"""

import os
import posixpath
import sys

import paramiko

HOST = os.getenv("SSH_HOST", "192.168.11.40")   # = Host wnk-app ใน ~/.ssh/config (30.25.1.40 ต่อจากเครื่องนี้ไม่ได้)
USER = os.getenv("SSH_USER", "root")
KEY = os.path.expanduser(os.getenv("SSH_KEY", "~/.ssh/wnk-app"))

APP_NAME = "lr"
APP_DIR = f"/opt/{APP_NAME}"
SERVICE = "wnk-lr"
#: พอร์ตที่ใช้แล้ว (ss -ltn 2026-11-12): 5100-5900, 6100-6900, 3000, 3333-3334, 8443, 9090 — 7000 ว่าง
PORT_APP = 7000
SSL_CONF = "/etc/httpd/conf.d/ssl.conf"
CATCH_ALL = "    ProxyPass / http://127.0.0.1:3000/"
#: RewriteRule ของแอปอื่นที่มีอยู่แล้ว — แทรกของ /lr ต่อท้าย (ไม่พบ = ข้าม ใช้งานได้แต่ต้องพิมพ์ / ท้าย URL)
REWRITE_ANCHOR = "    RewriteRule ^/ipd$ /ipd/ [R=302,L]"
SOURCE_ENV = "/opt/ipd/.env"
#: เครื่องที่นับว่า "อยู่ใน รพ." (ไม่ใช่ที่อยู่ส่วนตัว RFC1918): วง LAN ของ รพ. + IP สาธารณะของ รพ. (เข้าผ่าน Cloudflare)
LAN_NETS = "183.88.214.202/32"      # IP สาธารณะจริงของ รพ. (เข้าผ่าน Cloudflare) · เครื่องใน รพ. ใช้ 192.168.x.x นับเป็น LAN อยู่แล้ว · ห้ามใส่ IP บ้าน

LOCAL = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FILES = ["app.py", "audit.py", "cache.py", "charts.py", "config.py", "db.py", "listing.py", "loader.py",
                "manage.py", "metrics.py", "queries.py", "render.py", "store.py", "setup_check.py",
                "requirements.txt", ".env.example", "README.md", "INSTALL.md", "LICENSE", "NOTICE.md"]
UPLOAD_DIRS = ["templates", "static"]
SKIP = {"__pycache__", ".pyc", ".env", ".db", ".sqlite", "out"}


def run(cli, cmd, check=True, label=None):
    _i, o, e = cli.exec_command(cmd, timeout=600)
    rc = o.channel.recv_exit_status()
    out = o.read().decode(errors="replace").strip()
    err = e.read().decode(errors="replace").strip()
    print(f"\n$ {label or cmd}")
    print(f"  rc={rc}")
    if out:
        print("  " + out.replace("\n", "\n  "))
    if err:
        print("  [err] " + err.replace("\n", "\n  "))
    if check and rc != 0:
        raise SystemExit(f"!! ล้มเหลว: {label or cmd}")
    return rc, out, err


def sftp_mkdirs(sftp, remote):
    cur = ""
    for p in remote.strip("/").split("/"):
        cur += "/" + p
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


def upload_tree(sftp, local_dir, remote_dir):
    n = 0
    for rootd, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d not in SKIP]
        rel = os.path.relpath(rootd, local_dir)
        rdir = remote_dir if rel == "." else posixpath.join(remote_dir, rel.replace(os.sep, "/"))
        sftp_mkdirs(sftp, rdir)
        for f in files:
            if any(f.endswith(s) or f == s for s in SKIP):
                continue
            sftp.put(os.path.join(rootd, f), posixpath.join(rdir, f))
            n += 1
    print(f"  upload {local_dir} -> {remote_dir} ({n} ไฟล์)")


# --------------------------------------------------- เปิด sub-path บน 443

#: สคริปต์แก้ ssl.conf ที่รันบนเซิร์ฟเวอร์ — แทรกบล็อกก่อน catch-all · ไม่พบ catch-all = ไม่แก้ไฟล์
EDIT_SSL = r'''
import sys
p, catch, anchor, name, port = sys.argv[1:6]
lines = open(p, encoding="utf-8").read().split("\n")
if catch not in lines:
    sys.exit("ไม่พบบรรทัด catch-all ProxyPass / — ไม่แก้ไฟล์")
block = [
    f"    # LR Dashboard (gunicorn:{port}) sub-path",
    f"    ProxyPass /{name}/ http://127.0.0.1:{port}/",
    f"    ProxyPassReverse /{name}/ http://127.0.0.1:{port}/",
    f"    <Location /{name}/>",
    f"        RequestHeader set X-Forwarded-Prefix /{name}",
    f"    </Location>",
]
i = lines.index(catch)
lines[i:i] = block
added = len(block)
if anchor in lines:
    lines.insert(lines.index(anchor) + 1, f"    RewriteRule ^/{name}$ /{name}/ [R=302,L]")
    added += 1
else:
    print("ไม่พบ RewriteRule ยึด — ข้ามการ redirect /%s -> /%s/" % (name, name))
open(p, "w", encoding="utf-8").write("\n".join(lines))
print("แทรกแล้ว", added, "บรรทัด")
'''


def open_subpath(cli):
    rc, out, _ = run(cli, f"grep -c 'ProxyPass /{APP_NAME}/' {SSL_CONF} || true",
                     check=False, label="มี sub-path อยู่แล้วหรือยัง")
    if out.strip() not in ("", "0"):
        print(f"  มี /{APP_NAME}/ ใน ssl.conf อยู่แล้ว — ข้ามการแก้ไฟล์")
        return

    run(cli, f"cp -a {SSL_CONF} {SSL_CONF}.bak.$(date +%Y%m%d%H%M%S)", label="สำรอง ssl.conf")

    sftp = cli.open_sftp()
    with sftp.open("/tmp/edit_ssl_lr.py", "w") as fh:
        fh.write(EDIT_SSL)
    sftp.close()
    q = lambda s: "'" + s.replace("'", "'\\''") + "'"
    run(cli, f"python3 /tmp/edit_ssl_lr.py {SSL_CONF} {q(CATCH_ALL)} {q(REWRITE_ANCHOR)} "
             f"{APP_NAME} {PORT_APP} && rm -f /tmp/edit_ssl_lr.py",
        label=f"แทรก ProxyPass /{APP_NAME}/ ก่อน catch-all")

    rc, _, _ = run(cli, "httpd -t", check=False, label="httpd -t ตรวจ config")
    if rc != 0:
        run(cli, f"cp -a $(ls -1t {SSL_CONF}.bak.* | head -1) {SSL_CONF}",
            label="!! config ไม่ผ่าน — คืน backup")
        raise SystemExit("httpd -t ไม่ผ่าน คืน ssl.conf เดิมแล้ว ไม่ได้ reload")

    run(cli, "systemctl reload httpd", label="reload httpd")
    run(cli, "setsebool -P httpd_can_network_connect 1", check=False,
        label="SELinux อนุญาต httpd ต่อ backend")


# ------------------------------------------------------------------ main

def main():
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, key_filename=KEY, timeout=25)
    print("== เชื่อมต่อ SSH สำเร็จ:", HOST)

    print(f"\n===== ขั้นที่ 0: พอร์ต {PORT_APP} ต้องว่าง (หรือเป็นของ {SERVICE} เอง) =====")
    _, out, _ = run(cli, f"ss -ltnp 'sport = :{PORT_APP}' | tail -n +2", check=False,
                    label=f"ใครใช้พอร์ต {PORT_APP}")
    _, active, _ = run(cli, f"systemctl is-active {SERVICE} || true", check=False,
                       label=f"{SERVICE} รันอยู่ไหม")
    if out and active.strip() != "active":
        cli.close()
        raise SystemExit(f"!! พอร์ต {PORT_APP} มีแอปอื่นใช้อยู่ — เปลี่ยน PORT_APP ก่อน")
    run(cli, f"test -f {SOURCE_ENV}", label=f"ต้องมี {SOURCE_ENV} (บัญชี HOSxP อ่านอย่างเดียว)")

    print("\n===== ขั้นที่ 1: อัปโหลดไฟล์โปรเจกต์ =====")
    run(cli, f"mkdir -p {APP_DIR}", label="สร้างโฟลเดอร์แอป")
    sftp = cli.open_sftp()
    for f in UPLOAD_FILES:
        lp = os.path.join(LOCAL, f)
        if os.path.exists(lp):
            sftp.put(lp, posixpath.join(APP_DIR, f))
            print(f"  upload {f}")
    for d in UPLOAD_DIRS:
        ld = os.path.join(LOCAL, d)
        if os.path.isdir(ld):
            upload_tree(sftp, ld, posixpath.join(APP_DIR, d))
    sftp.close()

    print("\n===== ขั้นที่ 2: ตรวจ/สร้าง .env จากของ IPD =====")
    env_path = posixpath.join(APP_DIR, ".env")
    run(cli, f"test -f {env_path} && echo 'มี .env อยู่แล้ว — ข้าม (ไม่เขียนทับ)' || "
             f"(umask 077 && sed -e 's/^PORT=.*/PORT={PORT_APP}/' -e '/^IPD_/d' {SOURCE_ENV} > {env_path} "
             f"&& printf '\\nLR_LAN_NETS={LAN_NETS}\\n' >> {env_path} "
             f"&& chmod 600 {env_path} && echo 'สร้าง .env แล้ว (chmod 600)')",
        label=".env")

    print("\n===== ขั้นที่ 3: ทดสอบเชื่อมต่อฐานข้อมูล HOSxP =====")
    # อ่านรหัสจาก .env ฝั่งเซิร์ฟเวอร์แล้วส่งผ่าน env ไม่ใช่ argument (กันโผล่ใน ps)
    rc, _, _ = run(
        cli,
        f"set -a; . {env_path}; set +a; MYSQL_PWD=\"$DB_PASS\" mysql -h \"$DB_HOST\" "
        f"-P \"$DB_PORT\" -u \"$DB_USER\" \"$DB_NAME\" "
        f"-e 'select count(*) deliveries_30d from ipt_pregnancy where labor_date >= curdate() - interval 30 day; "
        f"select count(*) infants_total from ipt_labour_infant;'",
        check=False, label="ทดสอบ MySQL (ต้องอ่าน ipt_pregnancy / ipt_labour_infant ได้)")
    if rc != 0:
        cli.close()
        raise SystemExit("!! ต่อฐานข้อมูลไม่ได้ — หยุดก่อนติดตั้ง service")

    print("\n===== ขั้นที่ 4: venv + ติดตั้งไลบรารี =====")
    run(cli, f"cd {APP_DIR} && test -d .venv || python3 -m venv .venv", label="สร้าง venv")
    run(cli, f"{APP_DIR}/.venv/bin/python -m pip install --upgrade pip -q",
        check=False, label="upgrade pip")
    run(cli, f"{APP_DIR}/.venv/bin/pip install -q -r {APP_DIR}/requirements.txt",
        label="ติดตั้ง requirements (รวม gunicorn)")

    print("\n===== ขั้นที่ 5: systemd service =====")
    unit = (
        "[Unit]\n"
        "Description=LR Dashboard (Flask/Gunicorn) - Wang Nam Khiao Hospital\n"
        "After=network.target\n\n"
        "[Service]\n"
        f"WorkingDirectory={APP_DIR}\n"
        f"ExecStart={APP_DIR}/.venv/bin/gunicorn -w 2 --threads 8 -t 120 -b 0.0.0.0:{PORT_APP} app:app\n"
        "Restart=always\n"
        "User=root\n"
        "Environment=PYTHONUNBUFFERED=1\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    sftp = cli.open_sftp()
    with sftp.open(f"/etc/systemd/system/{SERVICE}.service", "w") as fh:
        fh.write(unit)
    sftp.close()
    run(cli, "systemctl daemon-reload", label="daemon-reload")
    run(cli, f"systemctl enable {SERVICE}", check=False, label="enable service")
    run(cli, f"systemctl restart {SERVICE}", label="restart service")

    print("\n===== ขั้นที่ 6: firewall (เฉพาะวงใน) =====")
    run(cli, f"firewall-cmd --permanent --add-port={PORT_APP}/tcp", check=False, label="add-port")
    run(cli, "firewall-cmd --reload", check=False, label="firewall reload")

    print(f"\n===== ขั้นที่ 7: เปิด sub-path /{APP_NAME}/ บน 443 =====")
    open_subpath(cli)

    print("\n===== ขั้นที่ 8: ตรวจสอบ =====")
    run(cli, f"sleep 4; systemctl is-active {SERVICE}", check=False, label="service active?")
    run(cli, f"curl -sS -o /dev/null -w 'HTTP %{{http_code}}' http://127.0.0.1:{PORT_APP}/healthz",
        check=False, label="healthz ภายในเครื่อง")
    run(cli, f"curl -sS -m 60 -o /dev/null -w 'HTTP %{{http_code}} %{{time_total}}s' "
             f"-H 'X-Forwarded-Prefix: /{APP_NAME}' http://127.0.0.1:{PORT_APP}/",
        check=False, label="หน้าแดชบอร์ดผ่าน prefix")
    run(cli, f"curl -skS -m 60 -o /dev/null -w 'HTTP %{{http_code}}' https://127.0.0.1/{APP_NAME}/",
        check=False, label="ผ่าน httpd 443")
    run(cli, f"cd {APP_DIR} && .venv/bin/python setup_check.py --no-audit", check=False,
        label="setup_check.py (ดูข้อ ✘ / ⚠ — โดยเฉพาะสิทธิ์บัญชี DB ต้องอ่านอย่างเดียว)")
    run(cli, f"journalctl -u {SERVICE} -n 15 --no-pager", check=False, label="log ล่าสุด")

    cli.close()
    print(f"\n========== เสร็จ! เข้าใช้ที่ https://wnkhos.go.th/{APP_NAME}/ ==========")
    print("ต่อไป: เปิด /lr/check จากเครื่องใน รพ. → ตรวจรหัส → เทียบรายงานเดิม 1–2 สัปดาห์ → ตั้ง LR_DATA_AUDITED=1 ใน .env")


if __name__ == "__main__":
    if not os.path.exists(KEY):
        sys.exit(f"ไม่พบ SSH key: {KEY} (ตั้ง env SSH_KEY ให้ชี้ไปที่ key ของเซิร์ฟเวอร์แอป)")
    main()
