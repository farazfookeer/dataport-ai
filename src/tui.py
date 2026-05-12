"""Textual TUI for Dataport AI for Tableau.

Four screens:
  1. Setup    — Two-pane setup: form on the left, pipeline preview on the right
  2. Run      — Live streaming logs with stage timeline + spinner
  3. Results  — Categorized story counts, output file list, open-report shortcut
  4. Error    — Traceback view with back-to-setup
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, set_key
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    Switch,
)

from .cleanse import CleanseConfig, cleanse
from .export import export_csv, export_hyper, export_insights, export_report
from .ingest import load
from .insights import generate_findings
from .logger import RunLogger
from .narrate import CATEGORY_TO_VIZ, NarrateError, narrate
from .profile import profile


STAGE_COLOR = {
    "INGEST": "cyan",
    "PROFILE": "magenta",
    "CLEANSE": "yellow",
    "INSIGHTS": "green",
    "NARRATE": "blue",
    "EXPORT": "white",
    "ERROR": "red bold",
    "INFO": "dim",
}

PIPELINE_STAGES = [
    ("①", "INGEST",   "Read CSV / Excel",        "cyan"),
    ("②", "PROFILE",  "Types · stats · dupes",   "magenta"),
    ("③", "CLEANSE",  "Audited fixes",           "yellow"),
    ("④", "INSIGHTS", "Trends · outliers",       "green"),
    ("⑤", "NARRATE",  "Claude data stories",     "blue"),
    ("⑥", "EXPORT",   ".hyper · CSV · HTML",     "white"),
]

OUTPUT_FILES = [
    ("report.html",         "Categorized stories"),
    ("cleaned.hyper",       "Tableau extract"),
    ("cleaned.csv",         "Portable backup"),
    ("insights.json",       "Findings JSON"),
    ("cleanse_audit.json",  "Every cleanse op"),
    ("run.log",             "Full step log"),
]


# ───────────────────────────── Setup screen ──────────────────────────────


class SetupScreen(Screen):
    CSS = """
    SetupScreen {
        background: $background;
    }

    #title-bar {
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }
    #subtitle-bar {
        height: 1;
        color: $text-muted;
        content-align: center middle;
        background: $surface;
    }

    #main-grid {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 3fr 2fr;
        grid-gutter: 1;
        padding: 1;
        height: 1fr;
    }

    .section {
        border: round $accent;
        padding: 0 2;
        margin-bottom: 1;
        height: auto;
        background: $surface;
    }
    .section-source     { border: round $primary 50%;  }
    .section-creds      { border: round $warning 60%;  }
    .section-options    { border: round $accent 60%;   }
    .section-preview    { border: round $success 60%;  }
    .section-bundle     { border: round $accent 50%;   }

    .field-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .hint {
        color: $text-muted;
        text-style: italic;
    }
    .status-ok      { color: $success; }
    .status-warn    { color: $warning; }
    .status-error   { color: $error;   }

    #status-line {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    #button-bar {
        height: 3;
        align-horizontal: right;
        padding: 0 1;
        background: $surface;
    }

    #save-row {
        height: 3;
        margin-top: 1;
    }
    #save-row Switch {
        margin-right: 1;
    }
    #save-row Label {
        height: 3;
        content-align: left middle;
    }
    #get-key-btn {
        width: 100%;
        margin-top: 1;
        background: $primary 30%;
        color: $text;
    }

    .pipeline-row {
        height: 1;
        color: $text;
    }
    .file-row {
        height: 1;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("ctrl+r",       "submit", "Run", show=True),
        Binding("f1",           "help",   "Help", show=True),
        Binding("question_mark", "help",   "Help", show=False),
        Binding("ctrl+q",       "quit",   "Quit", show=True),
    ]

    file_status: reactive[str] = reactive("")
    key_status:  reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("📊  D A T A P O R T   A I   ·   f o r   T a b l e a u", id="title-bar")
        yield Static("AI-powered data ingestion · profile · cleanse · narrate · export", id="subtitle-bar")

        with Container(id="main-grid"):
            # ── LEFT pane: form ──
            with VerticalScroll():
                with Container(classes="section section-source") as src:
                    src.border_title = "📂 Source"
                    yield Label("File (CSV, TSV, or Excel)", classes="field-label")
                    yield Input(
                        placeholder="path/to/data.csv",
                        id="source-input",
                        value=self._guess_default_source(),
                    )
                    yield Static("", id="file-status", classes="hint")

                with Container(classes="section section-creds") as cr:
                    cr.border_title = "🔑 Anthropic credentials (BYOK)"
                    yield Label("API key", classes="field-label")
                    yield Input(
                        placeholder="sk-ant-…",
                        id="api-key-input",
                        password=True,
                        value=os.environ.get("ANTHROPIC_API_KEY", ""),
                    )
                    yield Static("", id="key-status", classes="hint")
                    yield Button(
                        "🔗  Don't have a key? Get one (opens browser)",
                        id="get-key-btn",
                        variant="primary",
                    )
                    yield Label("Model", classes="field-label")
                    yield Input(
                        value=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                        id="model-input",
                    )
                    with Horizontal(id="save-row"):
                        yield Switch(value=False, id="save-key-switch")
                        yield Label("Save key to .env for future runs")

                with Container(classes="section section-options") as opt:
                    opt.border_title = "⚙ Options"
                    yield Label("Cleanse mode", classes="field-label")
                    yield Select(
                        options=[
                            ("Auto-clean (sensible defaults)", "auto"),
                            ("Skip cleansing", "none"),
                        ],
                        value="auto",
                        id="cleanse-select",
                        allow_blank=False,
                    )

            # ── RIGHT pane: preview / info ──
            with VerticalScroll():
                with Container(classes="section section-preview") as p:
                    p.border_title = "⚡ Pipeline"
                    for icon, name, desc, color in PIPELINE_STAGES:
                        yield Static(
                            f"  [bold {color}]{icon} {name:<9}[/bold {color}]"
                            f" [dim]{desc}[/dim]",
                            classes="pipeline-row",
                        )

                with Container(classes="section section-bundle") as b:
                    b.border_title = "📦 Output bundle"
                    for name, desc in OUTPUT_FILES:
                        yield Static(
                            f"  [cyan]{name:<20}[/cyan] [dim]{desc}[/dim]",
                            classes="file-row",
                        )

        yield Static("", id="status-line")
        with Horizontal(id="button-bar"):
            yield Button("Help (F1)", variant="default", id="help-btn")
            yield Button("Quit (Ctrl+Q)", variant="default", id="quit-btn")
            yield Button("▶  Run pipeline  (Ctrl+R)", variant="success", id="run-btn")

        yield Footer()

    def on_mount(self) -> None:
        self._update_file_status(self.query_one("#source-input", Input).value)
        self._update_key_status(self.query_one("#api-key-input", Input).value)

    # ── reactive validation ──

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "source-input":
            self._update_file_status(event.value)
        elif event.input.id == "api-key-input":
            self._update_key_status(event.value)

    def _update_file_status(self, value: str) -> None:
        status = self.query_one("#file-status", Static)
        v = value.strip()
        if not v:
            status.update("[dim italic]Enter a path to a CSV or Excel file[/dim italic]")
            return
        path = Path(v).expanduser()
        if not path.exists():
            status.update(f"[$error]✗ File not found: {path}[/$error]")
            return
        suffix = path.suffix.lower()
        if suffix not in {".csv", ".tsv", ".xlsx", ".xls"}:
            status.update(f"[$error]✗ Unsupported extension: {suffix}[/$error]")
            return
        size = path.stat().st_size
        size_str = self._format_size(size)
        kind = "CSV" if suffix == ".csv" else "TSV" if suffix == ".tsv" else "Excel"
        status.update(f"[$success]✓ {kind} · {size_str}[/$success]")

    def _update_key_status(self, value: str) -> None:
        status = self.query_one("#key-status", Static)
        v = value.strip()
        if not v:
            status.update("[dim italic]Required — get one at console.anthropic.com[/dim italic]")
        elif not v.startswith("sk-"):
            status.update("[$warning]⚠ Doesn't look like an Anthropic key (expected sk-…)[/$warning]")
        else:
            masked = f"{v[:7]}…{v[-4:]}" if len(v) > 12 else "…"
            status.update(f"[$success]✓ {masked}[/$success]")

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    @staticmethod
    def _guess_default_source() -> str:
        candidate = Path("samples/student_grades.csv")
        return str(candidate) if candidate.exists() else ""

    # ── actions ──

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-btn":
            self.app.exit()
        elif event.button.id == "run-btn":
            self.action_submit()
        elif event.button.id == "help-btn":
            self.action_help()
        elif event.button.id == "get-key-btn":
            self._open_url("https://console.anthropic.com/settings/keys")

    def _open_url(self, url: str) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", url], check=False)
            elif sys.platform == "win32":
                os.startfile(url)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", url], check=False)
        except Exception:
            self.query_one("#status-line", Static).update(
                f"[$warning]Couldn't open browser. Visit: {url}[/$warning]"
            )

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_submit(self) -> None:
        status = self.query_one("#status-line", Static)
        source_val = self.query_one("#source-input", Input).value.strip()
        api_key = self.query_one("#api-key-input", Input).value.strip()
        save_key = self.query_one("#save-key-switch", Switch).value
        cleanse_mode = self.query_one("#cleanse-select", Select).value
        model = (
            self.query_one("#model-input", Input).value.strip() or "claude-sonnet-4-6"
        )

        if not source_val:
            status.update("[$error]✗ Source file is required[/$error]")
            return
        source = Path(source_val).expanduser()
        if not source.exists():
            status.update(f"[$error]✗ File not found: {source}[/$error]")
            return
        if source.suffix.lower() not in {".csv", ".tsv", ".xlsx", ".xls"}:
            status.update(f"[$error]✗ Unsupported file type: {source.suffix}[/$error]")
            return
        if not api_key:
            status.update("[$error]✗ Anthropic API key is required (BYOK)[/$error]")
            return

        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_MODEL"] = model

        if save_key:
            env_path = Path(".env")
            env_path.touch(exist_ok=True)
            set_key(str(env_path), "ANTHROPIC_API_KEY", api_key)
            set_key(str(env_path), "ANTHROPIC_MODEL", model)

        self.app.push_screen(
            RunScreen(source=source, cleanse_mode=cleanse_mode, model=model)
        )

    def action_quit(self) -> None:
        self.app.exit()


# ───────────────────────────── Run screen ────────────────────────────────


class RunScreen(Screen):
    BINDINGS = [Binding("ctrl+c", "cancel", "Cancel")]

    CSS = """
    RunScreen {
        layout: vertical;
    }
    #run-title-bar {
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }
    #timeline {
        height: 3;
        padding: 1 2;
        background: $surface;
    }
    #log {
        border: round $accent;
        margin: 1;
        background: $background;
    }
    """

    current_stage: reactive[str] = reactive("INFO")

    def __init__(self, source: Path, cleanse_mode: str, model: str) -> None:
        super().__init__()
        self.source = source
        self.cleanse_mode = cleanse_mode
        self.model = model
        self.output_dir: Path | None = None
        self.result: dict[str, Any] | None = None
        self.rich_log: RichLog | None = None
        self._stages_done: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f"▶ Running pipeline on [bold]{self.source.name}[/bold]",
            id="run-title-bar",
        )
        yield Static(self._render_timeline(), id="timeline")
        self.rich_log = RichLog(highlight=True, markup=True, id="log", wrap=False)
        yield self.rich_log
        yield Footer()

    def watch_current_stage(self, new_stage: str) -> None:
        if new_stage in (s[1] for s in PIPELINE_STAGES):
            self._stages_done.add(new_stage)
        try:
            self.query_one("#timeline", Static).update(self._render_timeline())
        except Exception:
            pass

    def _render_timeline(self) -> str:
        parts = []
        for icon, name, _desc, color in PIPELINE_STAGES:
            if name in self._stages_done and name != self.current_stage:
                parts.append(f"[$success]✓ {name}[/$success]")
            elif name == self.current_stage:
                parts.append(f"[bold {color}]▶ {name}[/bold {color}]")
            else:
                parts.append(f"[dim]{icon} {name}[/dim]")
        return "  ".join(parts)

    def on_mount(self) -> None:
        self._run_pipeline()

    def _on_log(self, ts: str, stage: str, message: str) -> None:
        color = STAGE_COLOR.get(stage, "white")
        line = f"[dim]{ts}[/dim]  [{color}]{stage:<9}[/{color}]  {message}"
        self.app.call_from_thread(self.rich_log.write, line)
        self.app.call_from_thread(setattr, self, "current_stage", stage)

    @work(thread=True, exclusive=True)
    def _run_pipeline(self) -> None:
        try:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = Path("outputs") / f"{self.source.stem}_{run_id}"
            self.output_dir.mkdir(parents=True, exist_ok=True)

            logger = RunLogger(output_dir=self.output_dir, on_log=self._on_log)

            try:
                logger.log("INFO", f"Run ID: {run_id}")
                logger.log("INFO", f"Output: {self.output_dir}")

                df = load(self.source, logger)
                rows_before = len(df)
                profile_data = profile(df, logger)

                if self.cleanse_mode == "none":
                    logger.log("CLEANSE", "Skipped (user selected 'no cleanse')")
                    cleaned = df
                else:
                    cleaned = cleanse(df, profile_data, logger, CleanseConfig.auto())

                findings = generate_findings(cleaned, profile_data, logger)
                narration = narrate(findings, profile_data, logger, model=self.model)

                export_csv(cleaned, self.output_dir, logger)
                export_hyper(cleaned, self.output_dir, logger)
                export_insights(findings, narration, self.output_dir, logger)
                audit_path = logger.flush_audit()
                logger.log("EXPORT", f"Wrote {audit_path.name}")
                report_path = export_report(
                    source_name=self.source.name,
                    profile_data=profile_data,
                    by_category=narration["by_category"],
                    category_narratives=narration["category_narratives"],
                    cleanse_audit=logger.cleanse_audit_entries(),
                    output_dir=self.output_dir,
                    logger=logger,
                )

                self.result = {
                    "source": self.source,
                    "output_dir": self.output_dir,
                    "rows_before": rows_before,
                    "rows_after": len(cleaned),
                    "by_category": narration["by_category"],
                    "cleanse_audit": logger.cleanse_audit_entries(),
                    "report_path": report_path,
                }
            finally:
                logger.close()

            self.app.call_from_thread(self._finish)
        except NarrateError as e:
            self.app.call_from_thread(self._fail, f"LLM error: {e}")
        except Exception as e:
            tb = traceback.format_exc()
            self.app.call_from_thread(self._fail, f"{type(e).__name__}: {e}\n\n{tb}")

    def _finish(self) -> None:
        self.app.push_screen(ResultsScreen(self.result))

    def _fail(self, message: str) -> None:
        if self.rich_log:
            self.rich_log.write("[red bold]✗ FAILED[/red bold]")
            self.rich_log.write(f"[red]{message}[/red]")
        self.app.push_screen(ErrorScreen(message, self.output_dir))

    def action_cancel(self) -> None:
        self.app.exit(message="Run cancelled.")


# ───────────────────────────── Results screen ────────────────────────────


class ResultsScreen(Screen):
    BINDINGS = [
        Binding("o", "open_report",  "Open report",  show=True),
        Binding("n", "run_another",  "Run another",  show=True),
        Binding("q", "quit",         "Quit",         show=True),
    ]

    CSS = """
    ResultsScreen {
        layout: vertical;
    }
    #results-title-bar {
        height: 3;
        background: $success;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }
    #summary-grid {
        layout: grid;
        grid-size: 4 1;
        grid-gutter: 1;
        height: 5;
        padding: 1;
    }
    .stat-card {
        border: round $accent;
        padding: 0 1;
        content-align: center middle;
        background: $surface;
    }
    #results-main {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 3fr 2fr;
        grid-gutter: 1;
        height: 1fr;
        padding: 0 1;
    }
    #category-table {
        border: round $primary;
        background: $surface;
    }
    #file-panel {
        border: round $success;
        padding: 0 2;
        background: $surface;
    }
    #button-bar {
        height: 3;
        align-horizontal: right;
        padding: 0 1;
    }
    """

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("✓  Run complete", id="results-title-bar")

        r = self.result
        with Container(id="summary-grid"):
            yield Static(
                f"[bold]Source[/bold]\n[cyan]{r['source'].name}[/cyan]",
                classes="stat-card",
            )
            yield Static(
                f"[bold]Rows[/bold]\n[yellow]{r['rows_before']:,} → {r['rows_after']:,}[/yellow]",
                classes="stat-card",
            )
            yield Static(
                f"[bold]Cleanse ops[/bold]\n[magenta]{len(r['cleanse_audit'])}[/magenta]",
                classes="stat-card",
            )
            total_stories = sum(len(v) for v in r["by_category"].values())
            yield Static(
                f"[bold]Stories[/bold]\n[green]{total_stories} across {len(r['by_category'])} cats[/green]",
                classes="stat-card",
            )

        with Container(id="results-main"):
            table = DataTable(id="category-table", zebra_stripes=True, cursor_type="row")
            table.add_columns("Category", "Stories", "Suggested Tableau viz")
            if r["by_category"]:
                for cat, stories in r["by_category"].items():
                    table.add_row(
                        cat,
                        str(len(stories)),
                        ", ".join(CATEGORY_TO_VIZ.get(cat, [])),
                    )
            else:
                table.add_row("—", "0", "—")
            yield table

            with Container(id="file-panel") as fp:
                fp.border_title = "📦 Output bundle"
                yield Static(self._build_files_text())

        with Horizontal(id="button-bar"):
            yield Button("Quit (q)", id="quit-btn")
            yield Button("Run another (n)", variant="primary", id="another-btn")
            yield Button("📂 Open report (o)", variant="success", id="open-btn")
        yield Footer()

    def _build_files_text(self) -> str:
        d = self.result["output_dir"]
        lines = []
        for name, desc in OUTPUT_FILES:
            path = d / name
            if path.exists():
                size = path.stat().st_size
                size_str = SetupScreen._format_size(size)
                lines.append(
                    f"[$success]✓[/$success] [cyan]{name:<22}[/cyan] "
                    f"[dim]{desc} · {size_str}[/dim]"
                )
            else:
                lines.append(
                    f"[dim]·[/dim] [dim]{name:<22}[/dim] [dim]{desc} · not created[/dim]"
                )
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-btn":
            self.action_quit()
        elif event.button.id == "another-btn":
            self.action_run_another()
        elif event.button.id == "open-btn":
            self.action_open_report()

    def action_open_report(self) -> None:
        path = self.result.get("report_path")
        if not path or not Path(path).exists():
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            elif sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception:
            pass

    def action_run_another(self) -> None:
        self.app.pop_screen()
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


# ───────────────────────────── Error screen ──────────────────────────────


class ErrorScreen(Screen):
    BINDINGS = [
        Binding("b", "back", "Back to setup", show=True),
        Binding("q", "quit", "Quit",          show=True),
    ]

    CSS = """
    ErrorScreen { align: center middle; background: $background; }
    #err-box {
        width: 90%;
        height: 80%;
        border: round $error;
        padding: 1 2;
        background: $surface;
    }
    #err-title { color: $error; text-style: bold; height: 1; }
    #err-msg   { color: $text;  margin-top: 1; }
    #err-buttons {
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }
    """

    def __init__(self, message: str, output_dir: Path | None) -> None:
        super().__init__()
        self.message = message
        self.output_dir = output_dir

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="err-box"):
            yield Static("✗ Run failed", id="err-title")
            with VerticalScroll():
                yield Static(self.message, id="err-msg")
                if self.output_dir is not None:
                    yield Static(
                        f"\n[dim]Full log: {self.output_dir / 'run.log'}[/dim]"
                    )
            with Horizontal(id="err-buttons"):
                yield Button("Quit (q)", id="quit-btn")
                yield Button("Back to setup (b)", variant="primary", id="back-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_back()
        elif event.button.id == "quit-btn":
            self.action_quit()

    def action_back(self) -> None:
        self.app.pop_screen()
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


# ───────────────────────────── Help screen ──────────────────────────────


HELP_TEXT = """[bold cyan]What is Dataport AI for Tableau?[/bold cyan]

An AI-powered ingestion layer for Tableau. Drop in a CSV or Excel file and it will:

  [yellow]1.[/yellow] [bold]Profile[/bold] the data — detect types, missing values, duplicates, outliers
  [yellow]2.[/yellow] [bold]Cleanse[/bold] it — every fix is logged so you can defend each decision
  [yellow]3.[/yellow] [bold]Find insights[/bold] — trends, correlations, segments, anomalies
  [yellow]4.[/yellow] [bold]Narrate with Claude[/bold] — turn raw findings into plain-English data stories,
     grouped into 8 categories (Trends, Anomalies, Distributions, Relationships,
     Segments, Comparisons, Composition, Data Quality)
  [yellow]5.[/yellow] [bold]Export[/bold] — Tableau .hyper extract + cleaned CSV + HTML report

[bold cyan]Getting an Anthropic API key (one-time)[/bold cyan]

The narration step uses Claude. You bring your own key (BYOK):

  • Go to [bold]console.anthropic.com[/bold] and sign up
    (or click the "🔗 Don't have a key?" button on the setup screen)
  • Settings → API keys → 'Create Key'
  • Paste it into the API key field in this app
  • Toggle 'Save key to .env' so you only have to do this once

Cost is tiny — a typical run uses about $0.01-0.05 of API credit.

[bold cyan]Output files[/bold cyan]

Each run creates a timestamped folder in [magenta]outputs/[/magenta] with:

  [cyan]report.html[/cyan]         Pretty HTML report — open in any browser
  [cyan]cleaned.hyper[/cyan]       Drag this into Tableau Desktop for an instant extract
  [cyan]cleaned.csv[/cyan]         Same data as CSV (portable, type info lost)
  [cyan]insights.json[/cyan]       Machine-readable findings (for further analysis)
  [cyan]cleanse_audit.json[/cyan]  Every single cleansing decision, with reasoning
  [cyan]run.log[/cyan]             Step-by-step log of everything that happened

[bold cyan]Keyboard shortcuts[/bold cyan]

  [yellow]Ctrl+R[/yellow]   Run the pipeline
  [yellow]F1[/yellow]       This help screen
  [yellow]Ctrl+Q[/yellow]   Quit
  [yellow]Tab[/yellow]      Move between fields

[bold cyan]Troubleshooting[/bold cyan]

  [red]"Hyper API unavailable"[/red] — the .hyper file is skipped but cleaned.csv is still
                            written. You can load the CSV into Tableau directly.

  [red]"LLM error"[/red]             — usually a bad API key or no internet. Double-check the
                            key (it should start with [bold]sk-ant-[/bold]).

  [red]"File not found"[/red]        — paths are relative to wherever you launched the app.
                            Drop files into the [magenta]samples/[/magenta] folder for easy access.
"""


class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
        Binding("q",      "close", "Close", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: $background;
    }
    #help-box {
        width: 90%;
        height: 90%;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #help-title {
        height: 1;
        color: $accent;
        text-style: bold;
        content-align: center middle;
        margin-bottom: 1;
    }
    #help-content {
        height: 1fr;
    }
    #help-buttons {
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="help-box"):
            yield Static("📖  Help & Getting Started", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(HELP_TEXT)
            with Horizontal(id="help-buttons"):
                yield Button("Close (Esc)", variant="primary", id="close-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.action_close()

    def action_close(self) -> None:
        self.app.pop_screen()


# ─────────────────────────────── App ─────────────────────────────────────


class ConnectorApp(App):
    TITLE = "Dataport AI for Tableau"
    SUB_TITLE = "AI-powered data ingestion · Profile · Cleanse · Narrate · Export"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True, show=False)]

    def on_mount(self) -> None:
        load_dotenv()
        self.push_screen(SetupScreen())


def main() -> None:
    ConnectorApp().run()


if __name__ == "__main__":
    main()
