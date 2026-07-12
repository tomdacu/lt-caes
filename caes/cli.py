"""Command-line interface for normalized CAES analysis."""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .config import PlantConfig, PlantMode
from .logic import FIELD_RULES, active_fields
from .plant import CAESPlant
from .reporting import save_thermodynamic_plots, summary


def config_from_json(path: Path) -> PlantConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(PlantConfig)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
    return PlantConfig(**data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run normalized CAES efficiency and exergy analysis.")
    parser.add_argument("--config", type=Path, help="JSON configuration file")
    parser.add_argument("--mode", choices=[mode.value for mode in PlantMode], help="override plant mode")
    parser.add_argument("--plot", type=Path, help="write combined T-s, T-h, and p-h traces to PNG")
    parser.add_argument("--write-default-config", type=Path, metavar="PATH", help="write default JSON and exit")
    parser.add_argument("--explain-config", action="store_true", help="show active and dormant fields")
    args = parser.parse_args(argv)

    if args.write_default_config:
        args.write_default_config.write_text(json.dumps(PlantConfig().to_dict(), indent=2) + "\n", encoding="utf-8")
        return 0

    config = config_from_json(args.config) if args.config else PlantConfig()
    if args.mode:
        data = config.to_dict()
        data["mode"] = args.mode
        config = PlantConfig(**data)
    if args.explain_config:
        active = active_fields(config)
        for name, rule in FIELD_RULES.items():
            print(f"{'ACTIVE ' if name in active else 'dormant'}  {name}: {rule.help or rule.label}")
        print()
    result = CAESPlant(config).run()
    print(summary(result))
    if args.plot:
        print(f"Saved plot: {save_thermodynamic_plots(result, args.plot)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
