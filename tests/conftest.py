"""Shared helpers: every test drives a skill through its launcher, exactly as Claude does."""

import json
import subprocess
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
LAUNCHERS = {"chem-tools": ROOT / "chem-tools/scripts/chem", "cdx-tools": ROOT / "cdx-tools/scripts/cdx"}


class Skill:
    def __init__(self, name: str, workdir: Path):
        self.name, self.workdir = name, workdir
        self.env = {
            **dict(__import__("os").environ),
            "CHEM_EXPORT_DIR": str(workdir / "exports"),
            "CHEM_WORKDIR": str(workdir),
            "CHEM_SKILLS_LOG_DIR": str(workdir / "logs"),
        }

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(LAUNCHERS[self.name]), *args], cwd=self.workdir,
                              env=self.env, capture_output=True, text=True, timeout=300)

    def call(self, tool: str, tool_input: dict | None = None) -> tuple[int, dict]:
        res = self.raw(tool, json.dumps(tool_input or {}))
        try:
            return res.returncode, json.loads(res.stdout)
        except json.JSONDecodeError:
            pytest.fail(f"{tool} printed non-JSON output:\n{res.stdout}\n{res.stderr}")

    def ok(self, tool: str, tool_input: dict | None = None) -> dict:
        code, out = self.call(tool, tool_input)
        assert code == 0 and "error" not in out, out
        return out

    def error(self, tool: str, tool_input: dict | None = None) -> str:
        code, out = self.call(tool, tool_input)
        assert code == 1 and "error" in out, out
        return out["error"]

    def log_entries(self) -> list[dict]:
        path = self.workdir / "logs" / f"{self.name}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture
def chem(tmp_path):
    return Skill("chem-tools", tmp_path)


@pytest.fixture
def cdx(tmp_path):
    return Skill("cdx-tools", tmp_path)


def _pubchem_up() -> bool:
    try:
        return requests.get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/702/property/Title/TXT",
                            timeout=8).ok
    except requests.RequestException:
        return False


PUBCHEM_UP = _pubchem_up()


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="PubChem unreachable")
    for item in items:
        if "network" in item.keywords and not PUBCHEM_UP:
            item.add_marker(skip)
