# Chemistry skills for Claude

Two [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that give
Claude reliable chemistry tools:

| Skill | What it does | Backends |
|---|---|---|
| **chem-tools** | Compound identity (name ⇄ CAS ⇄ SMILES ⇄ CID), GHS hazards, experimental properties, vendors, substructure and bioactive-similarity search, RDKit descriptors, SDF/RXN/PNG output | PubChem, ChEMBL, RDKit |
| **cdx-tools** | Writes native, editable ChemDraw `.cdxml` files (captioned structure grids, reaction schemes with arrows, reagents and conditions, multi-step routes) and reads `.cdxml`/`.cdx` | RDKit (+ PubChem for names) |

They work as a pair: chem-tools answers the chemistry, and cdx-tools draws it.

## Install

**Claude Code (recommended):** this repository is a plugin marketplace. Add it once, then install;
`cdx-tools` pulls in `chem-tools` automatically:

```bash
claude plugin marketplace add Lancifonins/REPO_NAME
claude plugin install cdx-tools@chem-skills
```

Inside a session, `/plugin` lets you browse the `chem-skills` marketplace and install from it.
`claude plugin update cdx-tools@chem-skills` fetches new versions.

**Other ways:** download `chem-tools.skill` and `cdx-tools.skill` from the latest release, then:

- **claude.ai / Claude apps:** Settings → Capabilities → Skills → upload each `.skill` file.
  Code execution must be enabled. The skills install RDKit from PyPI on first use and query
  PubChem, so the sandbox needs network access to `pypi.org`, `files.pythonhosted.org`,
  `pubchem.ncbi.nlm.nih.gov` and `www.ebi.ac.uk`. If your organisation restricts this, use one of
  the options below.
- **Claude Code:** unzip into `~/.claude/skills/` (all projects) or `<project>/.claude/skills/`.
- **Claude desktop app with local tools (most reliable):** run both skills as local MCP servers,
  so the tools execute on your own computer. See
  [`cdx-tools/references/mcp-setup.md`](cdx-tools/references/mcp-setup.md).

Requirements: Python 3.10+. RDKit is installed automatically, via [uv](https://docs.astral.sh/uv/)
if present or else into a private venv in `~/.cache/chem-skills`. Your own Python environments are
not modified. ChemDraw is only needed to open the output.

Check a machine with `bash chem-tools/scripts/chem check` and `bash cdx-tools/scripts/cdx check`.

## Reporting problems

Both skills log failed tool calls locally. To report an issue, ask Claude to "run the chem-tools
(or cdx-tools) report", or run it yourself:

```bash
bash ~/.claude/skills/cdx-tools/scripts/cdx report
```

It prints a Markdown report with the skill version, an environment check and the recent failures
with tracebacks. Review it (tool inputs may include compound names or file paths), then send it to
the maintainer or paste it into an issue. Set `CHEM_SKILLS_DEBUG=1` to log successful calls too.

## Development

```
.claude-plugin/    marketplace.json: lists both skills as installable plugins
chem-tools/        skill: SKILL.md, scripts/, references/, .claude-plugin/plugin.json
cdx-tools/         skill: SKILL.md, scripts/, references/, .claude-plugin/plugin.json
tests/             end-to-end tests (each tool run through its launcher, as Claude runs it)
tools/build.py     validate + package into dist/
dist/              built .skill files (upload these)
```

The loop for fixing a bug or adding a feature:

```bash
# 1. edit the skill; with ~/.claude/skills symlinked here, Claude Code picks up changes immediately
ln -sfn "$PWD/chem-tools" ~/.claude/skills/chem-tools
ln -sfn "$PWD/cdx-tools" ~/.claude/skills/cdx-tools

# 2. test (tests needing PubChem are skipped automatically when it is unreachable)
uv run --no-project --with pytest --with rdkit --with requests python -m pytest

# 3. bump metadata.version in the skill's SKILL.md, note the change in CHANGELOG.md

# 4. validate and package
uv run --no-project --with pyyaml python tools/build.py

# 5. commit, push and attach dist/*.skill to a GitHub release; plugin users get the new
#    version with `claude plugin update`, and .skill users re-upload (same name replaces it)
```

`tools/build.py` copies each SKILL.md `metadata.version` into the skill's
`.claude-plugin/plugin.json`, so bump the version in SKILL.md only. Check the marketplace with
`claude plugin validate --strict .`.

A few conventions keep the two skills consistent:
- `scripts/diagnostics.py`, `scripts/check_env.py` (apart from its settings block),
  `scripts/pubchem.py` and the launcher logic are shared, so change them in both skills.
- Tools return JSON and raise `ToolError` for anything the user or Claude can fix. Any other
  exception is logged with a traceback as a `bug`.
- Every new tool needs a test in `tests/`.
