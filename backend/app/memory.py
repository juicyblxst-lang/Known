from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryResult:
    memories: list[dict[str, Any]]
    available: bool
    error: str | None = None


class SibylMemory:
    """Thin adapter around the official Sibyl Memory CLI.

    We intentionally keep the integration at a process boundary: the agent does
    not implement a second memory system and does not silently substitute a
    vector database when Sibyl is unavailable.
    """

    def __init__(self) -> None:
        self.command = os.getenv("SIBYL_COMMAND", "sibyl")
        self.workspace = os.getenv("SIBYL_WORKSPACE") or None

    def _run(self, *args: str) -> tuple[bool, str]:
        command = [self.command, *args]
        env = os.environ.copy()
        if self.workspace:
            env["SIBYL_WORKSPACE"] = self.workspace
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        output = (proc.stdout or proc.stderr).strip()
        return proc.returncode == 0, output

    def search(self, customer_id: str, query: str, limit: int = 8) -> MemoryResult:
        """Search customer-scoped durable memory.

        Sibyl CLI versions may expose different output flags, so we first ask
        for JSON and parse defensively. Unsupported output is reported instead
        of being fabricated.
        """
        ok, output = self._run(
            "search",
            query,
            "--customer-id",
            customer_id,
            "--limit",
            str(limit),
            "--json",
        )
        if not ok:
            return MemoryResult([], False, output)
        try:
            parsed = json.loads(output) if output else []
        except json.JSONDecodeError:
            return MemoryResult([], False, "Sibyl returned non-JSON output")
        if isinstance(parsed, dict):
            parsed = parsed.get("memories", parsed.get("results", []))
        if not isinstance(parsed, list):
            parsed = []
        return MemoryResult([x if isinstance(x, dict) else {"content": str(x)} for x in parsed], True)

    def remember(self, customer_id: str, content: str, memory_type: str = "fact") -> tuple[bool, str]:
        """Persist a durable, customer-scoped memory in Sibyl."""
        return self._run(
            "remember",
            content,
            "--customer-id",
            customer_id,
            "--type",
            memory_type,
        )
