"""จัดการผู้ใช้หน้ารายชื่อ (รันบนเครื่องที่มีไฟล์ data/lr.sqlite)

  python manage.py adduser <username> --display "ชื่อ" [--admin]
  python manage.py passwd <username>
  python manage.py disable <username>      # ปิดบัญชี (ย้ายหน่วย/ลาออก) · enable = เปิดคืน
  python manage.py users
  python manage.py audit [--user somchai] [--limit 100]   # ใครเปิดดูรายชื่อไหน เมื่อไร
"""

import argparse
import getpass
import sys

import store

if hasattr(sys.stdout, "reconfigure"):     # คอนโซล Windows (cp874) แสดงภาษาไทยเพี้ยน
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ask_password():
    pw = getpass.getpass("รหัสผ่าน: ")
    if len(pw) < 8 or pw != getpass.getpass("ยืนยันรหัสผ่าน: "):
        sys.exit("รหัสผ่านต้องยาวอย่างน้อย 8 ตัวและพิมพ์ตรงกันทั้งสองครั้ง")
    return pw


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("adduser")
    a.add_argument("username")
    a.add_argument("--display", required=True)
    a.add_argument("--admin", action="store_true")
    p = sub.add_parser("passwd")
    p.add_argument("username")
    for name in ("disable", "enable"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("users")
    q = sub.add_parser("audit")
    q.add_argument("--user")
    q.add_argument("--limit", type=int, default=100)
    args = ap.parse_args(argv)

    if args.cmd == "adduser":
        store.add_user(args.username, _ask_password(), args.display, args.admin)
        print("เพิ่มผู้ใช้แล้ว:", args.username)
    elif args.cmd == "passwd":
        print("เปลี่ยนรหัสแล้ว" if store.set_password(args.username, _ask_password()) else "ไม่พบผู้ใช้")
    elif args.cmd in ("disable", "enable"):
        ok = store.set_active(args.username, args.cmd == "enable")
        print("ทำแล้ว" if ok else "ไม่พบผู้ใช้")
    elif args.cmd == "users":
        for u in store.list_users():
            print(f"{u['username']:<16}{u['display']:<24}{'admin ' if u['is_admin'] else ''}{'' if u['active'] else '(ปิด)'}")
    elif args.cmd == "audit":
        for r in store.audit(args.user, args.limit):
            print(r["at"], r["username"] or "-", r["action"], r["detail"] or "", r["ip"] or "")


if __name__ == "__main__":
    main()
