from datetime import date

import config
from config import fy_of, fy_options, fy_range, load_config


def test_fy_range_2570():
    assert fy_range(2570) == (date(2026, 10, 1), date(2027, 9, 30))


def test_fy_range_2565():
    assert fy_range(2565) == (date(2021, 10, 1), date(2022, 9, 30))


def test_fy_of_boundary():
    assert fy_of(date(2026, 9, 30)) == 2569
    assert fy_of(date(2026, 10, 1)) == 2570


def test_fy_options_newest_first():
    opts = fy_options(date(2026, 11, 12))
    assert opts[0] == 2570 and opts[1] == 2569 and len(opts) == 6


def test_defaults():
    c = load_config({})
    assert c.normal_icd == ("O80",)
    assert c.bba_types == ("3",)
    assert c.dead_dchstts == ("08", "09")
    assert c.apgar1_max == 7
    assert c.lbw_grams == 2500


def test_env_list_trim_and_upper():
    assert load_config({"LR_NORMAL_ICD": "o80, O81"}).normal_icd == ("O80", "O81")


def test_env_dx_strips_dot():
    assert load_config({"LR_STILLBIRTH_ICD10": "z37.1"}).stillbirth_icd10 == ("Z371",)


def test_env_number():
    assert load_config({"LR_APGAR1_MAX": "6"}).apgar1_max == 6


def test_config_is_frozen():
    import dataclasses
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        load_config({}).apgar1_max = 1


def test_lab_defaults_match_labour_lab_master():
    # labour_lab ของ รพ.วังน้ำเขียว: 1 = VDRL, 2 = Anti HIV, 3 = HBsAg (docs/schema-notes.md)
    c = load_config({})
    assert (c.syphilis_labs, c.hiv_labs, c.hbv_labs) == (("1",), ("2",), ("3",))
