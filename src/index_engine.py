from __future__ import annotations

import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


OFFICIAL_PROVINCES = [
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز",
    "ایلام", "بوشهر", "تهران", "چهارمحال و بختیاری", "خراسان جنوبی",
    "خراسان رضوی", "خراسان شمالی", "خوزستان", "زنجان", "سمنان",
    "سیستان و بلوچستان", "فارس", "قزوین", "قم", "کردستان", "کرمان",
    "کرمانشاه", "کهگیلویه و بویراحمد", "گلستان", "گیلان", "لرستان",
    "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد",
]
OFFICIAL_SET = set(OFFICIAL_PROVINCES)
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

PROVINCE_FIXES = {
    "كل كشور": "کل کشور",
    "چهار محال و بختیاری": "چهارمحال و بختیاری",
    "مركزی": "مرکزی",
    "كرمان": "کرمان",
    "كرمانشاه": "کرمانشاه",
    "كهگیلویه و بویراحمد": "کهگیلویه و بویراحمد",
    "کهگیلویه و بویر احمد": "کهگیلویه و بویراحمد",
}
RISK_TERMS = (
    "بیکاری", "ترک تحصیل", "بازماندگی", "فقر", "تورم", "سرقت", "جرم",
    "خشونت", "کودک آزاری", "خودکشی", "اعتیاد", "بی خانمان", "اشتغال ناقص",
    "طلاق", "فلاکت", "خشکسالی", "crime", "inflation", "poverty", "unemployment",
)
PROTECTIVE_TERMS = (
    "ارتقاء تحصیلی", "سواد", "نسبت اشتغال", "مشارکت اقتصادی", "سرانه بودجه",
    "شاخص توسعه", "literacy", "employment ratio", "ظرفیت درمان", "تخت", "درمانگاه",
    "پزشک", "مدرسه", "کلاس", "آب شرب", "فاضلاب", "اینترنت",
)
STRUCTURAL_TERMS = ("population", "جمعیت", "identity", "religion", "household", "خانوار")


def normalize_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = text.replace("\u200c", " ").replace("\u200e", "").replace("\u200f", "")
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def normalize_province(value: object) -> str:
    return PROVINCE_FIXES.get(normalize_text(value), normalize_text(value))


def parse_year(value: object) -> float:
    text = normalize_text(value).translate(PERSIAN_DIGITS)
    match = re.search(r"(?<!\d)(1[34]\d{2})(?!\d)", text)
    return float(match.group(1)) if match else math.nan


def parse_numeric(value: object) -> float:
    text = normalize_text(value).translate(PERSIAN_DIGITS)
    text = text.replace("٬", "").replace(",", "").replace("٪", "").replace("%", "")
    text = text.replace("−", "-").replace("–", "-").strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if not re.fullmatch(r"[-+]?\d*\.?\d+", text):
        return math.nan
    return -float(text) if negative else float(text)


def _column_index(reference: str) -> int:
    index = 0
    for char in re.match(r"([A-Z]+)", reference).group(1):
        index = index * 26 + ord(char) - 64
    return index


def load_first_sheet_records(path: Path) -> pd.DataFrame:
    """Read a simple XLSX without requiring an Excel/Office installation."""
    with zipfile.ZipFile(path) as workbook_zip:
        workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        relations = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        relation_map = {node.attrib["Id"]: node.attrib["Target"] for node in relations}
        sheet = workbook.find("a:sheets/a:sheet", NS)
        if sheet is None:
            raise ValueError("The input workbook has no worksheet.")
        relation_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = relation_map[relation_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        shared: list[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.findall(".//a:t", NS))
                for item in root.findall("a:si", NS)
            ]
        root = ET.fromstring(workbook_zip.read(sheet_path))
        rows: list[dict[int, str]] = []
        for row in root.findall("a:sheetData/a:row", NS):
            parsed: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                value = cell.find("a:v", NS)
                cell_type = cell.attrib.get("t")
                if cell_type == "s" and value is not None:
                    text = shared[int(value.text)]
                elif cell_type == "inlineStr":
                    text = "".join(x.text or "" for x in cell.findall(".//a:t", NS))
                else:
                    text = value.text if value is not None else ""
                parsed[_column_index(cell.attrib["r"])] = text
            rows.append(parsed)
    if not rows:
        return pd.DataFrame()
    headers = {key: normalize_text(value) for key, value in rows[0].items()}
    return pd.DataFrame([
        {header: row.get(key, "") for key, header in headers.items() if header}
        for row in rows[1:]
    ])


def load_raw_input(path: Path) -> pd.DataFrame:
    raw = load_first_sheet_records(path)
    required = ["Indicator", "Province", "Year", "dataset name", "Category", "Value"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Input is missing required columns: {missing}")
    data = raw[required].copy().rename(columns={"dataset name": "dataset_name"})
    for column in ("Indicator", "Province", "dataset_name", "Category", "Value"):
        data[column] = data[column].map(normalize_text)
    data["province"] = data["Province"].map(normalize_province)
    data["year_num"] = data["Year"].map(parse_year)
    data["value_num"] = data["Value"].map(parse_numeric)
    data["series_id"] = data["Indicator"] + " || " + data["dataset_name"].replace("", "بدون زیرشاخص")
    data["series_text"] = (data["Indicator"] + " " + data["dataset_name"]).str.strip()
    data["geo_level"] = np.where(
        data["province"].isin(OFFICIAL_SET),
        "province",
        np.where(data["province"] == "کل کشور", "national", "other"),
    )
    data["raw_row_id"] = np.arange(1, len(data) + 1)
    return data


def infer_unit(series_text: str) -> str:
    text = normalize_text(series_text).lower()
    if any(term in text for term in ("درصد", "%", "percent")):
        return "percent"
    if any(term in text for term in ("نرخ", "ratio", "rate", "به ازای")):
        return "rate"
    if any(term in text for term in ("شاخص", "index", "ضریب")):
        return "index"
    if any(term in text for term in ("سرانه", "per capita", "percapita")):
        return "per_capita"
    return "count"


def infer_direction(series_text: str) -> str:
    text = normalize_text(series_text).lower()
    risk = any(term in text for term in RISK_TERMS)
    protective = any(term in text for term in PROTECTIVE_TERMS)
    if risk and not protective:
        return "higher_worse"
    if protective and not risk:
        return "higher_better"
    return "unknown"


def is_structural(series_text: str) -> bool:
    text = normalize_text(series_text).lower()
    return any(term in text for term in STRUCTURAL_TERMS)


def temporal_weight(age: float, settings: dict[str, Any], method: str | None = None) -> float:
    method = method or settings["method"]
    if age < 0:
        return 0.0
    if method == "linear":
        return max(float(settings["linear_floor"]), 1.0 - float(settings["linear_decay_per_year"]) * age)
    if method == "exponential":
        return math.exp(-float(settings["exponential_lambda"]) * age)
    if method == "stepwise":
        steps = sorted((float(key), float(value)) for key, value in settings["step_weights"].items())
        return [value for cutoff, value in steps if age <= cutoff][0] if any(age <= cutoff for cutoff, _ in steps) else steps[-1][1]
    raise ValueError(f"Unsupported temporal weighting method: {method}")


def derive_registry(data: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    provincial = data[(data["geo_level"] == "province") & data["year_num"].notna() & data["value_num"].notna()].copy()
    coverage = provincial.groupby("series_id")["province"].nunique().rename("provincial_coverage")
    missing = provincial.assign(is_missing=provincial["value_num"].isna()).groupby("series_id")["is_missing"].mean().rename("missing_ratio")
    summary = data.groupby("series_id", as_index=False).agg(
        indicator=("Indicator", "first"), dataset_name=("dataset_name", "first"),
        category=("Category", "first"), series_text=("series_text", "first"),
        observation_year_min=("year_num", "min"), observation_year_max=("year_num", "max"),
        raw_observation_count=("raw_row_id", "count"),
    )
    registry = summary.merge(coverage, on="series_id", how="left").merge(missing, on="series_id", how="left")
    registry["provincial_coverage"] = registry["provincial_coverage"].fillna(0).astype(int)
    registry["missing_ratio"] = registry["missing_ratio"].fillna(1.0)
    registry["unit_type"] = registry["series_text"].map(infer_unit)
    registry["direction"] = registry["series_text"].map(infer_direction)
    registry["transform"] = np.where(registry["unit_type"].eq("count"), "per_100k_population", "none")
    registry.loc[registry["unit_type"].eq("per_capita"), "transform"] = "none"
    registry["subindicator"] = registry["indicator"].where(registry["indicator"].ne(""), registry["dataset_name"])
    registry["reference_year"] = int(config["reference_year"])
    registry["reference_period"] = f"≤ {config['reference_year']}"
    registry["temporal_gap"] = (registry["reference_year"] - registry["observation_year_max"]).clip(lower=0)
    registry["temporal_quality"] = registry["temporal_gap"].map(lambda age: temporal_weight(age, config["temporal_weighting"]))
    registry["imputed_ratio"] = 0.0
    registry["source"] = ""
    registry["source_url"] = ""
    registry["source_quality"] = "unknown"
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
    registry.loc[ambiguous, ["inclusion_status", "exclusion_reason"]] = ["EXCLUDED", "direction cannot be justified from the available project metadata"]
    registry["category_weight"] = registry["category"].map(config["aggregation"]["category_weights"])
    registry["subindicator_weight"] = np.nan
    registry["series_weight"] = np.nan
    registry["review_status"] = "pending_source_and_concept_review"
    registry["review_notes"] = (
        "Generated from observed raw data. Source provenance and semantic direction need review before CORE status."
    )
    return registry.sort_values(["category", "subindicator", "series_id"]).reset_index(drop=True)


def _population_lookup(data: pd.DataFrame) -> pd.DataFrame:
    candidates = data[(data["geo_level"] == "province") & data["value_num"].notna() & data["year_num"].notna()].copy()
    text = candidates["series_text"].str.lower()
    candidates = candidates[text.str.contains("totalpopulation|جمعیت کل", regex=True, na=False)].copy()
    if candidates.empty:
        return pd.DataFrame(columns=["province", "year_num", "population"])
    candidates["priority"] = np.where(candidates["series_id"].str.contains("TotalPopulation", na=False), 0, 1)
    return (candidates.sort_values(["province", "year_num", "priority"])
            .groupby(["province", "year_num"], as_index=False).first()
            [["province", "year_num", "value_num"]].rename(columns={"value_num": "population"}))


def transform_observations(data: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    reg = registry[["series_id", "inclusion_status", "direction", "transform", "category", "subindicator"]]
    out = data[(data["geo_level"] == "province") & data["year_num"].notna() & data["value_num"].notna()].merge(reg, on="series_id", how="inner")
    out = out[out["inclusion_status"].isin(["CORE", "CONDITIONAL"])].copy()
    out["value_transformed"] = out["value_num"].astype(float)
    out["transform_applied"] = "none"
    out["denominator_year"] = np.nan
    population = _population_lookup(data)
    if not population.empty:
        lookup = {(row.province, float(row.year_num)): float(row.population) for row in population.itertuples(index=False)}
        def population_for(row: pd.Series) -> tuple[float, float]:
            exact = lookup.get((row["province"], float(row["year_num"])))
            if exact is not None:
                return exact, float(row["year_num"])
            options = [(abs(float(year) - float(row["year_num"])), year, value)
                       for (province, year), value in lookup.items() if province == row["province"]]
            if not options:
                return math.nan, math.nan
            distance, year, value = min(options)
            return (value, year) if distance <= 2 else (math.nan, math.nan)
        count_mask = out["transform"].eq("per_100k_population")
        values = out.loc[count_mask].apply(population_for, axis=1, result_type="expand")
        if not values.empty:
            out.loc[count_mask, "population"] = values.iloc[:, 0].to_numpy()
            out.loc[count_mask, "denominator_year"] = values.iloc[:, 1].to_numpy()
            valid = count_mask & out["population"].gt(0)
            out.loc[valid, "value_transformed"] = out.loc[valid, "value_num"] / out.loc[valid, "population"] * 100000.0
            out.loc[valid, "transform_applied"] = "per_100k_population"
            out.loc[count_mask & ~valid, "value_transformed"] = np.nan
            out.loc[count_mask & ~valid, "transform_applied"] = "missing_population_denominator"
    else:
        count_mask = out["transform"].eq("per_100k_population")
        out.loc[count_mask, "value_transformed"] = np.nan
        out.loc[count_mask, "transform_applied"] = "missing_population_denominator"
    return out


def normalize_observations(observations: pd.DataFrame, method: str, scope: str) -> pd.DataFrame:
    if observations.empty:
        return observations.assign(normalized_score=pd.Series(dtype=float))
    out = observations.dropna(subset=["value_transformed"]).copy()
    group_columns = ["series_id", "year_num"] if scope == "within_year" else ["series_id"]
    normalized: list[pd.DataFrame] = []
    for _, group in out.groupby(group_columns, sort=False):
        values = group["value_transformed"].astype(float)
        if values.nunique() < 2:
            continue
        if method == "minmax":
            score = (values - values.min()) / (values.max() - values.min()) * 100.0
        elif method == "zscore":
            deviation = values.std(ddof=0)
            if np.isclose(deviation, 0):
                continue
            score = (50.0 + 10.0 * (values - values.mean()) / deviation).clip(0, 100)
        elif method == "robust":
            median = values.median()
            mad = (values - median).abs().median()
            if np.isclose(mad, 0):
                continue
            score = (50.0 + 10.0 * (values - median) / (1.4826 * mad)).clip(0, 100)
        else:
            raise ValueError(f"Unsupported normalization method: {method}")
        scored = group.copy()
        scored["normalized_score"] = np.where(scored["direction"].eq("higher_worse"), score, 100.0 - score)
        normalized.append(scored)
    return pd.concat(normalized, ignore_index=True) if normalized else out.iloc[0:0].assign(normalized_score=pd.Series(dtype=float))


def aggregate_temporally(normalized: pd.DataFrame, config: dict[str, Any], method: str | None = None, reference_year: int | None = None) -> pd.DataFrame:
    reference_year = int(reference_year or config["reference_year"])
    usable = normalized[normalized["year_num"] <= reference_year].copy()
    usable["temporal_gap"] = reference_year - usable["year_num"]
    usable["recency_weight"] = usable["temporal_gap"].map(lambda age: temporal_weight(float(age), config["temporal_weighting"], method))
    rows: list[dict[str, Any]] = []
    for (province, series_id), group in usable.groupby(["province", "series_id"], sort=False):
        weights = group["recency_weight"].to_numpy(dtype=float)
        scores = group["normalized_score"].to_numpy(dtype=float)
        rows.append({
            "province": province, "series_id": series_id,
            "series_score": float(np.average(scores, weights=weights)),
            "observation_count": int(len(group)),
            "first_observation_year": float(group["year_num"].min()),
            "last_observation_year": float(group["year_num"].max()),
            "recency_weight_sum": float(weights.sum()),
            "temporal_quality": float(weights.mean()),
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
    return active


def aggregate_index(series_scores: pd.DataFrame, weights: pd.DataFrame, category_weights: dict[str, float], min_categories: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
        indicator_count_used=("series_id", "nunique"), temporal_quality=("temporal_quality", "mean"),
        latest_observation_year=("last_observation_year", "max"),
    ).reset_index()
    quality = pd.DataFrame({"province": OFFICIAL_PROVINCES}).merge(observed, on="province", how="left")
    quality["indicator_count_used"] = quality["indicator_count_used"].fillna(0).astype(int)
    quality["missing_ratio"] = 1.0 - quality["indicator_count_used"] / expected if expected else np.nan
    quality["imputed_ratio"] = 0.0
    quality["temporal_quality"] = quality["temporal_quality"].fillna(0.0)
    quality["source_quality_status"] = "unknown_for_all_included_series"
    quality["data_quality_score"] = 100.0 * (0.60 * (1.0 - quality["missing_ratio"]) + 0.40 * quality["temporal_quality"])
    quality["data_quality_score_scope"] = "coverage and temporal freshness only; source provenance is unknown"
    quality["uncertainty_level"] = np.select(
        [quality["missing_ratio"] > 0.20, quality["temporal_quality"] < 0.65, quality["missing_ratio"] > 0.05],
        ["high", "high", "medium"], default="low",
    )
    quality["overall_confidence"] = "provisional: conditional series lack documented source provenance"
    return quality.merge(overall[["province", "overall_score", "rank"]], on="province", how="left")


def _scenario_weights(category_weights: dict[str, float]) -> dict[str, dict[str, float]]:
    categories = list(category_weights)
    scenarios = {"baseline": category_weights, "equal_weight": {category: 1 / len(categories) for category in categories}}
    for focus in categories:
        residual = 0.5 / (len(categories) - 1)
        scenarios[f"{focus}_emphasis"] = {category: (0.5 if category == focus else residual) for category in categories}
    return scenarios


def calculate_scenarios(category_scores: pd.DataFrame, baseline: pd.DataFrame, category_weights: dict[str, float], min_categories: int) -> pd.DataFrame:
    output: list[pd.DataFrame] = []
    base = baseline[["province", "overall_score", "rank"]].rename(columns={"overall_score": "baseline_score", "rank": "baseline_rank"})
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


def monte_carlo(series_scores: pd.DataFrame, weights: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    iterations = int(config["simulation_iterations"])
    rng = np.random.default_rng(int(config["random_seed"]))
    hierarchy = weights[["category", "subindicator", "series_id"]].drop_duplicates()
    categories = sorted(hierarchy["category"].unique())
    scores = series_scores[["province", "series_id", "series_score"]].merge(hierarchy, on="series_id", how="inner")
    results: list[pd.DataFrame] = []
    for iteration in range(iterations):
        category_draw = dict(zip(categories, rng.dirichlet(np.ones(len(categories)))))
        records: list[tuple[str, float]] = []
        for category, cat_group in hierarchy.groupby("category"):
            subindicators = sorted(cat_group["subindicator"].unique())
            sub_draw = dict(zip(subindicators, rng.dirichlet(np.ones(len(subindicators)))))
            for subindicator, sub_group in cat_group.groupby("subindicator"):
                series = sorted(sub_group["series_id"].unique())
                draws = rng.dirichlet(np.ones(len(series)))
                records.extend((series_id, category_draw[category] * sub_draw[subindicator] * draw) for series_id, draw in zip(series, draws))
        draw_frame = pd.DataFrame(records, columns=["series_id", "simulation_weight"])
        trial = scores.merge(draw_frame, on="series_id", how="inner")
        trial = (trial.assign(weighted=trial["series_score"] * trial["simulation_weight"])
                 .groupby("province", as_index=False).agg(weighted_sum=("weighted", "sum"), available_weight=("simulation_weight", "sum")))
        trial["score"] = trial["weighted_sum"] / trial["available_weight"]
        trial["rank"] = trial["score"].rank(ascending=False, method="min")
        trial["iteration"] = iteration
        results.append(trial[["iteration", "province", "score", "rank"]])
    draws = pd.concat(results, ignore_index=True)
    return (draws.groupby("province", as_index=False).agg(
        median_score=("score", "median"), score_std=("score", "std"), median_rank=("rank", "median"),
        rank_p05=("rank", lambda value: value.quantile(0.05)), rank_p95=("rank", lambda value: value.quantile(0.95)),
        probability_top_5=("rank", lambda value: (value <= 5).mean()), probability_top_10=("rank", lambda value: (value <= 10).mean()),
    ))


def leave_one_out(series_scores: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = baseline[["province", "overall_score", "rank"]].rename(columns={"overall_score": "baseline_score", "rank": "baseline_rank"})
    series_rows: list[pd.DataFrame] = []
    domain_rows: list[pd.DataFrame] = []
    available = set(series_scores["series_id"])
    category_weights = config["aggregation"]["category_weights"]
    for series_id in sorted(available):
        subset = series_scores[series_scores["series_id"] != series_id]
        weights = build_effective_weights(registry, set(subset["series_id"]), category_weights)
        overall, _, _ = aggregate_index(subset, weights, category_weights, int(config["minimum_categories_for_overall"]))
        comparison = overall.merge(base, on="province", how="left")
        comparison["removed_series_id"] = series_id
        comparison["score_delta"] = comparison["overall_score"] - comparison["baseline_score"]
        comparison["rank_delta"] = comparison["baseline_rank"] - comparison["rank"]
        series_rows.append(comparison[["removed_series_id", "province", "overall_score", "rank", "score_delta", "rank_delta"]])
    for category in category_weights:
        subset_weights = {key: value for key, value in category_weights.items() if key != category}
        total = sum(subset_weights.values())
        subset_weights = {key: value / total for key, value in subset_weights.items()}
        subset = series_scores[series_scores["series_id"].isin(set(registry.loc[registry["category"] != category, "series_id"]))]
        weights = build_effective_weights(registry[registry["category"] != category], set(subset["series_id"]), subset_weights)
        overall, _, _ = aggregate_index(subset, weights, subset_weights, max(1, int(config["minimum_categories_for_overall"]) - 1))
        comparison = overall.merge(base, on="province", how="left")
        comparison["removed_category"] = category
        comparison["score_delta"] = comparison["overall_score"] - comparison["baseline_score"]
        comparison["rank_delta"] = comparison["baseline_rank"] - comparison["rank"]
        domain_rows.append(comparison[["removed_category", "province", "overall_score", "rank", "score_delta", "rank_delta"]])
    return pd.concat(series_rows, ignore_index=True), pd.concat(domain_rows, ignore_index=True)


def redundancy_audit(series_scores: pd.DataFrame, weights: pd.DataFrame, threshold: float) -> pd.DataFrame:
    categories = weights[["series_id", "category", "subindicator"]].drop_duplicates()
    joined = series_scores.merge(categories, on="series_id", how="inner")
    rows: list[dict[str, Any]] = []
    for category, group in joined.groupby("category"):
        wide = group.pivot(index="province", columns="series_id", values="series_score")
        corr = wide.corr(method="pearson", min_periods=3)
        series_ids = list(corr.columns)
        sub_map = categories.set_index("series_id")["subindicator"].to_dict()
        for left_pos, left in enumerate(series_ids):
            for right in series_ids[left_pos + 1:]:
                value = corr.loc[left, right]
                overlap = sub_map.get(left) == sub_map.get(right)
                potential = bool(pd.notna(value) and abs(float(value)) >= threshold)
                rows.append({
                    "category": category, "indicator_a": left, "indicator_b": right, "correlation": value,
                    "same_concept_flag": overlap, "potential_double_counting": potential,
                    "recommended_action": "manual conceptual review" if potential else "no automatic removal",
                    "rationale": "High correlation is a review signal, not an exclusion rule." if potential else "No automatic action from correlation alone.",
                })
    return pd.DataFrame(rows)


def temporal_sensitivity(normalized: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame) -> pd.DataFrame:
    baseline_rank = baseline[["province", "rank"]].rename(columns={"rank": "baseline_rank"})
    rows: list[dict[str, Any]] = []
    methods = [config["temporal_weighting"]["method"]] + list(config["temporal_weighting"].get("alternatives", []))
    for reference_year in config["temporal_sensitivity_reference_years"]:
        for method in dict.fromkeys(methods):
            series = aggregate_temporally(normalized, config, method=method, reference_year=int(reference_year))
            weights = build_effective_weights(registry, set(series["series_id"]), config["aggregation"]["category_weights"])
            overall, _, _ = aggregate_index(series, weights, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
            merged = overall.merge(baseline_rank, on="province", how="inner")
            correlation = merged["rank"].corr(merged["baseline_rank"], method="spearman") if len(merged) >= 3 else np.nan
            rows.append({"reference_year": reference_year, "temporal_method": method, "province_count": len(merged), "rank_correlation_with_baseline": correlation})
    return pd.DataFrame(rows)


def normalization_sensitivity(transformed: pd.DataFrame, registry: pd.DataFrame, config: dict[str, Any], baseline: pd.DataFrame) -> pd.DataFrame:
    baseline_rank = baseline[["province", "rank"]].rename(columns={"rank": "baseline_rank"})
    methods = [config["normalization"]["method"]] + list(config["normalization"].get("alternatives", []))
    rows: list[dict[str, Any]] = []
    for method in dict.fromkeys(methods):
        normalized = normalize_observations(transformed, method, config["normalization"]["scope"])
        series = aggregate_temporally(normalized, config)
        weights = build_effective_weights(registry, set(series["series_id"]), config["aggregation"]["category_weights"])
        overall, _, _ = aggregate_index(series, weights, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
        merged = overall.merge(baseline_rank, on="province", how="inner")
        correlation = merged["rank"].corr(merged["baseline_rank"], method="spearman") if len(merged) >= 3 else np.nan
        rows.append({"normalization_method": method, "scope": config["normalization"]["scope"], "province_count": len(merged), "rank_correlation_with_baseline": correlation})
    return pd.DataFrame(rows)


def external_validation(overall: pd.DataFrame, input_dir: Path) -> pd.DataFrame:
    path = input_dir / "external_validation.csv"
    columns = ["metric", "n_matched", "pearson", "spearman", "kendall", "status", "limitation"]
    if not path.exists():
        return pd.DataFrame([{"metric": "", "n_matched": 0, "pearson": np.nan, "spearman": np.nan, "kendall": np.nan, "status": "unavailable", "limitation": "No external validation file found."}], columns=columns)
    validation = pd.read_csv(path, encoding="utf-8-sig")
    required = {"province", "metric", "value"}
    if not required.issubset(validation.columns):
        return pd.DataFrame([{"metric": "", "n_matched": 0, "pearson": np.nan, "spearman": np.nan, "kendall": np.nan, "status": "unavailable", "limitation": "Validation file lacks required columns."}], columns=columns)
    validation["province"] = validation["province"].map(normalize_province)
    rows: list[dict[str, Any]] = []
    for metric, group in validation.groupby("metric"):
        merged = overall[["province", "overall_score"]].merge(group[["province", "value"]], on="province", how="inner").dropna()
        if len(merged) < 3:
            rows.append({"metric": metric, "n_matched": len(merged), "pearson": np.nan, "spearman": np.nan, "kendall": np.nan, "status": "insufficient_or_unmatched", "limitation": "At least three correctly matched provinces are required; current identifiers do not provide them."})
        else:
            rows.append({"metric": metric, "n_matched": len(merged), "pearson": merged["overall_score"].corr(merged["value"], method="pearson"), "spearman": merged["overall_score"].corr(merged["value"], method="spearman"), "kendall": merged["overall_score"].corr(merged["value"], method="kendall"), "status": "association_only", "limitation": "Association is not causal validation; leakage must be reviewed manually."})
    return pd.DataFrame(rows, columns=columns)


def validation_leakage_check(registry: pd.DataFrame, input_dir: Path) -> pd.DataFrame:
    path = input_dir / "external_validation.csv"
    if not path.exists():
        return pd.DataFrame([{"metric": "", "included_series_matches": 0, "leakage_status": "not_assessed", "note": "No validation file was available."}])
    validation = pd.read_csv(path, encoding="utf-8-sig")
    aliases = {"poverty": ("poverty", "فقر"), "unemployment": ("unemployment", "بیکاری"), "inflation": ("inflation", "تورم")}
    active = registry[registry["inclusion_status"].isin(["CORE", "CONDITIONAL"])].copy()
    rows: list[dict[str, Any]] = []
    for metric in validation.get("metric", pd.Series(dtype=str)).dropna().unique():
        metric_text = normalize_text(metric).lower()
        terms = next((terms for token, terms in aliases.items() if token in metric_text), (metric_text,))
        matched = active[active["series_text"].str.lower().map(lambda text: any(term in text for term in terms))]
        rows.append({"metric": metric, "included_series_matches": len(matched), "leakage_status": "possible_conceptual_overlap" if len(matched) else "no_name_based_overlap_found", "note": "Name-based screening only; source lineage is unavailable, so independence cannot be confirmed."})
    return pd.DataFrame(rows)


def data_dictionary() -> pd.DataFrame:
    records = [
        ("overall_score", "Composite provincial score after hierarchical aggregation.", "0-100 approximate scale", "V2 scoring engine", "Temporal aggregation and weighted hierarchy", "Comparative index; not an absolute risk or causal measure."),
        ("series_score", "Temporally aggregated normalized series score.", "0-100", "Raw workbook", "Within-year normalization, direction adjustment, recency weighting", "Higher means greater contribution to the configured composite score."),
        ("temporal_quality", "Mean recency weight of observations used for a province-series.", "0-1", "V2 scoring engine", "Configured temporal function", "Freshness diagnostic, not a source-quality judgment."),
        ("missing_ratio", "Share of expected included series absent for a province.", "0-1", "V2 scoring engine", "No imputation in baseline", "Higher values increase uncertainty."),
        ("data_quality_score", "Quality score based on observed coverage and temporal freshness.", "0-100", "V2 scoring engine", "60% coverage and 40% temporal quality", "Does not assert source quality; provenance remains unknown."),
        ("inclusion_status", "Registry decision status for a series.", "category", "V2 registry", "Audit and review workflow", "CONDITIONAL series require documented review before promotion to CORE."),
    ]
    return pd.DataFrame(records, columns=["field_name", "definition", "unit", "source", "transformation", "interpretation"])


def missingness_profiles(raw: pd.DataFrame, series_scores: pd.DataFrame, weights: pd.DataFrame, quality: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    series = weights[["series_id", "category"]].drop_duplicates().merge(
        series_scores.groupby("series_id")["province"].nunique().rename("observed_provinces"), on="series_id", how="left"
    )
    series["observed_provinces"] = series["observed_provinces"].fillna(0).astype(int)
    series["missing_ratio"] = 1.0 - series["observed_provinces"] / len(OFFICIAL_PROVINCES)
    category = series.groupby("category", as_index=False).agg(series_count=("series_id", "nunique"), mean_missing_ratio=("missing_ratio", "mean"))
    year = raw[raw["geo_level"].eq("province")].groupby("year_num", dropna=False, as_index=False).agg(
        raw_rows=("raw_row_id", "count"), invalid_numeric_rows=("value_num", lambda value: int(value.isna().sum())), province_count=("province", "nunique")
    )
    return series, quality[["province", "indicator_count_used", "missing_ratio"]].copy(), category, year


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def run_pipeline(input_path: Path, output_dir: Path, config: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir.parent / "data"
    registry_dir = output_dir.parent / "registry"
    report_dir = output_dir.parent / "reports"
    for directory in (data_dir, registry_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw = load_raw_input(input_path)
    registry = derive_registry(raw, config)
    transformed = transform_observations(raw, registry)
    normalized = normalize_observations(transformed, config["normalization"]["method"], config["normalization"]["scope"])
    series_scores = aggregate_temporally(normalized, config)
    weights = build_effective_weights(registry, set(series_scores["series_id"]), config["aggregation"]["category_weights"])
    overall, category, subindicator = aggregate_index(series_scores, weights, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
    quality = province_quality(series_scores, weights, overall)
    final = quality.merge(overall[["province", "overall_score", "rank"]], on="province", how="left", suffixes=("", "_duplicate"))
    final = final.drop(columns=[column for column in final.columns if column.endswith("_duplicate")])
    scenarios = calculate_scenarios(category, overall, config["aggregation"]["category_weights"], int(config["minimum_categories_for_overall"]))
    simulations = monte_carlo(series_scores, weights, config)
    loo_series, loo_domain = leave_one_out(series_scores, registry, config, overall)
    redundancy = redundancy_audit(series_scores, weights, float(config["redundancy_correlation_threshold"]))
    temporal = temporal_sensitivity(normalized, registry, config, overall)
    normalization = normalization_sensitivity(transformed, registry, config, overall)
    validation = external_validation(overall, input_path.parent)
    leakage = validation_leakage_check(registry, input_path.parent)
    registry = registry.merge(weights[["series_id", "subindicator_weight", "series_weight", "effective_final_weight"]], on="series_id", how="left", suffixes=("", "_effective"))
    for column in ("subindicator_weight", "series_weight"):
        effective = f"{column}_effective"
        if effective in registry:
            registry[column] = registry[effective].combine_first(registry[column])
            registry = registry.drop(columns=[effective])
    diagnostics = pd.DataFrame([{
        "raw_rows": len(raw), "official_provinces_in_raw": raw.loc[raw["geo_level"].eq("province"), "province"].nunique(),
        "raw_series": raw["series_id"].nunique(), "registry_series": len(registry),
        "included_series": weights["series_id"].nunique(), "conditional_series": int((registry["inclusion_status"] == "CONDITIONAL").sum()),
        "excluded_series": int((registry["inclusion_status"] == "EXCLUDED").sum()),
        "categories": weights["category"].nunique(), "subindicators": weights[["category", "subindicator"]].drop_duplicates().shape[0],
        "duplicate_raw_rows": int(raw.duplicated(["Indicator", "Province", "Year", "dataset_name", "Category", "Value"]).sum()),
        "invalid_year_rows": int(raw["year_num"].isna().sum()), "invalid_value_rows": int(raw["value_num"].isna().sum()),
        "external_validation_status": "; ".join(validation["status"].astype(str).unique()),
    }])
    mapping = raw[["Province", "province", "geo_level"]].drop_duplicates().sort_values(["geo_level", "province", "Province"])
    missing_indicator, missing_province, missing_category, missing_year = missingness_profiles(raw, series_scores, weights, quality)
    series_contributions = series_scores.merge(weights[["series_id", "category", "subindicator", "effective_final_weight"]], on="series_id", how="inner")
    series_contributions["weighted_series_contribution"] = series_contributions["series_score"] * series_contributions["effective_final_weight"]
    category_contributions = category.copy()
    category_contributions["weighted_category_contribution"] = category_contributions["category_score"] * category_contributions["category_weight"]
    _write_csv(raw, data_dir / "raw_observations_standardized.csv")
    _write_csv(transformed, data_dir / "transformed_observations.csv")
    _write_csv(normalized, data_dir / "normalized_observations.csv")
    _write_csv(series_scores, output_dir / "series_scores.csv")
    _write_csv(weights, registry_dir / "effective_weights.csv")
    _write_csv(registry, registry_dir / "indicator_registry_final.csv")
    _write_csv(registry, registry_dir / "indicator_review.csv")
    _write_csv(mapping, registry_dir / "province_mapping.csv")
    _write_csv(subindicator, output_dir / "subindicator_scores.csv")
    _write_csv(category, output_dir / "category_scores.csv")
    _write_csv(category_contributions, output_dir / "province_category_contributions.csv")
    _write_csv(series_contributions, output_dir / "province_series_contributions.csv")
    _write_csv(final.sort_values("rank"), output_dir / "provincial_composite_index.csv")
    _write_csv(quality, output_dir / "province_data_quality.csv")
    _write_csv(scenarios, output_dir / "scenario_sensitivity.csv")
    _write_csv(simulations, output_dir / "monte_carlo_weight_sensitivity.csv")
    _write_csv(loo_series, output_dir / "sensitivity_indicator_loo.csv")
    _write_csv(loo_domain, output_dir / "sensitivity_domain_loo.csv")
    _write_csv(redundancy, output_dir / "redundancy_audit.csv")
    _write_csv(temporal, output_dir / "temporal_sensitivity.csv")
    _write_csv(normalization, output_dir / "normalization_sensitivity.csv")
    _write_csv(validation, output_dir / "external_validation_results.csv")
    _write_csv(leakage, output_dir / "validation_leakage_check.csv")
    _write_csv(missing_indicator, output_dir / "missingness_by_indicator.csv")
    _write_csv(missing_province, output_dir / "missingness_by_province.csv")
    _write_csv(missing_category, output_dir / "missingness_by_category.csv")
    _write_csv(missing_year, output_dir / "missingness_by_year.csv")
    _write_csv(diagnostics, output_dir / "model_diagnostics.csv")
    _write_csv(data_dictionary(), report_dir / "data_dictionary.csv")
    (report_dir / "run_summary.json").write_text(json.dumps({"input": str(input_path), "config": config, "diagnostics": diagnostics.iloc[0].to_dict()}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"V2 complete: {output_dir}")
