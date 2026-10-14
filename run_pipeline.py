from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.hardening import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the auditable V2 provincial composite-index pipeline."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config" / "config.json",
        help="Path to the JSON configuration file.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional override for the raw input workbook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "outputs",
        help="Directory for generated V2 outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.input is None:
        input_path = (config_path.parent / config["input_path"]).resolve()
    else:
        input_path = args.input.resolve()
    run_pipeline(input_path=input_path, output_dir=args.output.resolve(), config=config)


if __name__ == "__main__":
    main()
