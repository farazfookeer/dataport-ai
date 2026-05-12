"""Capture SVG screenshots of each TUI screen for the README.

Uses Textual's pilot API to drive the app and `save_screenshot` to export SVG.
Skips the real pipeline run (no API key needed) by injecting fake data into
Run and Results screens.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from src.narrate import CATEGORY_TO_VIZ
from src.tui import ConnectorApp, ResultsScreen, RunScreen, HelpScreen, SetupScreen

OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

TERM_SIZE = (130, 42)


# ─── fake data for the Results screen ──────────────────────────────────────

FAKE_RESULT = {
    "source": Path("samples/student_grades.csv"),
    "output_dir": Path("outputs/student_grades_20260513_142301"),
    "rows_before": 51,
    "rows_after": 50,
    "cleanse_audit": [
        {"operation": "dedupe", "rows_affected": 1},
        {"operation": "strip_whitespace", "rows_affected": 1},
        {"operation": "coerce_datetime", "rows_affected": 49},
        {"operation": "fill_missing", "rows_affected": 2},
        {"operation": "fill_missing", "rows_affected": 1},
        {"operation": "fill_missing", "rows_affected": 1},
        {"operation": "fill_missing", "rows_affected": 1},
    ],
    "by_category": {
        "Relationships": [{"headline": f"Strong correlation #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Relationships"],
                           "raw_finding": {}} for i in range(6)],
        "Trends":        [{"headline": f"Upward trend #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Trends"],
                           "raw_finding": {}} for i in range(5)],
        "Segments":      [{"headline": f"Segment finding #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Segments"],
                           "raw_finding": {}} for i in range(5)],
        "Distributions": [{"headline": f"Skew finding #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Distributions"],
                           "raw_finding": {}} for i in range(2)],
        "Anomalies":     [{"headline": f"Outlier finding #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Anomalies"],
                           "raw_finding": {}} for i in range(2)],
        "Composition":   [{"headline": f"Composition #{i}", "story": "...",
                           "viz_recommendations": CATEGORY_TO_VIZ["Composition"],
                           "raw_finding": {}} for i in range(2)],
    },
    "report_path": Path("outputs/student_grades_20260513_142301/report.html"),
}

FAKE_LOG_LINES = [
    ("INFO",     "Run ID: 20260513_142301"),
    ("INFO",     "Output: outputs/student_grades_20260513_142301"),
    ("INGEST",   "Reading student_grades.csv (2.8KB)"),
    ("INGEST",   "Loaded 51 rows × 11 columns"),
    ("PROFILE",  "Profiling 51 rows × 11 columns"),
    ("PROFILE",  "Types: 6 numeric · 3 categorical · 1 datetime · 1 bool"),
    ("PROFILE",  "Found 1 duplicate rows · 1.07% cells missing"),
    ("CLEANSE",  "Beginning cleansing pass"),
    ("CLEANSE",  "dedupe rule=exact_row_match rows_affected=1"),
    ("CLEANSE",  "strip_whitespace column='student_id' rows_affected=1"),
    ("CLEANSE",  "coerce_datetime column='enrollment_date' rows_affected=49"),
    ("CLEANSE",  "fill_missing column='study_hours_per_week' rows_affected=2"),
    ("CLEANSE",  "fill_missing column='attendance_pct' rows_affected=1"),
    ("CLEANSE",  "Cleansing complete: 50 rows × 11 columns remain"),
    ("INSIGHTS", "Scanning for trends, outliers, and relationships"),
    ("INSIGHTS", "Generated 22 raw findings"),
    ("NARRATE",  "Calling claude-sonnet-4-6 with 22 findings"),
]


# ─── monkey-patched RunScreen that skips the real worker ───────────────────

class FakeRunScreen(RunScreen):
    def on_mount(self) -> None:  # type: ignore[override]
        # Don't kick off the real pipeline. Write log lines directly
        # (bypass _on_log which uses call_from_thread).
        from src.tui import STAGE_COLOR
        for stage, msg in FAKE_LOG_LINES:
            color = STAGE_COLOR.get(stage, "white")
            line = f"[dim]14:23:0X[/dim]  [{color}]{stage:<9}[/{color}]  {msg}"
            self.rich_log.write(line)
            if stage in (s[1] for s in __import__("src.tui", fromlist=["PIPELINE_STAGES"]).PIPELINE_STAGES):
                self._stages_done.add(stage)
        self.current_stage = "NARRATE"
        # Force timeline refresh
        try:
            self.query_one("#timeline").update(self._render_timeline())
        except Exception:
            pass


# ─── capture flows ─────────────────────────────────────────────────────────

async def _wait_for(app: ConnectorApp, pilot, screen_type, tries: int = 20):
    for _ in range(tries):
        if isinstance(app.screen, screen_type):
            return
        await pilot.pause()
    raise RuntimeError(f"Screen {screen_type.__name__} never became active")


async def run_setup_capture() -> None:
    app = ConnectorApp()
    async with app.run_test(size=TERM_SIZE) as pilot:
        await _wait_for(app, pilot, SetupScreen)
        api_input = app.screen.query_one("#api-key-input")
        api_input.value = "sk-ant-api03-aB7XnQ8YzL4kVm9wPqR2sT5vWx0z1aBcDeFgHiJkLmNoPqRs"
        await pilot.pause()
        app.save_screenshot("01_setup.svg", path=str(OUT))
        print(f"✓ {OUT}/01_setup.svg")


async def run_help_capture() -> None:
    app = ConnectorApp()
    async with app.run_test(size=TERM_SIZE) as pilot:
        await _wait_for(app, pilot, SetupScreen)
        await pilot.press("f1")
        await _wait_for(app, pilot, HelpScreen)
        app.save_screenshot("02_help.svg", path=str(OUT))
        print(f"✓ {OUT}/02_help.svg")


async def run_run_capture() -> None:
    app = ConnectorApp()
    async with app.run_test(size=TERM_SIZE) as pilot:
        await _wait_for(app, pilot, SetupScreen)
        app.push_screen(
            FakeRunScreen(
                source=Path("samples/student_grades.csv"),
                cleanse_mode="auto",
                model="claude-sonnet-4-6",
            )
        )
        await _wait_for(app, pilot, FakeRunScreen)
        await pilot.pause()
        await pilot.pause()
        app.save_screenshot("03_run.svg", path=str(OUT))
        print(f"✓ {OUT}/03_run.svg")


async def run_results_capture() -> None:
    app = ConnectorApp()
    async with app.run_test(size=TERM_SIZE) as pilot:
        await _wait_for(app, pilot, SetupScreen)
        app.push_screen(ResultsScreen(FAKE_RESULT))
        await _wait_for(app, pilot, ResultsScreen)
        await pilot.pause()
        app.save_screenshot("04_results.svg", path=str(OUT))
        print(f"✓ {OUT}/04_results.svg")


async def main() -> None:
    await run_setup_capture()
    await run_help_capture()
    await run_run_capture()
    await run_results_capture()


if __name__ == "__main__":
    asyncio.run(main())
