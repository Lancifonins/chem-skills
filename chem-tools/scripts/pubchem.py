"""Thin PubChem / ChEMBL HTTP layer shared by every chemistry tool.

One pooled session with retries, a polite rate limit (PubChem allows 5 req/s),
and identifier resolution that never puts user text in a URL path unescaped.
"""

import re
import threading
import time
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
    if " " not in ident:
        RDLogger.DisableLog("rdApp.*")
        try:
            if Chem.MolFromSmiles(ident) is not None:
                return "smiles"
        finally:
            RDLogger.EnableLog("rdApp.*")
    return "name"


def resolve_cids(identifier: str, identifier_type: str = "auto") -> list[int]:
    """Map a name / CAS / SMILES / InChI / InChIKey / CID to PubChem CIDs."""
    ident = str(identifier).strip()
    if not ident:
        raise ToolError("Empty identifier.")
    kind = detect_identifier_type(ident) if identifier_type == "auto" else identifier_type

    if kind == "cid":
        return [int(ident)]
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


def smiles_for(identifier: str) -> str:
    """Local SMILES if the identifier parses, otherwise PubChem's SMILES for it."""
    if detect_identifier_type(identifier) == "smiles":
        return identifier.strip()
    props = properties_for_cids([resolve_cid(identifier)])
    if not props or not props[0].get("SMILES"):
        raise ToolError(f"PubChem returned no structure for '{identifier}'.")
    return props[0]["SMILES"]


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
