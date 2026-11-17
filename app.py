"""LR Dashboard — แดชบอร์ดห้องคลอด โรงพยาบาลวังน้ำเขียว (อ่านข้อมูลสดจาก HOSxP แบบอ่านอย่างเดียว)

หน้าหลัก/ส่งออก = จำนวนนับเท่านั้น · รายชื่อหลัง login (ดู Task 7) · /check เปิดเฉพาะ LAN
"""

import hmac
import ipaddress
import os
import re
import secrets
import tempfile
import threading
import urllib.parse
from datetime import date, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for

import audit
import charts
import db
import listing
import loader
import metrics
import queries
import render
import store
from cache import TTLCache
from config import fy_of, fy_options, fy_range, load_config

VERSION = "0.1.1"
DEV_CONTACT = "นายเผด็จชัย สิงหล โรงพยาบาลวังน้ำเขียว"
_HERE = os.path.dirname(os.path.abspath(__file__))
_PREFIX_RE = re.compile(r"(/[A-Za-z0-9._~-]+)+/?")


class PrefixMiddleware:
    """อ่าน X-Forwarded-Prefix → SCRIPT_NAME และ X-Forwarded-Proto → url_scheme (sub-path หลัง proxy)"""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_FORWARDED_PREFIX", "")
        # รับเฉพาะ path ภายใน เช่น /lr — กัน header ปลอม (//evil.example) ให้ลิงก์ชี้ออกนอกเว็บ
        if prefix and _PREFIX_RE.fullmatch(prefix):
            environ["SCRIPT_NAME"] = prefix.rstrip("/")
            path = environ.get("PATH_INFO", "")
            if path.startswith(prefix):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
        proto = environ.get("HTTP_X_FORWARDED_PROTO")
        if proto in ("http", "https"):
            environ["wsgi.url_scheme"] = proto
        return self.wsgi_app(environ, start_response)


app = Flask(__name__)
app.wsgi_app = PrefixMiddleware(app.wsgi_app)
#: กุญแจ session ของหน้ารายชื่อ — ไม่ตั้ง = ปิดหน้ารายชื่อ/login ทั้งหมด (แดชบอร์ดตัวเลขยังใช้ได้)
#: สุ่มเองไม่ได้: gunicorn หลาย worker จะได้กุญแจคนละตัว และ login หลุดทุกครั้งที่ restart
app.secret_key = os.getenv("LR_SECRET_KEY") or None
#: ชื่อ cookie ของตัวเอง — แอปอื่นบนโดเมนเดียวกันใช้ "session" (Path=/) ถ้าซ้ำ login ที่หนึ่งจะหลุดอีกที่
app.config.update(SESSION_COOKIE_NAME="lr_session", SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.getenv("LR_COOKIE_SECURE", "0") == "1", PERMANENT_SESSION_LIFETIME=8 * 3600)
_cache = TTLCache(maxsize=64)
_hosp_cache = TTLCache(maxsize=4)


def _ttl():
    try:
        return int(os.getenv("LR_CACHE_TTL", "300"))
    except ValueError:
        return 300


# ---------------------------------------------------------------- ชื่อ รพ. / แบรนด์

def hospital_name():
    """ชื่อโรงพยาบาล: env LR_HOSPITAL_NAME > opdconfig.hospitalname ของ HOSxP > "โรงพยาบาล" """
    env = os.getenv("LR_HOSPITAL_NAME")
    if env:
        return env
    hit = _hosp_cache.get("n", 3600)
    if hit:
        return hit
    try:
        name = (db.fetch_one("select hospitalname from opdconfig limit 1").get("hospitalname") or "").strip()
    except Exception:                                            # noqa: BLE001
        name = ""
    name = name or "โรงพยาบาล"
    _hosp_cache.set("n", name)
    return name


@app.context_processor
def _branding():
    img = lambda n: os.path.exists(os.path.join(_HERE, "static", "img", n))
    return {
        "hospital": hospital_name(),
        "logo_url": url_for("static", filename="img/hospital_logo.png" if img("hospital_logo.png") else "img/logo.png"),
        "version": VERSION, "css_v": VERSION,
        "dev_contact": os.getenv("LR_DEV_CONTACT", DEV_CONTACT),
        "check_allowed": _check_allowed(),
        "audited": os.getenv("LR_DATA_AUDITED") == "1",
    }


#: ทุกอย่างโหลดจากเว็บตัวเองเท่านั้น (ไม่มี CDN)
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'self'")


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Content-Security-Policy", CSP)
    return resp


# ---------------------------------------------------------------- LAN gate (เหมือน ANC dashboard)

TRUSTED_PROXIES = {x.strip() for x in os.getenv("LR_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if x.strip()}
_CF_DEFAULT = ("173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,"
               "190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,"
               "104.24.0.0/14,172.64.0.0/13,131.0.72.0/22")


def _nets(spec):
    out = []
    for x in spec.split(","):
        try:
            out.append(ipaddress.ip_network(x.strip(), strict=False))
        except ValueError:
            pass
    return out


CF_NETS = _nets(os.getenv("LR_CF_RANGES", _CF_DEFAULT))
LAN_NETS = _nets(os.getenv("LR_LAN_NETS", ""))      # เครือข่ายเพิ่มเติมที่นับเป็น "ใน รพ."


def _is_cf(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in CF_NETS)


def _client_ip():
    """IP ผู้ใช้: ค่าท้ายสุดของ X-Forwarded-For (Apache ต่อท้ายเอง) · ผ่าน Cloudflare จริงจึงเชื่อ CF-Connecting-IP"""
    peer = request.remote_addr
    if peer not in TRUSTED_PROXIES:
        return peer
    xff = [x.strip() for x in request.headers.get("X-Forwarded-For", "").split(",") if x.strip()]
    hop = xff[-1] if xff else peer
    cf = request.headers.get("CF-Connecting-IP", "").strip()
    return cf if cf and _is_cf(hop) else hop


def _from_lan():
    try:
        ip = ipaddress.ip_address((_client_ip() or "").strip())
    except ValueError:
        return False
    if any(ip in n for n in LAN_NETS):
        return True
    if request.headers.get("CF-Connecting-IP", "").strip():
        return False
    return ip.is_private or ip.is_loopback


def _check_allowed():
    """หน้าตรวจข้อมูลบอกโครงสร้างรหัสของ HOSxP — เปิดเฉพาะ LAN · LR_CHECK_OPEN=1 = เปิดทุกที่"""
    return os.getenv("LR_CHECK_OPEN", "0") == "1" or _from_lan()


# ---------------------------------------------------------------- ช่วงเวลา / ข้อมูล

def current_fy(today=None):
    return fy_of(today or date.today())


def _parse_date(v):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _parse_fy(v):
    try:
        fy = int(v)
    except (TypeError, ValueError):
        return None
    return fy if 2550 <= fy <= current_fy() + 1 else None


#: ช่วงเองต้องยาวอย่างน้อยเท่านี้ (วัน) — รพ.ที่คลอดสัปดาห์ละไม่กี่ราย ช่วง 1 วันทำให้ตัวเลขชี้ไปที่ผู้ป่วยรายเดียว
MIN_DAYS, MAX_DAYS = 28, 400


def resolve_range(args):
    """(d1, d2, fy|None) — fy ผิด/ไม่ส่ง = ปีงบปัจจุบัน · ส่ง d1,d2 ที่ถูกต้องยาว MIN_DAYS–MAX_DAYS วัน = ช่วงเอง"""
    a, b = _parse_date(args.get("d1")), _parse_date(args.get("d2"))
    if a and b and a <= b and MIN_DAYS <= (b - a).days + 1 <= MAX_DAYS:
        return a, b, None
    fy = _parse_fy(args.get("fy")) or current_fy()
    return (*fy_range(fy), fy)


def months_between(d1, d2):
    out, y, m = [], d1.year, d1.month
    while (y, m) <= (d2.year, d2.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _data(d1, d2, cfg):
    key = ("data", d1, d2)
    hit = _cache.get(key, _ttl())
    if hit is not None:
        return hit
    data = loader.load_data(d1, d2, cfg)
    if not data.get("errors"):
        _cache.set(key, data)            # ผลที่อ่านไม่ครบ (แหล่งใดล่ม) ไม่แคช — ลองใหม่ในคำขอถัดไป
    return data


def _delta(cur, prev):
    if not prev or cur is None:
        return None
    return round((cur - prev) * 100.0 / prev, 1)


def build_context(d1, d2, fy=None, today=None):
    cfg = load_config()
    today = today or date.today()
    partial = d2 > today                  # ปีงบ/ช่วงที่ยังไม่สิ้นสุด: ไม่เทียบกับปีงบก่อนที่ครบปีแล้ว (จะดูเหมือนลดฮวบ)
    data = _data(d1, d2, cfg)
    kpi = {r["key"]: r for r in metrics.kpi_rows(data, cfg)}
    uncoded = len(metrics.uncoded_ans(data, cfg))
    prev_kpi, prev_ref = {}, None
    if fy and not partial:
        pdata = _data(*fy_range(fy - 1), cfg)
        prev_kpi = {r["key"]: r for r in metrics.kpi_rows(pdata, cfg)}
        prev_ref = sum(r["n"] for r in pdata["refers"])
    refers = sum(r["n"] for r in data["refers"])
    cards = [
        {"key": "mothers", "label": "การคลอดทั้งหมด", "value": kpi["mothers"]["value"],
         "delta": _delta(kpi["mothers"]["value"], (prev_kpi.get("mothers") or {}).get("value"))},
        {"key": "normal", "label": "คลอดปกติ", "value": kpi["normal"]["value"],
         "delta": _delta(kpi["normal"]["value"], (prev_kpi.get("normal") or {}).get("value"))},
        {"key": "abnormal", "label": "มีภาวะแทรกซ้อน/หัตถการ", "value": kpi["abnormal"]["value"],
         "delta": _delta(kpi["abnormal"]["value"], (prev_kpi.get("abnormal") or {}).get("value"))},
        {"key": "referred", "label": "ส่งต่อ", "value": refers, "delta": _delta(refers, prev_ref)},
    ]
    months = metrics.monthly(data, cfg, months_between(d1, d2))
    try:
        recent = queries.recent_counts(today, cfg)
    except Exception:                                            # noqa: BLE001
        recent = {"days7": None}
    donut_parts = [("คลอดปกติ", kpi["normal"]["value"], charts.C_NORMAL),
                   ("มีภาวะแทรกซ้อน/หัตถการ", kpi["abnormal"]["value"], charts.C_COMPLICATED),
                   ("ยังไม่ลงรหัส Dx คลอด", uncoded, charts.C_UNCODED), ("ส่งต่อ", refers, charts.C_REFERRED)]
    return {"d1": d1, "d2": d2, "fy": fy, "partial": partial, "uncoded": uncoded, "cards": cards, "kpi": kpi, "months": months,
            "bar_svg": charts.stacked_bar(months), "donut_svg": charts.donut(donut_parts),
            "quality": metrics.quality_grid(data, cfg), "recent": recent, "errors": data["errors"],
            "audited": os.getenv("LR_DATA_AUDITED") == "1"}


# ---------------------------------------------------------------- template helpers

THAI_MONTHS = ("", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
               "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")


@app.template_filter("num")
def _num_filter(v):
    return "—" if v is None else f"{v:,}"


@app.template_filter("thai_date")
def _thai_date(d):
    return f"{d.day} {THAI_MONTHS[d.month]} {d.year + 543}"


# ---------------------------------------------------------------- routes

@app.route("/healthz")
def healthz():
    return "ok"


@app.route("/")
def index():
    d1, d2, fy = resolve_range(request.args)
    ctx = build_context(d1, d2, fy)
    return render_template("dashboard.html", d=ctx, fy=fy, fy_list=fy_options(n=8),
                           print_mode=request.args.get("print") == "1")


@app.route("/yearly")
def yearly():
    cfg = load_config()
    years = fy_options(n=6)[::-1]   # 5 ปีงบที่ผ่านมา + ปีปัจจุบัน (ครอบคลุมปีเดียวกับ kpi.jpg)
    table = metrics.yearly_table(lambda a, b: _data(a, b, cfg), years, cfg)
    today = date.today()
    return render_template("yearly.html", t=table, print_mode=request.args.get("print") == "1",
                           partial_years=[y for y in years if fy_range(y)[1] > today],
                           year_errors=[(y, e) for y, e in zip(years, table["errors"]) if e])


@app.route("/check")
def check_page():
    if not _check_allowed():
        abort(403)
    cfg = load_config()
    fy = _parse_fy(request.args.get("fy"))
    d1, d2 = fy_range(fy) if fy else (date.today() - timedelta(days=365), date.today())
    items = audit.audit(d1, d2, cfg)
    comp = audit.completeness(_data(d1, d2, cfg), cfg)
    return render_template("check.html", items=items, comp=comp, d1=d1, d2=d2, fy=fy, fy_list=fy_options(n=8))


# ---------------------------------------------------------------- login (หน้ารายชื่อ)

#: login ผิดเกินจำนวนนี้ใน LOGIN_WINDOW นาที → ปฏิเสธชั่วคราว (ตามชื่อผู้ใช้ / ตาม IP)
LOGIN_MAX_USER, LOGIN_MAX_IP, LOGIN_WINDOW = 10, 30, 15


def list_enabled():
    return bool(app.secret_key)


def _list_gate():
    """หน้ารายชื่อ/login: ปิดเมื่อไม่ตั้ง LR_SECRET_KEY · เข้าได้เฉพาะเครื่องใน รพ. เป็นค่าเริ่มต้น
    (ข้อมูลผู้ป่วยต้องไม่ออกอินเทอร์เน็ต) — LR_LIST_LAN_ONLY=0 เพื่อปิดข้อจำกัดนี้ด้วยตัวเอง"""
    if not list_enabled():
        abort(404)
    if os.getenv("LR_LIST_LAN_ONLY", "1") != "0" and not _from_lan():
        abort(403)


#: ผู้ใช้สมมติของ passkey — ไม่มีแถวในตาราง users · audit log ลงชื่อ "passkey" (ไม่รู้ว่าเป็นใคร จึงแนะนำบัญชีรายคนเมื่อต้องการตรวจสอบย้อนหลัง)
PASSKEY_USER = {"id": 0, "username": "passkey", "display": "passkey", "is_admin": 0, "active": 1}


def _passkey():
    """LR_PASSKEY = รหัสผ่านร่วมของหน่วย (ไม่ตั้ง = ปิด) · อ่านทุกครั้งที่เรียก เพื่อให้เปลี่ยนแล้วมีผลหลัง restart เท่านั้น"""
    return os.getenv("LR_PASSKEY", "")


def _passkey_tag():
    """ลายนิ้วมือของ passkey ที่เก็บใน session — เปลี่ยน passkey แล้วทุกคนที่เข้าไว้ถูกเตะออก"""
    return hmac.new(app.secret_key.encode(), b"passkey:" + _passkey().encode(), "sha256").hexdigest()


def _load_user():
    uid = session.get("uid") if list_enabled() else None
    g.user = store.get_user(uid) if uid else None
    tag = session.get("pk") if list_enabled() else None
    if g.user is None and tag and _passkey() and hmac.compare_digest(tag, _passkey_tag()):
        g.user = dict(PASSKEY_USER)
    return g.user


def _audit_log(action, detail=None):
    store.log(g.user["username"] if g.get("user") else None, action, detail, _client_ip())


def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        _list_gate()
        if not _load_user():
            # script_root = sub-path หลัง proxy (เช่น /lr) — ไม่ใส่จะเด้งไปเว็บหลักของ รพ.
            return redirect(url_for("login", next=request.script_root + request.full_path))
        return f(*a, **kw)
    return wrap


def _csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def _check_csrf():
    # session ใหม่ไม่มี csrf → "" == "" ผ่านได้ จึงต้องมีค่าจริงด้วย
    sent, want = request.form.get("csrf", ""), session.get("csrf", "")
    if not want or not secrets.compare_digest(sent, want):
        abort(400)


@app.context_processor
def _list_ctx():
    return {"list_on": list_enabled(), "csrf_token": _csrf_token if list_enabled() else (lambda: ""),
            "user": g.get("user"), "passkey_on": bool(_passkey())}


def _safe_next(nxt):
    """next= หลัง login: รับเฉพาะ path ในแอป · ปฏิเสธอักขระควบคุมและ \\ (เบราว์เซอร์อ่าน "/\\evil" เป็น "//evil")"""
    if "\\" in nxt or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in nxt):
        return None
    parts = urlsplit(nxt)
    if parts.scheme or parts.netloc or nxt.startswith("//"):
        return None
    return nxt if nxt.startswith(request.script_root + "/") else None


@app.route("/login", methods=["GET", "POST"])
def login():
    _list_gate()
    if request.method == "POST":
        _check_csrf()
        by_passkey = "passkey" in request.form
        username = "passkey" if by_passkey else request.form.get("username", "").strip()[:64]
        by_user, by_ip = store.recent_failures(username, _client_ip(), LOGIN_WINDOW)
        if by_user >= LOGIN_MAX_USER or by_ip >= LOGIN_MAX_IP:
            flash(f"ใส่รหัสผิดหลายครั้งเกินไป ลองใหม่อีก {LOGIN_WINDOW} นาที")
            return render_template("login.html"), 429
        if by_passkey:
            want = _passkey()
            ok = bool(want) and hmac.compare_digest(request.form.get("passkey", "").encode(), want.encode())
            u = dict(PASSKEY_USER) if ok else None
        else:
            u = store.check_login(username, request.form.get("password", ""))
        if u:
            session.clear()
            session.permanent = True
            if by_passkey:
                session["pk"] = _passkey_tag()
            else:
                session["uid"] = u["id"]
            g.user = u
            _audit_log("login")
            return redirect(_safe_next(request.args.get("next") or "") or url_for("list_index"))
        store.log(username, "login_fail", ip=_client_ip())
        flash("passkey ไม่ถูกต้อง" if by_passkey else "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    _list_gate()
    _check_csrf()
    if _load_user():
        _audit_log("logout")
    session.clear()
    return redirect(url_for("index"))


def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"     # มีชื่อผู้ป่วย — ห้ามแคชที่ proxy/เบราว์เซอร์
    return resp


@app.route("/list")
@login_required
def list_index():
    d1, d2, fy = resolve_range(request.args)
    return render_template("list_index.html", keys=listing.KEYS, fy=fy, fy_list=fy_options(n=8), d1=d1, d2=d2)


@app.route("/list/<key>")
@login_required
def list_page(key):
    d1, d2, fy = resolve_range(request.args)
    cfg = load_config()
    data = _data(d1, d2, cfg)
    ans = listing.members(key, data, cfg)
    if ans is None:
        abort(404)
    try:
        names = queries.case_names(ans)
    except Exception:                                            # noqa: BLE001 — ไม่มีชื่อก็ยังแสดง HN/AN ได้
        app.logger.exception("case_names failed")
        names = {}
    head, rows = listing.table(ans, data, names)
    _audit_log("view_list", f"k={key} d={d1}..{d2} n={len(rows)}")
    return _no_store(app.make_response(render_template("list.html", key=key, title=listing.KEYS[key], head=head,
                                                       rows=rows, d1=d1, d2=d2, fy=fy)))


# ---------------------------------------------------------------- ส่งออกหน้าแดชบอร์ด (ไม่มีข้อมูลรายคน)

MIME = {"png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}
EXPORT_ENABLED = os.getenv("LR_EXPORT", "1") == "1"
EXPORT_CACHE_TTL, EXPORT_WAIT = 300, 20
_export_cache = TTLCache(maxsize=128)
_render_lock = threading.Lock()


@app.route("/export.<fmt>")
def export(fmt):
    """ส่งออกหน้าแดชบอร์ดเป็น PNG / JPG / PDF ด้วย chromium headless (เรียกหน้าเดิมด้วย ?print=1 — ไม่มีแถบเตือน)"""
    if fmt not in MIME or not EXPORT_ENABLED:
        return {"error": "รองรับเฉพาะ png, jpg, pdf" if EXPORT_ENABLED else "ปิดการส่งออกไฟล์"}, 404
    # ส่งออกเฉพาะ "ปีงบ" (ไม่รับ d1/d2 เอง) — หน้านี้ไม่ต้อง login จึงจำกัดจำนวนชุดที่ต้องเรนเดอร์ (chromium หนัก)
    fy = _parse_fy(request.args.get("fy")) or current_fy()
    qs = urllib.parse.urlencode({"fy": fy, "print": "1"})
    url = f"http://127.0.0.1:{os.getenv('PORT', '5400')}/?{qs}"
    name = f"lr_{fy}.{fmt}"
    blob = _export_cache.get(name, EXPORT_CACHE_TTL)
    if blob is not None:
        return send_file(BytesIO(blob), mimetype=MIME[fmt], as_attachment=True, download_name=name)
    if not _render_lock.acquire(timeout=EXPORT_WAIT):
        return ({"error": "กำลังส่งออกไฟล์ของผู้ใช้อื่นอยู่ ลองใหม่ในอีกครู่"}, 503, {"Retry-After": "30"})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, name)
            render.render_to(fmt, url, out)
            blob = open(out, "rb").read()
        _export_cache.set(name, blob)
        return send_file(BytesIO(blob), mimetype=MIME[fmt], as_attachment=True, download_name=name)
    except Exception as e:                                       # noqa: BLE001
        app.logger.exception("export failed")
        return {"error": f"ส่งออกไม่สำเร็จ: {type(e).__name__}"}, 500
    finally:
        _render_lock.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5400")))
