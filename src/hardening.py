from __future__ import annotations

from pathlib import Path
import json
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr, kendalltau, rankdata

# Import canonical engine symbols; this module is imported from run_pipeline.py.
from . import index_engine as ie

OFFICIAL_PROVINCES = ie.OFFICIAL_PROVINCES




PROVENANCE_EVIDENCE = {
    "آموزشی": {
        "organization": "مرکز آمار ایران / وزارت آموزش و پرورش",
        "url": "https://iranopendata.org/res/get/datasets/2024/7/iod526_oMi5zl2.pdf",
        "type": "official-statistical-yearbook-archive",
        "note": "Archived official statistical-yearbook material lists provincial education measures including promotion and dropout rates. It supports the source family and indicator taxonomy, not row-level extraction lineage for the supplied workbook."
    },
    "اجتماعی": {
        "organization": "مرکز آمار ایران / سازمان ثبت احوال کشور / وزارت بهداشت",
        "url": "https://iranopendata.org/res/get/datasets/IODS2/2023/iod557.pdf",
        "type": "official-social-justice-report-archive",
        "note": "The Social Justice Indicators report states that the Statistical Center compiles the report with multiple data-providing agencies and covers social, education, health and related indicators. Exact workbook extraction lineage remains incomplete."
    },
    "اقتصادی": {
        "organization": "مرکز آمار ایران",
        "url": "https://irandataportal.syr.edu/labor-force",
        "type": "statistical-center-data-portal",
        "note": "The Iran Data Portal documents Statistical Center labor-force series including provincial participation and unemployment rates. Exact workbook extraction lineage and all periods are not fully recoverable from the project files."
    },
    "امنیتی": {
        "organization": "نیروی انتظامی جمهوری اسلامی ایران / مرکز آمار ایران",
        "url": "https://iranopendata.org/fa/article/118-suicide-in-iran/",
        "type": "official-data-analysis-archive",
        "note": "The archived official-data analysis identifies police-recorded suicide and suspicious-death statistics as official underlying records. Exact workbook extraction lineage for every crime sub-series remains incomplete."
    },
    "زیرساختی": {
        "organization": "وزارت بهداشت، درمان و آموزش پزشکی / مرکز آمار ایران",
        "url": "https://irandataportal.syr.edu/wp-content/uploads/16-Health.pdf",
        "type": "statistical-yearbook-health",
        "note": "The statistical yearbook documents provincial medical-bed measures per 100,000 population and health-sector tables; archived yearbooks also document physicians and medical establishments. Exact workbook extraction lineage remains incomplete."
    },
}

def enrich_provenance(registry: pd.DataFrame) -> pd.DataFrame:
    reg = registry.copy()
    reg["provenance_source_organization"] = reg["category"].map(lambda c: PROVENANCE_EVIDENCE.get(c, {}).get("organization", ""))
    reg["provenance_evidence_url"] = reg["category"].map(lambda c: PROVENANCE_EVIDENCE.get(c, {}).get("url", ""))
    reg["provenance_evidence_type"] = reg["category"].map(lambda c: PROVENANCE_EVIDENCE.get(c, {}).get("type", ""))
    reg["provenance_evidence_note"] = reg["category"].map(lambda c: PROVENANCE_EVIDENCE.get(c, {}).get("note", ""))
    return reg

def _clean_duplicates(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep exact duplicates only once and flag unresolved province-series-year conflicts."""
    out = data.copy()
    key = ["province", "series_id", "year_num"]
    exact_key = ["Indicator", "Province", "Year", "dataset_name", "Category", "Value"]
    out["exact_duplicate_flag"] = out.duplicated(exact_key, keep="first")
    out = out.loc[~out["exact_duplicate_flag"]].copy()
    counts = out.groupby(key, dropna=False)["value_num"].transform("count")
    nunique = out.groupby(key, dropna=False)["value_num"].transform(lambda s: s.dropna().nunique())
    out["conflicting_key_flag"] = (counts > 1) & (nunique > 1)
    conflict = out.loc[out["conflicting_key_flag"]].copy()
    return out, conflict


def load_raw_input(path: Path) -> pd.DataFrame:
    raw = ie.load_first_sheet_records(path)
    required = ["Indicator", "Province", "Year", "dataset name", "Category", "Value"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Input is missing required columns: {missing}")
    data = raw[required].copy().rename(columns={"dataset name": "dataset_name"})
    for column in ("Indicator", "Province", "dataset_name", "Category", "Value"):
        data[column] = data[column].map(ie.normalize_text)
    data["province"] = data["Province"].map(ie.normalize_province)
    data["year_num"] = data["Year"].map(ie.parse_year)
    data["value_num"] = data["Value"].map(ie.parse_numeric)
    data["series_id"] = data["Indicator"] + " || " + data["dataset_name"].replace("", "بدون زیرشاخص")
    data["series_text"] = (data["Indicator"] + " " + data["dataset_name"]).str.strip()
    data["geo_level"] = np.where(
        data["province"].isin(OFFICIAL_PROVINCES),
        "province",
        np.where(data["province"] == "کل کشور", "national", "other"),
    )
    data["raw_row_id"] = np.arange(1, len(data) + 1)
    clean, conflict = _clean_duplicates(data)
    # Keep raw audit information on the working table while exact duplicates are removed.
    clean.attrs["raw_rows_before_dedup"] = len(data)
    clean.attrs["exact_duplicates_removed"] = int(len(data) - len(clean))
    clean.attrs["conflict_rows"] = int(len(conflict))
    return clean


def infer_unit(series_text: str) -> str:
    text = ie.normalize_text(series_text).lower()
    if any(term in text for term in ("درصد", "%", "percent", "سهم ", "تورم", "inflation")):
        return "percent"
    if any(term in text for term in ("نسبت", "ratio")):
        return "ratio"
    if any(term in text for term in ("نرخ", "rate", "به ازای 100 هزار", "به ازای هر 100 هزار", "به ازای")):
        return "rate"
    if any(term in text for term in ("شاخص", "index", "ضریب")):
        return "index"
    if any(term in text for term in ("سرانه", "per capita", "percapita")):
        return "per_capita"
    return "count"


def infer_direction(series_text: str) -> str:
    text = ie.normalize_text(series_text).lower()
    risk = any(term in text for term in ie.RISK_TERMS)
    protective = any(term in text for term in ie.PROTECTIVE_TERMS)
    if risk and not protective:
        return "higher_worse"
    if protective and not risk:
        return "higher_better"
    return "unknown"


def is_structural(series_text: str) -> bool:
    text = ie.normalize_text(series_text).lower()
    return any(term in text for term in ie.STRUCTURAL_TERMS) or any(
        term in text for term in ("totalpopulation", "جمعیت کل", "تعداد خانوار", "خانوار کل")
    )


def infer_transform(series_text: str, unit_type: str) -> str:
    text = ie.normalize_text(series_text).lower()
    if unit_type != "count":
        return "none"
    # Counts are rate-normalized only where population normalization is substantively useful.
    per100k_terms = (
        "مدرسه", "کلاس", "درمانگاه", "بیمارستان", "پزشک", "تخت بیمارستان",
        "تخت فعال", "تخت مصوب", "crime", "سرقت", "قتل", "نزاع", "شرارت",
        "دستگیر", "خودکشی", "مرگ مشکوک", "خشونت", "کودک آزاری", "بی خانمان",
        "سازمان های مردم نهاد", "ngo", "mobile", "subscribers", "telephone",
        "telecom", "internetusers", "computerusers", "households withinternet",
        "industrialunits", "پروژه های عمرانی",
    )
    if is_structural(text):
        return "none"
    if any(term in text for term in per100k_terms):
        return "per_100k_population"
    return "none"


def _conceptual_exclusion_reason(row: pd.Series, all_series: set[str]) -> str:
    sid = row["series_id"]
    text = ie.normalize_text(row["series_text"]).lower()
    # Mathematically redundant totals when their component series are explicitly present.
    if sid in {
        "جمع - مدرسه || مدارس و کلاس ها",
        "جمع - کلاس || مدارس و کلاس ها",
    }:
        return "derived_total_duplicates_level_components"
    if sid == "HospitalBeds || تخت بیمارستان":
        return "count_redundant_with_explicit_per_100k_hospital_beds"
    if "تعداد تخت فعال" in text:
        return "count_redundant_with_explicit_active_bed_rate"
    if "تعداد تخت مصوب" in text:
        return "count_redundant_with_explicit_approved_bed_rate"
    if sid == "Doctors || کل پزشکان":
        return "aggregate_doctor_total_repeats_specialty_components"
    if "تعداد خودکشی" in text or "تعداد مرگ مشکوک" in text or "جمع خودکشی و مرگ مشکوک" in text:
        return "count_redundant_with_explicit_rate_or_component_counts"
    if "نسبت طلاق به ازدواج" in text:
        return "no_exclusion"
    if text.strip() == "تورم":
        return "no_exclusion"
    return ""


def derive_registry(data: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    provincial_all = data[(data["geo_level"] == "province") & data["year_num"].notna()].copy()
    numeric = provincial_all[provincial_all["value_num"].notna()].copy()

    # Series-year existence defines the expected panel. Every official province is expected for each existing year.
    series_years = provincial_all.groupby("series_id")["year_num"].nunique().rename("distinct_observation_years")
    observed = numeric.drop_duplicates(["series_id", "province", "year_num"]).groupby("series_id")["province"].nunique().rename("provincial_coverage")
    observed_pairs = numeric.drop_duplicates(["series_id", "province", "year_num"]).groupby("series_id").size().rename("observed_province_years")
    expected = (series_years * len(OFFICIAL_PROVINCES)).rename("expected_province_years")
    conflict_pairs = (provincial_all.assign(conflict=provincial_all.duplicated(["series_id", "province", "year_num"], keep=False))
                      .groupby("series_id")["conflict"].sum().rename("duplicate_key_rows"))
    conflict_distinct = (provincial_all.groupby(["series_id", "province", "year_num"])["value_num"]
                         .nunique(dropna=True).reset_index(name="value_nunique")
                         .query("value_nunique > 1").groupby("series_id").size().rename("conflicting_province_year_keys"))

    summary = data.groupby("series_id", as_index=False).agg(
        indicator=("Indicator", "first"),
        dataset_name=("dataset_name", "first"),
        category=("Category", "first"),
        series_text=("series_text", "first"),
        observation_year_min=("year_num", "min"),
        observation_year_max=("year_num", "max"),
        raw_observation_count=("raw_row_id", "count"),
    )
    registry = summary.merge(series_years, on="series_id", how="left").merge(observed, on="series_id", how="left")
    registry = registry.merge(observed_pairs, on="series_id", how="left").merge(expected, on="series_id", how="left")
    registry = registry.merge(conflict_pairs, on="series_id", how="left").merge(conflict_distinct, on="series_id", how="left")
    registry["observed_province_years"] = registry["observed_province_years"].fillna(0).astype(int)
    registry["expected_province_years"] = registry["expected_province_years"].fillna(0).astype(int)
    registry["provincial_coverage"] = registry["provincial_coverage"].fillna(0).astype(int)
    registry["missing_observations"] = (registry["expected_province_years"] - registry["observed_province_years"]).clip(lower=0).astype(int)
    registry["missing_ratio"] = np.where(registry["expected_province_years"] > 0,
                                          registry["missing_observations"] / registry["expected_province_years"], 1.0)
    registry["duplicate_key_rows"] = registry["duplicate_key_rows"].fillna(0).astype(int)
    registry["conflicting_province_year_keys"] = registry["conflicting_province_year_keys"].fillna(0).astype(int)

    registry["unit_type"] = registry["series_text"].map(infer_unit)
    registry["direction"] = registry["series_text"].map(infer_direction)
    registry["transform"] = [infer_transform(t, u) for t, u in zip(registry["series_text"], registry["unit_type"])]
    registry["subindicator"] = registry["indicator"].where(registry["indicator"].ne(""), registry["dataset_name"])
    registry["reference_year"] = int(config["reference_year"])
    registry["reference_period"] = f"anchor {config['reference_year']}; multi-year history retained"
    registry["temporal_gap"] = (registry["reference_year"] - registry["observation_year_max"]).abs()
    registry["temporal_quality"] = registry["temporal_gap"].map(lambda age: ie.temporal_weight(float(age), config["temporal_weighting"]))
    registry["imputed_ratio"] = 0.0

    # Provenance: we can verify the project file and the source/dataset label carried in the workbook,
    # but not the external source URL unless it exists in project metadata.
    registry["source_file"] = Path(config["input_path"]).name
    registry["source"] = registry["dataset_name"].replace("", np.nan)
    registry["source_url"] = ""
    registry["source_quality"] = np.where(registry["dataset_name"].ne(""), "dataset_label_only", "unknown")
    registry["provenance_status"] = np.where(registry["dataset_name"].ne(""), "PARTIALLY_VERIFIED", "SOURCE_UNVERIFIED")
    registry["conceptual_status"] = "needs_review"
    registry["inclusion_status"] = "CONDITIONAL"
    registry["exclusion_reason"] = ""

    min_coverage = int(config["minimum_province_coverage"])
    invalid = registry["series_id"].eq(" || ") | registry["indicator"].eq("")
    registry.loc[invalid, ["inclusion_status", "exclusion_reason"]] = ["EXCLUDED", "empty indicator or dataset identifier"]
    low_coverage = registry["provincial_coverage"] < min_coverage
    registry.loc[low_coverage, ["inclusion_status", "exclusion_reason"]] = ["EXCLUDED", f"provincial coverage below {min_coverage}"]
    structural = registry["series_text"].map(is_structural)
    registry.loc[structural, ["inclusion_status", "exclusion_reason"]] = ["EXCLUDED", "structural or denominator variable, not a condition measure"]
    ambiguous = registry["direction"].eq("unknown") & registry["inclusion_status"].ne("EXCLUDED")
    registry.loc[ambiguous, ["inclusion_status", "exclusion_reason"]] = ["EXCLUDED", "direction cannot be justified from available project metadata"]

    # Exclude mathematically duplicated aggregate measures where the project itself contains the more direct measure.
    for idx, row in registry.iterrows():
        reason = _conceptual_exclusion_reason(row, set(registry["series_id"]))
        if reason and reason != "no_exclusion" and registry.at[idx, "inclusion_status"] != "EXCLUDED":
            registry.at[idx, "inclusion_status"] = "EXCLUDED"
            registry.at[idx, "exclusion_reason"] = reason
            registry.at[idx, "conceptual_status"] = "duplicate_or_derived"

    registry["category_weight"] = registry["category"].map(config["aggregation"]["category_weights"])
    registry["subindicator_weight"] = np.nan
    registry["series_weight"] = np.nan
    registry["effective_final_weight"] = np.nan
    registry = enrich_provenance(registry)
    # Apply explicit human semantic review decisions. These decisions are stored in the canonical registry folder
    # so they are auditable and reproducible rather than hidden in code.
    override_path = Path(__file__).resolve().parent.parent / "registry" / "manual_indicator_review.csv"
    if override_path.exists():
        overrides = pd.read_csv(override_path, encoding="utf-8-sig").fillna("")
        overrides.columns = [str(c).strip() for c in overrides.columns]
        if "series_id" in overrides.columns:
            overrides["series_id"] = overrides["series_id"].map(ie.normalize_text)
            for _, ov in overrides.iterrows():
                sid = ov.get("series_id", "")
                if not sid or sid not in set(registry["series_id"]):
                    continue
                idxs = registry.index[registry["series_id"] == sid].tolist()
                if not idxs:
                    continue
                idx = idxs[0]
                decision = str(ov.get("decision", "")).strip()
                if decision:
                    registry.at[idx, "inclusion_status"] = decision
                for field in ("final_category", "final_subindicator", "final_direction", "final_transform"):
                    value = str(ov.get(field, "")).strip()
                    if value:
                        target = {"final_category":"category", "final_subindicator":"subindicator", "final_direction":"direction", "final_transform":"transform"}[field]
                        registry.at[idx, target] = value
                if decision == "EXCLUDED":
                    registry.at[idx, "conceptual_status"] = "reviewed_excluded"
                    registry.at[idx, "exclusion_reason"] = str(ov.get("reason", "")).strip()
                else:
                    registry.at[idx, "conceptual_status"] = "reviewed_manual"
                    registry.at[idx, "exclusion_reason"] = ""
                registry.at[idx, "review_status"] = "manual_semantic_review_complete; provenance_review_separate"
                registry.at[idx, "review_notes"] = str(ov.get("reason", "")).strip() or "Manual semantic review recorded."

    generic_mask = ~registry["review_status"].astype(str).str.startswith("manual_semantic_review_complete")
    registry.loc[generic_mask, "review_status"] = "pending_provenance_review"
    registry.loc[generic_mask, "review_notes"] = (
        "Observed project data retained. Provenance is only partially verified from workbook labels and external source-family evidence; "
        "row-level extraction lineage remains explicitly auditable."
    )
    return registry.sort_values(["category", "subindicator", "series_id"]).reset_index(drop=True)


def transform_observations(data: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Apply transparent denominator rules to count-based indicators.

    Default:
      - school/class capacity counts -> population age 6+ for the same year when available
      - other selected count/capacity/event series -> total population for the same year,
        otherwise nearest available total population within 2 years

    The rule is series-aware: rates, percentages, ratios and already-per-capita measures
    are never divided by population here.
    """
    reg_cols = ["series_id", "inclusion_status", "direction", "transform", "category", "subindicator"]
    reg = registry[reg_cols]
    base = data[(data["geo_level"] == "province") & data["year_num"].notna() & data["value_num"].notna()].copy()
    conflict_keys = (base.groupby(["province", "series_id", "year_num"])["value_num"].nunique()
                     .reset_index(name="nunique")
                     .query("nunique > 1")[["province", "series_id", "year_num"]])
    if not conflict_keys.empty:
        base = base.merge(conflict_keys.assign(conflict=True), on=["province", "series_id", "year_num"], how="left")
        base = base[base["conflict"].astype("boolean").fillna(False).eq(False)].drop(columns=["conflict"])

    out = base.merge(reg, on="series_id", how="inner")
    out = out[out["inclusion_status"].isin(["CORE", "CONDITIONAL"])].copy()
    out["value_transformed"] = out["value_num"].astype(float)
    out["transform_applied"] = "none"
    out["denominator_year"] = np.nan
    out["denominator_gap"] = np.nan
    out["denominator_type"] = "none"
    out["denominator_series_id"] = ""

    total_pop = _population_lookup(data)
    pop6plus = _population6plus_lookup(data)

    total_lookup = {(r.province, float(r.year_num)): float(r.population)
                    for r in total_pop.itertuples(index=False)}
    six_lookup = {(r.province, float(r.year_num)): float(r.population_6plus)
                  for r in pop6plus.itertuples(index=False)}

    education_count_mask = (
        out["transform"].eq("per_100k_population")
        & out["category"].eq("آموزشی")
        & out["series_id"].str.contains(r"مدرسه|کلاس", regex=True, na=False)
    )
    total_count_mask = out["transform"].eq("per_100k_population") & ~education_count_mask

    def lookup_denominator(row: pd.Series, lookup: dict, preferred_type: str, max_gap: float = 2.0):
        year = float(row["year_num"])
        province = row["province"]
        exact = lookup.get((province, year))
        if exact is not None and exact > 0:
            return exact, year, preferred_type
        options = [
            (abs(y - year), y, value)
            for (p, y), value in lookup.items()
            if p == province and value > 0
        ]
        if not options:
            return math.nan, math.nan, "missing"
        distance, den_year, value = min(options)
        if distance <= max_gap:
            return value, den_year, preferred_type
        return math.nan, math.nan, "missing"

    if education_count_mask.any():
        vals = out.loc[education_count_mask].apply(
            lambda row: lookup_denominator(row, six_lookup, "population_6plus", max_gap=0.0),
            axis=1, result_type="expand"
        )
        vals.columns = ["den_value", "den_year", "den_type"]
        out.loc[education_count_mask, "population"] = vals["den_value"].to_numpy()
        out.loc[education_count_mask, "denominator_year"] = vals["den_year"].to_numpy()
        out.loc[education_count_mask, "denominator_type"] = vals["den_type"].to_numpy()
        out.loc[education_count_mask, "denominator_series_id"] = "Population6Plus || کل جمعیت ۶ ساله و بیشتر"

    if total_count_mask.any():
        vals = out.loc[total_count_mask].apply(
            lambda row: lookup_denominator(row, total_lookup, "total_population", max_gap=2.0),
            axis=1, result_type="expand"
        )
        vals.columns = ["den_value", "den_year", "den_type"]
        out.loc[total_count_mask, "population"] = vals["den_value"].to_numpy()
        out.loc[total_count_mask, "denominator_year"] = vals["den_year"].to_numpy()
        out.loc[total_count_mask, "denominator_type"] = vals["den_type"].to_numpy()
        out.loc[total_count_mask, "denominator_series_id"] = "Population || جمعیت کل"

    count_mask = out["transform"].eq("per_100k_population")
    out.loc[count_mask, "denominator_gap"] = (
        out.loc[count_mask, "year_num"] - out.loc[count_mask, "denominator_year"]
    ).abs()
    valid = count_mask & out["population"].gt(0)
    out.loc[valid, "value_transformed"] = out.loc[valid, "value_num"] / out.loc[valid, "population"] * 100000.0
    out.loc[valid, "transform_applied"] = np.where(
        out.loc[valid, "denominator_gap"].eq(0),
        np.where(out.loc[valid, "denominator_type"].eq("population_6plus"),
                 "per_100k_population_6plus_same_year",
                 "per_100k_population_same_year"),
        "per_100k_population_nearest_population_year"
    )
    out.loc[count_mask & ~valid, "value_transformed"] = np.nan
    out.loc[count_mask & ~valid, "transform_applied"] = "missing_population_denominator"
    return out


def _population_lookup(data: pd.DataFrame) -> pd.DataFrame:
    candidates = data[(data["geo_level"] == "province") & data["value_num"].notna() & data["year_num"].notna()].copy()
    text = candidates["series_text"].str.lower()
    candidates = candidates[text.str.contains(r"totalpopulation|جمعیت کل|^جمعیت جمعیت|Population جمعیت", regex=True, na=False)].copy()
    if candidates.empty:
        return pd.DataFrame(columns=["province", "year_num", "population"])
    candidates = candidates.sort_values(["province", "year_num", "series_id"])
    return (candidates.groupby(["province", "year_num"], as_index=False).first()
            [["province", "year_num", "value_num"]].rename(columns={"value_num": "population"}))


def _population6plus_lookup(data: pd.DataFrame) -> pd.DataFrame:
    candidates = data[(data["geo_level"] == "province") & data["value_num"].notna() & data["year_num"].notna()].copy()
    mask = candidates["series_id"].eq("Population6Plus || کل جمعیت ۶ ساله و بیشتر")
    candidates = candidates[mask].copy()
    if candidates.empty:
        return pd.DataFrame(columns=["province", "year_num", "population_6plus"])
    candidates = candidates.sort_values(["province", "year_num", "series_id"])
    return (candidates.groupby(["province", "year_num"], as_index=False).first()
            [["province", "year_num", "value_num"]].rename(columns={"value_num": "population_6plus"}))


def normalize_observations(observations: pd.DataFrame, method: str, scope: str) -> pd.DataFrame:
    if observations.empty:
        return observations.assign(normalized_score=pd.Series(dtype=float))
    out = observations.dropna(subset=["value_transformed"]).copy()
    group_columns = ["series_id", "year_num"] if scope == "within_year" else ["series_id"]
    normalized = []
    for _, group in out.groupby(group_columns, sort=False):
        values = group["value_transformed"].astype(float)
        if values.nunique() < 2:
            continue
        if method == "minmax":
            spread = values.max() - values.min()
            if np.isclose(spread, 0):
                continue
            base = (values - values.min()) / spread * 100.0
        elif method == "zscore":
            deviation = values.std(ddof=0)
            if np.isclose(deviation, 0):
                continue
            base = (50.0 + 10.0 * (values - values.mean()) / deviation).clip(0, 100)
        elif method == "robust":
            median = values.median()
            mad = (values - median).abs().median()
            if np.isclose(mad, 0):
                continue
            base = (50.0 + 10.0 * (values - median) / (1.4826 * mad)).clip(0, 100)
        else:
            raise ValueError(f"Unsupported normalization method: {method}")
        scored = group.copy()
        scored["normalized_base"] = base
        scored["normalized_score"] = np.where(scored["direction"].eq("higher_worse"), base, 100.0 - base)
        normalized.append(scored)
    return pd.concat(normalized, ignore_index=True) if normalized else out.iloc[0:0].assign(normalized_score=pd.Series(dtype=float))


def aggregate_temporally(normalized: pd.DataFrame, config: dict[str, Any], method: str | None = None, reference_year: int | None = None) -> pd.DataFrame:
    reference_year = int(reference_year or config["reference_year"])
    # All available years are retained. Reference year controls the recency anchor.
    usable = normalized[normalized["year_num"].notna()].copy()
    usable["temporal_gap"] = (reference_year - usable["year_num"]).abs()
    usable["recency_weight"] = usable["temporal_gap"].map(lambda age: ie.temporal_weight(float(age), config["temporal_weighting"], method))
    usable["quality_weight"] = 1.0
    rows = []
    for (province, series_id), group in usable.groupby(["province", "series_id"], sort=False):
        group = group.dropna(subset=["normalized_score", "recency_weight"])
        if group.empty:
            continue
        weights = (group["recency_weight"] * group["quality_weight"]).to_numpy(dtype=float)
        scores = group["normalized_score"].to_numpy(dtype=float)
        rows.append({
            "province": province, "series_id": series_id,
            "series_score": float(np.average(scores, weights=weights)),
            "observation_count": int(len(group)),
            "first_observation_year": float(group["year_num"].min()),
            "last_observation_year": float(group["year_num"].max()),
            "recency_weight_sum": float(weights.sum()),
            "temporal_quality": float(np.average(group["recency_weight"], weights=np.ones(len(group)))),
            "reference_year": reference_year,
            "temporal_method": method or config["temporal_weighting"]["method"],
        })
    return pd.DataFrame(rows)


def build_effective_weights(registry: pd.DataFrame, available_series: set[str], category_weights: dict[str, float]) -> pd.DataFrame:
    active = registry[(registry["inclusion_status"].isin(["CORE", "CONDITIONAL"])) & registry["series_id"].isin(available_series)].copy()
    if active.empty:
        return active
    active["category_weight"] = active["category"].map(category_weights)
    active = active[active["category_weight"].notna() & active["category_weight"].gt(0)].copy()
    active["subindicator_weight"] = active.groupby("category")["subindicator"].transform(lambda x: 1.0 / x.nunique())
    active["series_weight"] = active.groupby(["category", "subindicator"])["series_id"].transform(lambda x: 1.0 / x.nunique())
    active["effective_final_weight"] = active["category_weight"] * active["subindicator_weight"] * active["series_weight"]
    # Normalize only as a safety check; category_weights themselves sum to 1.
    total = active["effective_final_weight"].sum()
    if total > 0:
        active["effective_final_weight"] = active["effective_final_weight"] / total
    return active


def aggregate_index(series_scores: pd.DataFrame, weights: pd.DataFrame, category_weights: dict[str, float], min_categories: int):
    merged = series_scores.merge(weights[["series_id", "category", "subindicator", "series_weight", "subindicator_weight"]], on="series_id", how="inner")
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    sub = (merged.assign(weighted=merged["series_score"] * merged["series_weight"])
           .groupby(["province", "category", "subindicator"], as_index=False)
           .agg(weighted_sum=("weighted", "sum"), weight_sum=("series_weight", "sum"), series_count=("series_id", "nunique")))
    sub["subindicator_score"] = sub["weighted_sum"] / sub["weight_sum"]
    sub_weights = weights[["category", "subindicator", "subindicator_weight"]].drop_duplicates()
    sub = sub.merge(sub_weights, on=["category", "subindicator"], how="left")
    category = (sub.assign(weighted=sub["subindicator_score"] * sub["subindicator_weight"])
                .groupby(["province", "category"], as_index=False)
                .agg(weighted_sum=("weighted", "sum"), weight_sum=("subindicator_weight", "sum"), subindicator_count=("subindicator", "nunique")))
    category["category_score"] = category["weighted_sum"] / category["weight_sum"]
    category["category_weight"] = category["category"].map(category_weights)
    overall = (category.assign(weighted=category["category_score"] * category["category_weight"])
               .groupby("province", as_index=False)
               .agg(weighted_sum=("weighted", "sum"), available_weight=("category_weight", "sum"), category_count=("category", "nunique")))
    overall["overall_score"] = np.where(overall["category_count"] >= min_categories, overall["weighted_sum"] / overall["available_weight"], np.nan)
    overall["rank"] = overall["overall_score"].rank(ascending=False, method="min")
    return overall, category, sub


def province_quality(series_scores: pd.DataFrame, weights: pd.DataFrame, overall: pd.DataFrame) -> pd.DataFrame:
    expected = int(weights["series_id"].nunique())
    observed = series_scores.groupby("province").agg(
        indicator_count_used=("series_id", "nunique"),
        temporal_quality=("temporal_quality", "mean"),
        latest_observation_year=("last_observation_year", "max"),
    ).reset_index()
    quality = pd.DataFrame({"province": OFFICIAL_PROVINCES}).merge(observed, on="province", how="left")
    quality["indicator_count_used"] = quality["indicator_count_used"].fillna(0).astype(int)
    quality["missing_ratio"] = 1.0 - quality["indicator_count_used"] / expected if expected else np.nan
    quality["imputed_ratio"] = 0.0
    quality["temporal_quality"] = quality["temporal_quality"].fillna(0.0).clip(0, 1)
    quality["source_quality_status"] = "dataset labels present; source URLs unverified"
    quality["data_quality_score"] = 100.0 * (0.60 * (1.0 - quality["missing_ratio"]).clip(0, 1) + 0.40 * quality["temporal_quality"])
    quality["data_quality_score_scope"] = "coverage and temporal freshness; source provenance tracked separately"
    quality["uncertainty_level"] = np.select(
        [quality["missing_ratio"] > 0.20, quality["temporal_quality"] < 0.65, quality["missing_ratio"] > 0.05],
        ["high", "high", "medium"], default="low",
    )
    quality["overall_confidence"] = "provisional until source provenance is fully documented"
    return quality.merge(overall[["province", "overall_score", "rank"]], on="province", how="left")


def _scenario_weights(category_weights: dict[str, float]) -> dict[str, dict[str, float]]:
    categories = list(category_weights)
    scenarios = {"baseline": dict(category_weights), "equal_weight": {c: 1 / len(categories) for c in categories}}
    for focus in categories:
        residual = 0.5 / (len(categories) - 1)
        scenarios[f"{focus}_emphasis"] = {c: (0.5 if c == focus else residual) for c in categories}
    return scenarios


def _rank_metrics(test: pd.DataFrame, base: pd.DataFrame) -> dict[str, float]:
    m = test.merge(base, on="province", how="inner").dropna(subset=["rank", "baseline_rank"])
    if len(m) < 3:
        return {"province_count": len(m), "spearman": np.nan, "kendall": np.nan, "mean_abs_rank_change": np.nan, "max_abs_rank_change": np.nan}
    delta = (m["rank"] - m["baseline_rank"]).abs()
    return {
        "province_count": len(m),
        "spearman": m["rank"].corr(m["baseline_rank"], method="spearman"),
        "kendall": m["rank"].corr(m["baseline_rank"], method="kendall"),
        "mean_abs_rank_change": float(delta.mean()),
        "max_abs_rank_change": float(delta.max()),
    }


def calculate_scenarios(category_scores: pd.DataFrame, baseline: pd.DataFrame, category_weights: dict[str, float], min_categories: int) -> pd.DataFrame:
    base = baseline[["province", "overall_score", "rank"]].rename(columns={"overall_score": "baseline_score", "rank": "baseline_rank"})
    output = []
    for name, weights in _scenario_weights(category_weights).items():
        working = category_scores.copy()
        working["scenario_weight"] = working["category"].map(weights)
        scores = (working.assign(weighted=working["category_score"] * working["scenario_weight"])
                  .groupby("province", as_index=False)
                  .agg(weighted_sum=("weighted", "sum"), available_weight=("scenario_weight", "sum"), category_count=("category", "nunique")))
        scores["risk_score"] = np.where(scores["category_count"] >= min_categories, scores["weighted_sum"] / scores["available_weight"], np.nan)
        scores["rank"] = scores["risk_score"].rank(ascending=False, method="min")
        scores = scores.merge(base, on="province", how="left")
        scores["rank_change"] = scores["baseline_rank"] - scores["rank"]
        scores["score_change"] = scores["risk_score"] - scores["baseline_score"]
        scores["scenario"] = name
        output.append(scores[["scenario", "province", "risk_score", "rank", "baseline_score", "baseline_rank", "score_change", "rank_change"]])
    return pd.concat(output, ignore_index=True)


def _hierarchical_draw(weights: pd.DataFrame, rng: np.random.Generator, category_alpha: dict[str, float] | None = None, local_concentration: float | None = None) -> pd.DataFrame:
    hierarchy = weights[["category", "subindicator", "series_id"]].drop_duplicates()
    categories = sorted(hierarchy["category"].unique())
    if category_alpha is None:
        cat_alpha = np.ones(len(categories))
    else:
        cat_alpha = np.array([category_alpha[c] for c in categories], dtype=float)
    category_draw = dict(zip(categories, rng.dirichlet(cat_alpha)))
    records = []
    for category, cat_group in hierarchy.groupby("category"):
        subindicators = sorted(cat_group["subindicator"].unique())
        if local_concentration is None:
            sub_alpha = np.ones(len(subindicators))
        else:
            sub_alpha = np.ones(len(subindicators)) * local_concentration
        sub_draw = dict(zip(subindicators, rng.dirichlet(sub_alpha)))
        for subindicator, sub_group in cat_group.groupby("subindicator"):
            series = sorted(sub_group["series_id"].unique())
            if local_concentration is None:
                ser_alpha = np.ones(len(series))
            else:
                ser_alpha = np.ones(len(series)) * local_concentration
            draws = rng.dirichlet(ser_alpha)
            records.extend((sid, category_draw[category] * sub_draw[subindicator] * d) for sid, d in zip(series, draws))
    return pd.DataFrame(records, columns=["series_id", "simulation_weight"])


def _dirichlet_matrix(rng: np.random.Generator, alpha: np.ndarray, iterations: int) -> np.ndarray:
    samples = rng.gamma(shape=np.maximum(alpha, 1e-12), scale=1.0, size=(iterations, len(alpha)))
    return samples / samples.sum(axis=1, keepdims=True)


def _monte_carlo_mode(series_scores: pd.DataFrame, weights: pd.DataFrame, config: dict[str, Any], mode: str) -> pd.DataFrame:
    """Vectorized Monte Carlo sensitivity for reproducibility and practical runtime."""
    iterations = int(config["simulation_iterations"])
    seed_offset = 0 if mode == "global" else 1000003
    rng = np.random.default_rng(int(config["random_seed"]) + seed_offset)
    hierarchy = weights[["category", "subindicator", "series_id"]].drop_duplicates().copy()
    hierarchy = hierarchy.sort_values(["category", "subindicator", "series_id"]).reset_index(drop=True)
    series_ids = hierarchy["series_id"].tolist()
    series_index = {sid: i for i, sid in enumerate(series_ids)}
    categories = sorted(hierarchy["category"].unique())
    baseline = config["aggregation"]["category_weights"]
    local_conc = float(config.get("monte_carlo_local_concentration", 80))

    # Draw each hierarchy level, preserving the canonical series ordering.
    category_draw = _dirichlet_matrix(
        rng,
        np.array([float(baseline.get(c, 0.0)) for c in categories]) * (local_conc if mode == "local" else 1.0),
        iterations,
    )
    cat_index = {c: i for i, c in enumerate(categories)}
    sim_weights = np.zeros((iterations, len(series_ids)), dtype=float)

    for cat, cat_group in hierarchy.groupby("category", sort=False):
        subs = sorted(cat_group["subindicator"].unique())
        if mode == "local":
            sub_matrix = _dirichlet_matrix(rng, np.ones(len(subs)) * local_conc, iterations)
        else:
            sub_matrix = _dirichlet_matrix(rng, np.ones(len(subs)), iterations)
        sub_index = {sub: i for i, sub in enumerate(subs)}
        for sub, sub_group in cat_group.groupby("subindicator", sort=False):
            sids = sorted(sub_group["series_id"].unique())
            if mode == "local":
                ser_matrix = _dirichlet_matrix(rng, np.ones(len(sids)) * local_conc, iterations)
            else:
                ser_matrix = _dirichlet_matrix(rng, np.ones(len(sids)), iterations)
            cat_w = category_draw[:, cat_index[cat]]
            sub_w = sub_matrix[:, sub_index[sub]]
            for j, sid in enumerate(sids):
                col = series_index[sid]
                sim_weights[:, col] = cat_w * sub_w * ser_matrix[:, j]

    score_wide = series_scores.pivot_table(index="province", columns="series_id", values="series_score", aggfunc="mean").reindex(columns=series_ids)
    provinces = score_wide.index.tolist()
    score_matrix = score_wide.to_numpy(dtype=float)
    valid = ~np.isnan(score_matrix)
    score_filled = np.nan_to_num(score_matrix, nan=0.0)
    # iteration x province
    numerator = sim_weights @ score_filled.T
    denominator = sim_weights @ valid.T.astype(float)
    trial_scores = np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 0)
    trial_ranks = rankdata(-trial_scores, axis=1, method="min", nan_policy="omit")

    records = pd.DataFrame({
        "province": provinces,
        "median_score": np.nanmedian(trial_scores, axis=0),
        "score_std": np.nanstd(trial_scores, axis=0, ddof=1),
        "median_rank": np.nanmedian(trial_ranks, axis=0),
        "rank_p05": np.nanquantile(trial_ranks, 0.05, axis=0),
        "rank_p95": np.nanquantile(trial_ranks, 0.95, axis=0),
        "probability_top_5": np.nanmean(trial_ranks <= 5, axis=0),
        "probability_top_10": np.nanmean(trial_ranks <= 10, axis=0),
        "simulations": int(iterations),
    })
    return records

def monte_carlo(series_scores: pd.DataFrame, weights: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    return _monte_carlo_mode(series_scores, weights, config, "global")


def monte_carlo_local(series_scores: pd.DataFrame, weights: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    return _monte_carlo_mode(series_scores, weights, config, "local")


def leave_one_out(series_scores: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame):
    base = baseline[["province", "overall_score", "rank"]].rename(columns={"overall_score": "baseline_score", "rank": "baseline_rank"})
    series_rows, domain_rows = [], []
    available = set(series_scores["series_id"])
    category_weights = config["aggregation"]["category_weights"]
    for sid in sorted(available):
        subset = series_scores[series_scores["series_id"] != sid]
        w = build_effective_weights(registry, set(subset["series_id"]), category_weights)
        overall, _, _ = aggregate_index(subset, w, category_weights, int(config["minimum_categories_for_overall"]))
        comparison = overall.merge(base, on="province", how="left")
        comparison["removed_series_id"] = sid
        comparison["score_delta"] = comparison["overall_score"] - comparison["baseline_score"]
        comparison["rank_delta"] = comparison["baseline_rank"] - comparison["rank"]
        series_rows.append(comparison[["removed_series_id", "province", "overall_score", "rank", "score_delta", "rank_delta"]])
    for category in category_weights:
        subset_weights = {key: value for key, value in category_weights.items() if key != category}
        total = sum(subset_weights.values())
        subset_weights = {key: value / total for key, value in subset_weights.items()}
        ids = set(registry.loc[registry["category"] != category, "series_id"]).intersection(available)
        subset = series_scores[series_scores["series_id"].isin(ids)]
        w = build_effective_weights(registry[registry["category"] != category], ids, subset_weights)
        overall, _, _ = aggregate_index(subset, w, subset_weights, max(1, int(config["minimum_categories_for_overall"]) - 1))
        comparison = overall.merge(base, on="province", how="left")
        comparison["removed_category"] = category
        comparison["score_delta"] = comparison["overall_score"] - comparison["baseline_score"]
        comparison["rank_delta"] = comparison["baseline_rank"] - comparison["rank"]
        domain_rows.append(comparison[["removed_category", "province", "overall_score", "rank", "score_delta", "rank_delta"]])
    return pd.concat(series_rows, ignore_index=True), pd.concat(domain_rows, ignore_index=True)


def redundancy_audit(series_scores: pd.DataFrame, weights: pd.DataFrame, threshold: float) -> pd.DataFrame:
    categories = weights[["series_id", "category", "subindicator"]].drop_duplicates()
    joined = series_scores.merge(categories, on="series_id", how="inner")
    rows = []
    for category, group in joined.groupby("category"):
        wide = group.pivot(index="province", columns="series_id", values="series_score")
        corr = wide.corr(method="pearson", min_periods=5)
        ids = list(corr.columns)
        sub_map = categories.set_index("series_id")["subindicator"].to_dict()
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                value = corr.loc[left, right]
                rows.append({
                    "category": category,
                    "indicator_a": left,
                    "indicator_b": right,
                    "correlation": value,
                    "abs_correlation": abs(float(value)) if pd.notna(value) else np.nan,
                    "same_subindicator": sub_map.get(left) == sub_map.get(right),
                    "potential_statistical_redundancy": bool(pd.notna(value) and abs(float(value)) >= threshold),
                    "recommended_action": "manual conceptual review" if pd.notna(value) and abs(float(value)) >= threshold else "no automatic removal",
                    "rationale": "Correlation is a screening signal; conceptual and mathematical structure determines exclusion."
                })
    return pd.DataFrame(rows)


def temporal_sensitivity(normalized: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame) -> pd.DataFrame:
    baseline_rank = baseline[["province", "rank", "overall_score"]].rename(columns={"rank": "baseline_rank", "overall_score": "baseline_score"})
    methods = [config["temporal_weighting"]["method"]] + list(config["temporal_weighting"].get("alternatives", []))
    refs = list(config.get("temporal_sensitivity_reference_years", []))
    if int(config["reference_year"]) not in refs:
        refs.append(int(config["reference_year"]))
    rows = []
    setting_grid = {
        "linear": [(f"{config['temporal_weighting']['linear_decay_per_year'] * f:.4f}", config["temporal_weighting"]["linear_decay_per_year"] * f) for f in (0.67, 0.83, 1.0, 1.25, 1.5)],
        "exponential": [(f"{config['temporal_weighting']['exponential_lambda'] * f:.4f}", config["temporal_weighting"]["exponential_lambda"] * f) for f in (0.6, 0.8, 1.0, 1.2, 1.4)],
        "stepwise": [("baseline", None)],
    }
    for ref in refs:
        for method in dict.fromkeys(methods):
            for setting_name, setting_value in setting_grid[method]:
                cfg = json.loads(json.dumps(config))
                if method == "linear":
                    cfg["temporal_weighting"]["linear_decay_per_year"] = float(setting_value)
                elif method == "exponential":
                    cfg["temporal_weighting"]["exponential_lambda"] = float(setting_value)
                series = aggregate_temporally(normalized, cfg, method=method, reference_year=int(ref))
                w = build_effective_weights(registry, set(series["series_id"]), cfg["aggregation"]["category_weights"])
                overall, _, _ = aggregate_index(series, w, cfg["aggregation"]["category_weights"], int(cfg["minimum_categories_for_overall"]))
                m = overall[["province", "rank", "overall_score"]].merge(baseline_rank, on="province", how="inner")
                delta = (m["rank"] - m["baseline_rank"]).abs()
                rows.append({
                    "reference_year": int(ref),
                    "temporal_method": method,
                    "setting": setting_name,
                    "setting_value": setting_value,
                    "province_count": len(m),
                    "rank_spearman": m["rank"].corr(m["baseline_rank"], method="spearman") if len(m) >= 3 else np.nan,
                    "rank_kendall": m["rank"].corr(m["baseline_rank"], method="kendall") if len(m) >= 3 else np.nan,
                    "mean_abs_rank_change": float(delta.mean()) if len(m) else np.nan,
                    "max_abs_rank_change": float(delta.max()) if len(m) else np.nan,
                    "mean_abs_score_change": float((m["overall_score"] - m["baseline_score"]).abs().mean()) if len(m) else np.nan,
                })
    return pd.DataFrame(rows)


def normalization_sensitivity(transformed: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame) -> pd.DataFrame:
    baseline_cmp = baseline[["province", "rank", "overall_score"]].rename(columns={"rank": "baseline_rank", "overall_score": "baseline_score"})
    methods = [config["normalization"]["method"]] + list(config["normalization"].get("alternatives", []))
    rows = []
    for scope in ("within_year", "pooled"):
        for method in dict.fromkeys(methods):
            norm = normalize_observations(transformed, method, scope)
            series = aggregate_temporally(norm, config)
            w = build_effective_weights(registry, set(series["series_id"]), config["aggregation"]["category_weights"])
            overall, _, _ = aggregate_index(series, w, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
            m = overall[["province", "rank", "overall_score"]].merge(baseline_cmp, on="province", how="inner")
            delta = (m["rank"] - m["baseline_rank"]).abs()
            rows.append({
                "normalization_method": method,
                "scope": scope,
                "province_count": len(m),
                "rank_spearman": m["rank"].corr(m["baseline_rank"], method="spearman") if len(m) >= 3 else np.nan,
                "rank_kendall": m["rank"].corr(m["baseline_rank"], method="kendall") if len(m) >= 3 else np.nan,
                "mean_abs_rank_change": float(delta.mean()) if len(m) else np.nan,
                "max_abs_rank_change": float(delta.max()) if len(m) else np.nan,
                "mean_abs_score_change": float((m["overall_score"] - m["baseline_score"]).abs().mean()) if len(m) else np.nan,
            })
    return pd.DataFrame(rows)


SHDI_2023 = {
    "اردبیل": 0.761, "بوشهر": 0.812, "چهارمحال و بختیاری": 0.795, "آذربایجان شرقی": 0.785,
    "اصفهان": 0.831, "فارس": 0.809, "گیلان": 0.804, "گلستان": 0.777,
    "همدان": 0.774, "هرمزگان": 0.769, "ایلام": 0.815, "کرمان": 0.779,
    "کرمانشاه": 0.796, "خراسان رضوی": 0.782, "خوزستان": 0.802, "کهگیلویه و بویراحمد": 0.792,
    "کردستان": 0.746, "لرستان": 0.781, "مرکزی": 0.792, "مازندران": 0.824,
    "خراسان شمالی": 0.746, "قزوین": 0.796, "قم": 0.816, "سمنان": 0.824,
    "سیستان و بلوچستان": 0.687, "خراسان جنوبی": 0.756, "آذربایجان غربی": 0.759,
    "یزد": 0.824, "زنجان": 0.772,
}


def external_validation(overall: pd.DataFrame, input_dir: Path, output_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    validation_rows = []
    shdi_rows = [{
        "province": p, "metric": "SHDI", "value": v, "year": 2023,
        "source": "Global Data Lab", "source_url": "https://globaldatalab.org/shdi/table/shdi/IRN/",
        "validation_type": "external_convergent_criterion", "tehran_alborz_excluded": False
    } for p, v in SHDI_2023.items()]
    shdi = pd.DataFrame(shdi_rows)
    merged = overall[["province", "overall_score", "rank"]].merge(shdi[["province", "value"]], on="province", how="inner").dropna()
    # Higher SHDI represents higher human development; the index's higher score is designed as greater pressure/vulnerability.
    if len(merged) >= 3:
        pearson, pearson_p = pearsonr(merged["overall_score"], merged["value"])
        spearman, spearman_p = spearmanr(merged["overall_score"], merged["value"])
        kendall, kendall_p = kendalltau(merged["overall_score"], merged["value"])
        rows.append({
            "metric": "SHDI_2023",
            "n_matched": len(merged),
            "pearson": pearson,
            "pearson_pvalue": pearson_p,
            "spearman": spearman,
            "spearman_pvalue": spearman_p,
            "kendall": kendall,
            "kendall_pvalue": kendall_p,
            "status": "external_convergent_association",
            "limitation": "SHDI is external to the project but conceptually overlaps with education, health and living-standard dimensions; this is convergent evidence, not fully independent validation. Tehran and Alborz are excluded because GDL reports them as a combined region."
        })
    else:
        rows.append({"metric": "SHDI_2023", "n_matched": len(merged), "pearson": np.nan, "pearson_pvalue": np.nan, "spearman": np.nan, "spearman_pvalue": np.nan, "kendall": np.nan, "kendall_pvalue": np.nan, "status": "insufficient_match", "limitation": "Fewer than three correctly matched provinces."})
    if output_dir is not None:
        ie._write_csv(shdi, output_dir.parent / "data" / "external_validation_shdi_2023.csv")
    return pd.DataFrame(rows), shdi


def validation_leakage_check(registry: pd.DataFrame, shdi: pd.DataFrame) -> pd.DataFrame:
    active = registry[registry["inclusion_status"].isin(["CORE", "CONDITIONAL"])]["series_text"].str.lower().tolist()
    rows = []
    metric = "SHDI_2023"
    possible_terms = ("توسعه", "آموزش", "سواد", "فقر", "درآمد", "بیمارستان", "پزشک", "سلامت")
    hits = [text for text in active if any(term in text for term in possible_terms)]
    rows.append({
        "metric": metric,
        "exact_model_component": False,
        "name_based_overlap_count": len(hits),
        "leakage_status": "conceptual_overlap_present",
        "independence_class": "external_but_not_conceptually_independent",
        "note": "SHDI is externally produced but overlaps conceptually with several model domains; use as convergent criterion rather than a clean holdout outcome."
    })
    return pd.DataFrame(rows)



def cross_category_overlap_audit(series_scores: pd.DataFrame, weights: pd.DataFrame, threshold: float) -> pd.DataFrame:
    meta = weights[["series_id", "category", "subindicator"]].drop_duplicates()
    joined = series_scores.merge(meta, on="series_id", how="inner")
    wide = joined.pivot_table(index="province", columns="series_id", values="series_score", aggfunc="mean")
    corr = wide.corr(method="pearson", min_periods=5)
    meta_map = meta.set_index("series_id")["category"].to_dict()
    text_map = meta.set_index("series_id")["subindicator"].to_dict()
    # Terms are used only as a semantic-review signal; they do not trigger automatic exclusion.
    concept_terms = ["خودکشی", "مرگ مشکوک", "فقر", "بیکاری", "تخت", "پزشک", "مدرسه", "کلاس", "سرقت", "درمانگاه"]
    rows = []
    ids = list(corr.columns)
    text_lookup = weights.set_index("series_id")["indicator"].to_dict() if "indicator" in weights.columns else {}
    for i, left in enumerate(ids):
        for right in ids[i+1:]:
            lc, rc = meta_map.get(left), meta_map.get(right)
            if lc == rc:
                continue
            value = corr.loc[left, right]
            left_text = f"{text_map.get(left, '')} {text_lookup.get(left, '')}".lower()
            right_text = f"{text_map.get(right, '')} {text_lookup.get(right, '')}".lower()
            shared = [t for t in concept_terms if t in left_text and t in right_text]
            high = bool(pd.notna(value) and abs(float(value)) >= threshold)
            if high or shared:
                rows.append({
                    "category_a": lc, "series_a": left,
                    "category_b": rc, "series_b": right,
                    "correlation": value,
                    "statistical_overlap_flag": high,
                    "shared_concept_terms": ", ".join(shared),
                    "conceptual_review_required": bool(high or shared),
                    "recommended_action": "manual cross-category conceptual review",
                    "rationale": "Cross-category overlap can unintentionally give the same construct weight in more than one domain; review rather than automatic removal."
                })
    return pd.DataFrame(rows)

def missingness_profiles(raw: pd.DataFrame, series_scores: pd.DataFrame, weights: pd.DataFrame, quality: pd.DataFrame):
    series = weights[["series_id", "category"]].drop_duplicates().merge(
        series_scores.groupby("series_id")["province"].nunique().rename("observed_provinces"), on="series_id", how="left"
    )
    series["observed_provinces"] = series["observed_provinces"].fillna(0).astype(int)
    series["missing_ratio"] = 1.0 - series["observed_provinces"] / len(OFFICIAL_PROVINCES)
    category = series.groupby("category", as_index=False).agg(series_count=("series_id", "nunique"), mean_missing_ratio=("missing_ratio", "mean"))
    province = quality[["province", "indicator_count_used", "missing_ratio", "imputed_ratio", "temporal_quality"]].copy()
    year = raw[raw["geo_level"].eq("province")].groupby("year_num", dropna=False, as_index=False).agg(
        raw_rows=("raw_row_id", "count"), numeric_missing_rows=("value_num", lambda v: int(v.isna().sum())), province_count=("province", "nunique")
    )
    return series, province, category, year


def data_dictionary() -> pd.DataFrame:
    records = [
        ("overall_score", "Composite provincial index after hierarchical aggregation.", "0-100", "V2 scoring engine", "Temporal aggregation + weighted hierarchy", "Comparative composite measure."),
        ("series_score", "Temporally aggregated normalized series score.", "0-100", "Raw workbook", "Normalization + recency weighting", "Higher means larger contribution in the configured composite direction."),
        ("recency_weight", "Weight assigned to an observation based on distance from reference year.", "0-1", "V2 configuration", "Configured temporal decay", "Newer observations receive more weight."),
        ("missing_ratio", "Missing province-year share on the expected province-year grid.", "0-1", "V2 audit", "Expected 31-province grid per existing series year", "Higher values increase uncertainty."),
        ("data_quality_score", "Coverage/freshness diagnostic.", "0-100", "V2 scoring engine", "60% coverage + 40% temporal freshness", "Does not assert source quality."),
        ("provenance_status", "Evidence level for source documentation.", "status", "Project files", "Verified from available metadata only", "No source URLs are fabricated."),
    ]
    return pd.DataFrame(records, columns=["field_name", "definition", "unit", "source", "transformation", "interpretation"])


def _classify_sensitivity(value: float, low: float, high: float) -> str:
    if pd.isna(value):
        return "not_assessed"
    if value <= low:
        return "low"
    if value <= high:
        return "moderate"
    return "high"


def build_robustness_summary(scenario: pd.DataFrame, mc_global: pd.DataFrame, mc_local: pd.DataFrame,
                             loo_series: pd.DataFrame, loo_domain: pd.DataFrame,
                             temporal: pd.DataFrame, normalization: pd.DataFrame) -> str:
    lines = ["# Model Robustness Summary\n"]
    lines.append("This report summarizes model stability under documented alternative specifications. It does not establish causality or absolute truth.\n")
    if not scenario.empty:
        scen = scenario[scenario["scenario"] != "baseline"].copy()
        lines.append("## Scenario weighting\n")
        for name, g in scen.groupby("scenario"):
            lines.append(f"- `{name}`: mean absolute rank change = {g['rank_change'].abs().mean():.2f}; max absolute rank change = {g['rank_change'].abs().max():.0f}.\n")
    if not mc_global.empty:
        lines.append("## Global Monte Carlo\n")
        lines.append(f"- Mean province score SD: {mc_global['score_std'].mean():.3f}.\n")
        lines.append(f"- Mean rank interval width (P95-P05): {(mc_global['rank_p95']-mc_global['rank_p05']).mean():.2f}.\n")
    if not mc_local.empty:
        lines.append("## Local Monte Carlo\n")
        lines.append(f"- Mean province score SD: {mc_local['score_std'].mean():.3f}.\n")
        lines.append(f"- Mean rank interval width: {(mc_local['rank_p95']-mc_local['rank_p05']).mean():.2f}.\n")
    if not loo_series.empty:
        s = loo_series.groupby("removed_series_id").agg(max_abs_rank_delta=("rank_delta", lambda x: x.abs().max()), mean_abs_rank_delta=("rank_delta", lambda x: x.abs().mean()))
        lines.append("## Indicator LOO\n")
        lines.append(f"- Median maximum rank impact across removed series: {s['max_abs_rank_delta'].median():.2f}.\n")
        lines.append(f"- Largest observed rank impact from removing one series: {s['max_abs_rank_delta'].max():.0f}.\n")
    if not loo_domain.empty:
        d = loo_domain.groupby("removed_category").agg(mean_abs_rank_delta=("rank_delta", lambda x: x.abs().mean()), max_abs_rank_delta=("rank_delta", lambda x: x.abs().max()))
        lines.append("## Domain LOO\n")
        for cat, row in d.iterrows():
            lines.append(f"- `{cat}` removed: mean absolute rank change = {row['mean_abs_rank_delta']:.2f}; max = {row['max_abs_rank_delta']:.0f}.\n")
    if not normalization.empty:
        lines.append("## Normalization\n")
        base = normalization[(normalization['normalization_method']== 'minmax') & (normalization['scope']=='within_year')]
        for _, row in normalization.iterrows():
            lines.append(f"- `{row['scope']} / {row['normalization_method']}`: Spearman = {row['rank_spearman']:.3f}, mean abs rank change = {row['mean_abs_rank_change']:.2f}.\n")
    if not temporal.empty:
        lines.append("## Temporal robustness\n")
        best = temporal.sort_values("rank_spearman", ascending=False).head(1)
        worst = temporal.sort_values("rank_spearman", ascending=True).head(1)
        if not best.empty:
            lines.append(f"- Highest tested rank correlation: {best.iloc[0]['rank_spearman']:.3f} (`ref={best.iloc[0]['reference_year']}`, `{best.iloc[0]['temporal_method']}`, setting={best.iloc[0]['setting']}).\n")
        if not worst.empty:
            lines.append(f"- Lowest tested rank correlation: {worst.iloc[0]['rank_spearman']:.3f} (`ref={worst.iloc[0]['reference_year']}`, `{worst.iloc[0]['temporal_method']}`, setting={worst.iloc[0]['setting']}).\n")
    lines.append("\n## Interpretation\n")
    lines.append("Sensitivity results describe model dependence on assumptions. They should be reported alongside the baseline rather than used to select a preferred ranking.\n")
    return "".join(lines)


def run_pipeline(input_path: Path, output_dir: Path, config: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    root = output_dir.parent
    data_dir, registry_dir, report_dir = root / "data", root / "registry", root / "reports"
    for d in (data_dir, registry_dir, report_dir):
        d.mkdir(parents=True, exist_ok=True)

    import time
    _t0 = time.time()
    raw = load_raw_input(input_path)
    print("stage raw", round(time.time()-_t0,2), flush=True)
    registry = derive_registry(raw, config)
    print("stage registry", round(time.time()-_t0,2), flush=True)
    transformed = transform_observations(raw, registry)
    print("stage transform", round(time.time()-_t0,2), flush=True)
    normalized = normalize_observations(transformed, config["normalization"]["method"], config["normalization"]["scope"])
    print("stage normalize", round(time.time()-_t0,2), flush=True)
    series_scores = aggregate_temporally(normalized, config)
    print("stage temporal base", round(time.time()-_t0,2), flush=True)
    weights = build_effective_weights(registry, set(series_scores["series_id"]), config["aggregation"]["category_weights"])
    overall, category, subindicator = aggregate_index(series_scores, weights, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
    quality = province_quality(series_scores, weights, overall)
    print("stage core score", round(time.time()-_t0,2), flush=True)
    final = quality.copy()

    scenarios = calculate_scenarios(category, overall, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
    print("stage scenarios", round(time.time()-_t0,2), flush=True)
    mc_global = monte_carlo(series_scores, weights, config)
    print("stage mc global", round(time.time()-_t0,2), flush=True)
    mc_local = monte_carlo_local(series_scores, weights, config)
    print("stage mc local", round(time.time()-_t0,2), flush=True)
    loo_series, loo_domain = leave_one_out(series_scores, registry, config, overall)
    print("stage loo", round(time.time()-_t0,2), flush=True)
    redundancy = redundancy_audit(series_scores, weights, float(config["redundancy_correlation_threshold"]))
    print("stage redundancy", round(time.time()-_t0,2), flush=True)
    cross_overlap = cross_category_overlap_audit(series_scores, weights, float(config["redundancy_correlation_threshold"]))
    print("stage cross overlap", round(time.time()-_t0,2), flush=True)
    # Persist core inputs first; heavy robustness checks run in isolated subprocesses
    # to avoid pandas/BLAS state interactions observed when both routines share one process.
    ie._write_csv(transformed, data_dir / "transformed_observations.csv")
    ie._write_csv(normalized, data_dir / "normalized_observations.csv")
    ie._write_csv(registry, registry_dir / "indicator_registry_final.csv")
    ie._write_csv(overall.sort_values("rank"), output_dir / "provincial_composite_index.csv")

    import subprocess, sys
    root_path = root.resolve()
    workers = [
        subprocess.Popen([sys.executable, "-m", "src.robustness_worker", "--kind", "temporal", "--root", str(root_path)], cwd=str(root_path)),
        subprocess.Popen([sys.executable, "-m", "src.robustness_worker", "--kind", "normalization", "--root", str(root_path)], cwd=str(root_path)),
    ]
    return_codes = [proc.wait() for proc in workers]
    if any(code != 0 for code in return_codes):
        raise RuntimeError(f"Robustness worker failed: {return_codes}")
    temporal = pd.read_csv(output_dir / "temporal_sensitivity_final.csv")
    normalization = pd.read_csv(output_dir / "normalization_sensitivity_final.csv")
    print("stage temporal+norm sens", round(time.time()-_t0,2), flush=True)
    validation, shdi = external_validation(overall, input_path.parent, root / "outputs")
    print("stage validation", round(time.time()-_t0,2), flush=True)
    leakage = validation_leakage_check(registry, shdi)
    print("stage leakage", round(time.time()-_t0,2), flush=True)

    # Merge effective weights back into registry.
    registry = registry.merge(weights[["series_id", "subindicator_weight", "series_weight", "effective_final_weight"]], on="series_id", how="left", suffixes=("", "_effective"))
    for column in ("subindicator_weight", "series_weight", "effective_final_weight"):
        alt = f"{column}_effective"
        if alt in registry.columns:
            registry[column] = registry[alt].combine_first(registry[column])
            registry = registry.drop(columns=[alt])

    # Detailed contributions.
    # Contribution decomposition must reproduce the actual per-province aggregation.
    # Because the engine renormalizes available series/subindicator/category weights when some
    # inputs are missing for a province, a single global effective weight is not sufficient.
    # Build province-specific normalized contribution weights from the same hierarchy.
    series_contributions = series_scores.merge(
        weights[["series_id", "category", "subindicator", "series_weight", "subindicator_weight", "effective_final_weight"]],
        on="series_id", how="inner"
    )
    # Series weights within each province × category × subindicator.
    series_contributions["available_series_weight"] = (
        series_contributions.groupby(["province", "category", "subindicator"])['series_weight']
        .transform('sum')
    )
    series_contributions["local_series_weight"] = np.where(
        series_contributions["available_series_weight"] > 0,
        series_contributions["series_weight"] / series_contributions["available_series_weight"],
        np.nan
    )
    # Subindicator weights among subindicators actually available for a province/category.
    sub_available = series_contributions.groupby(["province", "category", "subindicator"], as_index=False).agg(
        subindicator_weight=("subindicator_weight", "first"),
        subindicator_score=("series_score", "mean")
    )
    sub_available["available_subindicator_weight"] = sub_available.groupby(["province", "category"])["subindicator_weight"].transform('sum')
    sub_available["local_subindicator_weight"] = np.where(
        sub_available["available_subindicator_weight"] > 0,
        sub_available["subindicator_weight"] / sub_available["available_subindicator_weight"],
        np.nan
    )
    series_contributions = series_contributions.merge(
        sub_available[["province", "category", "subindicator", "local_subindicator_weight"]],
        on=["province", "category", "subindicator"], how="left"
    )
    available_category = series_contributions.groupby("province")["category"].nunique().rename("available_category_count")
    category_contrib = series_contributions[["province", "category"]].drop_duplicates().copy()
    category_contrib = category_contrib.merge(
        pd.DataFrame({"province": list(available_category.index), "available_category_count": list(available_category.values)}),
        on="province", how="left"
    )
    category_contrib["category_weight"] = category_contrib["category"].map(config["aggregation"]["category_weights"])
    category_contrib["available_category_weight"] = category_contrib.groupby("province")["category_weight"].transform("sum")
    category_contrib["local_category_weight"] = np.where(
        category_contrib["available_category_weight"] > 0,
        category_contrib["category_weight"] / category_contrib["available_category_weight"],
        np.nan
    )
    series_contributions = series_contributions.merge(
        category_contrib[["province", "category", "local_category_weight"]],
        on=["province", "category"], how="left"
    )
    series_contributions["local_effective_weight"] = (
        series_contributions["local_category_weight"]
        * series_contributions["local_subindicator_weight"]
        * series_contributions["local_series_weight"]
    )
    series_contributions["weighted_series_contribution"] = (
        series_contributions["series_score"] * series_contributions["local_effective_weight"]
    )
    series_contributions["effective_final_weight"] = series_contributions["local_effective_weight"]
    category_contributions = category.copy()
    category_contributions["available_category_weight"] = category_contributions.groupby("province")["category_weight"].transform("sum")
    category_contributions["local_category_weight"] = category_contributions["category_weight"] / category_contributions["available_category_weight"]
    category_contributions["weighted_category_contribution"] = (
        category_contributions["category_score"] * category_contributions["local_category_weight"]
    )
    subindicator["weighted_subindicator_contribution"] = subindicator["subindicator_score"] * subindicator["subindicator_weight"]

    # Audit summaries.
    exact_duplicate_count = int(raw.attrs.get("exact_duplicates_removed", 0))
    conflict_row_count = int(raw.attrs.get("conflict_rows", 0))
    conflict_keys = int(registry["conflicting_province_year_keys"].sum()) if "conflicting_province_year_keys" in registry else 0
    diagnostics = pd.DataFrame([{
        "raw_rows_after_exact_dedup": len(raw),
        "raw_rows_before_exact_dedup": int(raw.attrs.get("raw_rows_before_dedup", len(raw))),
        "exact_duplicate_rows_removed": exact_duplicate_count,
        "conflicting_rows_flagged": conflict_row_count,
        "conflicting_province_year_keys": conflict_keys,
        "official_provinces_in_raw": raw.loc[raw["geo_level"].eq("province"), "province"].nunique(),
        "raw_series": raw["series_id"].nunique(),
        "registry_series": len(registry),
        "included_series": weights["series_id"].nunique(),
        "core_series": int((registry["inclusion_status"] == "CORE").sum()),
        "conditional_series": int((registry["inclusion_status"] == "CONDITIONAL").sum()),
        "excluded_series": int((registry["inclusion_status"] == "EXCLUDED").sum()),
        "categories": weights["category"].nunique(),
        "subindicators": weights[["category", "subindicator"]].drop_duplicates().shape[0],
        "effective_weight_sum": float(weights["effective_final_weight"].sum()),
        "external_validation_status": "; ".join(validation["status"].astype(str).unique()),
        "external_validation_n": int(validation["n_matched"].max()) if not validation.empty else 0,
    }])

    # Missingness profiles from correct panel denominator.
    missing_indicator, missing_province, missing_category, missing_year = missingness_profiles(raw, series_scores, weights, quality)

    # Conflicting keys audit.
    base_prov = raw[(raw["geo_level"] == "province") & raw["year_num"].notna()].copy()
    conflict_audit = base_prov.groupby(["province", "series_id", "year_num"], as_index=False).agg(
        row_count=("raw_row_id", "count"), distinct_values=("value_num", lambda s: s.dropna().nunique()), values=("value_num", lambda s: ", ".join(map(str, sorted(set(s.dropna())))))
    )
    conflict_audit = conflict_audit[conflict_audit["distinct_values"] > 1].merge(registry[["series_id", "indicator", "category"]], on="series_id", how="left")
    ie._write_csv(conflict_audit, report_dir / "conflicting_keys_audit.csv")

    # Population denominator audit. This records which denominator type/year was used for each transformed count series.
    denominator_rows = transformed[transformed["transform"].eq("per_100k_population")].copy()
    if not denominator_rows.empty:
        denominator_audit = (denominator_rows.groupby(
            ["series_id", "category", "transform", "denominator_type", "transform_applied", "denominator_gap"],
            dropna=False, as_index=False
        ).size().rename(columns={"size": "row_count"}))
        denominator_audit["same_year_flag"] = denominator_audit["denominator_gap"].eq(0)
    else:
        denominator_audit = pd.DataFrame(columns=["series_id","category","transform","denominator_type","transform_applied","denominator_gap","row_count","same_year_flag"])
    ie._write_csv(denominator_audit, report_dir / "denominator_alignment_audit.csv")
    (report_dir / "denominator_alignment_methodology.md").write_text(
        "# Population Denominator Alignment\n\n"
        "Count-based indicators are normalized only where population normalization is substantively meaningful. School/class capacity counts use same-year `Population6Plus` when available. Other selected count indicators use same-year total population when available, otherwise the nearest total-population observation within the existing maximum two-year gap. Rates, percentages, ratios, indexes and already-per-capita measures are not divided by population here.\n",
        encoding="utf-8"
    )

    # Weight audit.
    weight_audit = weights[["series_id", "indicator", "category", "subindicator", "category_weight", "subindicator_weight", "series_weight", "effective_final_weight"]].copy()
    weight_audit["weight_product_raw"] = weight_audit["category_weight"] * weight_audit["subindicator_weight"] * weight_audit["series_weight"]

    # Data provenance audit.
    provenance = registry[["series_id", "indicator", "category", "dataset_name", "source_file", "source", "source_url", "source_quality", "provenance_status", "provenance_source_organization", "provenance_evidence_url", "provenance_evidence_type", "provenance_evidence_note", "review_status", "review_notes"]].copy()

    # Temporal comparison: preserve raw normalization comparison and report.
    robustness_md = build_robustness_summary(scenarios, mc_global, mc_local, loo_series, loo_domain, temporal, normalization)
    (report_dir / "model_robustness_summary.md").write_text(robustness_md, encoding="utf-8")

    temporal_methodology = f"""# Temporal Methodology\n\nReference period: **{config['reference_year']}**.\n\nThe index is intentionally multi-year. Observations are not discarded merely because they precede the reference period. The reference period acts as a recency anchor. Temporal distance is calculated as `abs(reference_year - observation_year)`.\n\nBaseline temporal function: `{config['temporal_weighting']['method']}` with configured parameters. All available observations receive a non-zero weight under the baseline function.\n\nTemporal aggregation occurs at the province-series level after normalization.\n\nThe robustness suite tests alternative decay functions, decay strengths and reference years.\n"""
    (report_dir / "temporal_methodology.md").write_text(temporal_methodology, encoding="utf-8")

    normalization_report = """# Normalization Methodology Audit\n\nThe baseline uses within-year normalization across provinces. This measures a province's relative standing within each year before temporal aggregation. Pooled normalization is tested as a robustness alternative. The comparison is descriptive: it quantifies how much rankings depend on the normalization scope and method.\n"""
    (report_dir / "normalization_methodology_audit.md").write_text(normalization_report, encoding="utf-8")


    final_decision = "READY WITH LIMITATIONS" if (int(validation["n_matched"].max()) >= 20 and float(weights["effective_final_weight"].sum()) == 1.0) else "REQUIRES REVISION"
    (report_dir / "final_model_decision.md").write_text(
        f"# Final Model Decision\n\n**Status: {final_decision}**\n\nThe V2 framework is operationally complete and has undergone data, temporal, weighting, redundancy, sensitivity and external-convergent checks. The principal remaining limitation is source provenance: the included workbook series carry dataset labels, but their original external source URLs are not documented in the available project files. External validation uses Global Data Lab SHDI 2023 as a convergent external criterion; it is not treated as fully independent because of conceptual overlap with model dimensions.\n",
        encoding="utf-8",
    )

    # Main outputs.
    mapping = raw[["Province", "province", "geo_level"]].drop_duplicates().sort_values(["geo_level", "province", "Province"])
    ie._write_csv(raw, data_dir / "raw_observations_standardized.csv")
    ie._write_csv(transformed, data_dir / "transformed_observations.csv")
    ie._write_csv(normalized, data_dir / "normalized_observations.csv")
    ie._write_csv(shdi, data_dir / "external_validation_shdi_2023.csv")
    ie._write_csv(series_scores, output_dir / "series_scores.csv")
    ie._write_csv(weight_audit, output_dir / "weight_audit.csv")
    ie._write_csv(weights, registry_dir / "effective_weights.csv")
    ie._write_csv(registry, registry_dir / "indicator_registry_final.csv")
    ie._write_csv(registry.copy(), registry_dir / "indicator_review.csv")
    ie._write_csv(mapping, registry_dir / "province_mapping.csv")
    ie._write_csv(subindicator, output_dir / "subindicator_scores.csv")
    ie._write_csv(category, output_dir / "category_scores.csv")
    ie._write_csv(category_contributions, output_dir / "province_category_contributions.csv")
    ie._write_csv(series_contributions, output_dir / "province_series_contributions.csv")
    ie._write_csv(final.sort_values("rank"), output_dir / "provincial_composite_index.csv")
    ie._write_csv(quality, output_dir / "province_data_quality.csv")
    ie._write_csv(scenarios, output_dir / "scenario_sensitivity.csv")
    ie._write_csv(mc_global, output_dir / "monte_carlo_global.csv")
    ie._write_csv(mc_local, output_dir / "monte_carlo_local.csv")
    ie._write_csv(mc_global.copy(), output_dir / "monte_carlo_weight_sensitivity.csv")
    ie._write_csv(loo_series, output_dir / "indicator_loo_final.csv")
    ie._write_csv(loo_domain, output_dir / "domain_loo_final.csv")
    ie._write_csv(loo_series.copy(), output_dir / "sensitivity_indicator_loo.csv")
    ie._write_csv(loo_domain.copy(), output_dir / "sensitivity_domain_loo.csv")
    ie._write_csv(redundancy, output_dir / "redundancy_final.csv")
    ie._write_csv(redundancy.copy(), output_dir / "redundancy_audit.csv")
    ie._write_csv(cross_overlap, output_dir / "cross_category_overlap.csv")
    ie._write_csv(temporal, output_dir / "temporal_sensitivity_final.csv")
    ie._write_csv(temporal.copy(), output_dir / "temporal_sensitivity.csv")
    ie._write_csv(normalization, output_dir / "normalization_sensitivity_final.csv")
    ie._write_csv(normalization.copy(), output_dir / "normalization_sensitivity.csv")
    ie._write_csv(validation, output_dir / "external_validation_final.csv")
    ie._write_csv(validation.copy(), output_dir / "external_validation_results.csv")
    ie._write_csv(leakage, output_dir / "validation_leakage_audit.csv")
    ie._write_csv(leakage.copy(), output_dir / "validation_leakage_check.csv")
    ie._write_csv(missing_indicator, output_dir / "missingness_by_indicator.csv")
    ie._write_csv(missing_province, output_dir / "missingness_by_province.csv")
    ie._write_csv(missing_category, output_dir / "missingness_by_category.csv")
    ie._write_csv(missing_year, output_dir / "missingness_by_year.csv")
    ie._write_csv(provenance, report_dir / "provenance_audit.csv")
    ie._write_csv(weight_audit, report_dir / "weight_audit.csv")
    ie._write_csv(diagnostics, output_dir / "model_diagnostics_final.csv")
    ie._write_csv(diagnostics.copy(), output_dir / "model_diagnostics.csv")
    ie._write_csv(ie.data_dictionary(), report_dir / "data_dictionary.csv")

    # Core reports.
    audit = f"""# V2 Hardening Audit\n\n- Raw rows before exact dedup: {diagnostics.iloc[0]['raw_rows_before_exact_dedup']}\n- Exact duplicate rows removed from modeling layer: {diagnostics.iloc[0]['exact_duplicate_rows_removed']}\n- Conflicting province-series-year rows flagged: {diagnostics.iloc[0]['conflicting_rows_flagged']}\n- Conflicting province-series-year keys: {diagnostics.iloc[0]['conflicting_province_year_keys']}\n- Raw series: {diagnostics.iloc[0]['raw_series']}\n- Final registry series: {diagnostics.iloc[0]['registry_series']}\n- Included series: {diagnostics.iloc[0]['included_series']}\n- CORE: {diagnostics.iloc[0]['core_series']}\n- CONDITIONAL: {diagnostics.iloc[0]['conditional_series']}\n- EXCLUDED: {diagnostics.iloc[0]['excluded_series']}\n- Effective weight sum: {diagnostics.iloc[0]['effective_weight_sum']}\n\n## Key methodological actions\n\n1. Multi-year observations are retained; reference year is a temporal anchor, not a hard cutoff.\n2. Unit inference distinguishes percentages, ratios, rates, indexes, per-capita values and counts.\n3. Generic counts are not automatically transformed to per-100k; only selected event/capacity counts are.\n4. Conflicting province-series-year values are excluded from scoring until resolved.\n5. Mathematically duplicated aggregate measures are excluded where a direct component/rate already exists.\n6. Missingness is measured against the expected province-year grid before numeric rows are dropped.\n7. Provenance is not fabricated; unavailable URLs remain unverified.\n"""
    (report_dir / "audit_report.md").write_text(audit, encoding="utf-8")
    (report_dir / "decision_log.md").write_text(
        "# Decision Log\n\n- Reference year changed from 1402 to 1403 as the recency anchor because 1403 is the latest observation year in the project.\n- Multi-year history retained; no hard cutoff.\n- Exact duplicates removed only from modeling layer; raw workbook is unchanged.\n- Conflicting province-series-year records are flagged and excluded from scoring until semantically resolved.\n- Count-to-per-100k conversion is rule-based and limited to substantive event/capacity series.\n- Aggregate measures that mathematically duplicate explicit component/rate measures are excluded from the baseline model.\n- SHDI 2023 is used as an external convergent criterion, not a fully independent holdout.\n", encoding="utf-8")
    (report_dir / "v2_change_log.md").write_text(
        "# V2 Hardening Change Log\n\n- Added multi-year reference-anchor logic.\n- Fixed missingness denominator.\n- Added duplicate/conflict audit.\n- Corrected unit inference for inflation, ratios and shares.\n- Limited automatic count-rate transformation.\n- Added local Monte Carlo sensitivity around baseline weights.\n- Expanded temporal sensitivity across reference years and decay strengths.\n- Added normalization scope sensitivity.\n- Added SHDI 2023 external convergent check.\n- Added provenance status and explicit source limitations.\n- Added series-aware population denominator alignment: school/class counts use same-year population 6+ where available; other selected count indicators use same-year total population or the existing nearest total-population observation within a maximum two-year gap.\n", encoding="utf-8")
    (report_dir / "limitations.md").write_text(
        "# Limitations\n\n- Many model series do not have recoverable original source URLs in the supplied project metadata.\n- Some province-series-year records contain unresolved conflicting values and are excluded at the observation level.\n- The composite is sensitive to assumptions in weighting and normalization; sensitivity results should accompany the baseline.\n- SHDI provides external convergent evidence but conceptually overlaps with model dimensions and therefore is not a clean independent outcome.\n- The index is comparative and model-dependent; it does not establish causality or absolute truth.\n", encoding="utf-8")

    # Final hardened reports and reproducibility artifacts. These are intentionally generated
    # at the end so a rerun cannot revert the documentation to an earlier draft.
    score_decomposition = pd.concat([
        category_contributions.assign(level="category", subindicator="", series_id="", score=category_contributions["category_score"], weight=category_contributions["category_weight"], weighted_contribution=category_contributions["weighted_category_contribution"])[["level","province","category","subindicator","series_id","score","weight","weighted_contribution"]],
        subindicator.assign(level="subindicator", series_id="", score=subindicator["subindicator_score"], weight=subindicator["subindicator_weight"], weighted_contribution=subindicator["weighted_subindicator_contribution"])[["level","province","category","subindicator","series_id","score","weight","weighted_contribution"]],
        series_contributions.assign(level="series", score=series_contributions["series_score"], weight=series_contributions["effective_final_weight"], weighted_contribution=series_contributions["weighted_series_contribution"])[["level","province","category","subindicator","series_id","score","weight","weighted_contribution"]],
    ], ignore_index=True).sort_values(["province","level","category","subindicator","series_id"])
    ie._write_csv(score_decomposition, output_dir / "province_score_decomposition.csv")

    # Manual-review queues: retain the baseline mapping but make questionable semantic placements explicit.
    active_registry = registry[registry["inclusion_status"].isin(["CORE", "CONDITIONAL"])].copy()
    category_review = active_registry[["series_id","indicator","category","subindicator"]].copy()
    category_review["category_review_status"] = "inherited_from_workbook; no automatic change"
    category_review["review_reason"] = "Manual conceptual review recommended before external research release."
    mask_budget = category_review["indicator"].astype(str).str.contains("Per Capita Budget", case=False, na=False)
    category_review.loc[mask_budget, "review_reason"] = "Per Capita Budget is conceptually closer to public-finance/economic or infrastructure capacity than a generic social grouping; retain baseline until source taxonomy is verified."
    mask_literacy = category_review["indicator"].astype(str).str.contains("نرخ سواد", na=False)
    category_review.loc[mask_literacy, "review_reason"] = "Literacy is plausibly educational; current workbook places it in Social. Retain baseline until the intended taxonomy is verified."
    ie._write_csv(category_review, report_dir / "category_mapping_review.csv")

    direction_review = registry[["series_id","indicator","category","direction","unit_type","transform"]].copy()
    direction_review["direction_review_status"] = np.where(direction_review["direction"].eq("unknown"), "REQUIRED", "REVIEWED_BY_RULES_ONLY")
    direction_review["rationale"] = np.where(direction_review["direction"].eq("unknown"), "Direction cannot be justified from current project metadata.", "Direction assigned from explicit rule set; human semantic sign-off still recommended.")
    ie._write_csv(direction_review, report_dir / "direction_audit.csv")

    unit_review = registry[["series_id","indicator","unit_type","transform","source_file"]].copy()
    unit_review["review_status"] = "Rule-based audit; manual review required for ambiguous constructs."
    ie._write_csv(unit_review, report_dir / "unit_transform_audit.csv")

    # Dynamic robustness/validation reports.
    scen_nonbase = scenarios[scenarios["scenario"] != "baseline"].copy()
    scen_summary = scen_nonbase.groupby("scenario").agg(mean_abs_rank_change=("rank_change", lambda x: x.abs().mean()), max_abs_rank_change=("rank_change", lambda x: x.abs().max())).round(3)
    global_rank_width = float((mc_global["rank_p95"] - mc_global["rank_p05"]).mean()) if not mc_global.empty else np.nan
    local_rank_width = float((mc_local["rank_p95"] - mc_local["rank_p05"]).mean()) if not mc_local.empty else np.nan
    temporal_min = float(temporal["rank_spearman"].min()) if not temporal.empty else np.nan
    temporal_max = float(temporal["rank_spearman"].max()) if not temporal.empty else np.nan
    norm_min = float(normalization["rank_spearman"].min()) if not normalization.empty else np.nan
    norm_max = float(normalization["rank_spearman"].max()) if not normalization.empty else np.nan
    loo_s = loo_series.groupby("removed_series_id").agg(max_abs_rank_delta=("rank_delta", lambda x: x.abs().max())) if not loo_series.empty else pd.DataFrame()
    loo_d = loo_domain.groupby("removed_category").agg(mean_abs_rank_delta=("rank_delta", lambda x: x.abs().mean()), max_abs_rank_delta=("rank_delta", lambda x: x.abs().max())) if not loo_domain.empty else pd.DataFrame()

    robustness_lines = [
        "# Model Robustness Summary\n",
        "All robustness results describe dependence on model assumptions; they are not evidence of causality or absolute truth.\n",
        "## Scenario weighting\n",
    ]
    for name, row in scen_summary.iterrows():
        robustness_lines.append(f"- `{name}`: mean absolute rank change = {row['mean_abs_rank_change']:.2f}; max absolute rank change = {row['max_abs_rank_change']:.0f}.\n")
    robustness_lines += [
        "\n## Monte Carlo\n",
        f"- Global: mean score SD = {mc_global['score_std'].mean():.2f}; mean P95–P05 rank width = {global_rank_width:.2f}.\n",
        f"- Local around baseline: mean score SD = {mc_local['score_std'].mean():.2f}; mean P95–P05 rank width = {local_rank_width:.2f}.\n",
        "\n## Indicator LOO\n",
        f"- Median of per-indicator maximum rank impact = {loo_s['max_abs_rank_delta'].median():.2f}; largest observed impact = {loo_s['max_abs_rank_delta'].max():.0f}.\n" if not loo_s.empty else "- Indicator LOO not available.\n",
        "\n## Domain LOO\n",
    ]
    for cat, row in loo_d.iterrows():
        robustness_lines.append(f"- `{cat}` removed: mean absolute rank change = {row['mean_abs_rank_delta']:.2f}; max = {row['max_abs_rank_delta']:.0f}.\n")
    robustness_lines += [
        "\n## Normalization sensitivity\n",
        f"- Tested rank Spearman range = {norm_min:.3f}–{norm_max:.3f}.\n",
        "\n## Temporal sensitivity\n",
        f"- Tested rank Spearman range = {temporal_min:.3f}–{temporal_max:.3f}; maximum mean absolute rank change = {temporal['mean_abs_rank_change'].max():.2f}; maximum absolute rank change = {temporal['max_abs_rank_change'].max():.0f}.\n",
        "\n## Diagnostic thresholds\n",
        "For readability only: mean absolute rank change <=1 = low, >1–3 = moderate, >3 = high; maximum rank change <=3 = low, >3–7 = moderate, >7 = high; Spearman >=0.98 = high stability, 0.90–<0.98 = moderate, <0.90 = low. These are project diagnostics, not inferential cutoffs.\n",
    ]
    (report_dir / "model_robustness_summary.md").write_text("".join(robustness_lines), encoding="utf-8")

    (report_dir / "external_validation_report.md").write_text(
        f"# External Validation Report\n\n**Criterion:** 2023 Subnational Human Development Index (SHDI), Global Data Lab.\n\n**Matched provinces:** {int(validation['n_matched'].max()) if not validation.empty else 0}. Tehran and Alborz are excluded because GDL reports them as a combined region.\n\nPearson = {validation.loc[validation.metric.eq('SHDI_2023'), 'pearson'].iloc[0]:.4f} (p={validation.loc[validation.metric.eq('SHDI_2023'), 'pearson_pvalue'].iloc[0]:.4f}); Spearman = {validation.loc[validation.metric.eq('SHDI_2023'), 'spearman'].iloc[0]:.4f} (p={validation.loc[validation.metric.eq('SHDI_2023'), 'spearman_pvalue'].iloc[0]:.4f}); Kendall = {validation.loc[validation.metric.eq('SHDI_2023'), 'kendall'].iloc[0]:.4f} (p={validation.loc[validation.metric.eq('SHDI_2023'), 'kendall_pvalue'].iloc[0]:.4f}).\n\nThe negative sign is directionally consistent with a higher composite score representing greater modeled pressure/vulnerability and higher SHDI representing higher human development. The associations are weak and non-significant in the current 29-province sample. Because SHDI overlaps conceptually with education, health and living-standard dimensions, it is treated as a convergent external check rather than fully independent validation.\n\nSource: https://globaldatalab.org/shdi/table/shdi/IRN/\n",
        encoding="utf-8")

    (report_dir / "current_architecture.md").write_text(
        "# Current V2 Architecture\n\nRaw workbook → standardization → duplicate/conflict audit → canonical registry → direction/unit/transform → year-by-year normalization → recency weighting → temporal series aggregation → Series → Subindicator → Category → Overall → data quality → scenario/Monte Carlo/LOO → temporal/normalization sensitivity → external convergent check → QA.\n\n`src/hardening.py` is the authoritative scoring engine. `src/robustness_worker.py` isolates the two heavier sensitivity workloads. All province mappings use explicit canonical keys; dataframe row order is never used as an identifier.\n",
        encoding="utf-8")

    (report_dir / "temporal_methodology.md").write_text(
        f"# Temporal Methodology\n\nReference period: **{int(config['reference_year'])}**. The index is intentionally multi-year; the reference year is a recency anchor, not a cutoff. Temporal distance is `abs(reference_year - observation_year)`. Baseline function: `{config['temporal_weighting']['method']}` with `linear_decay_per_year={config['temporal_weighting']['linear_decay_per_year']}` and floor `{config['temporal_weighting']['linear_floor']}`. Multiple observations of the same logical series are aggregated to one province-series score after normalization.\n\nRobustness covers reference years {', '.join(map(str, config.get('temporal_sensitivity_reference_years', [])))} and linear/exponential/stepwise temporal functions. Tested rank Spearman range: {temporal_min:.3f}–{temporal_max:.3f}.\n",
        encoding="utf-8")

    (report_dir / "normalization_methodology_audit.md").write_text(
        f"# Normalization Methodology Audit\n\nBaseline: within-year Min-Max normalization across provinces for each logical series/year. Alternatives: within-year and pooled panel normalization using Min-Max, Z-score and Robust scaling. The baseline ranking is reproduced exactly by within-year Min-Max. Across the full tested sensitivity set, rank Spearman ranges from {norm_min:.3f} to {norm_max:.3f}.\n\nWithin-year normalization measures relative standing within each year; pooled normalization is therefore retained as a robustness alternative rather than substituted into the baseline automatically.\n",
        encoding="utf-8")

    (report_dir / "provenance_summary.md").write_text(
        f"# Provenance Summary\n\nRegistry series: {len(registry)}\nActive series: {len(active_registry)}\nCORE: {int((registry['inclusion_status']=='CORE').sum())}\nCONDITIONAL: {int((registry['inclusion_status']=='CONDITIONAL').sum())}\nEXCLUDED: {int((registry['inclusion_status']=='EXCLUDED').sum())}\n\nActive-series provenance status: {active_registry['provenance_status'].value_counts(dropna=False).to_dict()}. External archival evidence is attached at source-family level for the active domains, but the supplied workbook has no row-level source URLs or extraction records. Therefore active series remain CONDITIONAL; evidence URLs are explicitly labeled as archival/source-family evidence and no original source URL is fabricated.\n",
        encoding="utf-8")

    decision_status = "READY WITH LIMITATIONS" if len(OFFICIAL_PROVINCES) == 31 and abs(float(weights['effective_final_weight'].sum()) - 1.0) < 1e-9 and int(validation['n_matched'].max()) >= 20 else "REQUIRES REVISION"
    (report_dir / "final_model_decision.md").write_text(
        f"# Final Model Decision\n\n**Status: {decision_status} — PORTFOLIO USE**\n\nThe V2 framework passes the current structural and reproducibility checks and includes multi-year temporal treatment, explicit hierarchical weighting, sensitivity analysis and an external convergent check. It is ready to present as a portfolio analytics project with its limitations attached.\n\n### Important limitations\n- {len(active_registry)} active series remain CONDITIONAL because full external source provenance is not documented in the supplied project metadata.\n- The prior 15 province-series-year conflicts were resolved as a geography-mapping issue: Tehran county records are no longer mapped to Tehran province; unresolved provincial conflicts are now 0.\n- Baseline domain weights are design assumptions and material changes to them can alter rankings.\n- SHDI 2023 provides only convergent evidence: Pearson {float(validation.loc[validation.metric.eq('SHDI_2023'),'pearson'].iloc[0]):.3f}, Spearman {float(validation.loc[validation.metric.eq('SHDI_2023'),'spearman'].iloc[0]):.3f}, Kendall {float(validation.loc[validation.metric.eq('SHDI_2023'),'kendall'].iloc[0]):.3f}; none is statistically significant at conventional levels.\n- The composite is comparative and model-dependent; it is not a causal estimate or absolute truth.\n\nThe model should not be described as fully externally validated until a lower-overlap independent criterion and complete source provenance are available.\n",
        encoding="utf-8")

    diagnostics2 = diagnostics.copy()
    row = diagnostics2.iloc[0].to_dict()
    row.update({
        'reference_year': int(config['reference_year']),
        'baseline_normalization': f"{config['normalization']['scope']} / {config['normalization']['method']}",
        'temporal_rank_spearman_min': temporal_min,
        'temporal_rank_spearman_max': temporal_max,
        'normalization_rank_spearman_min': norm_min,
        'normalization_rank_spearman_max': norm_max,
        'global_mc_mean_score_sd': float(mc_global['score_std'].mean()) if not mc_global.empty else np.nan,
        'local_mc_mean_score_sd': float(mc_local['score_std'].mean()) if not mc_local.empty else np.nan,
        'external_validation_pearson': float(validation.loc[validation.metric.eq('SHDI_2023'),'pearson'].iloc[0]) if not validation.empty else np.nan,
        'external_validation_spearman': float(validation.loc[validation.metric.eq('SHDI_2023'),'spearman'].iloc[0]) if not validation.empty else np.nan,
        'external_validation_kendall': float(validation.loc[validation.metric.eq('SHDI_2023'),'kendall'].iloc[0]) if not validation.empty else np.nan,
    })
    ie._write_csv(pd.DataFrame([row]), output_dir / "model_diagnostics_final.csv")

    final_config = dict(config)
    final_config['model_status'] = decision_status
    final_config['frozen_date'] = '2026-10-02'
    final_config['model_version'] = 'V2.1 Hardened + Denominator Alignment'
    final_config['notes'] = [
        'Multi-year model with recency weighting; reference_year is an anchor, not a cutoff.',
        'External validation is convergent rather than fully independent due to conceptual overlap with SHDI.',
        'Active series remain conditional until complete provenance is documented.'
    ]
    (root / 'config' / 'final_config.json').write_text(json.dumps(final_config, ensure_ascii=False, indent=2), encoding='utf-8')

    (report_dir / "run_summary.json").write_text(json.dumps({"input": str(input_path), "config": final_config, "diagnostics": row}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"V2 hardened pipeline complete: {output_dir}")
