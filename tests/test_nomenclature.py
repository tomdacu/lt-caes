from caes.config import PlantMode
from caes.nomenclature import (
    LTAHP_LABEL,
    LTA_LABEL,
    plant_concept_label,
    plant_mode_label,
)


def test_concept_labels_separate_machine_values_from_user_text():
    """The machine value is stable; the label is the only thing users read."""
    assert plant_mode_label(PlantMode.DIABATIC) == "AD-CAES (ambient diabatic)"
    assert plant_mode_label(PlantMode.ADIABATIC).startswith("LTA/LTAHP-CAES")

    # The heat flag, not the mode value, is what names the concept.
    assert plant_concept_label("adiabatic") == LTA_LABEL
    assert plant_concept_label("adiabatic", exports_heat=True) == LTAHP_LABEL
    assert (
        plant_concept_label("diabatic", exports_heat=True)
        == plant_mode_label(PlantMode.DIABATIC)
    )
