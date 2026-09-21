from caes import HeatOfftake
from caes.nomenclature import (
    HEAT_OFFTAKE_LABELS,
    LTAHP_LABEL,
    LTA_LABEL,
    plant_concept_label,
)


def test_the_heat_user_flag_names_the_concept():
    """One plant, two products: the off-take flag is the only thing that changes
    the name a reader sees, because it is the only thing that changes the plant."""
    assert plant_concept_label(exports_heat=False) == LTA_LABEL
    assert plant_concept_label(exports_heat=True) == LTAHP_LABEL
    assert HEAT_OFFTAKE_LABELS[HeatOfftake.NONE].endswith(LTA_LABEL)
    assert HEAT_OFFTAKE_LABELS[HeatOfftake.HEAT_USER].endswith(LTAHP_LABEL)


def test_every_label_keeps_the_low_temperature_adiabatic_stem():
    """LTA and LTAHP differ by what the stored heat does, never by how it is
    stored, so no label may drop the stem that says what the family is."""
    labels = (LTA_LABEL, LTAHP_LABEL, *HEAT_OFFTAKE_LABELS.values())
    for label in labels:
        assert "low-temperature adiabatic" in label
