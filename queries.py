"""SQL อ่านอย่างเดียวของ LR dashboard — คืน list[dict] ที่แปลงชนิดแล้ว

รหัสทุกตัวมาจาก Config และส่งเป็นพารามิเตอร์ (ห้ามเขียนรหัสตายตัวใน SQL) · `%` ตัวอักษรใน SQL เขียน `%%`
ทุกฟังก์ชันรับ (d1, d2, cfg) ช่วงปิดหัวท้าย `between d1 and d2`
"""

import re
from datetime import date, datetime, timedelta

import db


def _d(v):
    """date | 'YYYY-MM-DD' (โหมด ssh คืน str) | None → date | None"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _i(v):
    """ค่าว่าง/NULL → None · ตัวเลขที่เป็น str → int"""
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _s(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


def _in(codes):
    """`in ()` เป็น SQL ผิดไวยากรณ์ — รายการว่างใช้ค่าที่ไม่มีวันตรงกับข้อมูล"""
    return tuple(codes) if codes else ("\x00none",)


# ---------------------------------------------------------------- การคลอด (ระดับแม่ = 1 AN)

#: หลักฐานว่า AN ใน ipt_pregnancy เป็นการคลอดจริง: มีทารกใน ipt_labour_infant หรือมี Dx คลอด (cfg.delivery_icd10)
#: — ฐานจริงมีแถวที่ไม่ใช่การคลอด (รอคลอด/ไม่คลอด) ปนอยู่ และ ipt_pregnancy.abort เป็น NULL ทั้งตาราง
_INFANT_EVIDENCE = ("exists (select 1 from ipt_labour il0 join ipt_labour_infant i0 on i0.ipt_labour_id = il0.ipt_labour_id "
                    "where il0.an = p.an)")
_DX_EVIDENCE = ("exists (select 1 from iptdiag d0 where d0.an = p.an "
                "and left(replace(d0.icd10, '.', ''), 3) in %(deliv)s)")
DELIVERED = f"({_INFANT_EVIDENCE} or {_DX_EVIDENCE})"
NOT_DELIVERED = f"not {_INFANT_EVIDENCE} and not {_DX_EVIDENCE}"
NOT_ABORT_FLAG = "not (coalesce(p.abort, 'N') = 'Y' or coalesce(p.pregnancy_abort_type_id, 0) > 0)"

#: is_abort = 1 หมายถึง "ไม่นับเป็นการคลอด" (ธงแท้ง หรือไม่มีหลักฐานการคลอด) — ชื่อเดิมคงไว้ให้ metrics/tests ใช้ร่วมกัน
DELIVERIES = f"""
select p.an, p.labor_date, date_format(p.labor_date, '%%Y-%%m') ym,
       if(coalesce(p.twin_child_count, 0) >= 2, 1, 0) twin,
       if({NOT_ABORT_FLAG} and {DELIVERED}, 0, 1) is_abort
  from ipt_pregnancy p
 where p.labor_date between %(d1)s and %(d2)s
"""


def deliveries(d1, d2, cfg):
    return [{"an": r["an"], "labor_date": _d(r["labor_date"]), "ym": r["ym"],
             "twin": _i(r.get("twin")) or 0, "is_abort": _i(r.get("is_abort")) or 0}
            for r in db.fetch(DELIVERIES, {"d1": d1, "d2": d2, "deliv": _in(cfg.delivery_icd10)})]


DELIVERY_DX = """
select distinct d.an, replace(upper(d.icd10), '.', '') icd10
  from ipt_pregnancy p
  join iptdiag d on d.an = p.an
 where p.labor_date between %(d1)s and %(d2)s
"""


def delivery_dx(d1, d2, cfg):
    return [{"an": r["an"], "icd10": r["icd10"]} for r in db.fetch(DELIVERY_DX, {"d1": d1, "d2": d2}) if r.get("icd10")]


DELIVERY_OPS = """
select distinct o.an, replace(o.icd9, '.', '') icd9
  from ipt_pregnancy p
  join iptoprt o on o.an = p.an
 where p.labor_date between %(d1)s and %(d2)s
"""


def delivery_ops(d1, d2, cfg):
    return [{"an": r["an"], "icd9": r["icd9"]} for r in db.fetch(DELIVERY_OPS, {"d1": d1, "d2": d2}) if r.get("icd9")]


# ---------------------------------------------------------------- ทารก

INFANTS = """
select i.ipt_labour_id, il.an, i.birth_date, date_format(i.birth_date, '%%Y-%%m') ym,
       i.birth_weight weight, i.apgar_score_min1 apgar1, i.apgar_score_min5 apgar5,
       i.infant_dchstts dchstts, coalesce(n.dead, 'N') dead,
       i.infant_delivery_type_id bba_type, i.labor_ba_id, i.infant_icd10,
       datediff(ib.dchdate, i.birth_date) days_to_dch
  from ipt_labour_infant i
  join ipt_labour il on il.ipt_labour_id = i.ipt_labour_id
  left join ipt_newborn n on n.an = i.infant_an
  left join ipt ib on ib.an = i.infant_an
 where i.birth_date between %(d1)s and %(d2)s
"""


def infants(d1, d2, cfg):
    """ทารกเกิดใน รพ. · dead = ipt_newborn.dead='Y' หรือ infant_dchstts ∈ cfg.dead_dchstts (ตาม ANC dashboard)
    · bba_type = infant_delivery_type_id (นับเป็น BBA เมื่ออยู่ใน cfg.bba_types — ตัดสินใน metrics)"""
    dead, bba = _in(cfg.dead_dchstts), _in(cfg.bba_types)
    out = []
    for r in db.fetch(INFANTS, {"d1": d1, "d2": d2, "dead": dead, "bba": bba}):
        dchstts = _s(r.get("dchstts"))
        out.append({"ipt_labour_id": _i(r["ipt_labour_id"]), "an": r.get("an"), "birth_date": _d(r["birth_date"]),
                    "ym": r["ym"], "weight": _i(r.get("weight")), "apgar1": _i(r.get("apgar1")),
                    "apgar5": _i(r.get("apgar5")), "dchstts": dchstts,
                    "dead": str(r.get("dead") or "N").upper() == "Y" or dchstts in dead,
                    "bba_type": _s(r.get("bba_type")), "labor_ba_id": _i(r.get("labor_ba_id")),
                    "infant_icd10": _s(r.get("infant_icd10")), "days_to_dch": _i(r.get("days_to_dch"))})
    return out


# ---------------------------------------------------------------- ผลแล็บตอนคลอด (ipt_labour_lab → ipt_labour.an)

LAB_RESULTS = """
select il.an,
       case when l.lab_id in %(syph)s then 'syphilis'
            when l.lab_id in %(hiv)s then 'hiv'
            when l.lab_id in %(hbv)s then 'hbv' end lab_key,
       l.lab_value result
  from ipt_labour_lab l
  join ipt_labour il on il.ipt_labour_id = l.ipt_labour_id
  join ipt_pregnancy p on p.an = il.an
 where p.labor_date between %(d1)s and %(d2)s
   and (l.lab_id in %(syph)s or l.lab_id in %(hiv)s or l.lab_id in %(hbv)s)
union all
select p.an, 'amph' lab_key, o.lab_order_result result
  from ipt_pregnancy p
  join lab_head h on h.vn = p.an
  join lab_order o on o.lab_order_number = h.lab_order_number
 where p.labor_date between %(d1)s and %(d2)s and o.lab_items_code in %(amph)s
"""


def lab_results(d1, d2, cfg):
    args = {"d1": d1, "d2": d2, "syph": _in(cfg.syphilis_labs), "hiv": _in(cfg.hiv_labs), "hbv": _in(cfg.hbv_labs),
            "amph": _in(cfg.amph_labs)}
    return [{"an": r["an"], "lab_key": r["lab_key"], "result": r.get("result")} for r in db.fetch(LAB_RESULTS, args)]


# ---------------------------------------------------------------- ผล lab ตลอดการตั้งครรภ์ (แบบ ANC dashboard)

#: ชื่อรายการใน lab_items ของแต่ละการตรวจ (ชื่อต้องขึ้นต้นด้วยคำนี้ — Ampicillin ไม่ใช่ Amphetamine) — ตรวจที่ /check
LAB_NAME_RX = {"syphilis": r"^(vdrl|rpr|tpha|syphilis)\b", "hbv": r"^hbs\s*ag\b",
               "hiv": r"^(anti-?\s*hiv|hiv\s*ag)\b", "amph": r"^(meth)?amphetamine\b"}


def lab_item_codes(cfg):
    """{การตรวจ: (lab_items_code, ...)} — รหัสที่ตั้งใน env ใช้ก่อน · ที่ไม่ได้ตั้งเลือกจากชื่อรายการ lab_items"""
    conf = {"syphilis": tuple(cfg.syphilis_items), "hiv": tuple(cfg.hiv_items), "hbv": tuple(cfg.hbv_items),
            "amph": tuple(cfg.amph_labs)}
    if all(conf.values()):
        return conf
    picked = {k: set() for k in conf}
    for r in db.fetch("select lab_items_code code, lab_items_name name from lab_items"):
        name = str(r.get("name") or "").strip()
        for k, rx in LAB_NAME_RX.items():
            if re.search(rx, name, re.I):
                picked[k].add(str(r["code"]))
    return {k: conf[k] or tuple(sorted(picked[k])) for k in conf}


PREGNANCY_LABS = """
select p.an, lo.lab_items_code code, lo.lab_order_result result
  from ipt_pregnancy p
  join ipt i on i.an = p.an
  join lab_head lh on lh.hn = i.hn
  join lab_order lo on lo.lab_order_number = lh.lab_order_number
 where p.labor_date between %(d1)s and %(d2)s and lo.lab_items_code in %(codes)s
   and lh.order_date between date_sub(p.labor_date, interval %(before)s day)
                         and date_add(p.labor_date, interval %(after)s day)
"""


def pregnancy_lab_results(d1, d2, cfg):
    """ผล lab (ซิฟิลิส/HIV/HBsAg/Amphetamine) ของมารดาตลอดการตั้งครรภ์ — จับด้วย HN ภายใน cfg.lab_window_before วัน
    ก่อนวันคลอดถึง cfg.lab_window_after วันหลังคลอด · พบผลบวกครั้งใดก็นับเป็นบวก (metrics) เหมือน ANC dashboard"""
    test_of = {c: k for k, codes in lab_item_codes(cfg).items() for c in codes}
    rows = db.fetch(PREGNANCY_LABS, {"d1": d1, "d2": d2, "codes": _in(tuple(test_of)),
                                     "before": cfg.lab_window_before, "after": cfg.lab_window_after})
    return [{"an": r["an"], "lab_key": test_of[str(r["code"])], "result": r.get("result")}
            for r in rows if str(r.get("code")) in test_of]


# ---------------------------------------------------------------- แบบคัดกรองครรภ์เสี่ยง ข้อ "ติดยาเสพติด ติดสุรา"

SUBSTANCE_FLAGS = """
select p.an, max(if(c.person_anc_classifying_id is not null, 1, 0)) flag
  from ipt_pregnancy p
  join ipt i on i.an = p.an
  join (select a0.person_anc_id, pt.hn, a0.lmp, a0.labor_date from person_anc a0
          join person pe on pe.person_id = a0.person_id
          join patient pt on pt.hn = pe.patient_hn) a
    on a.hn = i.hn
   and p.labor_date between coalesce(a.lmp, date_sub(p.labor_date, interval %(before)s day))
                        and date_add(coalesce(a.labor_date, p.labor_date), interval %(after)s day)
  left join person_anc_classifying c on c.person_anc_id = a.person_anc_id and c.check_value = 'Y'
       and c.person_anc_classifying_item_id in %(items)s
 where p.labor_date between %(d1)s and %(d2)s
 group by p.an
"""


def substance_flags(d1, d2, cfg):
    """เฉพาะมารดาที่จับคู่กับทะเบียนฝากครรภ์ (person_anc) ได้ · flag = 1 ถ้าแบบคัดกรองติ๊ก 'Y' ในข้อ cfg.substance_items
    — ไม่มีแถว = ไม่มีข้อมูลของมารดารายนั้น (ไม่ใช่ 'ไม่ติด')"""
    rows = db.fetch(SUBSTANCE_FLAGS, {"d1": d1, "d2": d2, "items": _in(cfg.substance_items),
                                      "before": cfg.lab_window_before, "after": cfg.lab_window_after})
    return [{"an": r["an"], "flag": _i(r.get("flag")) or 0} for r in rows]


# ---------------------------------------------------------------- ส่งต่อ + ช่วงล่าสุด

REFERS_SQL = f"""
select date_format(r.refer_date, '%%Y-%%m') ym, count(*) n
  from referout r
  join ipt_pregnancy p on p.an = r.vn
 where r.refer_date between %(d1)s and %(d2)s and {NOT_DELIVERED}
 group by ym
"""


def lr_refers(d1, d2, cfg):
    """ส่งต่อ = มารดาที่รับไว้ห้องคลอด (AN อยู่ใน ipt_pregnancy) แล้วส่งต่อโดยยังไม่ได้คลอดที่ รพ. — นับตามเดือนที่ส่งต่อ
    (referout.vn = AN สำหรับผู้ป่วยใน · ทารกส่งต่อ (Dx Z38/P..) อยู่ใต้ AN ของทารก จึงไม่ปนมา)"""
    rows = db.fetch(REFERS_SQL, {"d1": d1, "d2": d2, "deliv": _in(cfg.delivery_icd10)})
    return [{"ym": r["ym"], "n": _i(r["n"]) or 0} for r in rows]


def recent_counts(today, cfg):
    d1, d2 = today - timedelta(days=6), today
    rows = db.fetch(f"select count(*) n from ipt_pregnancy p where p.labor_date between %(d1)s and %(d2)s "
                    f"and {NOT_ABORT_FLAG} and {DELIVERED}",
                    {"d1": d1, "d2": d2, "deliv": _in(cfg.delivery_icd10)})
    return {"days7": (_i(rows[0]["n"]) or 0) if rows else 0}


CASE_NAMES = """
select i.an, i.hn, concat(coalesce(pt.pname, ''), coalesce(pt.fname, ''), ' ', coalesce(pt.lname, '')) name
  from ipt i left join patient pt on pt.hn = i.hn
 where i.an in %(ans)s
"""


def case_names(ans):
    """{an: {hn, name}} — ข้อมูลระบุตัวผู้ป่วย: ใช้เฉพาะหน้ารายชื่อหลัง login เท่านั้น"""
    ans, out = list(ans), {}
    for i in range(0, len(ans), 500):
        for r in db.fetch(CASE_NAMES, {"ans": tuple(ans[i:i + 500])}):
            out[r["an"]] = {"hn": r.get("hn") or "", "name": (r.get("name") or "").strip()}
    return out
