#!/usr/bin/env python3
"""Regenerate scripts/reagents.json (shared by chem-tools and cdx-tools) from PubChem.

    uv run --no-project --with requests python tools/gen_reagents.py

Reagent abbreviations such as NBS, NIS or BOP are also valid SMILES, so the skills check this
table before treating a short all-letter string as SMILES. Only full names are written here; the
structures come from PubChem, so a typo in a hand-written SMILES can't creep in. Review the
printed titles after regenerating.
"""

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# abbreviation -> PubChem name to look up
REAGENTS = {
    # halogenation
    "NBS": "N-bromosuccinimide", "NCS": "N-chlorosuccinimide", "NIS": "N-iodosuccinimide",
    "DBDMH": "1,3-dibromo-5,5-dimethylhydantoin", "TCCA": "trichloroisocyanuric acid",
    "Selectfluor": "selectfluor",
    # coupling / activation
    "DCC": "dicyclohexylcarbodiimide", "DIC": "N,N'-diisopropylcarbodiimide",
    "EDC": "1-ethyl-3-(3-dimethylaminopropyl)carbodiimide", "HOBt": "1-hydroxybenzotriazole",
    "HATU": "HATU", "HBTU": "HBTU", "BOP": "BOP reagent", "PyBOP": "PyBOP",
    "CDI": "1,1'-carbonyldiimidazole", "NHS": "N-hydroxysuccinimide", "DPPA": "diphenylphosphoryl azide",
    "DEAD": "diethyl azodicarboxylate", "DIAD": "diisopropyl azodicarboxylate",
    # bases and nucleophilic catalysts
    "DMAP": "4-dimethylaminopyridine", "DBU": "1,8-diazabicyclo[5.4.0]undec-7-ene",
    "DABCO": "1,4-diazabicyclo[2.2.2]octane", "DIPEA": "N,N-diisopropylethylamine",
    "DIEA": "N,N-diisopropylethylamine", "TEA": "triethylamine", "TMEDA": "tetramethylethylenediamine",
    "LDA": "lithium diisopropylamide", "LiHMDS": "lithium bis(trimethylsilyl)amide",
    "LHMDS": "lithium bis(trimethylsilyl)amide", "NaHMDS": "sodium bis(trimethylsilyl)amide",
    "KHMDS": "potassium bis(trimethylsilyl)amide",
    # reductants / oxidants
    "DIBAL": "diisobutylaluminum hydride", "LAH": "lithium aluminum hydride",
    "DDQ": "2,3-dichloro-5,6-dicyano-1,4-benzoquinone", "mCPBA": "3-chloroperbenzoic acid",
    "DMP": "Dess-Martin periodinane", "IBX": "2-iodoxybenzoic acid", "NMO": "N-methylmorpholine N-oxide",
    "TPAP": "tetrapropylammonium perruthenate", "PCC": "pyridinium chlorochromate",
    "PDC": "pyridinium dichromate", "TEMPO": "TEMPO", "TBHP": "tert-butyl hydroperoxide",
    "DTBP": "di-tert-butyl peroxide", "CAN": "ceric ammonium nitrate",
    "PIDA": "(diacetoxyiodo)benzene", "PIFA": "[bis(trifluoroacetoxy)iodo]benzene",
    "AIBN": "azobisisobutyronitrile", "BHT": "2,6-di-tert-butyl-4-methylphenol",
    # acids, sulfonylating and silylating agents
    "TFA": "trifluoroacetic acid", "TFAA": "trifluoroacetic anhydride", "TfOH": "triflic acid",
    "TsOH": "p-toluenesulfonic acid", "PTSA": "p-toluenesulfonic acid", "TsCl": "tosyl chloride",
    "MsCl": "methanesulfonyl chloride", "PPTS": "pyridinium p-toluenesulfonate",
    "TMSCl": "chlorotrimethylsilane",
    "TBSCl": "tert-butyldimethylsilyl chloride", "TBDPSCl": "tert-butyldiphenylchlorosilane",
    "TIPSCl": "triisopropylsilyl chloride", "TMSOTf": "trimethylsilyl trifluoromethanesulfonate",
    "TBAF": "tetrabutylammonium fluoride", "TBAI": "tetrabutylammonium iodide",
    "TBAB": "tetrabutylammonium bromide",
    # solvents
    "THF": "tetrahydrofuran", "DCM": "dichloromethane", "DCE": "1,2-dichloroethane",
    "DMF": "N,N-dimethylformamide", "DMSO": "dimethyl sulfoxide", "DMA": "N,N-dimethylacetamide",
    "NMP": "N-methyl-2-pyrrolidone", "DME": "1,2-dimethoxyethane", "MTBE": "methyl tert-butyl ether",
    "HMPA": "hexamethylphosphoramide", "DMPU": "DMPU", "HFIP": "hexafluoroisopropanol",
    "TFE": "2,2,2-trifluoroethanol", "MeCN": "acetonitrile",
    # ligands
    "dppf": "1,1'-bis(diphenylphosphino)ferrocene", "dppe": "1,2-bis(diphenylphosphino)ethane",
    "dppp": "1,3-bis(diphenylphosphino)propane", "dba": "dibenzylideneacetone",
    "cod": "1,5-cyclooctadiene", "XPhos": "XPhos", "SPhos": "SPhos",
}

# Abbreviations that name several different compounds: refuse to guess
AMBIGUOUS = {
    "CBS": "CBS can mean the (R)- or (S)-2-methyl-CBS-oxazaborolidine (or another CBS catalyst). "
           "Give the full name or a SMILES with stereochemistry.",
    "TMS": "TMS can mean tetramethylsilane or the trimethylsilyl group. Give the full name or a SMILES.",
    "CSA": "CSA (10-camphorsulfonic acid) is used racemic and as either enantiomer. Give (+)-, (-)- "
           "or (±)-CSA, or a SMILES.",
    "BINAP": "BINAP is used as (R)-, (S)- or racemic BINAP. Say which, or give a SMILES.",
    "CO": "as SMILES 'CO' is methanol (CH4O), but CO usually means carbon monoxide (or Co, cobalt). "
          "Give the full name, or {\"smiles\": \"CO\"} for methanol.",
    "NO": "as SMILES 'NO' is hydroxylamine (H3NO), but NO usually means nitric oxide. "
          "Give the full name, or {\"smiles\": \"NO\"} for hydroxylamine.",
    "CN": "as SMILES 'CN' is methylamine (CH5N), but CN usually means cyanide. "
          "Give the full name, or {\"smiles\": \"CN\"} for methylamine.",
    "CS": "as SMILES 'CS' is methanethiol (CH4S), but CS usually means carbon monosulfide or caesium (Cs). "
          "Give the full name, or {\"smiles\": \"CS\"} for methanethiol.",
    "SO": "as SMILES 'SO' is a sulfur-oxygen hydride, but SO usually means sulfur monoxide. Give the full name.",
    "Bn": "Bn is a benzyl group, not a compound. Draw the whole molecule as SMILES.",
    "Boc": "Boc is a protecting group, not a compound. Draw the whole molecule as SMILES "
           "(Boc2O is di-tert-butyl dicarbonate).",
}


def fetch(name: str, attempts: int = 4) -> dict:
    for i in range(attempts):  # PubChem returns occasional 502/503s under load
        try:
            return _fetch(name)
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code < 500 or i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def _fetch(name: str) -> dict:
    r = requests.post(f"{PUG}/compound/name/cids/JSON", data={"name": name}, timeout=20)
    r.raise_for_status()
    cid = r.json()["IdentifierList"]["CID"][0]
    p = requests.get(f"{PUG}/compound/cid/{cid}/property/Title,SMILES,MolecularFormula/JSON", timeout=20)
    p.raise_for_status()
    props = p.json()["PropertyTable"]["Properties"][0]
    return {"name": props["Title"], "cid": cid, "smiles": props["SMILES"], "formula": props["MolecularFormula"]}


def main() -> int:
    table, failed = {}, []
    for abbr, query in REAGENTS.items():
        try:
            table[abbr] = {"query": query, **fetch(query)}
            print(f"{abbr:9} {table[abbr]['formula']:16} {table[abbr]['name']}")
        except Exception as e:
            failed.append(f"{abbr} ({query}): {e}")
        time.sleep(0.25)  # PubChem asks for <= 5 requests/second
    if failed:
        print("\nFAILED:\n  " + "\n  ".join(failed))
        return 1
    data = {"_note": "Generated by tools/gen_reagents.py from PubChem. Do not edit by hand.",
            "reagents": table, "ambiguous": AMBIGUOUS}
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    for skill in ("chem-tools", "cdx-tools"):
        (ROOT / skill / "scripts" / "reagents.json").write_text(text)
    print(f"\nwrote {len(table)} reagents + {len(AMBIGUOUS)} ambiguous entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
