"""SQL อ่านอย่างเดียวของ LR dashboard — คืน list[dict] ที่แปลงชนิดแล้ว

รหัสทุกตัวมาจาก Config และส่งเป็นพารามิเตอร์ (ห้ามเขียนรหัสตายตัวใน SQL) · `%` ตัวอักษรใน SQL เขียน `%%`
ทุกฟังก์ชันรับ (d1, d2, cfg) ช่วงปิดหัวท้าย `between d1 and d2`
"""

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

DELIVERIES = """
select p.an, p.labor_date, date_format(p.labor_date, '%%Y-%%m') ym,
       if(coalesce(p.twin_child_count, 0) >= 2, 1, 0) twin,
       if(coalesce(p.abort, 'N') = 'Y' or coalesce(p.pregnancy_abort_type_id, 0) > 0, 1, 0) is_abort
  from ipt_pregnancy p
 where p.labor_date between %(d1)s and %(d2)s
"""


def deliveries(d1, d2, cfg):
    return [{"an": r["an"], "labor_date": _d(r["labor_date"]), "ym": r["ym"],
             "twin": _i(r.get("twin")) or 0, "is_abort": _i(r.get("is_abort")) or 0}
            for r in db.fetch(DELIVERIES, {"d1": d1, "d2": d2})]


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
"""


def lab_results(d1, d2, cfg):
    args = {"d1": d1, "d2": d2, "syph": _in(cfg.syphilis_labs), "hiv": _in(cfg.hiv_labs), "hbv": _in(cfg.hbv_labs)}
    return [{"an": r["an"], "lab_key": r["lab_key"], "result": r.get("result")} for r in db.fetch(LAB_RESULTS, args)]


# ---------------------------------------------------------------- ส่งต่อ + ช่วงล่าสุด

def lr_refers(d1, d2, cfg):
    """ส่งต่อรายเดือน — ตอนนี้นับ referout ที่ Dx หลัก (pdx) ขึ้นต้นด้วย cfg.refer_dx_prefix · นิยามละเอียดยืนยันใน Task 6"""
    args = {"d1": d1, "d2": d2}
    conds = []
    for i, p in enumerate(cfg.refer_dx_prefix or ("\x00none",)):
        args[f"rp{i}"] = p + "%"
        conds.append(f"r.pdx like %(rp{i})s")
    sql = ("select date_format(r.refer_date, '%%Y-%%m') ym, count(*) n from referout r "
           "where r.refer_date between %(d1)s and %(d2)s and (" + " or ".join(conds) + ") group by ym")
    return [{"ym": r["ym"], "n": _i(r["n"]) or 0} for r in db.fetch(sql, args)]


def recent_counts(today, cfg):
    d1, d2 = today - timedelta(days=6), today
    rows = db.fetch("select count(*) n from ipt_pregnancy p where p.labor_date between %(d1)s and %(d2)s "
                    "and not (coalesce(p.abort, 'N') = 'Y' or coalesce(p.pregnancy_abort_type_id, 0) > 0)",
                    {"d1": d1, "d2": d2})
    return {"days7": _i(rows[0]["n"]) or 0 if rows else 0}
