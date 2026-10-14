# Data Dictionary

This dictionary is generated from the final V2.1 repository files. Column names below are the actual names in the CSVs.

## Final provincial composite index

| Column | Type |
|---|---|
| `province` | `object` |
| `indicator_count_used` | `int64` |
| `temporal_quality` | `float64` |
| `latest_observation_year` | `float64` |
| `missing_ratio` | `float64` |
| `imputed_ratio` | `float64` |
| `source_quality_status` | `object` |
| `data_quality_score` | `float64` |
| `data_quality_score_scope` | `object` |
| `uncertainty_level` | `object` |
| `overall_confidence` | `object` |
| `overall_score` | `float64` |
| `rank` | `float64` |

## Category scores

| Column | Type |
|---|---|
| `province` | `object` |
| `category` | `object` |
| `weighted_sum` | `float64` |
| `weight_sum` | `float64` |
| `subindicator_count` | `int64` |
| `category_score` | `float64` |
| `category_weight` | `float64` |

## Series scores

| Column | Type |
|---|---|
| `province` | `object` |
| `series_id` | `object` |
| `series_score` | `float64` |
| `observation_count` | `int64` |
| `first_observation_year` | `float64` |
| `last_observation_year` | `float64` |
| `recency_weight_sum` | `float64` |
| `temporal_quality` | `float64` |
| `reference_year` | `int64` |
| `temporal_method` | `object` |

## Subindicator scores

| Column | Type |
|---|---|
| `province` | `object` |
| `category` | `object` |
| `subindicator` | `object` |
| `weighted_sum` | `float64` |
| `weight_sum` | `float64` |
| `series_count` | `int64` |
| `subindicator_score` | `float64` |
| `subindicator_weight` | `float64` |
| `weighted_subindicator_contribution` | `float64` |

## Province score decomposition

| Column | Type |
|---|---|
| `level` | `object` |
| `province` | `object` |
| `category` | `object` |
| `subindicator` | `float64` |
| `series_id` | `float64` |
| `score` | `float64` |
| `weight` | `float64` |
| `weighted_contribution` | `float64` |

## Indicator registry

| Column | Type |
|---|---|
| `series_id` | `object` |
| `indicator` | `object` |
| `dataset_name` | `object` |
| `category` | `object` |
| `series_text` | `object` |
| `observation_year_min` | `float64` |
| `observation_year_max` | `float64` |
| `raw_observation_count` | `int64` |
| `distinct_observation_years` | `float64` |
| `provincial_coverage` | `int64` |
| `observed_province_years` | `int64` |
| `expected_province_years` | `int64` |
| `duplicate_key_rows` | `int64` |
| `conflicting_province_year_keys` | `int64` |
| `missing_observations` | `int64` |
| `missing_ratio` | `float64` |
| `unit_type` | `object` |
| `direction` | `object` |
| `transform` | `object` |
| `subindicator` | `object` |
| `reference_year` | `int64` |
| `reference_period` | `object` |
| `temporal_gap` | `float64` |
| `temporal_quality` | `float64` |
| `imputed_ratio` | `float64` |
| `source_file` | `object` |
| `source` | `object` |
| `source_url` | `float64` |
| `source_quality` | `object` |
| `provenance_status` | `object` |
| `conceptual_status` | `object` |
| `inclusion_status` | `object` |
| `exclusion_reason` | `object` |
| `category_weight` | `float64` |
| `subindicator_weight` | `float64` |
| `series_weight` | `float64` |
| `effective_final_weight` | `float64` |
| `provenance_source_organization` | `object` |
| `provenance_evidence_url` | `object` |
| `provenance_evidence_type` | `object` |
| `provenance_evidence_note` | `object` |
| `review_status` | `object` |
| `review_notes` | `object` |

## Transformed observations

| Column | Type |
|---|---|
| `Indicator` | `object` |
| `Province` | `object` |
| `Year` | `int64` |
| `dataset_name` | `object` |
| `Category` | `object` |
| `Value` | `int64` |
| `province` | `object` |
| `year_num` | `float64` |
| `value_num` | `float64` |
| `series_id` | `object` |
| `series_text` | `object` |
| `geo_level` | `object` |
| `raw_row_id` | `int64` |
| `exact_duplicate_flag` | `bool` |
| `conflicting_key_flag` | `bool` |
| `inclusion_status` | `object` |
| `direction` | `object` |
| `transform` | `object` |
| `category` | `object` |
| `subindicator` | `object` |
| `value_transformed` | `float64` |
| `transform_applied` | `object` |
| `denominator_year` | `float64` |
| `denominator_gap` | `float64` |
| `denominator_type` | `object` |
| `denominator_series_id` | `object` |
| `population` | `float64` |
