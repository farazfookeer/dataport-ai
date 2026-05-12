from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Template

from .logger import RunLogger


def export_csv(df: pd.DataFrame, output_dir: Path, logger: RunLogger) -> Path:
    path = output_dir / "cleaned.csv"
    df.to_csv(path, index=False)
    logger.log("EXPORT", f"Wrote {path.name} ({_size(path)})")
    return path


def export_hyper(df: pd.DataFrame, output_dir: Path, logger: RunLogger) -> Path | None:
    """Write a Tableau .hyper extract. Returns the path or None if Hyper API
    is unavailable on the system."""
    try:
        from tableauhyperapi import (
            Connection,
            CreateMode,
            HyperProcess,
            SqlType,
            TableDefinition,
            TableName,
            Telemetry,
            Inserter,
            NULLABLE,
        )
    except Exception as e:  # pragma: no cover
        logger.log("EXPORT", f"Hyper API unavailable, skipping .hyper output ({e})")
        return None

    path = output_dir / "cleaned.hyper"
    if path.exists():
        path.unlink()

    columns = []
    for col, dtype in df.dtypes.items():
        sql_type = _pandas_to_sql(dtype)
        columns.append(TableDefinition.Column(str(col), sql_type, NULLABLE))

    table_name = TableName("Extract", "Extract")
    table_def = TableDefinition(table_name=table_name, columns=columns)

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(
            endpoint=hyper.endpoint,
            database=path,
            create_mode=CreateMode.CREATE_AND_REPLACE,
        ) as connection:
            connection.catalog.create_schema("Extract")
            connection.catalog.create_table(table_def)
            with Inserter(connection, table_def) as inserter:
                for row in df.itertuples(index=False, name=None):
                    inserter.add_row(
                        [None if pd.isna(v) else v for v in row]
                    )
                inserter.execute()

    logger.log("EXPORT", f"Wrote {path.name} ({_size(path)})")
    return path


def _pandas_to_sql(dtype) -> Any:
    from tableauhyperapi import SqlType

    if pd.api.types.is_bool_dtype(dtype):
        return SqlType.bool()
    if pd.api.types.is_integer_dtype(dtype):
        return SqlType.big_int()
    if pd.api.types.is_float_dtype(dtype):
        return SqlType.double()
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return SqlType.timestamp()
    return SqlType.text()


def export_insights(
    findings: list[dict[str, Any]],
    narration: dict[str, Any],
    output_dir: Path,
    logger: RunLogger,
) -> Path:
    path = output_dir / "insights.json"
    payload = {
        "findings": findings,
        "stories": narration.get("stories", []),
        "category_narratives": narration.get("category_narratives", {}),
        "by_category": narration.get("by_category", {}),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.log("EXPORT", f"Wrote {path.name}")
    return path


REPORT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tableau Connector Report — {{ source_name }}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
         margin: 0; padding: 2rem; max-width: 1100px; margin: auto;
         background: #0f1216; color: #e6e9ef; }
  h1 { font-weight: 700; font-size: 1.9rem; margin-bottom: 0.3rem; }
  h2 { margin-top: 2.5rem; font-size: 1.3rem; border-bottom: 1px solid #2a313c; padding-bottom: 0.3rem; }
  h3 { margin-top: 1.5rem; font-size: 1.05rem; color: #9eb3ff; }
  .meta { color: #8895a8; font-size: 0.9rem; margin-bottom: 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; }
  .stat { background: #1a1f29; border: 1px solid #2a313c; border-radius: 8px; padding: 0.9rem 1rem; }
  .stat .label { font-size: 0.75rem; text-transform: uppercase; color: #8895a8; letter-spacing: 0.05em; }
  .stat .value { font-size: 1.4rem; font-weight: 600; margin-top: 0.3rem; }
  .story { background: #1a1f29; border-left: 3px solid #5a7fff; padding: 0.8rem 1rem;
           margin: 0.6rem 0; border-radius: 4px; }
  .story .headline { font-weight: 600; }
  .story .body { color: #c5cddb; margin-top: 0.3rem; font-size: 0.95rem; }
  .story .viz { color: #88c1a0; margin-top: 0.4rem; font-size: 0.82rem; }
  .narrative { color: #b9c4d6; font-style: italic; margin: 0.5rem 0 1rem; padding-left: 0.7rem;
               border-left: 2px solid #4a3f6b; }
  table { border-collapse: collapse; width: 100%; margin-top: 0.8rem; font-size: 0.88rem; }
  th, td { text-align: left; padding: 0.45rem 0.7rem; border-bottom: 1px solid #2a313c; }
  th { color: #8895a8; font-weight: 500; }
  code { background: #1a1f29; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.85em; }
  .pill { display: inline-block; background: #2a3142; color: #9eb3ff; padding: 0.1rem 0.55rem;
          border-radius: 999px; font-size: 0.75rem; margin-left: 0.4rem; }
</style>
</head>
<body>
<h1>📊 Tableau Connector Report</h1>
<div class="meta">{{ source_name }} · generated {{ generated_at }}</div>

<h2>Dataset overview</h2>
<div class="grid">
  <div class="stat"><div class="label">Rows</div><div class="value">{{ overall.rows }}</div></div>
  <div class="stat"><div class="label">Columns</div><div class="value">{{ overall.columns }}</div></div>
  <div class="stat"><div class="label">Duplicate rows</div><div class="value">{{ overall.duplicate_rows }}</div></div>
  <div class="stat"><div class="label">Missing cells</div><div class="value">{{ overall.missing_pct }}%</div></div>
</div>

<h2>Data stories by category</h2>
{% for category, stories in by_category.items() %}
  <h3>{{ category }} <span class="pill">{{ stories|length }}</span></h3>
  {% if category_narratives.get(category) %}
    <div class="narrative">{{ category_narratives[category] }}</div>
  {% endif %}
  {% for s in stories %}
    <div class="story">
      <div class="headline">{{ s.headline }}</div>
      <div class="body">{{ s.story }}</div>
      {% if s.viz_recommendations %}
        <div class="viz">📈 Suggested Tableau viz: {{ s.viz_recommendations|join(", ") }}</div>
      {% endif %}
    </div>
  {% endfor %}
{% endfor %}

<h2>Column profile</h2>
<table>
  <thead><tr><th>Column</th><th>Kind</th><th>Missing</th><th>Unique</th><th>Notes</th></tr></thead>
  <tbody>
  {% for col, info in columns.items() %}
    <tr>
      <td><code>{{ col }}</code></td>
      <td>{{ info.kind }}</td>
      <td>{{ info.missing }} ({{ info.missing_pct }}%)</td>
      <td>{{ info.unique }}</td>
      <td>
        {% if info.kind == "numeric" %}
          mean={{ info.mean }}, median={{ info.median }}, outliers={{ info.outliers_iqr or 0 }}
        {% elif info.kind == "datetime" %}
          {{ info.min }} → {{ info.max }} ({{ info.span_days }}d)
        {% elif info.kind == "categorical" %}
          top: {% for t in info.top_values[:3] %}{{ t.value }} ({{ t.count }}){% if not loop.last %}, {% endif %}{% endfor %}
        {% endif %}
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<h2>Cleanse audit</h2>
{% if cleanse_audit %}
<table>
  <thead><tr><th>Operation</th><th>Column</th><th>Rule</th><th>Rows affected</th><th>Details</th></tr></thead>
  <tbody>
  {% for entry in cleanse_audit %}
    <tr>
      <td><code>{{ entry.operation }}</code></td>
      <td>{{ entry.column or "—" }}</td>
      <td>{{ entry.rule }}</td>
      <td>{{ entry.rows_affected }}</td>
      <td><code>{{ entry.details }}</code></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p style="color: #8895a8">No cleansing operations were applied.</p>
{% endif %}

</body>
</html>"""


def export_report(
    source_name: str,
    profile_data: dict[str, Any],
    by_category: dict[str, list[dict[str, Any]]],
    category_narratives: dict[str, str],
    cleanse_audit: list[dict[str, Any]],
    output_dir: Path,
    logger: RunLogger,
) -> Path:
    template = Template(REPORT_TEMPLATE)
    html = template.render(
        source_name=source_name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        overall=profile_data["overall"],
        columns=profile_data["columns"],
        by_category=by_category,
        category_narratives=category_narratives,
        cleanse_audit=cleanse_audit,
    )
    path = output_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    logger.log("EXPORT", f"Wrote {path.name} ({_size(path)})")
    return path


def _size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
