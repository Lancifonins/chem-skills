"""ChemDraw tools: write native .cdxml documents (structures, grids, reaction schemes) and read
.cdxml/.cdx files. Each tool returns a JSON-serialisable dict or raises ToolError.

Files are written under CHEM_EXPORT_DIR (default ./exports) and read only from inside
CHEM_WORKDIR (default: current directory).
"""

import contextlib
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdChemReactions, rdMolDescriptors

import pubchem as pc
from cdxml_writer import BOLD, FORMULA, LABEL_SIZE, LINE_H, PLAIN, CDXMLDocument, prepare, rich_runs, text_width
from pubchem import ToolError

RDLogger.DisableLog("rdApp.*")

EXPORT_DIR = Path(os.environ.get("CHEM_EXPORT_DIR", "exports"))
WORKDIR = Path(os.environ.get("CHEM_WORKDIR", ".")).resolve()

GAP = 18.0          # space between neighbouring objects, pt
CAPTION_GAP = 10.0  # structure bottom -> caption top
CAPTION_FIELDS = ("number", "name", "cas", "formula", "mw")


# ------------------------------------------------------------------ helpers

@contextlib.contextmanager
def _quiet_stderr():
    """RDKit's CDXML parser logs to C++ stderr (e.g. about text listed as reaction agents)."""
    fd = os.dup(2)
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 2)
        try:
            yield
        finally:
            os.dup2(fd, 2)
            os.close(fd)


@dataclass
class Compound:
    query: str
    mol: Chem.Mol
    label: str | None = None      # custom compound number, e.g. "3a"
    name: str | None = None


def _export_path(filename: str) -> Path:
    stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("._") or "drawing"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return (EXPORT_DIR / f"{stem}.cdxml").resolve()


def _input_path(path: str) -> Path:
    p = (WORKDIR / path).resolve()
    if not p.is_relative_to(WORKDIR):
        raise ToolError(f"'{path}' is outside the working directory.")
    if not p.is_file():
        raise ToolError(f"File not found: {path}")
    return p


def _resolve(spec) -> Compound:
    """spec: 'name / CAS / SMILES' or {"structure": ..., "label": "3a", "name": "..."}."""
    if isinstance(spec, dict):
        structure, label, name = spec.get("structure"), spec.get("label"), spec.get("name")
    else:
        structure, label, name = spec, None, None
    if not structure or not isinstance(structure, str):
        raise ToolError(f"Missing structure in {spec!r}.")
    is_smiles = pc.detect_identifier_type(structure) == "smiles"
    mol = Chem.MolFromSmiles(pc.smiles_for(structure))
    if mol is None:
        raise ToolError(f"Could not build a structure for '{structure}'.")
    return Compound(structure, mol, label, name or (None if is_smiles else structure))


def _resolve_all(specs) -> tuple[list[Compound], list[str]]:
    ok, failed = [], []
    for s in specs:
        try:
            ok.append(_resolve(s))
        except ToolError as e:
            failed.append(f"{s if isinstance(s, str) else s.get('structure')}: {e}")
    return ok, failed


def _caption_fields(caption: str) -> list[str]:
    if caption in ("", "none", None):
        return []
    fields = caption.split("_")
    bad = [f for f in fields if f not in CAPTION_FIELDS]
    if bad:
        raise ToolError(f"Unknown caption fields {bad}; combine {list(CAPTION_FIELDS)} with '_' or use 'none'.")
    return fields


class _Numberer:
    def __init__(self, start: int):
        self.n = start

    def next(self, comp: Compound) -> str:
        if comp.label:
            return comp.label
        label = str(self.n)
        self.n += 1
        return label


def _caption_runs(comp: Compound, fields: list[str], numberer: _Numberer) -> list[tuple[str, int]]:
    lines: list[list[tuple[str, int]]] = []
    for f in fields:
        if f == "number":
            lines.append([(numberer.next(comp), BOLD)])
        elif f == "name":
            name = comp.name
            if not name:  # SMILES input: ask PubChem for a name
                try:
                    props = pc.properties_for_cids([pc.resolve_cid(Chem.MolToSmiles(comp.mol), "smiles")])
                    name = props[0].get("Title") if props else None
                except ToolError:
                    name = None
            if name:
                lines.append([(name, PLAIN)])
        elif f == "cas":
            try:
                cas = (pc.cas_numbers_for_cid(pc.resolve_cid(Chem.MolToSmiles(comp.mol), "smiles")) or [None])[0]
            except ToolError:
                cas = None
            lines.append([(f"CAS {cas or 'n/a'}", PLAIN)])
        elif f == "formula":
            lines.append([(rdMolDescriptors.CalcMolFormula(comp.mol), FORMULA)])
        elif f == "mw":
            lines.append([(f"MW {Descriptors.MolWt(comp.mol):.2f}", PLAIN)])
    runs: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if i:
            runs.append(("\n", PLAIN))
        runs.extend(line)
    return runs


def _text_height(runs) -> float:
    return ("".join(t for t, _ in runs).count("\n") + 1) * LINE_H * LABEL_SIZE


def _summary(comps: list[Compound]) -> list[dict]:
    return [{"input": c.query, "smiles": Chem.MolToSmiles(c.mol),
             "formula": rdMolDescriptors.CalcMolFormula(c.mol), **({"label": c.label} if c.label else {})}
            for c in comps]


def _write(doc: CDXMLDocument, filename: str) -> str:
    path = _export_path(filename)
    path.write_text(doc.to_string(), encoding="utf-8")
    # Self-check: the file must parse back to the same number of structures
    with _quiet_stderr():
        ok = Chem.MolsFromCDXMLFile(str(path))
    if not ok:
        raise ToolError(f"Internal error: {path.name} did not re-read as CDXML.")
    return str(path)


# ------------------------------------------------------------- structures

def _layout_grid(doc: CDXMLDocument, comps: list[Compound], columns: int, fields: list[str],
                 numberer: _Numberer) -> None:
    preps = [prepare(c.mol) for c in comps]
    captions = [_caption_runs(c, fields, numberer) if fields else [] for c in comps]
    cols = max(1, min(columns, len(comps)))
    cell_w = max(max(p.width for p in preps), max((text_width("".join(t for t, _ in r)) for r in captions), default=0)) + 2 * GAP
    y = 0.0
    for r in range(0, len(comps), cols):
        row = list(range(r, min(r + cols, len(comps))))
        struct_h = max(preps[i].height for i in row)
        cap_h = max((_text_height(captions[i]) for i in row if captions[i]), default=0)
        for j, i in enumerate(row):
            cx = j * cell_w + cell_w / 2
            p = preps[i]
            doc.add_molecule(p, cx - p.width / 2, y + (struct_h - p.height) / 2)
            if captions[i]:
                doc.add_text(cx, y + struct_h + CAPTION_GAP, captions[i])
        y += struct_h + (CAPTION_GAP + cap_h if cap_h else 0) + 2 * GAP


def draw_structures(compounds: list, layout: str = "grid", columns: int = 4, caption: str = "name",
                    number_start: int = 1, filename: str = "structures", separate_files: bool = False) -> dict:
    if layout not in ("grid", "row"):
        raise ToolError("layout must be 'grid' or 'row'.")
    fields = _caption_fields(caption)
    comps, failed = _resolve_all(compounds)
    if not comps:
        raise ToolError("None of the compounds could be resolved: " + "; ".join(failed))
    numberer = _Numberer(number_start)
    cols = len(comps) if layout == "row" else columns

    if separate_files:
        paths = []
        for c in comps:
            doc = CDXMLDocument(c.name or c.query)
            _layout_grid(doc, [c], 1, fields, numberer)
            paths.append(_write(doc, c.label or c.name or Chem.MolToSmiles(c.mol)))
        return {"paths": paths, "compounds": _summary(comps), "failed": failed}

    doc = CDXMLDocument(filename)
    _layout_grid(doc, comps, cols, fields, numberer)
    return {"path": _write(doc, filename), "layout": layout, "compounds": _summary(comps), "failed": failed}


# --------------------------------------------------------------- reactions

def _arrow_text_lines(items: list[str], max_chars: int = 26) -> str:
    joined = ", ".join(items)
    return joined if len(joined) <= max_chars else "\n".join(items)


def draw_reaction(reactants: list | None = None, products: list | None = None,
                  reagents: list | None = None, conditions: str = "", yield_text: str = "",
                  steps: list | None = None, caption: str = "number", number_start: int = 1,
                  reagents_as: str = "text", filename: str = "reaction") -> dict:
    """Single step via reactants/products/reagents/conditions, or a linear multi-step scheme via
    `reactants` (starting materials) + `steps`: [{"reagents", "conditions", "yield", "products"}]."""
    if reagents_as not in ("text", "structures"):
        raise ToolError("reagents_as must be 'text' or 'structures'.")
    if steps is None:
        if not products:
            raise ToolError("Give reactants and products, or reactants plus a list of steps.")
        steps = [{"reagents": reagents or [], "conditions": conditions, "yield": yield_text, "products": products}]
    if not reactants:
        raise ToolError("reactants (the starting materials) are required.")
    fields = _caption_fields(caption)
    numberer = _Numberer(number_start)

    failed: list[str] = []
    stages = []
    for group in [reactants] + [s.get("products") or [] for s in steps]:
        comps, bad = _resolve_all(group)
        failed.extend(bad)
        if not comps:
            raise ToolError("A stage of the scheme has no resolvable compounds. " + "; ".join(failed))
        stages.append(comps)

    doc = CDXMLDocument(filename)
    preps = [[prepare(c.mol) for c in st] for st in stages]
    caption_top = max(p.height / 2 for st in preps for p in st) + CAPTION_GAP
    x = 0.0
    stage_frags, pending_captions = [], []
    for si, (st, st_preps) in enumerate(zip(stages, preps)):
        frags = []
        for ci, (comp, p) in enumerate(zip(st, st_preps)):
            if ci:
                doc.add_text(x + GAP * 0.75, -9, [("+", PLAIN)], size=14)
                x += GAP * 1.5
            frags.append(doc.add_molecule(p, x, -p.height / 2))
            if fields:
                pending_captions.append((x + p.width / 2, comp))
            x += p.width
        stage_frags.append(frags)

        if si == len(steps):
            break
        step = steps[si]
        above_ids, below_ids = [], []
        above_w = below_w = 0.0
        above_objs = []
        names = [r if isinstance(r, str) else r.get("name") or r.get("structure") for r in step.get("reagents") or []]
        if names and reagents_as == "structures":
            rcomps, bad = _resolve_all(step["reagents"])
            failed.extend(bad)
            above_objs = [prepare(c.mol) for c in rcomps]
            above_w = sum(p.width for p in above_objs) + GAP * max(0, len(above_objs) - 1)
        elif names:
            above_text = rich_runs(_arrow_text_lines(names))
            above_w = text_width("".join(t for t, _ in above_text))
        below_lines = [ln.strip() for ln in re.split(r"[;\n]", step.get("conditions") or "") if ln.strip()]
        if step.get("yield"):
            below_lines.append(str(step["yield"]))
        below_text = rich_runs("\n".join(below_lines)) if below_lines else []
        if below_text:
            below_w = text_width("".join(t for t, _ in below_text))

        length = max(60.0, above_w + 16, below_w + 16)
        tail = x + GAP * 0.75
        head = tail + length
        arrow = doc.add_arrow(tail, head, 0.0)
        mid = (tail + head) / 2
        if above_objs:
            ax = mid - above_w / 2
            for p in above_objs:
                above_ids.append(doc.add_molecule(p, ax, -6 - p.height))
                ax += p.width + GAP
        elif names:
            above_ids.append(doc.add_text(mid, -5 - _text_height(above_text), above_text))
        if below_text:
            below_ids.append(doc.add_text(mid, 5, below_text))
        doc.add_step([], [], arrow, above_ids, below_ids)
        x = head + GAP * 0.75

    # Captions go on one common baseline under the whole scheme
    for cx, comp in pending_captions:
        runs = _caption_runs(comp, fields, numberer)
        if runs:
            doc.add_text(cx, caption_top, runs)
    for i, step in enumerate(doc.steps):
        step["reactants"], step["products"] = stage_frags[i], stage_frags[i + 1]

    path = _write(doc, filename)
    rxn_smiles = [">".join([".".join(Chem.MolToSmiles(c.mol) for c in stages[i]), "",
                            ".".join(Chem.MolToSmiles(c.mol) for c in stages[i + 1])])
                  for i in range(len(steps))]
    return {"path": path, "steps": len(steps), "reaction_smiles": rxn_smiles,
            "compounds": [_summary(st) for st in stages], "failed": failed}


# -------------------------------------------------------------- conversion

def convert_to_chemdraw(path: str, layout: str = "grid", columns: int = 4, caption: str = "name",
                        filename: str | None = None) -> dict:
    """Turn .sdf/.mol/.smi (grid of structures) or .rxn (reaction scheme) into a .cdxml file."""
    p = _input_path(path)
    ext = p.suffix.lower()
    out_name = filename or p.stem
    if ext == ".rxn":
        rxn = rdChemReactions.ReactionFromRxnFile(str(p))
        if rxn is None:
            raise ToolError(f"Could not parse reaction file {path}.")
        smi = lambda ms: [Chem.MolToSmiles(m) for m in ms]
        return draw_reaction(reactants=smi(rxn.GetReactants()), products=smi(rxn.GetProducts()),
                             reagents=smi(rxn.GetAgents()), reagents_as="structures",
                             caption="none" if caption == "name" else caption, filename=out_name)
    if ext in (".sdf", ".sd"):
        mols = [m for m in Chem.SDMolSupplier(str(p)) if m is not None]
    elif ext == ".mol":
        mols = [Chem.MolFromMolFile(str(p))]
    elif ext in (".smi", ".smiles", ".txt"):
        mols = []
        for line in p.read_text().splitlines():
            if line.strip():
                parts = line.split(None, 1)
                m = Chem.MolFromSmiles(parts[0])
                if m is not None and len(parts) > 1:
                    m.SetProp("_Name", parts[1].strip())
                mols.append(m)
    else:
        raise ToolError(f"Unsupported file type '{ext}' (use .sdf, .mol, .smi or .rxn).")
    mols = [m for m in mols if m is not None and m.GetNumAtoms()]
    if not mols:
        raise ToolError(f"No readable structures in {path}.")
    specs = [{"structure": Chem.MolToSmiles(m),
              "name": m.GetProp("_Name") if m.HasProp("_Name") and m.GetProp("_Name") else None}
             for m in mols]
    return draw_structures(specs, layout=layout, columns=columns, caption=caption, filename=out_name)


# ----------------------------------------------------------------- reading

def read_chemdraw(path: str, max_structures: int = 100) -> dict:
    """Structures, reactions and free text from a .cdxml or binary .cdx file."""
    p = _input_path(path)
    ext = p.suffix.lower()
    if ext not in (".cdxml", ".cdx"):
        raise ToolError("read_chemdraw reads .cdxml and .cdx files.")
    params = Chem.CDXMLParserParams()
    params.format = Chem.CDXMLFormat.CDX if ext == ".cdx" else Chem.CDXMLFormat.CDXML
    if ext == ".cdx" and not Chem.HasChemDrawCDXSupport():
        raise ToolError("This RDKit build cannot read binary .cdx; save the file as .cdxml in ChemDraw.")
    try:
        with _quiet_stderr():
            mols = list(Chem.MolsFromCDXMLFile(str(p), params))
    except Exception as e:
        raise ToolError(f"Could not parse {path}: {e}") from e

    structures = []
    for i, mol in enumerate(mols[:max_structures]):
        if mol is None or mol.GetNumAtoms() == 0:
            continue
        structures.append({
            "index": i + 1,
            "smiles": Chem.MolToSmiles(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "molecular_weight": round(Descriptors.MolWt(mol), 3),
            "inchikey": Chem.MolToInchiKey(mol) or None,
        })

    reactions = []
    try:
        with _quiet_stderr():
            rxns = list(rdChemReactions.ReactionsFromCDXMLFile(str(p))) if ext == ".cdxml" else []
        reactions = [rdChemReactions.ReactionToSmiles(r) for r in rxns]
    except Exception:
        pass

    texts = []
    if ext == ".cdxml":
        try:
            root = ET.parse(p).getroot()
            atom_texts = {id(t) for n in root.iter("n") for t in n.iter("t")}
            for t in root.iter("t"):
                if id(t) not in atom_texts:
                    s = "".join(x.text or "" for x in t.iter("s")).strip()
                    if s:
                        texts.append(s)
        except ET.ParseError:
            pass

    if not structures and not texts:
        raise ToolError(f"No structures or text found in {path}.")
    return {"file": str(p.relative_to(WORKDIR)), "structure_count": len(structures),
            "structures": structures, "reactions": reactions, "text": texts}
