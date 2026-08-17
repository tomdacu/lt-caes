"""The GUI solver must remain serializable across a spawned worker process."""

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

from caes.config import PlantConfig, PlantMode
from caes.gui import _solve_config
from caes.gui import CAESGUI


def test_gui_solver_runs_in_an_independent_spawned_process():
    config = PlantConfig(mode=PlantMode.DIABATIC, compressor_stages=1, expander_stages=1)
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as executor:
        result = executor.submit(_solve_config, config).result(timeout=30)

    assert result.mode == PlantMode.DIABATIC.value
    assert result.round_trip_efficiency >= 0.0
    assert any(
        process.kind == "throttling"
        for process in result.discharging.processes
    )


class _Value:
    """Minimal Tk variable stand-in for testing the parser without a display."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_gui_parser_keeps_coolant_cascade_groups_integer():
    """The GUI's displayed numeric text must preserve count-valued fields."""
    config = PlantConfig()
    gui = CAESGUI.__new__(CAESGUI)
    gui._variables = {
        name: _Value(value)
        for name, value in config.to_dict().items()
    }

    parsed = gui._parse_values()

    assert parsed.coolant_cascade_groups == 1
    assert isinstance(parsed.coolant_cascade_groups, int)
