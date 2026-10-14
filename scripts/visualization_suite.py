"""
Iran Provincial Index — Complete Visualization Suite
Final-model version: keeps the visual details of the supplied v2 polished code.

Creates:
    01_ranking.png
    02_category_heatmap.png
    03_map.png
    04_radar.png
    05_monte_carlo_stability.png

Requirements:
    pip install matplotlib pandas numpy geopandas requests arabic_reshaper python-bidi

Default paths are configured for the user's Windows project layout, but can be
overridden with environment variables:
    INDEX_BASE
    INDEX_SAVE_DIR
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import MaxNLocator

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise ImportError(
        "Persian text support is required. Install with: "
        "pip install arabic_reshaper python-bidi"
    ) from exc


# ============================================================
# Base settings
# ============================================================
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / "outputs"
DEFAULT_SAVE_DIR = REPO_ROOT / "visuals"

BASE = Path(os.environ.get("INDEX_BASE", str(DEFAULT_BASE)))
SAVE_DIR = Path(os.environ.get("INDEX_SAVE_DIR", str(DEFAULT_SAVE_DIR)))
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Font
# ------------------------------------------------------------
PREFERRED_FONTS = ["IRANSans", "B Nazanin", "Vazirmatn", "Tahoma", "Arial"]
available_fonts = {f.name for f in fm.fontManager.ttflist}
chosen_font = next((f for f in PREFERRED_FONTS if f in available_fonts), "DejaVu Sans")
plt.rcParams["font.family"] = chosen_font
print(f"🔤 فونت انتخاب‌شده: {chosen_font}")

# ------------------------------------------------------------
# Visual identity — intentionally preserved from supplied code
# ------------------------------------------------------------
BG = "#faf7f2"
TEXT_DARK = "#2b2320"
TEXT_MUTED = "#8a8278"

CUSTOM_CMAP = LinearSegmentedColormap.from_list(
    "risk_cmap",
    ["#fdf4e3", "#f6c667", "#e8743b", "#c0392b", "#5e0d20"],
)

MAP_GEOJSON_URLS = [
    "https://raw.githubusercontent.com/mrunderline/iran-geojson/master/iran_geo.json",
    "https://raw.githubusercontent.com/hosseinhabibi2004/iran-geojson/refs/heads/master/data/provinces/provinces.min.geojson",
]



# ============================================================
# Helpers
# ============================================================
def fa(text: object) -> str:
    """نمایش درست متن فارسی/عربی (راست‌به‌چپ) در matplotlib."""
    return get_display(arabic_reshaper.reshape(str(text)))


def _require_file(filename: str) -> Path:
    path = BASE / filename
    if not path.exists():
        raise FileNotFoundError(
            f"فایل موردنیاز پیدا نشد: {path}\n"
            f"BASE فعلی: {BASE}\n"
            "مسیر INDEX_BASE را بررسی کنید."
        )
    return path


def _save(fig: plt.Figure, filename: str, dpi: int = 320) -> Path:
    out = SAVE_DIR / filename
    fig.savefig(out, dpi=dpi, bbox_inches="tight", facecolor=BG)
    print("✅ ذخیره شد:", out)
    return out


def normalize_name(p: object) -> str:
    """Standardize Persian/English province names for GeoJSON joins."""
    if pd.isna(p):
        return ""
    p = str(p).strip()
    p = (p.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
           .replace("ۀ", "ه").replace("‌", " "))
    p = " ".join(p.replace("-", " ").replace("_", " ").split())
    aliases = {
        "چهار محال و بختیاری": "چهارمحال و بختیاری",
        "كهگیلویه و بویراحمد": "کهگیلویه و بویراحمد",
        "کهگیلویه و بویر احمد": "کهگیلویه و بویراحمد",
        "البرز": "البرز", "Alborz": "البرز", "Alborz Province": "البرز",
        "تهران": "تهران", "Tehran": "تهران", "Tehran Province": "تهران",
        "East Azerbaijan": "آذربایجان شرقی", "East Azarbaijan": "آذربایجان شرقی",
        "West Azerbaijan": "آذربایجان غربی", "West Azarbaijan": "آذربایجان غربی",
        "Razavi Khorasan": "خراسان رضوی", "Khorasan Razavi": "خراسان رضوی",
        "North Khorasan": "خراسان شمالی", "South Khorasan": "خراسان جنوبی",
        "Kohgiluyeh and Boyer-Ahmad": "کهگیلویه و بویراحمد",
        "Kohgiluyeh and Boyer Ahmad": "کهگیلویه و بویراحمد",
        "Chaharmahal and Bakhtiari": "چهارمحال و بختیاری",
        "Chaharmahal and Bakhtiyari": "چهارمحال و بختیاری",
        "Sistan and Baluchestan": "سیستان و بلوچستان",
        "Sistan and Balochestan": "سیستان و بلوچستان",
        "Qom": "قم", "Ghom": "قم", "Qazvin": "قزوین", "Ghazvin": "قزوین",
        "Ardabil": "اردبیل", "Ardebil": "اردبیل", "Bushehr": "بوشهر", "Boushehr": "بوشهر",
        "Ilam": "ایلام", "Lorestan": "لرستان", "Kurdistan": "کردستان",
        "Kermanshah": "کرمانشاه", "Khuzestan": "خوزستان", "Isfahan": "اصفهان",
        "Fars": "فارس", "Kerman": "کرمان", "Yazd": "یزد", "Semnan": "سمنان",
        "Zanjan": "زنجان", "Hormozgan": "هرمزگان", "Gilan": "گیلان",
        "Mazandaran": "مازندران", "Golestan": "گلستان", "Markazi": "مرکزی",
        "Hamadan": "همدان", "Central": "مرکزی",
    }
    if p in aliases:
        return aliases[p]
    pl = p.lower()
    if pl.endswith(" province"):
        pl = pl[:-9].strip()
    for k, v in aliases.items():
        if str(k).lower() == pl:
            return v
    if p.startswith("استان "):
        p = p[6:].strip()
    return p


def load_composite() -> pd.DataFrame:
    df = pd.read_csv(_require_file("provincial_composite_index.csv"))
    required = {"province", "overall_score", "rank"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"ستون‌های لازم در provincial_composite_index.csv نیستند: {sorted(missing)}")
    return df.copy()


def load_categories() -> pd.DataFrame:
    df = pd.read_csv(_require_file("category_scores.csv"))
    required = {"province", "category", "category_score"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"ستون‌های لازم در category_scores.csv نیستند: {sorted(missing)}")
    return df.copy()


# ============================================================
# 1) Final provincial ranking
# ============================================================
def plot_ranking() -> Path:
    df = load_composite().sort_values("overall_score", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10.5, 13), facecolor=BG)
    ax.set_facecolor(BG)

    score_min = float(df["overall_score"].min())
    score_max = float(df["overall_score"].max())
    denom = max(score_max - score_min, 1e-9)
    norm = (df["overall_score"] - score_min) / denom
    colors = [CUSTOM_CMAP(float(v)) for v in norm]

    bars = ax.barh(
        range(len(df)),
        df["overall_score"],
        color=colors,
        edgecolor="white",
        linewidth=0.8,
        height=0.70,
        zorder=3,
    )

    for b in bars:
        b.set_path_effects(
            [pe.withSimplePatchShadow(offset=(1, -1.2), alpha=0.18, shadow_rgbFace="#000000")]
        )

    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(
        [fa(p) for p in df["province"]],
        fontsize=10.5,
        color=TEXT_DARK,
    )

    for i, score in enumerate(df["overall_score"]):
        ax.text(
            float(score) + 0.7,
            i,
            f"{float(score):.1f}",
            va="center",
            fontsize=9,
            color=TEXT_MUTED,
            fontweight="medium",
        )

    mean_score = float(df["overall_score"].mean())
    ax.axvline(mean_score, color="#999", linestyle=(0, (4, 3)), linewidth=1, alpha=0.6, zorder=1)
    ax.text(
        mean_score,
        len(df) + 0.6,
        fa(f"میانگین: {mean_score:.1f}"),
        ha="center",
        fontsize=8.5,
        color="#777",
    )

    ax.set_xlabel(fa("امتیاز ترکیبی"), fontsize=12, color=TEXT_DARK, labelpad=10)
    ax.set_title(fa("رتبه‌بندی نهایی استان‌های ایران"), fontsize=19, fontweight="bold", color=TEXT_DARK, pad=22)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", alpha=0.18, zorder=0)
    ax.set_xlim(0, score_max * 1.12)

    plt.tight_layout()
    out = _save(fig, "01_ranking.png", dpi=320)
    plt.show()
    return out


# ============================================================
# 2) Province × category heatmap
# ============================================================
def plot_category_heatmap() -> Path:
    df = load_categories()
    pivot = df.pivot_table(index="province", columns="category", values="category_score", aggfunc="mean")
    pivot = pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]

    fig, ax = plt.subplots(figsize=(8.5, 13.5), facecolor=BG)
    ax.set_facecolor(BG)

    data = pivot.to_numpy(dtype=float)
    im = ax.imshow(
        data,
        aspect="auto",
        cmap=CUSTOM_CMAP,
        interpolation="nearest",
        vmin=float(np.nanmin(data)),
        vmax=float(np.nanmax(data)),
    )

    # Cell boundaries similar to the supplied seaborn version.
    ax.set_xticks(np.arange(-0.5, data.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, data.shape[0], 1), minor=True)
    ax.grid(which="minor", color=BG, linestyle="-", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if not np.isnan(data[i, j]):
                ax.text(
                    j,
                    i,
                    f"{data[i, j]:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7.8,
                    color=TEXT_DARK,
                )

    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(
        [fa(p) for p in pivot.index],
        fontsize=9.8,
        rotation=0,
        color=TEXT_DARK,
    )
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(
        [fa(c) for c in pivot.columns],
        fontsize=11.5,
        rotation=25,
        ha="right",
        color=TEXT_DARK,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title(fa("امتیاز هر استان به تفکیک حوزه"), fontsize=17, fontweight="bold", color=TEXT_DARK, pad=16)
    ax.tick_params(length=0)

    cbar = fig.colorbar(im, ax=ax, shrink=0.45, pad=0.02)
    cbar.set_label(fa("امتیاز دسته"), fontsize=10.5, color=TEXT_DARK)
    cbar.outline.set_visible(False)

    plt.tight_layout()
    out = _save(fig, "02_category_heatmap.png", dpi=320)
    plt.show()
    return out


# ============================================================
# 3) Geographic map
# ============================================================
def plot_map(geojson_url: Optional[str] = None) -> Path:
    try:
        import geopandas as gpd
        import requests
    except ImportError as exc:  # pragma: no cover - optional map dependency
        raise ImportError(
            "برای نقشه این دو بسته را نصب کنید: pip install geopandas requests"
        ) from exc

    print("🌍 در حال دریافت GeoJSON نقشه ایران...")
    urls = [geojson_url] if geojson_url else MAP_GEOJSON_URLS
    geo_data = None
    last_error = None
    for url in urls:
        try:
            response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            geo_data = response.json()
            print("✅ GeoJSON دریافت شد:", url)
            break
        except Exception as exc:
            last_error = exc
    if geo_data is None:
        raise RuntimeError(f"GeoJSON download failed: {last_error}")

    gdf = gpd.GeoDataFrame.from_features(geo_data["features"])

    risk = load_composite()
    risk["province_norm"] = risk["province"].map(normalize_name)

    geo_name_col = next((c for c in ["NAME_1", "name", "NAME", "name_en", "name:en", "name_fa", "name:fa"] if c in gdf.columns), None)
    if geo_name_col is None:
        raise ValueError(f"هیچ فیلد نام استان در GeoJSON پیدا نشد. ستون‌ها: {list(gdf.columns)}")

    gdf["province_norm"] = gdf[geo_name_col].map(normalize_name)

    # Some province boundaries are stored as multiple features.
    gdf = gdf.dissolve(by="province_norm", as_index=False)

    model_provinces = set(risk["province_norm"].dropna())
    geo_provinces = set(gdf["province_norm"].dropna())
    missing = sorted(model_provinces - geo_provinces)
    print(f"✅ Match شده: {len(model_provinces & geo_provinces)} از {len(model_provinces)} استان")
    if missing:
        print("⚠️ استان‌های unmatched:", ", ".join(missing))

    merged = gdf.merge(risk, on="province_norm", how="left", validate="one_to_one")
    merged["area"] = merged.geometry.area

    fig, ax = plt.subplots(figsize=(13, 14), facecolor=BG)
    ax.set_facecolor(BG)

    valid = merged["overall_score"].dropna()
    if valid.empty:
        raise ValueError("هیچ استانی بین GeoJSON و فایل امتیاز ترکیبی match نشد.")

    vmin, vmax = float(valid.min()), float(valid.max())

    merged.plot(
        column="overall_score",
        cmap=CUSTOM_CMAP,
        linewidth=1.2,
        edgecolor="#ffffff",
        ax=ax,
        vmin=vmin,
        vmax=vmax,
        missing_kwds={"color": "#e8e4df"},
    )

    area_valid = merged["area"].dropna()
    area_min, area_max = float(area_valid.min()), float(area_valid.max())
    area_denom = max(area_max - area_min, 1e-9)
    median_score = float(valid.median())

    for _, row in merged.iterrows():
        if pd.isna(row.get("overall_score")):
            continue

        c = row.geometry.centroid
        norm_area = (float(row["area"]) - area_min) / area_denom
        fontsize_name = 6.2 + norm_area * 6.5

        text_color = "white" if float(row["overall_score"]) >= median_score else TEXT_DARK
        stroke = "#4a0d14" if float(row["overall_score"]) >= median_score else "#ffffff"

        label = f"{fa(row['province_norm'])}\n{float(row['overall_score']):.0f}"
        txt = ax.annotate(
            label,
            xy=(c.x, c.y),
            ha="center",
            va="center",
            fontsize=fontsize_name,
            color=text_color,
            fontweight="bold",
            linespacing=1.9,
            zorder=5,
        )
        txt.set_path_effects([pe.withStroke(linewidth=2.3, foreground=stroke)])

    ax.set_title(fa("نقشه امتیاز ترکیبی استان‌های ایران"), fontsize=23, fontweight="bold", color=TEXT_DARK, pad=18)

    sm = plt.cm.ScalarMappable(cmap=CUSTOM_CMAP, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.01, aspect=22)
    cbar.set_label(fa("امتیاز ترکیبی"), fontsize=11.5, color=TEXT_DARK)
    cbar.outline.set_visible(False)

    ax.axis("off")
    bounds = merged.total_bounds
    pad_x = (bounds[2] - bounds[0]) * 0.03
    pad_y = (bounds[3] - bounds[1]) * 0.03
    ax.set_xlim(bounds[0] - pad_x, bounds[2] + pad_x)
    ax.set_ylim(bounds[1] - pad_y, bounds[3] + pad_y)

    fig.text(
        0.5,
        0.025,
        fa("منبع: مدل ترکیبی چندبعدی V2.1 — پنج حوزه اقتصادی، اجتماعی، آموزشی، امنیتی، زیرساختی"),
        ha="center",
        fontsize=9,
        color=TEXT_MUTED,
    )

    plt.tight_layout()
    out = _save(fig, "03_map.png", dpi=360)
    plt.show()
    return out


# ============================================================
# 4) Radar profile
# ============================================================
def plot_radar(provinces: Optional[Iterable[str]] = None) -> Path:
    df = load_categories()
    comp = load_composite()

    categories = df["category"].drop_duplicates().tolist()
    if not categories:
        raise ValueError("هیچ دسته‌ای در category_scores.csv پیدا نشد.")

    if provinces is None:
        sorted_comp = comp.sort_values("rank")
        best = sorted_comp.iloc[0]["province"]
        worst = sorted_comp.iloc[-1]["province"]
        middle = sorted_comp.iloc[len(sorted_comp) // 2]["province"]
        provinces = [best, middle, worst]
    else:
        provinces = list(provinces)

    if len(provinces) != 3:
        raise ValueError("این نسخه برای حفظ جزئیات نمودار اصلی، دقیقاً 3 استان را می‌گیرد.")

    n = len(categories)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9.5, 9.5), subplot_kw=dict(polar=True), facecolor=BG)
    ax.set_facecolor(BG)

    # Preserved from supplied code.
    colors = ["#2d5f3e", "#d9822b", "#8e1a2f"]

    for prov, color in zip(provinces, colors):
        sub = df[df["province"] == prov].set_index("category").reindex(categories)
        values = sub["category_score"].to_numpy(dtype=float).tolist()
        values += values[:1]

        ax.plot(angles, values, linewidth=2.4, label=fa(prov), color=color, zorder=3)
        ax.fill(angles, values, alpha=0.10, color=color, zorder=2)
        ax.scatter(angles, values, s=22, color=color, zorder=4, edgecolor="white", linewidth=0.8)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(
        [fa(c) for c in categories],
        fontsize=12.5,
        color=TEXT_DARK,
        fontweight="medium",
    )
    ax.tick_params(axis="x", pad=22)
    ax.set_ylim(0, 112)
    ax.set_rgrids(
        [20, 40, 60, 80, 100],
        labels=["20", "40", "60", "80", "100"],
        fontsize=8,
        color="#999",
    )
    ax.set_rlabel_position(360 / n / 2)
    ax.spines["polar"].set_color("#ddd")
    ax.grid(color="#e3ddd3", alpha=0.8, linewidth=0.8)
    ax.set_title(
        fa("مقایسه پروفایل استان‌ها در پنج حوزه"),
        fontsize=17,
        fontweight="bold",
        color=TEXT_DARK,
        pad=32,
    )
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.12), fontsize=10.5, frameon=False)

    plt.tight_layout()
    out = _save(fig, "04_radar.png", dpi=320)
    plt.show()
    return out


# ============================================================
# 5) Monte Carlo stability
# ============================================================
def plot_monte_carlo_stability() -> Path:
    path = _require_file("monte_carlo_local.csv")
    df = pd.read_csv(path).sort_values("median_rank").reset_index(drop=True)

    required = {"province", "rank_p05", "rank_p95", "median_rank"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"ستون‌های لازم در monte_carlo_local.csv نیستند: {sorted(missing)}")

    fig, ax = plt.subplots(figsize=(10.5, 13), facecolor=BG)
    ax.set_facecolor(BG)

    y = np.arange(len(df))
    ax.hlines(y, df["rank_p05"], df["rank_p95"], color="#eab98f", linewidth=2.8, alpha=0.8, zorder=2)
    ax.scatter(
        df["median_rank"],
        y,
        s=42,
        color="#b8402a",
        zorder=3,
        edgecolor="white",
        linewidth=0.9,
    )

    ax.set_yticks(y)
    ax.set_yticklabels([fa(p) for p in df["province"]], fontsize=9.8, color=TEXT_DARK)
    ax.set_xlabel(
        fa("رتبه (با بازه عدم‌قطعیت ۹۰٪ از شبیه‌سازی مونت‌کارلو)"),
        fontsize=11,
        color=TEXT_DARK,
        labelpad=10,
    )
    ax.set_title(
        fa("پایداری رتبه‌بندی زیر وزن‌دهی‌های مختلف"),
        fontsize=17,
        fontweight="bold",
        color=TEXT_DARK,
        pad=16,
    )
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.18)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()
    out = _save(fig, "05_monte_carlo_stability.png", dpi=320)
    plt.show()
    return out


# ============================================================
# Run all
# ============================================================
def main() -> None:
    print(f"📁 BASE: {BASE}")
    print(f"🖼️ SAVE_DIR: {SAVE_DIR}")

    plot_ranking()
    plot_category_heatmap()
    plot_map()
    plot_radar()
    plot_monte_carlo_stability()

    print("\n🎉 همه نمودارها ساخته شدن:", SAVE_DIR)


if __name__ == "__main__":
    main()
