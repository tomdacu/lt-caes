from caes.config import PlantMode
from caes.nomenclature import (
    LTHP_LABEL,
    LTA_LABEL,
    plant_concept_label,
    plant_mode_label,
)


def test_mode_label_keeps_machine_value_separate_from_user_text():
    assert plant_mode_label(PlantMode.DIABATIC) == "AD-CAES (ambient diabatic)"
    assert plant_mode_label(PlantMode.ADIABATIC).startswith("LTA/LTHP-CAES")


def test_adiabatic_mode_is_named_lta_or_lthp_by_heat_offtake():
    assert plant_concept_label("adiabatic") == LTA_LABEL
    assert plant_concept_label("adiabatic", exports_heat=True) == LTHP_LABEL


def test_diabatic_concept_does_not_change_with_heat_flag():
    assert plant_concept_label("diabatic", exports_heat=True) == "AD-CAES (ambient diabatic)"
