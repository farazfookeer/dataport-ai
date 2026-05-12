"""Smoke-test the pipeline end-to-end except the LLM narrate step.

This verifies ingest -> profile -> cleanse -> insights -> export(csv/json/report)
without needing an Anthropic API key. The narrate step is stubbed.
"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console

from src.cleanse import CleanseConfig, cleanse
from src.export import export_csv, export_insights, export_report
from src.ingest import load
from src.insights import generate_findings
from src.logger import RunLogger
from src.narrate import CATEGORY_TO_VIZ
from src.profile import profile


def stub_narrate(findings, profile_data, logger):
    """Stand-in for the LLM narrate step. Buckets each finding by its 'type'
    so we can still render the report."""
    logger.log("NARRATE", f"[STUB] Bucketing {len(findings)} findings without LLM")
    type_to_cat = {
        "correlation": "Relationships",
        "outliers": "Anomalies",
        "distribution_skew": "Distributions",
        "data_quality_missing": "Data Quality",
        "data_quality_cardinality": "Data Quality",
        "concentration": "Composition",
        "composition": "Composition",
        "trend": "Trends",
        "segment": "Segments",
        "comparison": "Comparisons",
    }
    by_cat = {}
    for f in findings:
        cat = type_to_cat.get(f["type"], "Data Quality")
        by_cat.setdefault(cat, []).append(
            {
                "headline": f["summary"][:60],
                "story": f["summary"],
                "viz_recommendations": CATEGORY_TO_VIZ.get(cat, []),
                "raw_finding": f,
            }
        )
    narratives = {
        cat: f"({len(items)} finding{'s' if len(items)!=1 else ''} in this category)"
        for cat, items in by_cat.items()
    }
    return {"stories": [], "category_narratives": narratives, "by_category": by_cat}


def main():
    console = Console()
    source = Path("samples/student_grades.csv")
    output_dir = Path("outputs/verify_run")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = RunLogger(output_dir=output_dir, console=console)
    logger.log("INFO", f"Verification run -> {output_dir}")

    df = load(source, logger)
    profile_data = profile(df, logger)
    cleaned = cleanse(df, profile_data, logger, CleanseConfig.auto())
    findings = generate_findings(cleaned, profile_data, logger)
    narration = stub_narrate(findings, profile_data, logger)

    export_csv(cleaned, output_dir, logger)
    export_insights(findings, narration, output_dir, logger)
    logger.flush_audit()
    export_report(
        source_name=source.name,
        profile_data=profile_data,
        by_category=narration["by_category"],
        category_narratives=narration["category_narratives"],
        cleanse_audit=logger.cleanse_audit_entries(),
        output_dir=output_dir,
        logger=logger,
    )
    logger.close()

    console.print(f"\n[bold green]✓ Verification complete[/bold green] — see {output_dir}/")


if __name__ == "__main__":
    main()
