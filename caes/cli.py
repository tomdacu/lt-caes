"""Command-line interface for normalized CAES analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import PlantConfig, load_config, save_config
from .logic import FIELD_RULES, active_fields
from .plant import CAESPlant
from .reporting import save_sankey_plots, save_thermodynamic_plots, summary
from .thermodynamics import PropertyAPI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run normalized CAES efficiency and exergy analysis.")
    parser.add_argument("--config", type=Path, help="JSON configuration file")
    parser.add_argument(
        "--property-api",
        choices=[api.value for api in PropertyAPI],
        default=PropertyAPI.ABSTRACT_STATE.value,
        help="CoolProp front end for diagnostic A/B tests (default: abstract_state)",
    )
    parser.add_argument("--plot", type=Path, help="write combined T-s, h-s, and p-h traces to PNG")
    parser.add_argument("--sankey", type=Path, help="write the energy Sankey and exergy Grassmann diagrams to PNG")
    parser.add_argument("--pid", type=Path, help="write the P&ID schematic for this configuration to PNG")
    parser.add_argument("--write-default-config", type=Path, metavar="PATH", help="write default JSON and exit")
    parser.add_argument("--explain-config", action="store_true", help="show active and dormant fields")
    args = parser.parse_args(argv)

    if args.write_default_config:
        save_config(PlantConfig(), args.write_default_config)
        return 0

    config = load_config(args.config) if args.config else PlantConfig()
    if args.explain_config:
        active = active_fields(config)
        for name, rule in FIELD_RULES.items():
            print(f"{'ACTIVE ' if name in active else 'dormant'}  {name}: {rule.help or rule.label}")
        print()
    result = CAESPlant(config, property_api=args.property_api).run()
    print(summary(result))
    if args.plot:
        print(f"Saved plot: {save_thermodynamic_plots(result, args.plot)}")
    if args.sankey:
        print(f"Saved Sankeys: {save_sankey_plots(result, args.sankey)}")
    if args.pid:
        from .pid import save as save_pid

        print(f"Saved P&ID: {save_pid(config, result, args.pid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
