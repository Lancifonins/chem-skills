# Running chem-tools and cdx-tools as local MCP servers

Use this when the skills' scripts can't run where Claude is working: the Claude desktop app's chat,
or an agent VM without network access. A local MCP server runs the same tools natively on the
user's own computer, where they can use the user's Python/RDKit, reach PubChem and open ChemDraw.
The skills still supply the instructions, and the servers do the work.

## Setup (Claude desktop app)

1. Keep an unpacked copy of each skill folder somewhere permanent, e.g. `~/Claude/Skills/chem-tools`
   and `~/Claude/Skills/cdx-tools`. The servers run from these folders.
2. In the Claude desktop app, go to **Settings → Developer → Edit Config**, which opens
   `claude_desktop_config.json`. Add the entries below inside `"mcpServers"` (create that key if
   it's missing, and keep any other keys already in the file):

```json
"mcpServers": {
  "chem-tools": {
    "command": "/bin/bash",
    "args": ["/ABSOLUTE/PATH/TO/chem-tools/scripts/chem", "mcp"],
    "env": {
      "CHEM_EXPORT_DIR": "/ABSOLUTE/PATH/FOR/OUTPUT/FILES",
      "CHEM_WORKDIR": "/ABSOLUTE/PATH/THE/TOOLS/MAY/READ/FROM"
    }
  },
  "cdx-tools": {
    "command": "/bin/bash",
    "args": ["/ABSOLUTE/PATH/TO/cdx-tools/scripts/cdx", "mcp"],
    "env": {
      "CHEM_EXPORT_DIR": "/ABSOLUTE/PATH/FOR/OUTPUT/FILES",
      "CHEM_WORKDIR": "/ABSOLUTE/PATH/THE/TOOLS/MAY/READ/FROM"
    }
  }
}
```

3. Quit and reopen the app. The first start installs RDKit and the MCP library, which takes about
   a minute. With uv installed they come from uv's cache; otherwise they go into a private venv in
   `~/.cache/chem-skills` shared by both servers.
4. In a new chat, check that both servers appear in the tools menu, then ask for something like
   "draw aspirin and paracetamol in ChemDraw".

Paths must be absolute, because the app does not start the servers in your project folder.
`CHEM_EXPORT_DIR` is where .cdxml/.sdf/.png files are saved. `CHEM_WORKDIR` is the only folder the
tools may read input files from.

## What the servers add

| Server | Extra tools | Extras in results |
|---|---|---|
| chem-tools | `chem_system_check` | PNG images from `draw_structures_image` / `export_reaction` shown inline |
| cdx-tools | `open_in_chemdraw`, `cdx_system_check` | An RDKit preview of the structures stored in every written file |

## Troubleshooting

- **Server fails to start:** run `bash /ABSOLUTE/PATH/TO/cdx-tools/scripts/cdx check` in Terminal,
  which prints the same diagnosis in readable form. The app's MCP log
  (`~/Library/Logs/Claude/mcp*.log` on macOS) shows the launcher's messages.
- **"No Python 3.10+ found":** install uv (https://docs.astral.sh/uv/) or a newer Python, or set
  `"CHEM_SKILLS_PYTHON": "/path/to/python"` in `env` to an interpreter that already has rdkit,
  requests, pillow and mcp.
- **PubChem unreachable:** names and CAS numbers can't be resolved, but SMILES inputs still work.
