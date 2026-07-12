"""Command-line entry point for a reproducible CAES simulation."""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .config import PlantConfig, PlantMode
from .plant import CAESPlant
from .reporting import save_temperature_entropy_plot, summary


def _config_from_json(path: Path) -> PlantConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(PlantConfig)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
    if "mode" in data:
        data["mode"] = PlantMode(data["mode"])
    return PlantConfig(**data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a physically bounded CAES batch simulation.")
    parser.add_argument("--config", type=Path, help="JSON configuration file")
    parser.add_argument("--mode", choices=[mode.value for mode in PlantMode], help="override the configured plant mode")
    parser.add_argument("--plot", type=Path, help="write a T-s trace PNG")
    parser.add_argument("--write-default-config", type=Path, metavar="PATH", help="write a documented default JSON config and exit")
    args = parser.parse_args(argv)

    if args.write_default_config:
        args.write_default_config.write_text(json.dumps(PlantConfig().to_dict(), indent=2) + "\n", encoding="utf-8")
        return 0

    config = _config_from_json(args.config) if args.config else PlantConfig()
    if args.mode:
        data = config.to_dict()
        data["mode"] = PlantMode(args.mode)
        config = PlantConfig(**data)
    result = CAESPlant(config).run()
    print(summary(result))
    if args.plot:
        print(f"Saved plot: {save_temperature_entropy_plot(result, args.plot)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
