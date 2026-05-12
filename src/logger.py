from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.text import Text

LogCallback = Callable[[str, str, str], None]  # (timestamp, stage, message)

STAGE_STYLES = {
    "INGEST": "bold cyan",
    "PROFILE": "bold magenta",
    "CLEANSE": "bold yellow",
    "INSIGHTS": "bold green",
    "NARRATE": "bold blue",
    "EXPORT": "bold white",
    "ERROR": "bold red",
    "INFO": "dim",
}


class RunLogger:
    """Logs every step to console (Rich), text file (run.log), and a structured
    cleanse audit (cleanse_audit.json)."""

    def __init__(
        self,
        output_dir: Path,
        console: Console | None = None,
        on_log: LogCallback | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = console or Console()
        self.on_log = on_log
        self.log_path = self.output_dir / "run.log"
        self.audit_path = self.output_dir / "cleanse_audit.json"
        self._log_fh = self.log_path.open("w", encoding="utf-8")
        self._cleanse_audit: list[dict[str, Any]] = []

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log(self, stage: str, message: str) -> None:
        stage = stage.upper()
        style = STAGE_STYLES.get(stage, "white")
        ts = self._now()

        if self.on_log is not None:
            try:
                self.on_log(ts, stage, message)
            except Exception:
                pass
        else:
            text = Text()
            text.append(f"[{ts}] ", style="dim")
            text.append(f"{stage:<9}", style=style)
            text.append(message)
            self.console.print(text)

        self._log_fh.write(f"{datetime.now().isoformat()} [{stage}] {message}\n")
        self._log_fh.flush()

    def audit_cleanse(
        self,
        operation: str,
        column: str | None,
        rule: str,
        rows_affected: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a structured cleanse operation and emit a console line."""
        entry = {
            "timestamp": self._now_iso(),
            "operation": operation,
            "column": column,
            "rule": rule,
            "rows_affected": rows_affected,
            "details": details or {},
        }
        self._cleanse_audit.append(entry)

        col = f" column='{column}'" if column else ""
        self.log(
            "CLEANSE",
            f"{operation}{col} rule={rule} rows_affected={rows_affected}",
        )

    def cleanse_audit_entries(self) -> list[dict[str, Any]]:
        return list(self._cleanse_audit)

    def flush_audit(self) -> Path:
        self.audit_path.write_text(
            json.dumps(self._cleanse_audit, indent=2), encoding="utf-8"
        )
        return self.audit_path

    def close(self) -> None:
        try:
            self._log_fh.close()
        except Exception:
            pass
