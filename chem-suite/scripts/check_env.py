"""`check` command: report whether this machine is ready to run this skill and its companion.

Deliberately imports nothing heavy at module level so it can report a missing RDKit
instead of crashing on it. The same file ships in chem-tools and cdx-tools; only the
settings block below differs.
"""

import glob
import os
import platform
import subprocess
import sys
from pathlib import Path

# ---- per-skill settings
COMPANION = None                    # chem-suite contains both toolsets
COMPANION_LAUNCHER = ""
COMPANION_PROBE = ""
COMPANION_ROLE = ""
ENDPOINTS = {"pubchem": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/Title/TXT",
             "chembl": "https://www.ebi.ac.uk/chembl/api/data/status.json"}
CHECK_CHEMDRAW = True
# ----

SKILL_DIR = Path(__file__).resolve().parent.parent


def _companion_candidates() -> list[Path]:
    home = Path.home()
    env = os.environ.get(COMPANION.upper().replace("-", "_") + "_DIR", "")
    patterns = [
        env,
        str(SKILL_DIR.parent / COMPANION),                         # installed side by side
        str(home / ".claude/skills" / COMPANION),                  # Claude Code personal skills
        str(Path.cwd() / ".claude/skills" / COMPANION),            # Claude Code project skills
        f"/mnt/skills/*/{COMPANION}",                              # claude.ai / API sandboxes
        str(home / "Library/Application Support/Claude/local-agent-mode-sessions/"
                   f"skills-plugin/*/*/skills/{COMPANION}"),       # Claude desktop app
    ]
    found = []
    for pat in filter(None, patterns):
        for p in sorted(glob.glob(pat)):
            path = Path(p).resolve()
            if (path / "scripts" / COMPANION_LAUNCHER).is_file() and path not in found:
                found.append(path)
    return found


def _companion() -> dict:
    candidates = _companion_candidates()
    if not candidates:
        env = COMPANION.upper().replace("-", "_") + "_DIR"
        return {"found": False,
                "message": f"{COMPANION} skill not found. {COMPANION_ROLE}. Install {COMPANION} or set {env}."}
    path = candidates[0]
    launcher = path / "scripts" / COMPANION_LAUNCHER
    try:
        # Run it through its launcher with bash (the executable bit may not survive installation)
        res = subprocess.run(["bash", str(launcher), "list"], capture_output=True, text=True, timeout=300)
        works = res.returncode == 0 and COMPANION_PROBE in res.stdout
        detail = None if works else (res.stderr or res.stdout).strip()[-300:]
    except (OSError, subprocess.TimeoutExpired) as e:
        works, detail = False, str(e)
    out = {"found": True, "path": str(path), "command": f"bash {launcher}", "runs": works}
    if detail:
        out["error"] = detail
    return out


def _chemdraw() -> dict:
    system = platform.system()
    if system == "Darwin":
        apps = sorted(glob.glob("/Applications/ChemDraw*.app"))
        return {"installed": bool(apps), "apps": [Path(a).name for a in apps],
                "open_command": "open <file.cdxml>" if apps else None}
    if system == "Windows":
        roots = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
        hits = [p for r in roots if r for p in glob.glob(os.path.join(r, "*", "ChemDraw*", "ChemDraw.exe"))]
        return {"installed": bool(hits), "apps": hits}
    return {"installed": False, "note": "ChemDraw runs on macOS/Windows; .cdxml files can be copied there."}


def check() -> dict:
    from diagnostics import SKILL_NAME, VERSION, log_path

    report = {
        "skill": SKILL_NAME,
        "version": VERSION,
        "skill_dir": str(SKILL_DIR),
        "error_log": str(log_path()),
        "python": {"executable": sys.executable, "version": platform.python_version(),
                   "ok": sys.version_info >= (3, 10)},
        "runner": os.environ.get("CHEM_SKILLS_RUNNER", "direct (launcher not used)"),
        "platform": f"{platform.system()} {platform.machine()}",
    }
    problems, warnings = [], []
    if not report["python"]["ok"]:
        problems.append("Python 3.10+ is required.")

    try:
        import rdkit
        report["rdkit"] = {"ok": True, "version": rdkit.__version__}
        from rdkit import Chem
        report["rdkit"]["cdx_binary_reading"] = bool(Chem.HasChemDrawCDXSupport())
    except ImportError as e:
        report["rdkit"] = {"ok": False, "error": str(e)}
        problems.append("RDKit is missing: run the skill through its launcher (bash scripts/<launcher>) "
                        "without CHEM_SKILLS_PYTHON so it installs RDKit.")

    try:
        import requests
        report["requests"] = {"ok": True, "version": requests.__version__}
        reach = {}
        for name, url in ENDPOINTS.items():
            try:
                reach[name] = requests.get(url, timeout=8).ok
            except requests.RequestException:
                reach[name] = False
        report["network"] = reach
        down = [n for n, ok in reach.items() if not ok]
        if down:
            warnings.append(f"Unreachable: {', '.join(down)}. Name/CAS lookups need PubChem; "
                            "SMILES-only work still runs offline.")
    except ImportError as e:
        report["requests"] = {"ok": False, "error": str(e)}
        problems.append("requests is missing.")

    export_dir = Path(os.environ.get("CHEM_EXPORT_DIR", "exports")).resolve()
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        probe = export_dir / ".cdx_write_test"
        probe.write_text("ok")
        probe.unlink()
        report["export_dir"] = {"path": str(export_dir), "writable": True}
    except OSError as e:
        report["export_dir"] = {"path": str(export_dir), "writable": False, "error": str(e)}
        problems.append(f"Cannot write to {export_dir}; set CHEM_EXPORT_DIR to a writable folder.")

    if COMPANION:  # None in chem-suite, which contains both toolsets
        key = COMPANION.replace("-", "_")
        report[key] = _companion()
        if not report[key]["found"]:
            warnings.append(report[key]["message"])
        elif not report[key]["runs"]:
            warnings.append(f"{COMPANION} was found but failed to run; see {key}.error.")

    if CHECK_CHEMDRAW:
        report["chemdraw"] = _chemdraw()
        if not report["chemdraw"]["installed"]:
            warnings.append("ChemDraw was not found on this machine; files are still written and can be "
                            "opened elsewhere.")

    report["ready"] = not problems
    report["problems"] = problems
    report["warnings"] = warnings
    return report
