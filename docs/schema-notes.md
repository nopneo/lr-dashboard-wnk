# บันทึกโครงสร้างฐาน HOSxP ที่ LR dashboard ใช้ (นับ/คอลัมน์เท่านั้น — ไม่มีข้อมูลรายคน)

ตรวจเมื่อ 2026-11-12 ผ่าน `hosdb` แบบอ่านอย่างเดียว

| ตาราง | ใช้ทำอะไร | คอลัมน์ที่ใช้ |
|---|---|---|
| `ipt_pregnancy` | แม่ 1 แถว = 1 AN | `an`, `labor_date`, `twin_child_count`, `abort` (NULL ทั้งตาราง), `pregnancy_abort_type_id`, `deliver_type` |
| `ipt_labour` | ผูก `an` กับ `ipt_labour_id` | `ipt_labour_id`, `an` |
| `ipt_labour_infant` | ทารก | `ipt_labour_id`, `birth_date`, `birth_weight`, `apgar_score_min1/5`, `infant_dchstts`, `infant_delivery_type_id` (BBA = '3'), `labor_ba_id`, `infant_icd10`, `infant_an` |
| `ipt_newborn` | สถานะทารกที่มี AN | `an` (= `infant_an`), `dead` |
| `ipt` | วันจำหน่าย | `an`, `dchdate` |
| `iptdiag` / `iptoprt` | Dx / หัตถการ | `an`, `icd10` / `icd9` |
| `ipt_labour_lab` | ผลแล็บตอนคลอด | `ipt_labour_id`, `lab_id`, `lab_value` (text อิสระ) |
| `labour_lab` | master แล็บ | `lab_id` 1 = VDRL, 2 = Anti HIV, 3 = HBsAg · `lab_name` |
| `referout` | ส่งต่อ | `refer_date`, `pdx`, `vn` (ผูกกับ AN หรือไม่ — ยังไม่ยืนยัน) |

## ผลตรวจกับฐานจริง (ปีงบ 2565–2569)

- แถวใน `ipt_pregnancy` = 102/86/95/72/78 · แม่ที่มีทารกใน `ipt_labour_infant` = 92/85/92/72/78 · `abort` เป็น NULL ทั้งหมด
  → "จำนวนคลอด" ต้องกรองแถวที่ไม่ใช่การคลอด (แท้ง/ไม่คลอด) ด้วยวิธีอื่น (Task 6)
- `infant_delivery_type_id`: '1' ×407, '3' ×8, '2' ×1, ว่าง ×4 → '3' (BBA ตาม ANC) พบ 8 ราย ใน 5 ปี
- `infant_dchstts`: '05' ×414, '04' ×5, '03' ×1 · ไม่มี '08'/'09' และ `ipt_newborn.dead='Y'` = 0 ราย
- ผล `ipt_labour_lab.lab_value` พิมพ์มือ: `NR`, `neg`, `Neg`, `Negative`, `-ve`, `Non reactive` และมีตัวอักษรขยะนำหน้า `NR` บางราย
  → `classify_result` ต้องทนต่อรูปแบบเหล่านี้ (Task 3)
- `referout.pdx` ขึ้นต้น O = 59–84 ราย/ปี — มากกว่าจำนวนคลอดจึงรวมการส่งต่อ ANC/OPD ด้วย (Task 6 ต้องจำกัดเฉพาะส่งต่อจาก LR)
- Amphetamine: ไม่มีใน `ipt_labour_lab` → ต้องหาจาก `lab_order` (Task 6) จนกว่าจะพบ แสดง "ไม่มีข้อมูล"
