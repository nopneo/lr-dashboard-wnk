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
    return any(c.startswith(p) for c in codes if c for p in prefixes)


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


def uncoded_ans(data, cfg):
    """การคลอดที่ยังไม่มี Dx คลอด (cfg.delivery_icd10) และไม่มีหัตถการ — มักเป็นแฟ้มที่ยังลงรหัสไม่เสร็จ
    ไม่นับเป็น "ผิดปกติ" (ไม่งั้นเดือนล่าสุดที่ยังลงรหัสไม่ครบจะดูเหมือนมีภาวะแทรกซ้อนพุ่ง)"""
    special = set()
    for w in ("cs", "forceps", "vacuum", "breech"):
        special |= _op_ans(data, cfg, w)
    return [an for an in mother_ans(data)
            if an not in special and not _has(data["dx_by_an"].get(an, ()), cfg.delivery_icd10)]


def abnormal_ans(data, cfg):
    return set(mother_ans(data)) - normal_ans(data, cfg) - set(uncoded_ans(data, cfg))


#: ความหมายมาตรฐาน ICD-10 Z37.x (ผลของการคลอด) → (ทารกที่คลอดทั้งหมด, ที่ไร้ชีพ) — เป็นความหมายสากล ไม่ใช่รหัสเฉพาะ รพ.
Z37_BIRTHS = {"Z370": (1, 0), "Z371": (1, 1), "Z372": (2, 0), "Z373": (2, 1), "Z374": (2, 2),
              "Z375": (3, 0), "Z376": (3, 1), "Z377": (3, 3)}


def infant_is_still(r, cfg):
    """ทารกรายนี้ไร้ชีพ: สถานะจำหน่ายตาย (cfg.stillbirth_dchstts) หรือ Dx ของทารกเป็นรหัสไร้ชีพ"""
    icd = (r.get("infant_icd10") or "").replace(".", "").upper()
    return r.get("dchstts") in cfg.stillbirth_dchstts or _has([icd], cfg.stillbirth_icd10)


def _dx_births(codes, cfg):
    births = still = 0
    for c in codes:
        if c:
            b, st = Z37_BIRTHS.get(c[:4], (0, 0))
            births, still = max(births, b), max(still, st)
    if still == 0 and _has(codes, cfg.stillbirth_icd10):
        still, births = 1, max(births, 1)
    return births, still


def birth_summary(data, cfg):
    """สรุปทารกระดับรายคน: babies · still_total · still_idx (ดัชนีใน data["infants"]) · still_an · missing
    ใช้ทั้งแถวทารกและ Dx Z37.x ของมารดา — ถ้า Dx บอกว่ามีทารกมากกว่าแถวที่บันทึก จะเติมให้และนับใน missing"""
    infants, mothers = data["infants"], set(mother_ans(data))
    by_an = {}
    for i, r in enumerate(infants):
        by_an.setdefault(r["an"], []).append(i)
    babies = still_total = missing = 0
    still_idx, still_an = set(), set()
    for an in set(by_an) | mothers:
        idxs = by_an.get(an, [])
        flagged = [i for i in idxs if infant_is_still(infants[i], cfg)]
        ib, ist = _dx_births(data["dx_by_an"].get(an, ()), cfg) if an in mothers else (0, 0)
        still_n = max(len(flagged), ist)
        pool = sorted((i for i in idxs if i not in flagged), key=lambda i: (not infants[i]["dead"], i))
        still_idx |= set(flagged) | set(pool[:still_n - len(flagged)])
        births = max(len(idxs), ib, still_n)
        missing += births - len(idxs)
        babies += births
        still_total += still_n
        if still_n:
            still_an.add(an)
    return {"babies": babies, "still_total": still_total, "still_idx": still_idx, "still_an": still_an,
            "missing": missing}


def stillbirth_ans(data, cfg):
    return birth_summary(data, cfg)["still_an"] & set(mother_ans(data))


def twin_ans(data, cfg):
    mothers = set(mother_ans(data))
    out = {r["an"] for r in data["deliveries"] if r["twin"] and not r["is_abort"]}
    per_mother = Counter(r["ipt_labour_id"] for r in data["infants"])
    out |= {r["an"] for r in data["infants"] if per_mother[r["ipt_labour_id"]] >= 2}
    out |= {an for an in mothers if _dx_births(data["dx_by_an"].get(an, ()), cfg)[0] >= 2}      # Dx Z37.2–Z37.7
    return out & mothers


_NEG = re.compile(r"(non[\s\-_]*react|\bneg|\bnr\b|-\s*ve\b|ไม่พบ|ไม่ตรวจพบ|ลบ)")
_POS = re.compile(r"(react|\bpos|^r$|\+\s*ve\b|^\+$|\d\+|พบ|บวก|^wr$|weak|\d+\s*:\s*\d+)")   # titer เช่น 1:8 = reactive
#: ตัวแรกของคำที่ถูกต้อง: a-z · 0-9 · พยัญชนะไทย · สระนำ เ แ โ ใ ไ · เลขไทย · + · -
#: (ตัวผันภาษาไทยที่หลุดมาจากแป้นพิมพ์ เช่น "์NR" และอักขระขยะ tis-620 ถูกตัดทิ้ง)
_LEAD_JUNK = re.compile(r"^[^a-z0-9ก-ฮเ-ไ๐-๙+\-]+")


def classify_result(text):
    """ผลแล็บพิมพ์มือ → 'pos' | 'neg' | 'unclear' · ตรวจกลุ่มลบก่อน เพราะ "Non-reactive" มีคำว่า reactive อยู่ข้างใน
    ตัวอักษรขยะ/ตัวผันนำหน้าถูกตัดทิ้งก่อนจับคู่ · "ไม่ชัด" ไม่นับเป็นลบ และไม่นับเป็นบวกด้วย — จำนวนที่ไม่ชัด
    ถูกรายงานที่ /check (ความครบ + ผลแล็บ) เพื่อไม่ให้ผลบวกที่พิมพ์แปลกหายไปเงียบ ๆ"""
    if text is None:
        return "unclear"
    t = _LEAD_JUNK.sub("", str(text).strip().lower())
    if not t:
        return "unclear"
    if _NEG.search(t):
        return "neg"
    if _POS.search(t):
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
    births = birth_summary(data, cfg)
    v = {
        "mothers": len(mothers), "normal": len(normal), "abnormal": len(abnormal_ans(data, cfg)),
        "cs": len(_op_ans(data, cfg, "cs")), "forceps": len(_op_ans(data, cfg, "forceps")),
        "vacuum": len(_op_ans(data, cfg, "vacuum")), "breech": len(_op_ans(data, cfg, "breech")),
        "twins": len(twin_ans(data, cfg)),
        "bba": len({r["an"] for r in data["infants"] if r["bba_type"] in cfg.bba_types}),
        "babies": births["babies"], "still": births["still_total"], "live": births["babies"] - births["still_total"],
        "neo_death7": sum(1 for i, r in enumerate(data["infants"])
                          if r["dead"] and i not in births["still_idx"] and r["days_to_dch"] is not None
                          and r["days_to_dch"] <= 7),
        "apgar1_low": sum(1 for r in data["infants"] if r["apgar1"] is not None and r["apgar1"] <= cfg.apgar1_max),
    }
    for key in ("amph", "syphilis", "hiv", "hbv"):
        n = _lab_value(data, key)
        if n is not None:
            v[key] = n
    return [_row(k, v[k]) if k in v else _row(k, None, "nodata") for k in KPI_KEYS]


def monthly(data, cfg, months):
    """รายเดือน: ปกติ / มีภาวะแทรกซ้อน / ยังไม่ลงรหัส Dx คลอด / ส่งต่อ (ไม่นับเป็นคลอดที่ รพ.)"""
    normal, uncoded = normal_ans(data, cfg), set(uncoded_ans(data, cfg))
    out = {m: {"ym": m, "normal": 0, "complicated": 0, "uncoded": 0, "referred": 0} for m in months}
    for r in data["deliveries"]:
        if r["is_abort"] or r["ym"] not in out:
            continue
        out[r["ym"]]["normal" if r["an"] in normal else "uncoded" if r["an"] in uncoded else "complicated"] += 1
    for r in data["refers"]:
        if r["ym"] in out:
            out[r["ym"]]["referred"] += r["n"]
    return [out[m] for m in months]


def _mothers_with(data, prefixes):
    return sum(1 for an in mother_ans(data) if _has(data["dx_by_an"].get(an, ()), prefixes))


def is_asphyxia(r, cfg):
    """ทารกขาดออกซิเจน: Apgar 5 นาที < เกณฑ์ หรือ ICD ขาดออกซิเจน หรือมี labor_ba_id"""
    icd = (r.get("infant_icd10") or "").replace(".", "").upper()
    return ((r["apgar5"] is not None and r["apgar5"] < cfg.asphyxia_apgar5)
            or _has([icd], cfg.asphyxia_icd10) or (r["labor_ba_id"] or 0) > 0)


def lbw_pool(data):
    """ตัวหาร LBW: ทารกที่ไม่ตายและมีน้ำหนัก"""
    return [r for r in data["infants"] if not r["dead"] and r["weight"] is not None]


def quality_grid(data, cfg):
    """ตัวชี้วัดคุณภาพ: n = จำนวน, den = ตัวหาร (แม่ หรือ เด็ก)"""
    infants, mothers = data["infants"], len(mother_ans(data))

    alive = lbw_pool(data)
    items = [
        ("asphyxia", "Birth asphyxia", sum(1 for r in infants if is_asphyxia(r, cfg)), len(infants)),
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
    """ตารางผลงานรายปีงบ — loader(d1, d2) → data dict · คืน {"years", "errors" (รายปี), "rows": [{key,label,values}]}
    ปีที่อ่านข้อมูลบางแหล่งไม่ได้ → values เป็น None (หน้าเว็บแสดงขีด ไม่ใช่ 0)"""
    loaded = [loader(*fy_range(fy)) for fy in years]
    errors = [list(d.get("errors") or []) for d in loaded]
    per_year = [{r["key"]: r["value"] for r in kpi_rows(d, cfg)} for d in loaded]
    return {"years": list(years), "errors": errors,
            "rows": [{"key": k, "label": LABELS[k], "values": [None if errors[i] else y[k] for i, y in enumerate(per_year)]}
                     for k in KPI_KEYS]}
