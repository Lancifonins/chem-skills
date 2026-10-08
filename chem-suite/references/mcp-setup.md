# Running chem-suite as a local MCP server

Use this when the skills' scripts can't run where Claude is working: the Claude desktop app's chat,
or an agent VM without network access. A local MCP server runs the same tools natively on the
user's own computer, where they can use the user's Python/RDKit, reach PubChem and open ChemDraw.
The skill still supplies the instructions, and the server does the work.

## Setup (Claude desktop app)

1. Keep an unpacked copy of the skill folder somewhere permanent, e.g. `~/Claude/Skills/chem-suite`.
   The server runs from this folder.
2. In the Claude desktop app, go to **Settings → Developer → Edit Config**, which opens
   `claude_desktop_config.json`. Add the entry below inside `"mcpServers"` (create that key if
   it's missing, and keep any other keys already in the file):

```json
"mcpServers": {
  "chem-suite": {
    "command": "/bin/bash",
    "args": ["/ABSOLUTE/PATH/TO/chem-suite/scripts/chem", "mcp"],
    "env": {
      "CHEM_EXPORT_DIR": "/ABSOLUTE/PATH/FOR/OUTPUT/FILES",
      "CHEM_WORKDIR": "/ABSOLUTE/PATH/THE/TOOLS/MAY/READ/FROM"
    }
  }
}
```

3. Quit and reopen the app. The first start installs RDKit and the MCP library, which takes about
   a minute. With uv installed they come from uv's cache; otherwise they go into a private venv in
   `~/.cache/chem-skills`.
4. In a new chat, check that the server appears in the tools menu, then ask for something like
   "draw aspirin and paracetamol in ChemDraw".

Paths must be absolute, because the app does not start the server in your project folder.
`CHEM_EXPORT_DIR` is where .cdxml/.sdf/.png files are saved. `CHEM_WORKDIR` is the only folder the
tools may read input files from.

## What the server adds

- `open_in_chemdraw` and `system_check` tools.
- An RDKit preview of the structures stored in every .cdxml it writes.
- PNG images from `draw_structures_image` and `export_reaction`, shown inline.

Don't also register chem-tools or cdx-tools as servers: they would duplicate these tools.

## Troubleshooting

- **Server fails to start:** run `bash /ABSOLUTE/PATH/TO/chem-suite/scripts/chem check` in Terminal,
  which prints the same diagnosis in readable form. The app's MCP log
  (`~/Library/Logs/Claude/mcp*.log` on macOS) shows the launcher's messages.
- **"No Python 3.10+ found":** install uv (https://docs.astral.sh/uv/) or a newer Python, or set
  `"CHEM_SKILLS_PYTHON": "/path/to/python"` in `env` to an interpreter that already has rdkit,
  requests, pillow and mcp.
- **PubChem unreachable:** names and CAS numbers can't be resolved, but SMILES inputs still work.
