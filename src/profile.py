from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .logger import RunLogger


def profile(df: pd.DataFrame, logger: RunLogger) -> dict[str, Any]:
    """Build a structured profile of the dataframe.

    Returns a dict with overall stats and per-column details. Downstream
    modules (cleanse, insights) consume this as the source of truth.
    """
    logger.log("PROFILE", f"Profiling {len(df):,} rows × {len(df.columns)} columns")

    columns: dict[str, dict[str, Any]] = {}
    type_counts = {"numeric": 0, "categorical": 0, "datetime": 0, "boolean": 0, "other": 0}

    for col in df.columns:
        series = df[col]
        kind = _classify(series)
        type_counts[kind] += 1
        columns[col] = _column_profile(series, kind)

    duplicate_rows = int(df.duplicated().sum())
    total_cells = df.shape[0] * df.shape[1] if df.size else 1
    missing_cells = int(df.isna().sum().sum())

    overall = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
        "missing_pct": round(100 * missing_cells / total_cells, 2),
        "type_counts": type_counts,
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
    }

    correlations = _correlations(df)

    logger.log(
        "PROFILE",
        f"Types: {type_counts['numeric']} numeric · "
        f"{type_counts['categorical']} categorical · "
        f"{type_counts['datetime']} datetime · "
        f"{type_counts['boolean']} bool",
    )
    logger.log(
        "PROFILE",
        f"Found {duplicate_rows} duplicate rows · {overall['missing_pct']}% cells missing",
    )

    return {"overall": overall, "columns": columns, "correlations": correlations}


def _classify(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # Heuristic: try parsing as datetime if string-ish
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        sample = series.dropna().astype(str).head(20)
        if len(sample) >= 5:
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            if parsed.notna().sum() / len(sample) >= 0.8:
                return "datetime"
        return "categorical"
    return "other"


def _column_profile(series: pd.Series, kind: str) -> dict[str, Any]:
    n = len(series)
    missing = int(series.isna().sum())
    unique = int(series.nunique(dropna=True))

    base: dict[str, Any] = {
        "kind": kind,
        "dtype": str(series.dtype),
        "missing": missing,
        "missing_pct": round(100 * missing / n, 2) if n else 0,
        "unique": unique,
        "unique_pct": round(100 * unique / n, 2) if n else 0,
    }

    if kind == "numeric":
        s = series.dropna()
        if len(s):
            base.update(
                {
                    "mean": _safe_float(s.mean()),
                    "median": _safe_float(s.median()),
                    "std": _safe_float(s.std()),
                    "min": _safe_float(s.min()),
                    "max": _safe_float(s.max()),
                    "q1": _safe_float(s.quantile(0.25)),
                    "q3": _safe_float(s.quantile(0.75)),
                    "skew": _safe_float(s.skew()) if len(s) > 2 else None,
                    "outliers_iqr": _iqr_outlier_count(s),
                    "zeros": int((s == 0).sum()),
                    "negatives": int((s < 0).sum()),
                }
            )
    elif kind == "categorical":
        top = series.dropna().astype(str).value_counts().head(5)
        base["top_values"] = [{"value": k, "count": int(v)} for k, v in top.items()]
        base["high_cardinality"] = unique > 50 and unique / max(n, 1) > 0.5
    elif kind == "datetime":
        s = pd.to_datetime(series, errors="coerce").dropna()
        if len(s):
            base.update(
                {
                    "min": s.min().isoformat(),
                    "max": s.max().isoformat(),
                    "span_days": int((s.max() - s.min()).days),
                }
            )
    elif kind == "boolean":
        s = series.dropna()
        if len(s):
            base["true_count"] = int(s.sum())
            base["false_count"] = int(len(s) - s.sum())
    return base


def _iqr_outlier_count(s: pd.Series) -> int:
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((s < lo) | (s > hi)).sum())


def _correlations(df: pd.DataFrame) -> list[dict[str, Any]]:
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(numeric_only=True)
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if pd.notna(r) and abs(r) >= 0.5:
                pairs.append(
                    {"a": cols[i], "b": cols[j], "pearson": _safe_float(r)}
                )
    pairs.sort(key=lambda p: abs(p["pearson"]), reverse=True)
    return pairs[:20]


def _safe_float(x: Any) -> float | None:
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, 4)
    except (TypeError, ValueError):
        return None
