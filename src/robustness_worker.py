from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .hardening import normalization_sensitivity, temporal_sensitivity


def main() -> None:
    parser = argparse.ArgumentParser(description='Isolated robustness worker for V2.')
    parser.add_argument('--kind', choices=['temporal', 'normalization'], required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    data_dir = root / 'data'
    registry_dir = root / 'registry'
    output_dir = root / 'outputs'
    config = json.loads((root / 'config' / 'config.json').read_text(encoding='utf-8'))

    normalized = pd.read_csv(data_dir / 'normalized_observations.csv')
    transformed = pd.read_csv(data_dir / 'transformed_observations.csv')
    registry = pd.read_csv(registry_dir / 'indicator_registry_final.csv')
    baseline = pd.read_csv(output_dir / 'provincial_composite_index.csv')

    if args.kind == 'temporal':
        result = temporal_sensitivity(normalized, registry, config, baseline)
        result.to_csv(output_dir / 'temporal_sensitivity_final.csv', index=False, encoding='utf-8-sig')
        result.to_csv(output_dir / 'temporal_sensitivity.csv', index=False, encoding='utf-8-sig')
        result.to_csv(output_dir / 'temporal_method_comparison.csv', index=False, encoding='utf-8-sig')
    else:
        result = normalization_sensitivity(transformed, registry, config, baseline)
        result.to_csv(output_dir / 'normalization_sensitivity_final.csv', index=False, encoding='utf-8-sig')
        result.to_csv(output_dir / 'normalization_sensitivity.csv', index=False, encoding='utf-8-sig')
        result.to_csv(output_dir / 'normalization_comparison.csv', index=False, encoding='utf-8-sig')

    print(f'{args.kind} robustness worker complete: {len(result)} rows', flush=True)


if __name__ == '__main__':
    main()
