"""Version info, error logging and bug reports. Identical in chem-tools and cdx-tools.

Every failed tool call (and every call when CHEM_SKILLS_DEBUG=1) is appended as one JSON line to
${XDG_CACHE_HOME:-~/.cache}/chem-skills/logs/<skill>.jsonl (override with CHEM_SKILLS_LOG_DIR). `bash scripts/<launcher> report`
turns the latest entries plus a system check into a Markdown bug report users can send back.
Nothing leaves the machine unless the user shares the report.
"""

import datetime as _dt
import json
import os
import re
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MAX_LOG_BYTES = 1_000_000


def _frontmatter(key: str) -> str | None:
    try:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    m = re.search(rf"^\s*{key}:\s*[\"']?([^\"'\n]+)", head, re.MULTILINE)
    return m.group(1).strip() if m else None


SKILL_NAME = _frontmatter("name") or SKILL_DIR.name
VERSION = _frontmatter("version") or "unknown"


def log_path() -> Path:
    base = Path(os.environ.get("CHEM_SKILLS_LOG_DIR") or
                Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "chem-skills" / "logs")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:  # read-only home in some sandboxes
        base = Path(tempfile.gettempdir()) / "chem-skills-logs"
        base.mkdir(parents=True, exist_ok=True)
    return base / f"{SKILL_NAME}.jsonl"


def log_call(tool: str, tool_input: dict, result: dict, is_error: bool, tb: str | None = None) -> None:
    """Record errors always, and every call when CHEM_SKILLS_DEBUG=1. Never raises."""
    if not is_error and not os.environ.get("CHEM_SKILLS_DEBUG"):
        return
    try:
        path = log_path()
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_suffix(".jsonl.1"))
        entry = {
            "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "skill": SKILL_NAME, "version": VERSION, "tool": tool,
            "input": tool_input, "ok": not is_error,
            # An unexpected exception (with traceback) is a bug; a plain error is usually bad input
            "kind": "bug" if tb else ("error" if is_error else "ok"),
            "result": result if is_error else {k: result[k] for k in list(result)[:6]},
        }
        if tb:
            entry["traceback"] = tb[-4000:]
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def recent_entries(n: int = 5, only_errors: bool = True) -> list[dict]:
    path = log_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not only_errors or not e.get("ok"):
            entries.append(e)
    return entries[-n:]


def report(n: int = 5) -> str:
    """Markdown bug report: versions, environment check and the latest failures."""
    from check_env import check

    rep = check()
    lines = [
        f"## {SKILL_NAME} {VERSION} bug report",
        "",
        f"- Generated: {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"- Platform: {rep.get('platform')}; Python {rep['python']['version']} via {rep.get('runner')}",
        f"- RDKit: {rep.get('rdkit', {}).get('version', rep.get('rdkit'))}",
        f"- Network: {json.dumps(rep.get('network', {}))}",
        f"- Ready: {rep['ready']}",
    ]
    for label, items in (("Problems", rep["problems"]), ("Warnings", rep["warnings"])):
        if items:
            lines += ["", f"**{label}:**"] + [f"- {i}" for i in items]
    entries = recent_entries(n)
    lines += ["", f"### Last {len(entries)} failed calls (log: `{log_path()}`)"]
    if not entries:
        lines.append("None recorded.")
    for e in entries:
        lines += ["", f"**{e['time']} · `{e['tool']}` · {e['kind']}** (v{e.get('version')})",
                  "```json", json.dumps(e.get("input"), ensure_ascii=False), "```",
                  f"Error: {e.get('result', {}).get('error', e.get('result'))}"]
        if e.get("traceback"):
            lines += ["```", e["traceback"].strip(), "```"]
    lines += ["", "_Review before sharing: tool inputs above may include compound names or file paths._"]
    return "\n".join(lines)
