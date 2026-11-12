"""รายชื่อเบื้องหลังตัวเลข (หลัง login เท่านั้น) — ใช้นิยามเดียวกับ metrics เพื่อให้จำนวนรายชื่อตรงกับการ์ด/ตัวชี้วัด

นับเป็น "มารดา (AN)" — ตัวชี้วัดระดับทารกที่แม่มีทารกหลายคน (แฝด) จะนับแม่ครั้งเดียว
"""

import metrics

#: key → ชื่อหัวข้อรายชื่อ
KEYS = {
    "mothers": "การคลอดทั้งหมด", "normal": "คลอดปกติ", "abnormal": "คลอดผิดปกติ/มีภาวะแทรกซ้อน", "twins": "ครรภ์แฝด",
    "bba": "คลอดก่อนถึงโรงพยาบาล (BBA)", "still": "เด็กเกิดไร้ชีพ", "apgar1_low": "Apgar 1 นาที ≤ เกณฑ์",
    "asphyxia": "Birth asphyxia", "lbw": "ทารกน้ำหนักน้อย (LBW)", "pph": "PPH", "preterm": "คลอดก่อนกำหนด",
    "htn": "PIH / Pre-eclampsia", "prolonged": "เจ็บครรภ์ยืดเยื้อ/คลอดยาก", "fetal_distress": "Fetal distress",
    "prom": "ถุงน้ำคร่ำแตกก่อนเจ็บครรภ์",
}

_DX_KEYS = {"pph": "dx_pph", "preterm": "dx_preterm", "htn": "dx_htn", "prolonged": "dx_prolonged",
            "fetal_distress": "dx_fetal_distress", "prom": "dx_prom"}


def members(key, data, cfg):
    """AN ของมารดาที่เข้ากลุ่ม key (เรียงตามวันคลอด) · key ที่ไม่รู้จัก → None"""
    if key not in KEYS:
        return None
    mothers = set(metrics.mother_ans(data))
    inf = data["infants"]
    if key == "mothers":
        got = mothers
    elif key == "normal":
        got = metrics.normal_ans(data, cfg)
    elif key == "abnormal":
        got = mothers - metrics.normal_ans(data, cfg)
    elif key == "twins":
        got = metrics.twin_ans(data)
    elif key == "bba":
        got = {r["an"] for r in inf if r["bba_type"] in cfg.bba_types}
    elif key == "still":
        got = metrics.stillbirth_ans(data, cfg)
    elif key == "apgar1_low":
        got = {r["an"] for r in inf if r["apgar1"] is not None and r["apgar1"] <= cfg.apgar1_max}
    elif key == "asphyxia":
        got = {r["an"] for r in inf if metrics.is_asphyxia(r, cfg)}
    elif key == "lbw":
        got = {r["an"] for r in metrics.lbw_pool(data) if r["weight"] < cfg.lbw_grams}
    else:
        prefixes = getattr(cfg, _DX_KEYS[key])
        got = {an for an in mothers if metrics._has(data["dx_by_an"].get(an, ()), prefixes)}
    got &= mothers
    when = {r["an"]: r["labor_date"] for r in data["deliveries"]}
    return sorted(got, key=lambda a: (when.get(a) is None, when.get(a), a))


def table(ans, data, names):
    """(หัวตาราง, แถว) · names = {an: {hn, name}} (ไม่มี = ช่องว่าง) · dx = รหัส 3 ตัวแรกของ Dx กลุ่ม O/P/Z ของแม่คนนั้น"""
    when = {r["an"]: r["labor_date"] for r in data["deliveries"]}
    head = ["วันที่คลอด", "HN", "AN", "ชื่อ-สกุล", "Dx ที่เกี่ยวข้อง"]
    rows = []
    for an in ans:
        who = names.get(an) or {}
        dx = sorted({c[:3] for c in data["dx_by_an"].get(an, ()) if c and c[0] in "OPZ"})
        rows.append({"date": when.get(an), "hn": who.get("hn") or "", "an": an, "name": who.get("name") or "",
                     "dx": ", ".join(dx)})
    return head, rows
