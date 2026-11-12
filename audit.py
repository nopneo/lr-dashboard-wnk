"""Data Audit (หน้า /check) — ทุกรหัสที่แอปสมมติไว้ แสดง "แอปใช้ vs พบในข้อมูล" + ค่า env ที่ควรตั้ง

แสดงเฉพาะจำนวนนับ ไม่มีข้อมูลรายคน · แต่ละรายการรันแยกกัน (รายการหนึ่งล้มไม่ทำให้รายการอื่นหาย)
"""

import db
import metrics
from queries import DELIVERED, NOT_ABORT_FLAG, _in

#: ICD-10 ที่ถือว่าเป็น "การคลอด" ใช้กระทบยอดเท่านั้น (O80–O84)
DELIVERY_ICD = ("O80", "O81", "O82", "O83", "O84")



def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _found(rows):
    return [{"code": "" if r.get("code") is None else str(r["code"]), "name": r.get("name") or "", "n": _num(r["n"])}
            for r in rows]


def _item(key, title, app_uses, found, status, env, hint):
    return {"key": key, "title": title, "app_uses": app_uses, "found": found, "status": status, "env": env,
            "hint": hint}


def _guard(key, title, env, fn):
    try:
        return fn()
    except Exception as e:                                       # noqa: BLE001
        return _item(key, title, "—", [], "bad", env, f"ตรวจไม่ได้: {type(e).__name__}: {str(e)[:120]}")


# ---------------------------------------------------------------- กระทบยอดจำนวนคลอด 4 แหล่ง

def reconcile(d1, d2, cfg):
    a = {"d1": d1, "d2": d2}
    q = {
        "ipt_pregnancy": ("select count(*) n from ipt_pregnancy p where p.labor_date between %(d1)s and %(d2)s and "
                          + NOT_ABORT_FLAG + " and " + DELIVERED, {**a, "deliv": _in(cfg.delivery_icd10)}),
        "ipt_labour_infant_mothers": ("select count(distinct i.ipt_labour_id) n from ipt_labour_infant i "
                                      "where i.birth_date between %(d1)s and %(d2)s", a),
        "labor": ("select count(*) n from labor l where l.labour_finishdate between %(d1)s and %(d2)s", a),
        "icd_delivery": ("select count(distinct d.an) n from iptdiag d join ipt i on i.an = d.an "
                         "where i.dchdate between %(d1)s and %(d2)s and left(d.icd10, 3) in %(codes)s",
                         {**a, "codes": _in(DELIVERY_ICD)}),
    }
    sources = {k: _num((db.fetch(sql, args) or [{"n": 0}])[0]["n"]) for k, (sql, args) in q.items()}
    top, low = max(sources.values()), min(sources.values())
    diff = top - low
    return {"sources": sources, "max_diff": diff, "status": "warn" if diff > max(3, top * 0.05) else "ok"}


def _reconcile_item(d1, d2, cfg):
    r = reconcile(d1, d2, cfg)
    return _item("reconcile", "กระทบยอดจำนวนการคลอด 4 แหล่ง", "ipt_pregnancy ที่มีหลักฐานการคลอด (หลัก) เทียบ ipt_labour_infant · labor · ICD O80–O84",
                 [{"code": k, "name": "", "n": v} for k, v in r["sources"].items()], r["status"], "LR_DATA_AUDITED",
                 f"ส่วนต่างสูงสุด {r['max_diff']} ราย — ถ้าต่างมาก ให้หาสาเหตุก่อนใช้ตัวเลข (แท้ง/ไม่คลอด/ไม่มีบันทึกทารก) "
                 "แล้วตั้ง LR_DATA_AUDITED=1 เมื่อตรวจครบ")


# ---------------------------------------------------------------- รายการรหัส

def _dx_top(d1, d2, cfg, key, title, uses, env, codes=None, hint="", width=3):
    """Dx ที่พบในการคลอด จัดกลุ่มตาม `width` ตัวอักษรแรก (ไม่มีจุด) · codes = กรองเฉพาะรหัสที่แอปสนใจ (3 หรือ 4 ตัว)"""
    def run():
        grp = f"left(replace(d.icd10, '.', ''), {int(width)})"
        extra = (" and (left(replace(d.icd10, '.', ''), 3) in %(codes)s or left(replace(d.icd10, '.', ''), 4) in %(codes)s)"
                 if codes else "")
        rows = db.fetch(f"select {grp} code, '' name, count(distinct d.an) n "
                        "from ipt_pregnancy p join iptdiag d on d.an = p.an "
                        "where p.labor_date between %(d1)s and %(d2)s" + extra +
                        f" group by {grp} order by n desc limit 15",
                        {"d1": d1, "d2": d2, "codes": _in(codes) if codes else ()})
        return _item(key, title, uses, _found(rows), "ok", env, hint)
    return _guard(key, title, env, run)


def _normal_icd(d1, d2, cfg):
    it = _dx_top(d1, d2, cfg, "normal_icd", "Dx ที่พบในการคลอด (15 อันดับ) — คลอดปกติ",
                 f"คลอดปกติ = {', '.join(cfg.normal_icd)}", "LR_NORMAL_ICD",
                 hint="ตรวจว่ารหัสคลอดปกติของ รพ. ตรงกับที่ตั้ง · ถ้าไม่พบรหัสที่ตั้งเลย ตัวเลข 'คลอดปกติ' จะเป็น 0")
    if it["status"] != "bad" and not any(f["code"].startswith(p) for f in it["found"] for p in cfg.normal_icd):
        it["status"] = "warn"
    return it


def _special_ops(d1, d2, cfg):
    prefixes = (tuple(cfg.cs_icd9) + tuple(cfg.forceps_icd9) + tuple(cfg.vacuum_icd9) + tuple(cfg.breech_icd9))

    def run():
        rows = db.fetch("select left(replace(o.icd9, '.', ''), 3) code, '' name, count(distinct o.an) n "
                        "from ipt_pregnancy p join iptoprt o on o.an = p.an "
                        "where p.labor_date between %(d1)s and %(d2)s group by left(replace(o.icd9, '.', ''), 3) "
                        "order by n desc limit 15", {"d1": d1, "d2": d2})
        found = _found(rows)
        for f in found:
            hit = [p for p in prefixes if f["code"].startswith(p[:3])]
            f["name"] = "ตรงรหัสผ่าท้อง/คีม/สุญญากาศ/ท่าก้น ที่ตั้ง" if hit else ""
        return _item("special_ops", "หัตถการระหว่างคลอด (ICD-9)",
                     f"ผ่าท้อง {', '.join(cfg.cs_icd9)} · คีม {', '.join(cfg.forceps_icd9)} · "
                     f"สุญญากาศ {', '.join(cfg.vacuum_icd9)} · ท่าก้น {', '.join(cfg.breech_icd9)}",
                     found, "ok", "LR_CS_ICD9 · LR_FORCEPS_ICD9 · LR_VACUUM_ICD9 · LR_BREECH_ICD9",
                     "รพ.ที่ไม่ผ่าท้อง/ไม่ใช้คีมจะไม่พบรหัสเหล่านี้ — แถวนั้นจะเป็น 0 ซึ่งถูกต้อง")
    return _guard("special_ops", "หัตถการระหว่างคลอด (ICD-9)", "LR_CS_ICD9", run)


def _infant_codes(d1, d2, cfg, key, title, uses, env, col, configured, hint, master_word=None):
    """รหัสที่ตั้ง ต้องพบในข้อมูล หรือ (ถ้ากำหนด master_word) ยืนยันกับ master dchstts ว่าชื่อรหัสตรงความหมาย"""
    def run():
        rows = db.fetch(f"select {col} code, '' name, count(*) n from ipt_labour_infant "
                        "where birth_date between %(d1)s and %(d2)s group by " + col, {"d1": d1, "d2": d2})
        found = _found(rows)
        seen = {f["code"] for f in found}
        status, note = ("ok" if seen & set(configured) else "warn"), hint
        if master_word:
            master = db.fetch("select dchstts code, name from dchstts where dchstts in %(codes)s",
                              {"codes": _in(configured)})
            names = {str(m["code"]): str(m.get("name") or "") for m in master}
            if all(master_word in names.get(c, "").lower() for c in configured):
                status = "ok"
                note = (hint + " · master dchstts: " + ", ".join(f"{c} = {names[c]}" for c in configured)
                        + ("" if seen & set(configured) else " · ไม่พบทารกเสียชีวิตในช่วงนี้"))
        return _item(key, title, uses, found, status, env, note)
    return _guard(key, title, env, run)


def _apgar(d1, d2, cfg):
    def run():
        rows = db.fetch("select 'Apgar1 ว่าง' code, '' name, coalesce(sum(apgar_score_min1 is null), 0) n "
                        "from ipt_labour_infant where birth_date between %(d1)s and %(d2)s "
                        "union all select 'ทารกทั้งหมด', '', count(*) from ipt_labour_infant "
                        "where birth_date between %(d1)s and %(d2)s", {"d1": d1, "d2": d2})
        found = _found(rows)
        miss, total = (found + [{"n": 0}, {"n": 0}])[0]["n"], (found + [{"n": 0}, {"n": 0}])[1]["n"]
        return _item("apgar", "Apgar 1 นาที", f"≤ {cfg.apgar1_max} นับเป็นคะแนนต่ำ · ค่าว่างไม่นับ", found,
                     "warn" if total and miss / total > 0.1 else "ok", "LR_APGAR1_MAX",
                     "ถ้าค่าว่างมากกว่า 10% ตัวชี้วัด Apgar ≤ 7 จะต่ำกว่าความจริง")
    return _guard("apgar", "Apgar 1 นาที", "LR_APGAR1_MAX", run)


def _labs(d1, d2, cfg):
    ids = tuple(cfg.syphilis_labs) + tuple(cfg.hiv_labs) + tuple(cfg.hbv_labs)

    def run():
        rows = db.fetch("select l.lab_value code, l.lab_id name, count(*) n from ipt_labour_lab l "
                        "join ipt_labour il on il.ipt_labour_id = l.ipt_labour_id "
                        "join ipt_pregnancy p on p.an = il.an where p.labor_date between %(d1)s and %(d2)s "
                        "and l.lab_id in %(ids)s group by l.lab_value, l.lab_id order by n desc limit 40",
                        {"d1": d1, "d2": d2, "ids": _in(ids)})
        found = _found(rows)
        unclear = 0
        for f in found:
            cls = metrics.classify_result(f["code"])
            f["name"] = f"lab {f['name']} → {cls}"
            unclear += f["n"] if cls == "unclear" else 0
        total = sum(f["n"] for f in found)
        return _item("labs", "ผลแล็บตอนคลอด (VDRL / Anti-HIV / HBsAg) ใน ipt_labour_lab",
                     f"lab_id: VDRL {', '.join(cfg.syphilis_labs)} · HIV {', '.join(cfg.hiv_labs)} · "
                     f"HBsAg {', '.join(cfg.hbv_labs)}", found, "warn" if total and unclear / total > 0.1 else "ok",
                     "LR_LAB_SYPHILIS · LR_LAB_HIV · LR_LAB_HBV",
                     "ผลพิมพ์มือ จัดเป็นบวก/ลบ/ไม่ชัด · 'ไม่ชัด' ไม่นับเป็นลบ — ถ้ามากกว่า 10% ให้ตรวจคำที่ยังจับไม่ได้")
    return _guard("labs", "ผลแล็บตอนคลอด", "LR_LAB_SYPHILIS", run)


def _no_source(key, title, env, hint):
    return _item(key, title, "ยังไม่มีแหล่งข้อมูล", [], "warn", env, hint)


AMPH_NAME_LIKES = ("%%amphet%%", "%%methamph%%", "%%ยาบ้า%%")


def _amph(d1, d2, cfg):
    """lab_items ที่ชื่อคล้าย Amphetamine พร้อมจำนวนมารดาที่ถูกส่งตรวจ — ใช้เลือกรหัสสำหรับ LR_LAB_AMPH"""
    title = "Amphetamine ปัสสาวะของมารดา (lab_order)"

    def run():
        rows = db.fetch("select i.lab_items_code code, i.lab_items_name name, count(distinct x.an) n "
                        "from lab_items i left join (select p.an, o.lab_items_code from ipt_pregnancy p "
                        "join lab_head h on h.vn = p.an join lab_order o on o.lab_order_number = h.lab_order_number "
                        "where p.labor_date between %(d1)s and %(d2)s) x on x.lab_items_code = i.lab_items_code "
                        "where lower(i.lab_items_name) like %(l0)s or lower(i.lab_items_name) like %(l1)s "
                        "or lower(i.lab_items_name) like %(l2)s or i.lab_items_code in %(amph)s "
                        "group by i.lab_items_code, i.lab_items_name order by n desc limit 15",
                        {"d1": d1, "d2": d2, "l0": AMPH_NAME_LIKES[0], "l1": AMPH_NAME_LIKES[1], "l2": AMPH_NAME_LIKES[2],
                         "amph": _in(cfg.amph_labs)})
        found = _found(rows)
        used = {f["code"] for f in found if f["n"]}
        status = "ok" if used & set(cfg.amph_labs) else "warn"
        return _item("amph", title, f"lab_items_code: {', '.join(cfg.amph_labs) or '(ยังไม่ตั้ง)'}", found, status,
                     "LR_LAB_AMPH", "แสดงรายการ lab ที่ชื่อคล้าย Amphetamine/Methamphetamine ทั้งหมดและจำนวนมารดาที่ถูกส่งตรวจ — "
                     "เลือกรหัสของ รพ. นี้ใส่ LR_LAB_AMPH (ผลพิมพ์มือจัดบวก/ลบแบบเดียวกับ VDRL)")
    return _guard("amph", title, "LR_LAB_AMPH", run)


def audit(d1, d2, cfg):
    items = [
        _guard("reconcile", "กระทบยอดจำนวนการคลอด", "LR_DATA_AUDITED", lambda: _reconcile_item(d1, d2, cfg)),
        _normal_icd(d1, d2, cfg),
        _special_ops(d1, d2, cfg),
        _dx_top(d1, d2, cfg, "stillbirth", "Dx เด็กเกิดไร้ชีพ", f"{', '.join(cfg.stillbirth_icd10)}", "LR_STILLBIRTH_ICD10",
                codes=tuple(cfg.stillbirth_icd10), width=4, hint="Z37.1/.3/.4/.6 และ P95 · Z37.0/.2 = เกิดมีชีพ"),
        _infant_codes(d1, d2, cfg, "dead_dchstts", "สถานะจำหน่ายทารก — รหัสที่นับเป็นเสียชีวิต",
                      ", ".join(cfg.dead_dchstts), "LR_DEAD_DCHSTTS", "infant_dchstts", cfg.dead_dchstts,
                      "ตรวจว่ารหัสเสียชีวิตของ รพ. ตรงกับที่ตั้ง", master_word="dead"),
        _infant_codes(d1, d2, cfg, "bba_types", "ประเภทการคลอดของทารก — รหัสที่นับเป็นคลอดก่อนถึง รพ. (BBA)",
                      ", ".join(cfg.bba_types), "LR_BBA_TYPES", "infant_delivery_type_id", cfg.bba_types,
                      "ตรวจความหมายของ infant_delivery_type_id ใน รพ. นี้"),
        _apgar(d1, d2, cfg),
        _dx_top(d1, d2, cfg, "complication_dx", "Dx ภาวะแทรกซ้อนการคลอด",
                ", ".join(metrics.complication_prefixes(cfg)),
                "LR_DX_PPH · LR_DX_PRETERM · LR_DX_HTN · LR_DX_PROLONGED · LR_DX_FETAL_DISTRESS · LR_DX_PROM",
                codes=tuple({c[:3] for c in metrics.complication_prefixes(cfg)})),
        _labs(d1, d2, cfg),
        _amph(d1, d2, cfg),
        _no_source("alcohol_smoke", "สุรา/บุหรี่ของมารดา", "—",
                   "ไม่พบแหล่งข้อมูลในฐาน (ค้นคอลัมน์ชื่อ smok/alcohol/drink แล้ว ไม่มีตารางของห้องคลอด) — ตัวชี้วัดแสดง 'ไม่มีข้อมูล'"),
    ]
    return items


# ---------------------------------------------------------------- ความครบถ้วนของข้อมูล (จาก loader)

def completeness(data, cfg):
    mothers = set(metrics.mother_ans(data))
    infant_ans = {r["an"] for r in data["infants"]}
    missing = sum(1 for r in data["infants"] if r["apgar1"] is None)
    return [
        {"key": "mothers_without_infant", "title": "การคลอดที่ไม่มีบันทึกทารก", "n": len(mothers - infant_ans),
         "den": len(mothers)},
        {"key": "infants_without_mother", "title": "ทารกที่ไม่มีแถวการคลอดของมารดา", "n": len(infant_ans - mothers),
         "den": len(infant_ans)},
        {"key": "apgar1_missing", "title": "ทารกที่ไม่มี Apgar 1 นาที", "n": missing, "den": len(data["infants"])},
    ]
