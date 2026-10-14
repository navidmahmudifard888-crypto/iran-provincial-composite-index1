from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.hardening import infer_unit
from src.index_engine import normalize_province, temporal_weight


class V2IntegrityTests(unittest.TestCase):
    def test_province_normalization(self) -> None:
        self.assertEqual(normalize_province("چهار محال و بختیاری"), "چهارمحال و بختیاری")
        self.assertEqual(normalize_province("مركزی"), "مرکزی")

    def test_recency_weight_is_monotonic(self) -> None:
        settings = {
            "method": "linear", "linear_floor": 0.25, "linear_decay_per_year": 0.12,
            "exponential_lambda": 0.25, "step_weights": {"0": 1, "999": 0.45},
        }
        self.assertGreater(temporal_weight(0, settings), temporal_weight(3, settings))
        self.assertGreaterEqual(temporal_weight(30, settings), 0.25)

    def test_unit_inference_handles_inflation_ratio_and_percent(self) -> None:
        self.assertEqual(infer_unit("تورم"), "percent")
        self.assertEqual(infer_unit("نسبت طلاق به ازدواج"), "ratio")
        self.assertEqual(infer_unit("سهم شاغلان کل"), "percent")
        self.assertEqual(infer_unit("پزشک عمومی"), "count")

    def test_pipeline_outputs_are_keyed_by_province(self) -> None:
        p = ROOT / "outputs" / "provincial_composite_index.csv"
        df = pd.read_csv(p)
        self.assertEqual(df["province"].nunique(), 31)
        self.assertEqual(len(df), 31)
        self.assertFalse(df["overall_score"].isna().any())
        self.assertEqual(df["rank"].nunique(), 31)

    def test_weight_sum_and_reference_year(self) -> None:
        config = json.loads((ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["reference_year"], 1403)
        weights = pd.read_csv(ROOT / "registry" / "effective_weights.csv")
        self.assertAlmostEqual(weights["effective_final_weight"].sum(), 1.0, places=10)

    def test_external_convergent_criterion_matches_29_provinces(self) -> None:
        df = pd.read_csv(ROOT / "outputs" / "external_validation_final.csv")
        self.assertEqual(int(df.loc[0, "n_matched"]), 29)
        self.assertEqual(df.loc[0, "status"], "external_convergent_association")


if __name__ == "__main__":
    unittest.main()
