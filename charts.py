"""กราฟ SVG ฝั่งเซิร์ฟเวอร์ (ไม่พึ่ง JS/CDN) — กราฟแท่งซ้อนรายเดือน + โดนัทสัดส่วน"""

import math

from markupsafe import Markup, escape

TH_MONTHS = ("", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
C_NORMAL, C_COMPLICATED, C_REFERRED, C_UNCODED = "#1e88e5", "#ec6b9a", "#f5a623", "#9aa7b8"


def month_label(ym):
    y, m = ym.split("-")
    return f"{TH_MONTHS[int(m)]} {str(int(y) + 543)[-2:]}"


def _nice_max(v):
    """ขอบบนของแกน Y — เป็นพหุคูณของ 4 เสมอ เพื่อให้เส้นแบ่ง 4 ช่องเป็นจำนวนเต็ม"""
    step = 4 if v <= 40 else 20 if v <= 160 else 100
    return max(4, int(math.ceil(v / step) * step))


def stacked_bar(months, width=760, height=300):
    """months: [{ym, normal, complicated, referred}] · แท่งซ้อน ปกติ+แทรกซ้อน = คลอดที่ รพ. · ส่งต่อ = แท่งเล็กข้างกัน"""
    left, right, top, bottom = 38, 8, 26, 34
    ph, pw = height - top - bottom, width - left - right
    peak = max([max(m["normal"] + m["complicated"] + m.get("uncoded", 0), m["referred"]) for m in months] or [0])
    if peak == 0:
        return Markup(f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="ไม่มีข้อมูล" class="chart">'
                      f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" class="muted-t">ไม่มีข้อมูล</text></svg>')
    ymax = _nice_max(peak)
    y = lambda v: top + ph - ph * v / ymax
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="จำนวนการคลอดรายเดือน" class="chart">']
    for i in range(5):
        v = ymax * i / 4
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{v:g}</text>')
    slot = pw / len(months)
    bw = min(34.0, slot * 0.46)
    for i, m in enumerate(months):
        cx = left + slot * (i + 0.5)
        n, c, r, u = m["normal"], m["complicated"], m["referred"], m.get("uncoded", 0)
        x0 = cx - bw / 2 - (4 if r else 0)
        parts.append('<g class="bar-col">')
        if n:
            parts.append(f'<rect x="{x0:.1f}" y="{y(n):.1f}" width="{bw:.1f}" height="{y(0) - y(n):.1f}" '
                         f'fill="{C_NORMAL}" rx="2"><title>ปกติ {n}</title></rect>')
        if c:
            parts.append(f'<rect x="{x0:.1f}" y="{y(n + c):.1f}" width="{bw:.1f}" height="{y(n) - y(n + c):.1f}" '
                         f'fill="{C_COMPLICATED}" rx="2"><title>มีภาวะแทรกซ้อน {c}</title></rect>')
        if u:
            parts.append(f'<rect x="{x0:.1f}" y="{y(n + c + u):.1f}" width="{bw:.1f}" height="{y(n + c) - y(n + c + u):.1f}" '
                         f'fill="{C_UNCODED}" rx="2"><title>ยังไม่ลงรหัส Dx คลอด {u}</title></rect>')
        total = n + c + u
        parts.append(f'<text x="{x0 + bw / 2:.1f}" y="{y(total) - 5:.1f}" text-anchor="middle" class="val">{total}</text>')
        if r:
            rw = max(8.0, bw * 0.34)
            parts.append(f'<rect x="{x0 + bw + 3:.1f}" y="{y(r):.1f}" width="{rw:.1f}" height="{y(0) - y(r):.1f}" '
                         f'fill="{C_REFERRED}" rx="2"><title>ส่งต่อ {r}</title></rect>')
        parts.append(f'<text x="{cx:.1f}" y="{height - 12}" text-anchor="middle" class="axis">{escape(month_label(m["ym"]))}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return Markup("".join(parts))


def donut(parts, size=220):
    """parts: [(label, n, color)] · ตัวเลขกลางวง = รวม · แสดงรายการพร้อมจำนวนและร้อยละ"""
    total = sum(n for _, n, _ in parts)
    if total == 0:
        return Markup(f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="ไม่มีข้อมูล" class="donut">'
                      f'<circle cx="{size / 2}" cy="{size / 2}" r="{size * 0.36}" fill="none" stroke="#e3e8ef" stroke-width="{size * 0.16}"/>'
                      f'<text x="{size / 2}" y="{size / 2 + 5}" text-anchor="middle" class="muted-t">ไม่มีข้อมูล</text></svg>')
    r, cx = size * 0.36, size / 2
    circ = 2 * math.pi * r
    out = [f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="สัดส่วนประเภทการคลอด" class="donut">']
    offset = 0.0
    for label, n, color in parts:
        if n:
            frac = n / total
            out.append(f'<circle cx="{cx}" cy="{cx}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{size * 0.16:.1f}" '
                       f'stroke-dasharray="{circ * frac:.2f} {circ:.2f}" stroke-dashoffset="{-offset:.2f}" '
                       f'transform="rotate(-90 {cx} {cx})"><title>{escape(label)} {n}</title></circle>')
            offset += circ * frac
    out.append(f'<text x="{cx}" y="{cx - 2}" text-anchor="middle" class="d-total">{total}</text>'
               f'<text x="{cx}" y="{cx + 18}" text-anchor="middle" class="axis">ราย</text>')
    out.append("</svg>")
    legend = "".join(f'<li><i style="background:{color}"></i>{escape(label)} <b>{n}</b> ราย ({round(n * 100 / total)}%)</li>'
                     for label, n, color in parts)
    return Markup("".join(out) + f'<ul class="legend">{legend}</ul>')
