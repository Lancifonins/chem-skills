"""Thin PubChem / ChEMBL HTTP layer shared by every chemistry tool.

One pooled session with retries, a polite rate limit (PubChem allows 5 req/s),
and identifier resolution that never puts user text in a URL path unescaped.
"""

import contextlib
import io
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
TIMEOUT = 20

CAS_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")
INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


class ToolError(Exception):
    """A user-facing failure; the message is returned to Claude as the tool error."""


_session = requests.Session()
_session.headers["User-Agent"] = "chem-skill/1.0 (research assistant)"
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
    ),
)

_MIN_INTERVAL = 0.22
_last_call = 0.0
_lock = threading.Lock()


def _throttle():
    global _last_call
    with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def request(method: str, url: str, **kwargs) -> requests.Response:
    """HTTP call with throttling; 404 is returned (callers treat it as 'not found')."""
    _throttle()
    try:
        res = _session.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as e:
        raise ToolError(f"Network error contacting {url.split('/')[2]}: {e}") from e
    if res.status_code >= 400 and res.status_code != 404:
        detail = ""
        try:
            detail = res.json().get("Fault", {}).get("Message", "")
        except ValueError:
            pass
        # PubChem answers 400 "No CID found" for unknown names
        if "No CID found" in detail or "not found" in detail.lower():
            res.status_code = 404
            return res
        raise ToolError(f"{url.split('/')[2]} returned HTTP {res.status_code} {detail}".strip())
    return res


def get_json(url: str, **kwargs) -> dict | None:
    res = request("GET", url, **kwargs)
    return None if res.status_code == 404 else res.json()


def seg(text: str) -> str:
    """Escape a value for use as one URL path segment (SMILES contain '/', '#', etc.)."""
    return quote(str(text), safe="")


# ---------------------------------------------------------------- CAS numbers

def is_valid_cas(cas: str) -> bool:
    """Format + check-digit validation (the old regex accepted any ##-##-# string)."""
    m = CAS_RE.match(cas.strip())
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


def cas_numbers_for_cid(cid: int) -> list[str]:
    """Valid CAS numbers among a CID's synonyms, in PubChem's relevance order."""
    data = get_json(f"{PUG}/compound/cid/{cid}/synonyms/JSON")
    if not data:
        return []
    synonyms = data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
    seen, out = set(), []
    for s in synonyms:
        s = s.strip()
        if s not in seen and is_valid_cas(s):
            seen.add(s)
            out.append(s)
    return out


# ------------------------------------------------------ identifier resolution

_ALL_LETTERS = re.compile(r"^[A-Za-z]+$")
# Characters that occur in SMILES but essentially never in compound names
_SMILES_SYNTAX = re.compile(r"[=#@\\/%\[\]()]")
_NAME_SYNTAX = re.compile(r"[\s,']")


@dataclass
class Resolved:
    """A structure plus how the input was understood, so tools can report it back."""
    smiles: str
    interpreted_as: str              # smiles | abbreviation | name | cas | cid | inchi | inchikey
    name: str | None = None
    cid: int | None = None
    note: str | None = None

    def info(self) -> dict:
        out = {"interpreted_as": self.interpreted_as}
        if self.note:
            out["note"] = self.note
        return out


@contextlib.contextmanager
def _silence_fd2():
    """RDKit writes some messages straight to the C++ stderr stream."""
    saved = os.dup(2)
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 2)
        try:
            yield
        finally:
            os.dup2(saved, 2)
            os.close(saved)


def smiles_problem(smiles: str) -> str | None:
    """RDKit's reason a SMILES is invalid (syntax or chemistry), or None if it is fine."""
    from rdkit import Chem, RDLogger, rdBase

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("rdkit")
    logger.addHandler(handler)
    logger.propagate = False
    rdBase.LogToPythonLogger()
    RDLogger.EnableLog("rdApp.error")
    try:
        with _silence_fd2():
            mol = Chem.MolFromSmiles(smiles, sanitize=False)
            problems = [] if mol is None else Chem.DetectChemistryProblems(mol)
    finally:
        RDLogger.DisableLog("rdApp.*")
        rdBase.LogToCppStreams()
        logger.removeHandler(handler)
    if mol is not None:
        return problems[0].Message() if problems else None
    text = stream.getvalue()
    lines = [re.sub(r"^\[[\d:]+\]\s*", "", ln).strip() for ln in text.splitlines() if ln.strip()]
    reason = lines[0] if lines else "could not be parsed"
    reason = re.sub(r"^SMILES Parse Error:\s*", "", reason)
    reason = re.sub(r"\s+(while parsing|for input):.*$", "", reason)
    pos = re.search(r"around position (\d+)", text)
    return reason + (f" near character {pos.group(1)}" if pos else "")


def _looks_like_smiles(ident: str) -> bool:
    """True for strings that can only be meant as SMILES (so a parse failure is a real error)."""
    if _NAME_SYNTAX.search(ident) or not _SMILES_SYNTAX.search(ident):
        return False
    bare = re.sub(r"\[[^\]]*\]", "", ident).replace("Cl", "").replace("Br", "")
    return not re.search(r"[a-z]", re.sub(r"[cnospb]", "", bare))  # other lowercase = a name


_REAGENTS: dict | None = None


def reagent_table() -> tuple[dict, dict]:
    """(abbreviation -> reagent, abbreviation -> why it is ambiguous), from reagents.json."""
    global _REAGENTS
    if _REAGENTS is None:
        try:
            _REAGENTS = json.loads((Path(__file__).with_name("reagents.json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _REAGENTS = {}
    return _REAGENTS.get("reagents", {}), _REAGENTS.get("ambiguous", {})


def detect_identifier_type(identifier: str) -> str:
    from rdkit import Chem, RDLogger

    ident = identifier.strip()
    if ident.isdigit():
        return "cid"
    if CAS_RE.match(ident):
        return "cas"
    if INCHIKEY_RE.match(ident):
        return "inchikey"
    if ident.startswith("InChI="):
        return "inchi"
    if ident in reagent_table()[0]:
        return "abbreviation"
    if " " not in ident:
        RDLogger.DisableLog("rdApp.*")
        if Chem.MolFromSmiles(ident) is not None or _looks_like_smiles(ident):
            return "smiles"
    return "name"


def resolve_cids(identifier: str, identifier_type: str = "auto") -> list[int]:
    """Map a name / CAS / SMILES / InChI / InChIKey / CID to PubChem CIDs (no ambiguity checks)."""
    ident = str(identifier).strip()
    if not ident:
        raise ToolError("Empty identifier.")
    kind = detect_identifier_type(ident) if identifier_type == "auto" else identifier_type

    if kind == "cid":
        return [int(ident)]
    if kind == "abbreviation":
        entry = reagent_table()[0].get(ident)
        if not entry:
            raise ToolError(f"'{ident}' is not in the reagent abbreviation table.")
        return [entry["cid"]]
    if kind in ("name", "cas"):  # PubChem indexes CAS numbers as synonyms
        res = request("POST", f"{PUG}/compound/name/cids/JSON", data={"name": ident})
    elif kind == "smiles":
        res = request("POST", f"{PUG}/compound/smiles/cids/JSON", data={"smiles": ident})
    elif kind == "inchi":
        res = request("POST", f"{PUG}/compound/inchi/cids/JSON", data={"inchi": ident})
    elif kind == "inchikey":
        res = request("GET", f"{PUG}/compound/inchikey/{seg(ident)}/cids/JSON")
    else:
        raise ToolError(f"Unknown identifier_type '{identifier_type}'.")

    if res.status_code == 404:
        return []
    cids = [c for c in res.json().get("IdentifierList", {}).get("CID", []) if c]
    return cids


def resolve_cid(identifier: str, identifier_type: str = "auto") -> int:
    cids = resolve_cids(identifier, identifier_type)
    if not cids:
        raise ToolError(f"PubChem has no compound matching '{identifier}'.")
    return cids[0]


def _formula(smiles: str) -> str:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    return rdMolDescriptors.CalcMolFormula(mol) if mol is not None else "?"


def resolve_structure(identifier: str, identifier_type: str = "auto") -> Resolved:
    """Turn any identifier into a structure, refusing to guess when the input is ambiguous.

    All-letter strings like NBS, NIS or BOP are valid SMILES *and* reagent abbreviations, so in
    auto mode they go through the reagent table and abbreviation rules instead of silently
    becoming an N-B-S chain.
    """
    ident = str(identifier).strip()
    if not ident:
        raise ToolError("Empty identifier.")
    kind = identifier_type
    reagents, ambiguous = reagent_table()

    if kind == "auto":
        if ident in ambiguous:
            raise ToolError(f"'{ident}' is ambiguous: {ambiguous[ident]}")
        kind = detect_identifier_type(ident)
        if kind == "smiles" and _ALL_LETTERS.match(ident):
            return _all_letter_smiles(ident)

    if kind == "abbreviation":
        entry = reagents.get(ident)
        if not entry:
            raise ToolError(f"'{ident}' is not in the reagent abbreviation table.")
        return Resolved(entry["smiles"], "abbreviation", entry["name"], entry["cid"],
                        f"'{ident}' read as the reagent abbreviation for {entry['name']} ({entry['formula']}).")
    if kind == "smiles":
        problem = smiles_problem(ident)
        if problem:
            raise ToolError(f"'{ident}' is not valid SMILES: {problem}.")
        return Resolved(ident, "smiles")

    try:
        cid = resolve_cid(ident, kind)
    except ToolError as e:
        hint = ""
        if kind == "name" and " " not in ident and re.search(r"[A-Z]", ident):
            problem = smiles_problem(ident)
            if problem:
                hint = f" If it was meant as SMILES, it is not valid: {problem}."
        raise ToolError(f"{e}{hint}") from None
    props = properties_for_cids([cid])
    if not props or not props[0].get("SMILES"):
        raise ToolError(f"PubChem returned no structure for '{ident}'.")
    note = None
    if kind == "name" and len(ident) <= 6 and " " not in ident:
        # Short names match depositor synonyms of unrelated compounds surprisingly often
        note = (f"'{ident}' was looked up as a PubChem name and matched {props[0].get('Title')} "
                f"({props[0].get('MolecularFormula', '?')}). Check this is the compound you meant.")
    return Resolved(props[0]["SMILES"], kind, props[0].get("Title"), cid, note)


def _all_letter_smiles(ident: str) -> Resolved:
    """All-letter strings are valid SMILES but often abbreviations ('NBS' parses as H2N-BH-SH).

    Known reagents and two-letter formulas are handled by the reagent table before this point.
    Of the rest, boron or phosphorus in an all-letter SMILES is almost never intended, so those
    are refused; anything else is read as SMILES, with its formula reported so it can be checked.
    """
    formula = _formula(ident)
    if re.search(r"B(?!r)|P", ident):
        raise ToolError(
            f"'{ident}' looks like an abbreviation: read as SMILES it would be {formula}, which is "
            f"unlikely to be meant, and it is not in the reagent table. Give the full compound name, or "
            f"pass {{\"smiles\": \"{ident}\"}} (identifier_type 'smiles') if you really mean that SMILES.")
    note = None
    if len(ident) <= 4 and ident.isupper():
        note = (f"'{ident}' read as SMILES ({formula}). If it was meant as an abbreviation, give the "
                "full compound name instead.")
    return Resolved(ident, "smiles", note=note)


PROPERTY_FIELDS = (
    "Title,IUPACName,MolecularFormula,MolecularWeight,ExactMass,"
    "SMILES,ConnectivitySMILES,InChIKey,XLogP,TPSA,Charge"
)


def properties_for_cids(cids: list[int]) -> list[dict]:
    """Batch property fetch - one request for many CIDs instead of N+1 lookups."""
    if not cids:
        return []
    data = get_json(f"{PUG}/compound/cid/{','.join(map(str, cids))}/property/{PROPERTY_FIELDS}/JSON")
    return data.get("PropertyTable", {}).get("Properties", []) if data else []


def smiles_for(identifier: str, identifier_type: str = "auto") -> str:
    """SMILES for any identifier (see resolve_structure for how ambiguity is handled)."""
    return resolve_structure(identifier, identifier_type).smiles


# ---------------------------------------------------------- PUG-View sections

def pug_view_section(cid: int, heading: str) -> list[dict]:
    """All Information entries under a PUG-View heading, however deeply nested."""
    data = get_json(f"{PUG_VIEW}/data/compound/{cid}/JSON", params={"heading": heading})
    if not data:
        return []
    found = []

    def walk(sections):
        for sec in sections:
            if sec.get("TOCHeading") == heading:
                found.extend(sec.get("Information", []))
            walk(sec.get("Section", []))

    walk(data.get("Record", {}).get("Section", []))
    return found


def info_strings(info: dict) -> list[str]:
    value = info.get("Value", {})
    strings = [s.get("String", "").strip() for s in value.get("StringWithMarkup", [])]
    if "Number" in value:
        unit = value.get("Unit", "")
        strings.append(" ".join([", ".join(map(str, value["Number"])), unit]).strip())
    return [s for s in strings if s]
