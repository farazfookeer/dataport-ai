from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .logger import RunLogger


def generate_findings(
    df: pd.DataFrame, profile_data: dict[str, Any], logger: RunLogger
) -> list[dict[str, Any]]:
    """Generate structured raw findings. The narrate layer turns these into
    categorized stories."""
    logger.log("INSIGHTS", "Scanning for trends, outliers, and relationships")
    findings: list[dict[str, Any]] = []

    cols_info = profile_data.get("columns", {})
    findings += _correlation_findings(profile_data)
    findings += _outlier_findings(cols_info)
    findings += _skew_findings(cols_info)
    findings += _missing_findings(cols_info, profile_data["overall"]["rows"])
    findings += _cardinality_findings(cols_info)
    findings += _concentration_findings(df, cols_info)
    findings += _composition_findings(df, cols_info)
    findings += _trend_findings(df, cols_info)
    findings += _segment_findings(df, cols_info)
    findings += _comparison_findings(df, cols_info)

    findings.sort(key=lambda f: f.get("importance", 0), reverse=True)
    logger.log("INSIGHTS", f"Generated {len(findings)} raw findings")
    return findings


def _correlation_findings(profile_data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in profile_data.get("correlations", []):
        r = c["pearson"]
        direction = "positive" if r > 0 else "negative"
        out.append(
            {
                "type": "correlation",
                "columns": [c["a"], c["b"]],
                "payload": {"pearson": r, "direction": direction},
                "summary": f"{c['a']} and {c['b']} have a {direction} correlation (r={r:.2f})",
                "importance": abs(r),
            }
        )
    return out


def _outlier_findings(cols_info: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        if info["kind"] != "numeric":
            continue
        n_out = info.get("outliers_iqr", 0)
        if n_out > 0:
            out.append(
                {
                    "type": "outliers",
                    "columns": [col],
                    "payload": {"count": n_out},
                    "summary": f"{col} has {n_out} IQR outliers",
                    "importance": min(0.9, 0.3 + n_out / 100),
                }
            )
    return out


def _skew_findings(cols_info: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        if info["kind"] != "numeric":
            continue
        skew = info.get("skew")
        if skew is None:
            continue
        if abs(skew) >= 1.0:
            direction = "right" if skew > 0 else "left"
            out.append(
                {
                    "type": "distribution_skew",
                    "columns": [col],
                    "payload": {"skew": skew, "direction": direction},
                    "summary": f"{col} is {direction}-skewed (skew={skew:.2f})",
                    "importance": min(0.8, abs(skew) / 3),
                }
            )
    return out


def _missing_findings(cols_info: dict[str, Any], n_rows: int) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        pct = info.get("missing_pct", 0)
        if pct >= 5:
            out.append(
                {
                    "type": "data_quality_missing",
                    "columns": [col],
                    "payload": {"missing_pct": pct, "missing_count": info["missing"]},
                    "summary": f"{col} is {pct}% missing ({info['missing']} of {n_rows} rows)",
                    "importance": min(0.95, pct / 100),
                }
            )
    return out


def _cardinality_findings(cols_info: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        if info["kind"] == "categorical" and info.get("high_cardinality"):
            out.append(
                {
                    "type": "data_quality_cardinality",
                    "columns": [col],
                    "payload": {"unique": info["unique"], "unique_pct": info["unique_pct"]},
                    "summary": f"{col} has very high cardinality ({info['unique']} unique values)",
                    "importance": 0.4,
                }
            )
    return out


def _concentration_findings(
    df: pd.DataFrame, cols_info: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        if info["kind"] != "categorical":
            continue
        top = info.get("top_values", [])
        if not top:
            continue
        total = sum(t["count"] for t in top) + (
            len(df) - sum(t["count"] for t in top) - info["missing"]
        )
        leader = top[0]
        if total and leader["count"] / max(len(df) - info["missing"], 1) >= 0.7:
            share = leader["count"] / max(len(df) - info["missing"], 1)
            out.append(
                {
                    "type": "concentration",
                    "columns": [col],
                    "payload": {"value": leader["value"], "share": round(share, 3)},
                    "summary": (
                        f"{col} is dominated by '{leader['value']}' "
                        f"({share:.0%} of non-null values)"
                    ),
                    "importance": share,
                }
            )
    return out


def _composition_findings(
    df: pd.DataFrame, cols_info: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for col, info in cols_info.items():
        if info["kind"] != "categorical":
            continue
        if info.get("unique", 0) > 12 or info.get("unique", 0) < 2:
            continue
        top = info.get("top_values", [])
        if not top:
            continue
        out.append(
            {
                "type": "composition",
                "columns": [col],
                "payload": {"top_values": top},
                "summary": f"{col} composition: {', '.join(f'{t['value']} ({t['count']})' for t in top[:3])}",
                "importance": 0.5,
            }
        )
    return out


def _trend_findings(df: pd.DataFrame, cols_info: dict[str, Any]) -> list[dict[str, Any]]:
    """If we have at least one datetime column, compute simple linear trend
    direction for each numeric column ordered by date."""
    datetime_cols = [c for c, i in cols_info.items() if i["kind"] == "datetime"]
    numeric_cols = [c for c, i in cols_info.items() if i["kind"] == "numeric"]
    if not datetime_cols or not numeric_cols:
        return []

    date_col = datetime_cols[0]
    out = []
    try:
        ordered = df[[date_col] + numeric_cols].copy()
        ordered[date_col] = pd.to_datetime(ordered[date_col], errors="coerce")
        ordered = ordered.dropna(subset=[date_col]).sort_values(date_col)
        if len(ordered) < 6:
            return []
        x = np.arange(len(ordered))
        for ncol in numeric_cols:
            y = ordered[ncol].astype(float).to_numpy()
            mask = ~np.isnan(y)
            if mask.sum() < 6:
                continue
            slope, intercept = np.polyfit(x[mask], y[mask], 1)
            span = y[mask][-1] - y[mask][0]
            denom = abs(y[mask][0]) if y[mask][0] != 0 else 1
            pct_change = 100 * span / denom
            direction = "upward" if slope > 0 else "downward"
            if abs(pct_change) >= 10:
                out.append(
                    {
                        "type": "trend",
                        "columns": [ncol, date_col],
                        "payload": {
                            "slope": float(slope),
                            "pct_change": round(float(pct_change), 2),
                            "direction": direction,
                        },
                        "summary": (
                            f"{ncol} shows a {direction} trend over {date_col} "
                            f"({pct_change:+.1f}% start-to-end)"
                        ),
                        "importance": min(0.9, abs(pct_change) / 200),
                    }
                )
    except Exception:
        return out
    return out


def _segment_findings(
    df: pd.DataFrame, cols_info: dict[str, Any]
) -> list[dict[str, Any]]:
    """For each (categorical, numeric) pair with small cardinality, report which
    segment has the highest/lowest mean."""
    out = []
    cat_cols = [
        c
        for c, i in cols_info.items()
        if i["kind"] == "categorical" and 2 <= i.get("unique", 0) <= 10
    ]
    num_cols = [c for c, i in cols_info.items() if i["kind"] == "numeric"]
    for cat in cat_cols:
        for num in num_cols:
            try:
                grouped = df.groupby(cat)[num].mean(numeric_only=True).dropna()
            except Exception:
                continue
            if len(grouped) < 2:
                continue
            hi = grouped.idxmax()
            lo = grouped.idxmin()
            spread = grouped.max() - grouped.min()
            mean = grouped.mean()
            if mean == 0:
                continue
            relative = abs(spread / mean)
            if relative >= 0.2:
                out.append(
                    {
                        "type": "segment",
                        "columns": [cat, num],
                        "payload": {
                            "highest": {"value": str(hi), "mean": float(grouped.max())},
                            "lowest": {"value": str(lo), "mean": float(grouped.min())},
                            "spread": float(spread),
                        },
                        "summary": (
                            f"Average {num} differs by {cat}: "
                            f"'{hi}' is highest ({grouped.max():.2f}), "
                            f"'{lo}' is lowest ({grouped.min():.2f})"
                        ),
                        "importance": min(0.85, relative / 2),
                    }
                )
    return out


def _comparison_findings(
    df: pd.DataFrame, cols_info: dict[str, Any]
) -> list[dict[str, Any]]:
    """Top/bottom comparisons within numeric columns."""
    out = []
    for col, info in cols_info.items():
        if info["kind"] != "numeric":
            continue
        s = df[col].dropna()
        if len(s) < 10:
            continue
        try:
            top10 = s.nlargest(int(max(1, len(s) * 0.1)))
            share = top10.sum() / s.sum() if s.sum() else 0
            if share >= 0.4:
                out.append(
                    {
                        "type": "comparison",
                        "columns": [col],
                        "payload": {
                            "top_decile_share": round(float(share), 3),
                            "top_decile_size": int(len(top10)),
                        },
                        "summary": (
                            f"Top 10% of {col} accounts for {share:.0%} of its total"
                        ),
                        "importance": min(0.9, float(share)),
                    }
                )
        except Exception:
            continue
    return out
