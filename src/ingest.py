from __future__ import annotations

from pathlib import Path

import pandas as pd

from .logger import RunLogger

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}


def load(path: Path, logger: RunLogger, sheet: str | int | None = None) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame.

    Raises ValueError for unsupported file types.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Expected one of {sorted(SUPPORTED_SUFFIXES)}."
        )

    logger.log("INGEST", f"Reading {path.name} ({_human_size(path)})")

    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".tsv":
        df = pd.read_csv(path, sep="\t")
    else:
        df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)

    logger.log("INGEST", f"Loaded {len(df):,} rows × {len(df.columns)} columns")
    return df


def _human_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
