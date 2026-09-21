"""The GUI solver must remain serializable across a spawned worker process."""

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

from caes.config import PlantConfig
from caes.gui import _solve_config
from caes.gui import CAESGUI


def test_gui_solver_runs_in_an_independent_spawned_process():
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as executor:
        result = executor.submit(_solve_config, PlantConfig()).result(timeout=180)

    assert result.thermal_store is not None
    assert result.heat_offtake is not None, "the default point is LTAHP"
    assert result.round_trip_efficiency > 0.0
    # No isenthalpic pressure loss anywhere on the way to the turbines: every
    # joule of reheat is paid for with stored compression heat, not thrown away
    # in a valve.
    assert all(
        process.kind != "throttling"
        for process in result.discharging.processes
    )


class _Value:
    """Minimal Tk variable stand-in for testing the parser without a display."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_gui_parser_keeps_stage_counts_integer():
    """The GUI's displayed numeric text must preserve count-valued fields."""
    config = PlantConfig()
    gui = CAESGUI.__new__(CAESGUI)
    gui._variables = {
        name: _Value(value)
        for name, value in config.to_dict().items()
    }

    parsed = gui._parse_values()

    assert parsed.compressor_stages == config.compressor_stages
    assert isinstance(parsed.compressor_stages, int)
