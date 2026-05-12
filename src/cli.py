from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.align import Align
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .cleanse import CleanseConfig, cleanse
from .export import export_csv, export_hyper, export_insights, export_report
from .ingest import load
from .insights import generate_findings
from .logger import RunLogger
from .narrate import NarrateError, narrate
from .profile import profile

app = typer.Typer(
    add_completion=False,
    help="Profile, cleanse, and narrate spreadsheet data into Tableau-ready extracts.",
)

BANNER = r"""
  ╔════════════════════════════════════════════════════════════╗
  ║                                                            ║
  ║      D A T A P O R T   A I   ·   f o r   T a b l e a u    ║
  ║                                                            ║
  ║      profile · cleanse · narrate · export                  ║
  ║                                                            ║
  ╚════════════════════════════════════════════════════════════╝
"""


def _banner(console: Console) -> None:
    text = Text(BANNER, style="bold cyan")
    console.print(Align.center(text))


def _print_summary(
    console: Console,
    source: Path,
    df_rows_before: int,
    df_rows_after: int,
    by_category: dict[str, list],
    cleanse_audit: list,
    output_dir: Path,
) -> None:
    cat_table = Table(box=ROUNDED, title="📚 Data Stories by Category", title_style="bold blue")
    cat_table.add_column("Category", style="bold")
    cat_table.add_column("Stories", justify="right", style="cyan")
    cat_table.add_column("Suggested viz", style="dim")
    from .narrate import CATEGORY_TO_VIZ

    if by_category:
        for cat, stories in by_category.items():
            cat_table.add_row(
                cat, str(len(stories)), ", ".join(CATEGORY_TO_VIZ.get(cat, []))
            )
    else:
        cat_table.add_row("—", "0", "—")

    files_table = Table(box=ROUNDED, title="📦 Output Bundle", title_style="bold green")
    files_table.add_column("File", style="bold")
    files_table.add_column("Purpose", style="dim")
    files_table.add_row("report.html", "Categorized stories + cleanse audit (open in browser)")
    files_table.add_row("cleaned.hyper", "Tableau Desktop extract — drag into Tableau")
    files_table.add_row("cleaned.csv", "Portable cleaned data")
    files_table.add_row("insights.json", "Machine-readable findings + stories")
    files_table.add_row("cleanse_audit.json", "Every cleansing decision, logged")
    files_table.add_row("run.log", "Full step-by-step run log")

    stats_table = Table.grid(padding=(0, 2))
    stats_table.add_row(
        Text("Source", style="dim"),
        Text(source.name, style="bold"),
    )
    stats_table.add_row(
        Text("Rows", style="dim"),
        Text(f"{df_rows_before:,} → {df_rows_after:,}", style="bold"),
    )
    stats_table.add_row(
        Text("Cleanse ops", style="dim"),
        Text(str(len(cleanse_audit)), style="bold"),
    )
    stats_table.add_row(
        Text("Output dir", style="dim"),
        Text(str(output_dir), style="bold magenta"),
    )

    console.print()
    console.print(
        Panel(
            Group(stats_table, Text(""), cat_table, Text(""), files_table),
            title="[bold]✓ Run complete[/bold]",
            border_style="green",
            box=ROUNDED,
        )
    )


@app.command()
def run(
    source: Path = typer.Argument(..., exists=True, help="CSV or Excel file to analyze"),
    output: Path = typer.Option(
        Path("outputs"),
        "--output",
        "-o",
        help="Output directory (a timestamped subdir is created inside)",
    ),
    auto: bool = typer.Option(
        False, "--auto", help="Apply sensible-default cleansing without prompting"
    ),
    no_cleanse: bool = typer.Option(
        False, "--no-cleanse", help="Skip cleansing; profile and narrate only"
    ),
    model: str = typer.Option(
        None, "--model", help="Claude model ID (default: claude-sonnet-4-6 or $ANTHROPIC_MODEL)"
    ),
    sheet: str = typer.Option(
        None, "--sheet", help="Excel sheet name or index (default: first sheet)"
    ),
) -> None:
    """Run the full pipeline on a CSV or Excel file."""
    load_dotenv()
    console = Console()
    _banner(console)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            Panel(
                "[red]ANTHROPIC_API_KEY is not set.[/red]\n\n"
                "This tool uses Claude to generate data stories. Set the key via:\n"
                "  • environment: [cyan]export ANTHROPIC_API_KEY=sk-ant-...[/cyan]\n"
                "  • [cyan].env[/cyan] file in this directory (see [cyan].env.example[/cyan])",
                title="[red]✗ Missing API key[/red]",
                border_style="red",
                box=ROUNDED,
            )
        )
        raise typer.Exit(code=2)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output / f"{source.stem}_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = RunLogger(output_dir=output_dir, console=console)
    logger.log("INFO", f"Run ID: {run_id} · Output: {output_dir}")

    try:
        sheet_arg: str | int | None = None
        if sheet is not None:
            try:
                sheet_arg = int(sheet)
            except ValueError:
                sheet_arg = sheet

        df = load(source, logger, sheet=sheet_arg)
        rows_before = len(df)

        profile_data = profile(df, logger)

        if no_cleanse:
            logger.log("CLEANSE", "Skipped (--no-cleanse)")
            cleaned = df
        else:
            config = CleanseConfig.auto() if auto else CleanseConfig.auto()
            cleaned = cleanse(df, profile_data, logger, config)

        findings = generate_findings(cleaned, profile_data, logger)
        narration = narrate(findings, profile_data, logger, model=model)

        export_csv(cleaned, output_dir, logger)
        export_hyper(cleaned, output_dir, logger)
        export_insights(findings, narration, output_dir, logger)
        audit_path = logger.flush_audit()
        logger.log("EXPORT", f"Wrote {audit_path.name}")
        export_report(
            source_name=source.name,
            profile_data=profile_data,
            by_category=narration["by_category"],
            category_narratives=narration["category_narratives"],
            cleanse_audit=logger.cleanse_audit_entries(),
            output_dir=output_dir,
            logger=logger,
        )

        _print_summary(
            console=console,
            source=source,
            df_rows_before=rows_before,
            df_rows_after=len(cleaned),
            by_category=narration["by_category"],
            cleanse_audit=logger.cleanse_audit_entries(),
            output_dir=output_dir,
        )

    except NarrateError as e:
        logger.log("ERROR", str(e))
        console.print(Panel(str(e), title="[red]LLM error[/red]", border_style="red"))
        raise typer.Exit(code=3)
    except Exception as e:
        logger.log("ERROR", f"{type(e).__name__}: {e}")
        console.print(
            Panel(
                f"[red]{type(e).__name__}[/red]: {e}\n\nSee [cyan]{output_dir/'run.log'}[/cyan] for full log.",
                title="[red]✗ Failed[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
    finally:
        logger.close()


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"dataport-ai {__version__}")


if __name__ == "__main__":
    app()
