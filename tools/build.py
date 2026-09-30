#!/usr/bin/env python3
"""Validate and package the skills into dist/ for uploading to Claude or sharing.

    uv run --no-project --with pyyaml python tools/build.py            # all skills
    uv run --no-project --with pyyaml python tools/build.py cdx-tools  # one skill

Writes dist/<name>-<version>.skill (keep these as release history) and dist/<name>.skill
(latest, the file to upload), and copies each SKILL.md metadata.version into the skill's
.claude-plugin/plugin.json so the plugin marketplace serves the same version. Validation mirrors Anthropic's skill validator and adds checks
that scripts compile and that files referenced from SKILL.md exist.
"""

import json
import py_compile
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ["chem-tools", "cdx-tools"]
DIST = ROOT / "dist"
ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
EXCLUDE_DIRS = {"__pycache__", "node_modules", "exports", "evals"}
EXCLUDE_FILES = {".DS_Store"}
EXECUTABLE = {"chem", "cdx", "chem.py", "cdx.py"}


def frontmatter(skill: Path) -> dict:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        raise ValueError("SKILL.md has no YAML frontmatter")
    data = yaml.safe_load(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return data


def validate(skill: Path) -> tuple[dict, list[str]]:
    errors = []
    try:
        fm = frontmatter(skill)
    except (OSError, ValueError, yaml.YAMLError) as e:
        return {}, [str(e)]

    extra = set(fm) - ALLOWED_KEYS
    if extra:
        errors.append(f"unexpected frontmatter keys: {sorted(extra)}")
    name = str(fm.get("name", "")).strip()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        errors.append(f"name '{name}' must be kebab-case, at most 64 characters")
    if name != skill.name:
        errors.append(f"name '{name}' should match the folder name '{skill.name}'")
    desc = str(fm.get("description", "")).strip()
    if not desc:
        errors.append("missing description")
    if len(desc) > 1024:
        errors.append(f"description is {len(desc)} characters (max 1024)")
    if "<" in desc or ">" in desc:
        errors.append("description cannot contain < or >")
    if len(str(fm.get("compatibility", ""))) > 500:
        errors.append("compatibility is longer than 500 characters")
    version = str((fm.get("metadata") or {}).get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append(f"metadata.version '{version}' should look like 1.2.3")

    body = (skill / "SKILL.md").read_text(encoding="utf-8")
    for ref in sorted(set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", body))):
        if not (skill / ref).exists():
            errors.append(f"SKILL.md mentions {ref}, which does not exist")

    for py in (skill / "scripts").glob("*.py"):
        try:
            py_compile.compile(str(py), doraise=True, cfile=str(ROOT / "dist" / ".pyc_check"))
        except py_compile.PyCompileError as e:
            errors.append(f"{py.name} does not compile: {e.msg.strip()}")
    for launcher in (skill / "scripts").iterdir():
        if launcher.suffix == "" and launcher.is_file():
            if subprocess.run(["bash", "-n", str(launcher)], capture_output=True).returncode:
                errors.append(f"{launcher.name}: bash syntax error")
    return fm, errors


def sync_plugin_manifest(skill: Path, version: str) -> None:
    """SKILL.md's metadata.version is the source of truth; mirror it into the plugin manifest."""
    path = skill / ".claude-plugin" / "plugin.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text())
    if manifest.get("version") != version or manifest.get("name") != skill.name:
        manifest.update(name=skill.name, version=version)
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"  synced {path.relative_to(ROOT)} to {version}")


def package(skill: Path, version: str) -> list[Path]:
    DIST.mkdir(exist_ok=True)
    outputs = [DIST / f"{skill.name}-{version}.skill", DIST / f"{skill.name}.skill"]
    for out in outputs:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(skill.rglob("*")):
                rel = f.relative_to(skill.parent)
                if not f.is_file() or f.name in EXCLUDE_FILES or EXCLUDE_DIRS & set(rel.parts):
                    continue
                info = zipfile.ZipInfo.from_file(f, str(rel))
                # Keep launchers executable for unzip tools that honour Unix modes
                mode = 0o755 if f.name in EXECUTABLE else 0o644
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, f.read_bytes())
    return outputs


def main(names: list[str]) -> int:
    failed = False
    for name in names or SKILLS:
        skill = ROOT / name
        fm, errors = validate(skill)
        if errors:
            failed = True
            print(f"✗ {name}")
            for e in errors:
                print(f"    - {e}")
            continue
        version = fm["metadata"]["version"]
        sync_plugin_manifest(skill, version)
        outs = package(skill, version)
        with zipfile.ZipFile(outs[0]) as z:
            n = len(z.namelist())
        print(f"✓ {name} {version}: {n} files -> {', '.join(o.name for o in outs)}")
    (DIST / ".pyc_check").unlink(missing_ok=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
