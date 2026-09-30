"""Chemistry tools. Each returns a JSON-serialisable dict or raises ToolError.

Network tools use PubChem/ChEMBL; structure tools run locally with RDKit.
Files are written under CHEM_EXPORT_DIR (default ./exports) and read only from
inside CHEM_WORKDIR (default: current directory).
"""

import os
import re
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, Draw, Lipinski, rdChemReactions, rdMolDescriptors

import pubchem as pc
from pubchem import ToolError

RDLogger.DisableLog("rdApp.*")

EXPORT_DIR = Path(os.environ.get("CHEM_EXPORT_DIR", "exports"))
WORKDIR = Path(os.environ.get("CHEM_WORKDIR", ".")).resolve()


# ------------------------------------------------------------------ helpers

def _mol(smiles: str, label: str = "") -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ToolError(f"RDKit could not parse the structure for '{label or smiles}'.")
    return mol


def _resolve_mols(compounds: list[str]) -> tuple[list[tuple[str, Chem.Mol]], list[str]]:
    """Turn names/CAS/SMILES into molecules; collects failures instead of aborting."""
    ok, failed = [], []
    for c in compounds:
        try:
            ok.append((c, _mol(pc.smiles_for(c), c)))
        except ToolError as e:
            failed.append(f"{c}: {e}")
    return ok, failed


def _export_path(filename: str, ext: str) -> Path:
    stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("._") or "structure"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return (EXPORT_DIR / f"{stem}{ext}").resolve()


def _input_path(path: str) -> Path:
    p = (WORKDIR / path).resolve()
    if not p.is_relative_to(WORKDIR):
        raise ToolError(f"'{path}' is outside the working directory.")
    if not p.is_file():
        raise ToolError(f"File not found: {path}")
    return p


def _describe(mol: Chem.Mol) -> dict:
    return {
        "smiles": Chem.MolToSmiles(mol),
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "molecular_weight": round(Descriptors.MolWt(mol), 3),
        "exact_mass": round(Descriptors.ExactMolWt(mol), 4),
        "inchikey": Chem.MolToInchiKey(mol) or None,
    }


def _layout_row(mols: list[Chem.Mol], x0: float = 0.0, gap: float = 2.0) -> float:
    """Place 2D depictions left-to-right by their real widths; returns the next free x."""
    x = x0
    for mol in mols:
        AllChem.Compute2DCoords(mol)
        conf = mol.GetConformer()
        xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
        ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
        dx, dy = x - min(xs), -(min(ys) + max(ys)) / 2
        for i in range(mol.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (p.x + dx, p.y + dy, 0.0))
        x += (max(xs) - min(xs)) + gap
    return x


# ------------------------------------------------------- compound info tool

SECTIONS = ("safety", "physical", "vendors")

PHYSICAL_HEADINGS = {
    "density": "Density",
    "boiling_point": "Boiling Point",
    "melting_point": "Melting Point",
    "flash_point": "Flash Point",
    "solubility": "Solubility",
    "vapor_pressure": "Vapor Pressure",
    "refractive_index": "Refractive Index",
    "pka": "Dissociation Constants",
}
DEFAULT_PHYSICAL = ["density", "boiling_point", "melting_point", "flash_point"]


def _identity(cid: int) -> dict:
    props = pc.properties_for_cids([cid])
    if not props:
        raise ToolError(f"PubChem CID {cid} has no property record.")
    p = props[0]
    cas = pc.cas_numbers_for_cid(cid)
    return {
        "name": p.get("Title"),
        "iupac_name": p.get("IUPACName"),
        "cas_number": cas[0] if cas else None,
        "other_cas_numbers": cas[1:5],
        "pubchem_cid": cid,
        "formula": p.get("MolecularFormula"),
        "molecular_weight": float(p["MolecularWeight"]) if p.get("MolecularWeight") else None,
        "exact_mass": float(p["ExactMass"]) if p.get("ExactMass") else None,
        "smiles": p.get("SMILES"),
        "inchikey": p.get("InChIKey"),
        "xlogp": p.get("XLogP"),
        "tpsa": p.get("TPSA"),
        "formal_charge": p.get("Charge"),
        "pubchem_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
    }


def _safety(cid: int) -> dict:
    infos = pc.pug_view_section(cid, "GHS Classification")
    if not infos:
        return {"ghs_available": False,
                "message": "PubChem has no GHS classification for this compound."}

    signal, pictograms, hazards, precautions = set(), [], [], []
    for info in infos:
        name = info.get("Name", "")
        strings = pc.info_strings(info)
        if name == "Signal":
            signal.update(strings)
        elif name == "Pictogram(s)":
            for s in info.get("Value", {}).get("StringWithMarkup", []):
                for m in s.get("Markup", []):
                    if m.get("Extra") and m["Extra"] not in pictograms:
                        pictograms.append(m["Extra"])
        elif name == "GHS Hazard Statements":
            hazards.extend(s for s in strings if s not in hazards)
        elif name == "Precautionary Statement Codes":
            for s in strings:
                for code in re.split(r",\s*|\s+and\s+", s):
                    code = code.strip()
                    if code.startswith("P") and code not in precautions:
                        precautions.append(code)

    return {
        "ghs_available": True,
        "signal_word": "Danger" if "Danger" in signal else ("Warning" if signal else None),
        "pictograms": pictograms,
        "hazard_statements": hazards,
        "precautionary_codes": precautions,
        "note": "Aggregated from multiple PubChem depositors; percentages show how many "
                "notifications report each hazard. Always confirm against the supplier SDS.",
        "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}#section=Safety-and-Hazards",
    }


def _physical(cid: int, properties: list[str], max_values: int) -> dict:
    out = {}
    for prop in properties:
        values = []
        for info in pc.pug_view_section(cid, PHYSICAL_HEADINGS[prop]):
            values.extend(pc.info_strings(info))
        out[prop] = values[:max_values] or None
    return {"experimental_values": out,
            "note": "Values are verbatim experimental reports (units and conditions vary)."}


def _vendors(cid: int, max_vendors: int) -> dict:
    data = pc.get_json(f"{pc.PUG_VIEW}/categories/compound/{cid}/JSON")
    categories = (data or {}).get("SourceCategories", {}).get("Categories", [])
    vendors = {}
    for cat in categories:
        if cat.get("Category") != "Chemical Vendors":
            continue
        for src in cat.get("Sources", []):
            name = src.get("SourceName")
            if name and name not in vendors:
                vendors[name] = src.get("SourceRecordURL") or src.get("SourceURL")
    return {
        "commercially_available": bool(vendors),
        "vendor_count": len(vendors),
        "vendors": [{"name": n, "url": u} for n, u in list(vendors.items())[:max_vendors]],
        "pubchem_vendors_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}#section=Chemical-Vendors",
    }


def get_compound_info(identifier: str, include: list[str] | None = None,
                      identifier_type: str = "auto", properties: list[str] | None = None,
                      max_values: int = 4, max_vendors: int = 15) -> dict:
    """Identity is always returned; `include` adds safety / physical / vendors sections."""
    include = list(dict.fromkeys(include or []))
    unknown = [s for s in include if s not in SECTIONS]
    if unknown:
        raise ToolError(f"Unknown sections {unknown}; choose from {list(SECTIONS)}.")
    properties = properties or DEFAULT_PHYSICAL
    unknown = [p for p in properties if p not in PHYSICAL_HEADINGS]
    if unknown:
        raise ToolError(f"Unknown properties {unknown}; choose from {list(PHYSICAL_HEADINGS)}.")

    cid = pc.resolve_cid(identifier, identifier_type)
    out = {"query": identifier, **_identity(cid)}
    fetchers = {
        "safety": lambda: _safety(cid),
        "physical": lambda: _physical(cid, properties, max_values),
        "vendors": lambda: _vendors(cid, max_vendors),
    }
    for section in include:
        try:  # one failing section shouldn't discard the others
            out[section] = fetchers[section]()
        except ToolError as e:
            out[section] = {"error": str(e)}
    return out


# ------------------------------------------------------------ search tools

def search_substructure(query: str, query_type: str = "smiles", max_results: int = 10,
                        include_cas: bool = False) -> dict:
    if query_type not in ("smiles", "smarts"):
        raise ToolError("query_type must be 'smiles' or 'smarts'.")
    check = Chem.MolFromSmarts(query) if query_type == "smarts" else Chem.MolFromSmiles(query)
    if check is None:
        raise ToolError(f"Invalid {query_type.upper()}: {query}")
    max_results = max(1, min(int(max_results), 50))
    data = pc.get_json(
        f"{pc.PUG}/compound/fastsubstructure/{query_type}/{pc.seg(query)}/cids/JSON",
        params={"MaxRecords": max_results},
    )
    cids = (data or {}).get("IdentifierList", {}).get("CID", [])
    matches = [
        {
            "name": p.get("Title"),
            "pubchem_cid": p.get("CID"),
            "formula": p.get("MolecularFormula"),
            "molecular_weight": p.get("MolecularWeight"),
            "smiles": p.get("SMILES"),
            **({"cas_number": (pc.cas_numbers_for_cid(p["CID"]) or [None])[0]} if include_cas else {}),
        }
        for p in pc.properties_for_cids(cids)
    ]
    return {"query": query, "query_type": query_type, "match_count": len(matches), "matches": matches}


def search_similar_bioactives(identifier: str, similarity_threshold: int = 80,
                              max_results: int = 12) -> dict:
    threshold = int(similarity_threshold)
    if not 40 <= threshold <= 100:
        raise ToolError("ChEMBL similarity_threshold must be between 40 and 100.")
    smiles = pc.smiles_for(identifier)
    data = pc.get_json(
        f"{pc.CHEMBL}/similarity/{pc.seg(smiles)}/{threshold}.json",
        params={"limit": max(1, min(int(max_results), 50))},
    )
    molecules = (data or {}).get("molecules", [])
    return {
        "query": identifier,
        "query_smiles": smiles,
        "threshold_percent": threshold,
        "results": [
            {
                "chembl_id": m.get("molecule_chembl_id"),
                "name": m.get("pref_name"),
                "similarity": float(m["similarity"]) if m.get("similarity") else None,
                "max_clinical_phase": m.get("max_phase"),
                "smiles": (m.get("molecule_structures") or {}).get("canonical_smiles"),
                "url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{m.get('molecule_chembl_id')}/",
            }
            for m in molecules
        ],
    }


# ------------------------------------------------------- local RDKit tools

def calculate_properties(identifier: str) -> dict:
    mol = _mol(pc.smiles_for(identifier), identifier)
    violations = sum([
        Descriptors.MolWt(mol) > 500,
        Descriptors.MolLogP(mol) > 5,
        Lipinski.NumHDonors(mol) > 5,
        Lipinski.NumHAcceptors(mol) > 10,
    ])
    return {
        "query": identifier,
        **_describe(mol),
        "logp_crippen": round(Descriptors.MolLogP(mol), 2),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 2),
        "h_bond_donors": Lipinski.NumHDonors(mol),
        "h_bond_acceptors": Lipinski.NumHAcceptors(mol),
        "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "rings": rdMolDescriptors.CalcNumRings(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "fraction_sp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        "stereocenters": len(Chem.FindMolChiralCenters(mol, includeUnassigned=True)),
        "lipinski_violations": violations,
    }


def read_structure_file(path: str, max_molecules: int = 50) -> dict:
    p = _input_path(path)
    ext = p.suffix.lower()
    if ext in (".sdf", ".sd"):
        mols = list(Chem.SDMolSupplier(str(p)))
    elif ext == ".mol":
        mols = [Chem.MolFromMolFile(str(p))]
    elif ext == ".cdxml":
        mols = list(Chem.MolsFromCDXMLFile(str(p)))
    elif ext in (".smi", ".smiles", ".txt"):
        mols = [Chem.MolFromSmiles(line.split()[0]) for line in p.read_text().splitlines() if line.strip()]
    else:
        raise ToolError(f"Unsupported file type '{ext}' (use .sdf, .mol, .cdxml or .smi). "
                        "Binary .cdx files must be re-saved as .cdxml or .sdf in ChemDraw.")

    records, unreadable = [], 0
    for i, mol in enumerate(mols[:max_molecules]):
        if mol is None or mol.GetNumAtoms() == 0:
            unreadable += 1
            continue
        # A ChemDraw canvas with several drawings comes in as one multi-fragment mol
        for frag in Chem.GetMolFrags(mol, asMols=True):
            rec = {"record": i + 1, **_describe(frag)}
            if mol.HasProp("_Name") and mol.GetProp("_Name"):
                rec["title"] = mol.GetProp("_Name")
            records.append(rec)
    if not records:
        raise ToolError(f"No readable structures in {path}.")
    return {"file": str(p.relative_to(WORKDIR)), "structure_count": len(records),
            "unreadable_records": unreadable, "structures": records}


def export_structures(compounds: list[str], filename: str = "structures",
                      layout: str = "separate") -> dict:
    """SDF export. 'separate' = one record per compound; 'single_canvas' = one side-by-side drawing."""
    if layout not in ("separate", "single_canvas"):
        raise ToolError("layout must be 'separate' or 'single_canvas'.")
    resolved, failed = _resolve_mols(compounds)
    if not resolved:
        raise ToolError("None of the compounds could be resolved: " + "; ".join(failed))

    path = _export_path(filename, ".sdf")
    with Chem.SDWriter(str(path)) as writer:
        if layout == "separate":
            for label, mol in resolved:
                AllChem.Compute2DCoords(mol)
                mol.SetProp("_Name", label)
                writer.write(mol)
        else:
            mols = [m for _, m in resolved]
            _layout_row(mols)
            canvas = mols[0]
            for m in mols[1:]:
                canvas = Chem.CombineMols(canvas, m)
            canvas.SetProp("_Name", " + ".join(label for label, _ in resolved))
            writer.write(canvas)
    return {"path": str(path), "layout": layout,
            "exported": [label for label, _ in resolved], "failed": failed,
            "note": "SDF opens directly in ChemDraw, MarvinSketch, etc."}


def draw_structures_image(compounds: list[str], legend: str = "name", columns: int = 4,
                          filename: str = "structures_grid", image_format: str = "png") -> dict:
    """Grid image with real text legends (replaces the old dummy-atom 'labels')."""
    if image_format not in ("png", "svg"):
        raise ToolError("image_format must be 'png' or 'svg'.")
    resolved, failed = _resolve_mols(compounds)
    if not resolved:
        raise ToolError("None of the compounds could be resolved: " + "; ".join(failed))

    legends = []
    for i, (label, mol) in enumerate(resolved, 1):
        parts = []
        if "index" in legend:
            parts.append(f"{i}")
        if "name" in legend:
            parts.append(label)
        if "cas" in legend:
            cas = None
            try:
                cas = (pc.cas_numbers_for_cid(pc.resolve_cid(label)) or [None])[0]
            except ToolError:
                pass
            parts.append(f"CAS {cas or 'n/a'}")
        if "formula" in legend:
            parts.append(rdMolDescriptors.CalcMolFormula(mol))
        legends.append("  ".join(parts))

    mols = [m for _, m in resolved]
    cols = max(1, min(int(columns), len(mols)))
    img = Draw.MolsToGridImage(mols, molsPerRow=cols, subImgSize=(300, 260), legends=legends,
                               useSVG=image_format == "svg")
    path = _export_path(filename, f".{image_format}")
    if image_format == "svg":
        path.write_text(img if isinstance(img, str) else img.data)
    else:
        img.save(str(path))
    return {"path": str(path), "compounds": [label for label, _ in resolved],
            "legends": legends, "failed": failed}


def export_reaction(reactants: list[str], products: list[str], reagents: list[str] | None = None,
                    filename: str = "reaction", image: bool = True) -> dict:
    """MDL .rxn (opens in ChemDraw with a real reaction arrow) plus an optional PNG preview."""
    rxn = rdChemReactions.ChemicalReaction()
    failed = []
    for group, add in ((reactants, rxn.AddReactantTemplate),
                       (products, rxn.AddProductTemplate),
                       (reagents or [], rxn.AddAgentTemplate)):
        resolved, bad = _resolve_mols(group)
        failed.extend(bad)
        for _, mol in resolved:
            AllChem.Compute2DCoords(mol)
            add(mol)
    if rxn.GetNumReactantTemplates() == 0 or rxn.GetNumProductTemplates() == 0:
        raise ToolError("Need at least one resolvable reactant and product. " + "; ".join(failed))

    path = _export_path(filename, ".rxn")
    path.write_text(rdChemReactions.ReactionToRxnBlock(rxn, separateAgents=True))
    out = {"rxn_path": str(path),
           "reaction_smiles": rdChemReactions.ReactionToSmiles(rxn),
           "failed": failed}
    if image:
        png = _export_path(filename, ".png")
        Draw.ReactionToImage(rxn, subImgSize=(260, 220)).save(str(png))
        out["image_path"] = str(png)
    return out


def image_to_structure(image_path: str, lookup: bool = True) -> dict:
    """Optical structure recognition with DECIMER (optional heavy dependency)."""
    try:
        from DECIMER import predict_SMILES
    except ImportError:
        raise ToolError("DECIMER is not installed (pip install decimer). Claude can also read "
                        "structure images directly and pass a SMILES to other tools.")
    p = _input_path(image_path)
    smiles = predict_SMILES(str(p))
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        raise ToolError(f"DECIMER produced an invalid structure: {smiles!r}")
    out = {"image": str(p.relative_to(WORKDIR)), "predicted": _describe(mol),
           "warning": "OCSR predictions can be wrong - check stereochemistry and charges."}
    if lookup:
        try:
            out["pubchem_match"] = get_compound_info(Chem.MolToSmiles(mol), identifier_type="smiles")
        except ToolError as e:
            out["pubchem_match"] = None
            out["lookup_error"] = str(e)
    return out
