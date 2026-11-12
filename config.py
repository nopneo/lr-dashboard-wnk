"""ค่าตั้งของแอป — อ่านจาก env ทั้งหมด (ค่าเริ่มต้น = รหัสมาตรฐาน HOSxP / ICD-10 / ICD-9-CM)

รหัสทุกตัวที่ SQL ใช้มาจากที่นี่ แล้วส่งเป็นพารามิเตอร์ — ห้ามเขียนรหัสตายตัวใน SQL
แต่ละ รพ. ตรวจว่าค่าตรงกับข้อมูลจริงได้ที่หน้า /check
"""

import os
from dataclasses import dataclass
from datetime import date

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def _list(v):
    return tuple(x.strip() for x in (v or "").split(",") if x.strip())


def _dx(v):
    return tuple(x.replace(".", "").upper() for x in _list(v))


def _num(v, default):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return int(f) if f == int(f) else f


@dataclass(frozen=True)
class Config:
    # คลอดปกติ / หัตถการ (ICD-10 ไม่มีจุด · ICD-9 ใช้เป็น prefix)
    normal_icd: tuple = ("O80",)
    cs_icd9: tuple = ("74",)
    forceps_icd9: tuple = ("720", "721", "722", "723", "724")
    forceps_icd10: tuple = ("O810", "O811", "O812", "O813")
    vacuum_icd9: tuple = ("727",)
    vacuum_icd10: tuple = ("O814",)
    breech_icd9: tuple = ("725",)
    breech_icd10: tuple = ("O830", "O831")
    # ทารก
    stillbirth_icd10: tuple = ("P95", "Z371", "Z373", "Z374", "Z376")
    dead_dchstts: tuple = ("08", "09")
    stillbirth_dchstts: tuple = ("08",)          # master dchstts: 08 = Dead Still Birth
    bba_types: tuple = ("3",)
    apgar1_max: int = 7
    asphyxia_apgar5: int = 7
    asphyxia_icd10: tuple = ("P21",)
    lbw_grams: int = 2500
    # Dx ภาวะแทรกซ้อน
    dx_pph: tuple = ("O72",)
    dx_preterm: tuple = ("O60",)
    dx_htn: tuple = ("O13", "O14", "O15", "O16")
    dx_prolonged: tuple = ("O63",)
    dx_fetal_distress: tuple = ("O68",)
    dx_prom: tuple = ("O42",)
    # lab ตอนคลอด: syphilis/hiv/hbv = labour_lab.lab_id ใน ipt_labour_lab · amph = lab_items_code ใน lab_order (ดู docs/schema-notes.md)
    syphilis_labs: tuple = ("1",)   # labour_lab.lab_id: 1 = VDRL
    hiv_labs: tuple = ("2",)        # 2 = Anti HIV
    hbv_labs: tuple = ("3",)        # 3 = HBsAg
    # lab_items_code ของ VDRL/TPHA · Anti-HIV · HBsAg ใน lab_order (ว่าง = เลือกจากชื่อรายการ แบบ ANC dashboard)
    syphilis_items: tuple = ()
    hiv_items: tuple = ()
    hbv_items: tuple = ()
    # ข้อของแบบคัดกรองครรภ์เสี่ยง (person_anc_classifying_item) "ติดยาเสพติด ติดสุรา"
    substance_items: tuple = ("17",)
    # หน้าต่างเวลาจับผล lab/แบบคัดกรองตลอดการตั้งครรภ์: กี่วันก่อนวันคลอด · กี่วันหลังวันคลอด
    lab_window_before: int = 300
    lab_window_after: int = 7
    amph_labs: tuple = ("139", "590", "2104", "1992")   # lab_items: Methamphetamine / Confirm / ฟรี / Urine Amphetamine
    # หลักฐานว่าเป็น "การคลอด" (ICD-10 3 ตัวแรก) — แถวใน ipt_pregnancy ที่ไม่มีทารกและไม่มี Dx เหล่านี้ไม่นับเป็นการคลอด
    delivery_icd10: tuple = ("O80", "O81", "O82", "O83", "O84", "Z37")


def load_config(env=os.environ):
    d = Config()
    g = env.get
    return Config(
        normal_icd=_dx(g("LR_NORMAL_ICD")) or d.normal_icd,
        cs_icd9=_dx(g("LR_CS_ICD9")) or d.cs_icd9,
        forceps_icd9=_dx(g("LR_FORCEPS_ICD9")) or d.forceps_icd9,
        forceps_icd10=_dx(g("LR_FORCEPS_ICD10")) or d.forceps_icd10,
        vacuum_icd9=_dx(g("LR_VACUUM_ICD9")) or d.vacuum_icd9,
        vacuum_icd10=_dx(g("LR_VACUUM_ICD10")) or d.vacuum_icd10,
        breech_icd9=_dx(g("LR_BREECH_ICD9")) or d.breech_icd9,
        breech_icd10=_dx(g("LR_BREECH_ICD10")) or d.breech_icd10,
        stillbirth_icd10=_dx(g("LR_STILLBIRTH_ICD10")) or d.stillbirth_icd10,
        dead_dchstts=_list(g("LR_DEAD_DCHSTTS")) or d.dead_dchstts,
        stillbirth_dchstts=_list(g("LR_STILLBIRTH_DCHSTTS")) or d.stillbirth_dchstts,
        bba_types=_list(g("LR_BBA_TYPES")) or d.bba_types,
        apgar1_max=int(_num(g("LR_APGAR1_MAX"), d.apgar1_max)),
        asphyxia_apgar5=int(_num(g("LR_ASPHYXIA_APGAR5"), d.asphyxia_apgar5)),
        asphyxia_icd10=_dx(g("LR_ASPHYXIA_ICD10")) or d.asphyxia_icd10,
        lbw_grams=int(_num(g("LR_LBW_GRAMS"), d.lbw_grams)),
        dx_pph=_dx(g("LR_DX_PPH")) or d.dx_pph,
        dx_preterm=_dx(g("LR_DX_PRETERM")) or d.dx_preterm,
        dx_htn=_dx(g("LR_DX_HTN")) or d.dx_htn,
        dx_prolonged=_dx(g("LR_DX_PROLONGED")) or d.dx_prolonged,
        dx_fetal_distress=_dx(g("LR_DX_FETAL_DISTRESS")) or d.dx_fetal_distress,
        dx_prom=_dx(g("LR_DX_PROM")) or d.dx_prom,
        syphilis_labs=_list(g("LR_LAB_SYPHILIS")) or d.syphilis_labs,
        hiv_labs=_list(g("LR_LAB_HIV")) or d.hiv_labs,
        hbv_labs=_list(g("LR_LAB_HBV")) or d.hbv_labs,
        amph_labs=_list(g("LR_LAB_AMPH")) or d.amph_labs,
        syphilis_items=_list(g("LR_LAB_SYPHILIS_ITEMS")) or d.syphilis_items,
        hiv_items=_list(g("LR_LAB_HIV_ITEMS")) or d.hiv_items,
        hbv_items=_list(g("LR_LAB_HBV_ITEMS")) or d.hbv_items,
        substance_items=_list(g("LR_SUBSTANCE_FORM_ITEMS")) or d.substance_items,
        lab_window_before=int(_num(g("LR_LAB_WINDOW_BEFORE"), d.lab_window_before)),
        lab_window_after=int(_num(g("LR_LAB_WINDOW_AFTER"), d.lab_window_after)),
        delivery_icd10=_dx(g("LR_DELIVERY_ICD10")) or d.delivery_icd10,
    )


# ---------------------------------------------------------------- ปีงบประมาณ (พ.ศ.)

def fy_range(fy_be):
    """ปีงบ พ.ศ. → (1 ต.ค. ปีก่อนหน้า, 30 ก.ย.) เป็น ค.ศ. · ปีงบ 2570 = 2026-10-01 ถึง 2027-09-30"""
    ce = fy_be - 543
    return date(ce - 1, 10, 1), date(ce, 9, 30)


def fy_of(d):
    """วันที่ → ปีงบประมาณ พ.ศ."""
    return d.year + 543 + (1 if d.month >= 10 else 0)


def fy_options(today=None, n=6):
    """ปีงบล่าสุดก่อน (ใหม่→เก่า) n ปี"""
    cur = fy_of(today or date.today())
    return [cur - i for i in range(n)]
