"""นิยามตัวชี้วัดห้องคลอด — ฟังก์ชันบริสุทธิ์ (ไม่ต่อฐานข้อมูล) รับ dict จาก loader.load_data

หน่วยนับ: แม่ = 1 การคลอด (AN) · เด็ก = 1 ราย · รหัสทุกตัวมาจาก Config
ตัวชี้วัดที่ไม่มีแหล่งข้อมูล → value None + status "nodata" (ห้ามแสดงเป็น 0)
"""

import re
from collections import Counter

from config import fy_range

KPI_KEYS = ("mothers", "normal", "abnormal", "cs", "forceps", "vacuum", "breech", "twins", "bba", "babies", "live",
            "still", "neo_death7", "apgar1_low", "amph", "alcohol_smoke", "syphilis", "hiv", "hbv")

LABELS = {
    "mothers": "จำนวนมารดาที่คลอด", "normal": "คลอดปกติ", "abnormal": "คลอดผิดปกติ",
    "cs": "ผ่าท้องคลอด", "forceps": "ใช้คีม", "vacuum": "ใช้เครื่องดูดสุญญากาศ",
    "breech": "คลอดท่าก้นทางช่องคลอด", "twins": "ครรภ์แฝด", "bba": "มารดาคลอดก่อนถึงโรงพยาบาล",
    "babies": "จำนวนเด็กเกิดทั้งหมด", "live": "จำนวนเด็กเกิดมีชีพ", "still": "จำนวนเด็กเกิดไร้ชีพ",
    "neo_death7": "จำนวนเด็ก 0–7 วันตาย", "apgar1_low": "เด็กแรกเกิด Apgar score 1 นาที ≤ 7",
    "amph": "มารดา Amphetamines", "alcohol_smoke": "มารดาติดสุรา/บุหรี่/คนใกล้ชิดสูบบุหรี่",
    "syphilis": "มารดา Syphilis", "hiv": "มารดา HIV", "hbv": "มารดา Hep B",
}


def pct(n, d):
    """ร้อยละ 1 ตำแหน่ง · ตัวหาร 0/None → None (ไม่ใช่ 0)"""
    if not d or n is None:
        return None
    return round(n * 100.0 / d, 1)


def _has(codes, prefixes):
    return any(c.startswith(p) for c in codes for p in prefixes)


def mother_ans(data):
    """AN ของการคลอดที่ไม่ใช่การแท้ง"""
    return [r["an"] for r in data["deliveries"] if not r["is_abort"]]


def complication_prefixes(cfg):
    return (tuple(cfg.dx_pph) + tuple(cfg.dx_preterm) + tuple(cfg.dx_htn) + tuple(cfg.dx_prolonged)
            + tuple(cfg.dx_fetal_distress) + tuple(cfg.dx_prom))


def _op_ans(data, cfg, which):
    """AN ที่มีหัตถการ/Dx ของ which ∈ cs|forceps|vacuum|breech"""
    icd9 = {"cs": cfg.cs_icd9, "forceps": cfg.forceps_icd9, "vacuum": cfg.vacuum_icd9, "breech": cfg.breech_icd9}[which]
    icd10 = {"cs": (), "forceps": cfg.forceps_icd10, "vacuum": cfg.vacuum_icd10, "breech": cfg.breech_icd10}[which]
    out = set()
    for an in mother_ans(data):
        if _has(data["ops_by_an"].get(an, ()), icd9) or (icd10 and _has(data["dx_by_an"].get(an, ()), icd10)):
            out.add(an)
    return out


def normal_ans(data, cfg):
    special = set()
    for w in ("cs", "forceps", "vacuum", "breech"):
        special |= _op_ans(data, cfg, w)
    comp = complication_prefixes(cfg)
    return {an for an in mother_ans(data)
            if _has(data["dx_by_an"].get(an, ()), cfg.normal_icd)
            and not _has(data["dx_by_an"].get(an, ()), comp) and an not in special}


def stillbirth_ans(data, cfg):
    mothers = set(mother_ans(data))
    out = {an for an in mothers if _has(data["dx_by_an"].get(an, ()), cfg.stillbirth_icd10)}
    out |= {r["an"] for r in data["infants"]
            if r["an"] in mothers and r.get("infant_icd10") and _has([r["infant_icd10"].replace(".", "").upper()],
                                                                    cfg.stillbirth_icd10)}
    return out


def twin_ans(data):
    mothers = set(mother_ans(data))
    out = {r["an"] for r in data["deliveries"] if r["twin"] and not r["is_abort"]}
    per_mother = Counter(r["ipt_labour_id"] for r in data["infants"])
    out |= {r["an"] for r in data["infants"] if per_mother[r["ipt_labour_id"]] >= 2}
    return out & mothers


_NEG = re.compile(r"(non[\s\-_]*react|neg|nr\b|-\s*ve\b|ไม่พบ|ไม่ตรวจพบ)")
_POS = re.compile(r"(react|pos|r\b|\+\s*ve\b|\+|พบ)")


def classify_result(text):
    """ผลแล็บพิมพ์มือ → 'pos' | 'neg' | 'unclear' · ตรวจกลุ่มลบก่อน เพราะ "Non-reactive" มีคำว่า reactive อยู่ข้างใน
    ตัวอักษรขยะนำหน้า (ผลจาก tis-620) ถูกตัดทิ้งก่อนจับคู่ · ไม่ชัดไม่นับเป็นลบ"""
    if text is None:
        return "unclear"
    t = re.sub(r"^[^a-z0-9ก-๙+\-]+", "", str(text).strip().lower())
    if not t:
        return "unclear"
    if _NEG.match(t):
        return "neg"
    if _POS.match(t):
        return "pos"
    return "unclear"


def _lab_value(data, key):
    """(จำนวนแม่ที่ผลบวก, มีผลแล็บของ key นี้หรือไม่) — แม่ 1 คนนับครั้งเดียว"""
    rows = [r for r in data["labs"] if r["lab_key"] == key]
    if not rows:
        return None
    mothers = set(mother_ans(data))
    return len({r["an"] for r in rows if r["an"] in mothers and classify_result(r["result"]) == "pos"})


def _row(key, value, status="ok"):
    return {"key": key, "label": LABELS[key], "value": value, "status": status}


def rate_per_thousand(n, den):
    if not den or n is None:
        return None
    return round(n * 1000.0 / den, 1)


def kpi_rows(data, cfg):
    mothers = mother_ans(data)
    normal = normal_ans(data, cfg)
    still = stillbirth_ans(data, cfg)
    babies = len(data["infants"])
    v = {
        "mothers": len(mothers), "normal": len(normal), "abnormal": len(mothers) - len(normal),
        "cs": len(_op_ans(data, cfg, "cs")), "forceps": len(_op_ans(data, cfg, "forceps")),
        "vacuum": len(_op_ans(data, cfg, "vacuum")), "breech": len(_op_ans(data, cfg, "breech")),
        "twins": len(twin_ans(data)),
        "bba": len({r["an"] for r in data["infants"] if r["bba_type"] in cfg.bba_types}),
        "babies": babies, "still": len(still), "live": babies - len(still),
        "neo_death7": sum(1 for r in data["infants"]
                          if r["dead"] and r["an"] not in still and r["days_to_dch"] is not None
                          and r["days_to_dch"] <= 7),
        "apgar1_low": sum(1 for r in data["infants"] if r["apgar1"] is not None and r["apgar1"] <= cfg.apgar1_max),
    }
    for key in ("amph", "syphilis", "hiv", "hbv"):
        n = _lab_value(data, key)
        if n is not None:
            v[key] = n
    return [_row(k, v[k]) if k in v else _row(k, None, "nodata") for k in KPI_KEYS]


def monthly(data, cfg, months):
    """รายเดือน: ปกติ / มีภาวะแทรกซ้อน (คลอดแล้วไม่เข้าเกณฑ์ปกติ) / ส่งต่อ (ไม่นับเป็นคลอดที่ รพ.)"""
    normal = normal_ans(data, cfg)
    out = {m: {"ym": m, "normal": 0, "complicated": 0, "referred": 0} for m in months}
    for r in data["deliveries"]:
        if r["is_abort"] or r["ym"] not in out:
            continue
        out[r["ym"]]["normal" if r["an"] in normal else "complicated"] += 1
    for r in data["refers"]:
        if r["ym"] in out:
            out[r["ym"]]["referred"] += r["n"]
    return [out[m] for m in months]


def _mothers_with(data, prefixes):
    return sum(1 for an in mother_ans(data) if _has(data["dx_by_an"].get(an, ()), prefixes))


def quality_grid(data, cfg):
    """ตัวชี้วัดคุณภาพ: n = จำนวน, den = ตัวหาร (แม่ หรือ เด็ก)"""
    infants, mothers = data["infants"], len(mother_ans(data))

    def asphyxia(r):
        icd = (r.get("infant_icd10") or "").replace(".", "").upper()
        return ((r["apgar5"] is not None and r["apgar5"] < cfg.asphyxia_apgar5)
                or _has([icd], cfg.asphyxia_icd10) or r["labor_ba_id"] is not None)

    alive = [r for r in infants if not r["dead"] and r["weight"] is not None]
    items = [
        ("asphyxia", "Birth asphyxia", sum(1 for r in infants if asphyxia(r)), len(infants)),
        ("pph", "PPH", _mothers_with(data, cfg.dx_pph), mothers),
        ("preterm", "คลอดก่อนกำหนด", _mothers_with(data, cfg.dx_preterm), mothers),
        ("htn", "PIH / Pre-eclampsia", _mothers_with(data, cfg.dx_htn), mothers),
        ("prolonged", "เจ็บครรภ์ยืดเยื้อ/คลอดยาก", _mothers_with(data, cfg.dx_prolonged), mothers),
        ("fetal_distress", "Fetal distress", _mothers_with(data, cfg.dx_fetal_distress), mothers),
        ("prom", "ถุงน้ำคร่ำแตกก่อนเจ็บครรภ์", _mothers_with(data, cfg.dx_prom), mothers),
        ("lbw", "ทารกน้ำหนักน้อย (LBW)", sum(1 for r in alive if r["weight"] < cfg.lbw_grams), len(alive)),
        ("refer", "ส่งต่อ", sum(r["n"] for r in data["refers"]), mothers),
    ]
    return [{"key": k, "label": lb, "n": n, "den": d} for k, lb, n, d in items]


def yearly_table(loader, years, cfg):
    """ตารางผลงานรายปีงบ — loader(d1, d2) → data dict · คืน {"years": [...], "rows": [{key,label,values}]}"""
    per_year = [{r["key"]: r["value"] for r in kpi_rows(loader(*fy_range(fy)), cfg)} for fy in years]
    return {"years": list(years),
            "rows": [{"key": k, "label": LABELS[k], "values": [y[k] for y in per_year]} for k in KPI_KEYS]}
