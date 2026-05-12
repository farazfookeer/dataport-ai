from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .logger import RunLogger


@dataclass
class CleanseConfig:
    """Configurable cleansing rules. Every enabled op is audited."""

    dedupe: bool = True
    strip_whitespace: bool = True
    coerce_datetimes: bool = True
    fill_missing_numeric: str | None = "median"  # "median" | "mean" | "zero" | None
    fill_missing_categorical: str | None = "unknown"  # "mode" | "unknown" | None
    clip_outliers_iqr: bool = False
    drop_high_missing_cols_pct: float | None = None  # e.g. 80.0
    normalize_column_names: bool = True

    @classmethod
    def auto(cls) -> "CleanseConfig":
        return cls(
            dedupe=True,
            strip_whitespace=True,
            coerce_datetimes=True,
            fill_missing_numeric="median",
            fill_missing_categorical="unknown",
            clip_outliers_iqr=False,
            drop_high_missing_cols_pct=None,
            normalize_column_names=True,
        )


def cleanse(
    df: pd.DataFrame,
    profile_data: dict[str, Any],
    logger: RunLogger,
    config: CleanseConfig | None = None,
) -> pd.DataFrame:
    """Apply cleansing rules. Every operation is recorded in the cleanse audit."""
    config = config or CleanseConfig.auto()
    logger.log("CLEANSE", "Beginning cleansing pass")
    out = df.copy()

    if config.normalize_column_names:
        out = _normalize_columns(out, logger)

    if config.drop_high_missing_cols_pct is not None:
        out = _drop_high_missing_cols(out, config.drop_high_missing_cols_pct, logger)

    if config.dedupe:
        out = _dedupe(out, logger)

    if config.strip_whitespace:
        out = _strip_whitespace(out, logger)

    if config.coerce_datetimes:
        out = _coerce_datetimes(out, profile_data, logger)

    if config.fill_missing_numeric:
        out = _fill_numeric(out, config.fill_missing_numeric, logger)

    if config.fill_missing_categorical:
        out = _fill_categorical(out, config.fill_missing_categorical, logger)

    if config.clip_outliers_iqr:
        out = _clip_outliers(out, logger)

    logger.log(
        "CLEANSE",
        f"Cleansing complete: {len(out):,} rows × {len(out.columns)} columns remain",
    )
    return out


def _normalize_columns(df: pd.DataFrame, logger: RunLogger) -> pd.DataFrame:
    renames = {}
    for col in df.columns:
        new = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        new = "".join(ch for ch in new if ch.isalnum() or ch == "_")
        if new and new != col:
            renames[col] = new
    if renames:
        df = df.rename(columns=renames)
        logger.audit_cleanse(
            "normalize_column_names",
            column=None,
            rule="snake_case",
            rows_affected=0,
            details={"renamed": renames},
        )
    return df


def _drop_high_missing_cols(
    df: pd.DataFrame, threshold_pct: float, logger: RunLogger
) -> pd.DataFrame:
    n = len(df)
    drops = []
    for col in df.columns:
        pct = 100 * df[col].isna().sum() / n if n else 0
        if pct >= threshold_pct:
            drops.append(col)
    if drops:
        df = df.drop(columns=drops)
        logger.audit_cleanse(
            "drop_columns",
            column=None,
            rule=f"missing_pct >= {threshold_pct}",
            rows_affected=0,
            details={"columns_dropped": drops},
        )
    return df


def _dedupe(df: pd.DataFrame, logger: RunLogger) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = before - len(df)
    if removed:
        logger.audit_cleanse(
            "dedupe",
            column=None,
            rule="exact_row_match",
            rows_affected=removed,
            details={"rows_before": before, "rows_after": len(df)},
        )
    return df


def _strip_whitespace(df: pd.DataFrame, logger: RunLogger) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object"]).columns:
        original = df[col]
        stripped = original.astype("string").str.strip()
        changed = int((original.astype("string") != stripped).fillna(False).sum())
        if changed:
            df[col] = stripped
            logger.audit_cleanse(
                "strip_whitespace",
                column=col,
                rule="trim_leading_trailing",
                rows_affected=changed,
            )
    return df


def _coerce_datetimes(
    df: pd.DataFrame, profile_data: dict[str, Any], logger: RunLogger
) -> pd.DataFrame:
    for col, info in profile_data.get("columns", {}).items():
        if col not in df.columns:
            continue
        if info.get("kind") == "datetime" and not pd.api.types.is_datetime64_any_dtype(
            df[col]
        ):
            before_null = int(df[col].isna().sum())
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
            after_null = int(df[col].isna().sum())
            coerced = after_null - before_null
            logger.audit_cleanse(
                "coerce_datetime",
                column=col,
                rule="pd.to_datetime errors=coerce",
                rows_affected=int(df[col].notna().sum()),
                details={"newly_null": coerced},
            )
    return df


def _fill_numeric(df: pd.DataFrame, strategy: str, logger: RunLogger) -> pd.DataFrame:
    for col in df.select_dtypes(include=[np.number]).columns:
        missing = int(df[col].isna().sum())
        if missing == 0:
            continue
        if strategy == "median":
            value = df[col].median()
        elif strategy == "mean":
            value = df[col].mean()
        elif strategy == "zero":
            value = 0
        else:
            continue
        if pd.isna(value):
            continue
        df[col] = df[col].fillna(value)
        logger.audit_cleanse(
            "fill_missing",
            column=col,
            rule=f"numeric:{strategy}",
            rows_affected=missing,
            details={"value_applied": float(value)},
        )
    return df


def _fill_categorical(
    df: pd.DataFrame, strategy: str, logger: RunLogger
) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object", "string", "category"]).columns:
        missing = int(df[col].isna().sum())
        if missing == 0:
            continue
        if strategy == "mode":
            mode = df[col].mode()
            value = mode.iloc[0] if not mode.empty else "Unknown"
        elif strategy == "unknown":
            value = "Unknown"
        else:
            continue
        df[col] = df[col].fillna(value)
        logger.audit_cleanse(
            "fill_missing",
            column=col,
            rule=f"categorical:{strategy}",
            rows_affected=missing,
            details={"value_applied": str(value)},
        )
    return df


def _clip_outliers(df: pd.DataFrame, logger: RunLogger) -> pd.DataFrame:
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) < 4:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        affected = int(((df[col] < lo) | (df[col] > hi)).sum())
        if affected:
            df[col] = df[col].clip(lower=lo, upper=hi)
            logger.audit_cleanse(
                "clip_outliers",
                column=col,
                rule="IQR_1.5x",
                rows_affected=affected,
                details={"lower": float(lo), "upper": float(hi)},
            )
    return df
