"""รวมผล queries เป็นชุดข้อมูลเดียว (dict) สำหรับ metrics / app / audit

แหล่งไหนล้ม → ใส่ชื่อใน data["errors"] แล้วใช้ค่าว่าง (หน้าเว็บขึ้นเตือน ไม่ล่มทั้งหน้า)
"""

import logging
from collections import defaultdict

import queries

log = logging.getLogger(__name__)

SOURCES = ("deliveries", "delivery_dx", "delivery_ops", "infants", "lab_results", "pregnancy_lab_results",
           "substance_flags", "lr_refers")


def load_data(d1, d2, cfg):
    errors, got = [], {}
    for name in SOURCES:
        try:
            got[name] = getattr(queries, name)(d1, d2, cfg)
        except Exception:                                    # noqa: BLE001 — ไม่ให้แหล่งเดียวทำทั้งหน้าล่ม
            log.exception("query %s failed", name)
            got[name] = []
            errors.append(name)
    dx, ops = defaultdict(set), defaultdict(set)
    for r in got["delivery_dx"]:
        dx[r["an"]].add(r["icd10"])
    for r in got["delivery_ops"]:
        ops[r["an"]].add(r["icd9"])
    return {"deliveries": got["deliveries"], "dx_by_an": dict(dx), "ops_by_an": dict(ops),
            "infants": got["infants"], "labs": got["lab_results"] + got["pregnancy_lab_results"],
            "substance": got["substance_flags"], "refers": got["lr_refers"], "errors": errors}
