"""Minimal native ChemDraw (CDXML) writer.

Coordinates are ChemDraw points (1/72 inch), y pointing down, ACS-1996 drawing
settings (14.4 pt bonds, Arial 10). Structures come from RDKit molecules; text,
arrows and reaction-step metadata are written as native ChemDraw objects so the
result is fully editable in ChemDraw.
"""

import math
import re
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from rdkit import Chem
from rdkit.Chem import rdDepictor

BOND_LENGTH = 14.4
FONT_ID = 3
LABEL_SIZE = 10.0
CHAR_W = 0.56   # average Arial glyph width, in em
LINE_H = 1.2    # line height, in em
MARGIN = 36.0   # page margin, pt
PAGE_W, PAGE_H = 540.0, 720.0

# CDXML face bits: 1 bold, 2 italic, 32 subscript, 64 superscript; 96 = ChemDraw's "formula"
# style, which subscripts digits and superscripts a trailing +/- (so "NH3+" renders as NH3+).
PLAIN, BOLD, ITALIC, SUBSCRIPT, SUPERSCRIPT, FORMULA = 0, 1, 2, 32, 64, 96

# Text fonts use iso-8859-1, so anything outside Latin-1 would show as "?" in ChemDraw.
# Greek goes through the Symbol font the way ChemDraw writes it (Latin letter in Symbol = Greek).
SYMBOL_FONT_ID = 7
_GREEK_TO_SYMBOL = dict(zip("αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ", "abgdezhqiklmnxoprstufcywGDQLXPSFYW"))
_REPLACEMENTS = {"\u2212": "-", "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-",
                 "\u2192": "->", "\u27f6": "->", "\u2022": "\u00b7", "\u2032": "'", "\u2033": "''",
                 "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2264": "<=",
                 "\u2265": ">=", "\u2248": "~", "\u2026": "...", "\u2009": " ", "\u202f": " "}


def encode_text(text: str, warnings: list[str] | None = None) -> list[tuple[str, int]]:
    """Split text into (chunk, font id) pieces that ChemDraw can display."""
    import unicodedata

    pieces: list[tuple[str, int]] = []
    for ch in text:
        if ch in _GREEK_TO_SYMBOL:
            out, font = _GREEK_TO_SYMBOL[ch], SYMBOL_FONT_ID
        else:
            out, font = _REPLACEMENTS.get(ch, ch), FONT_ID
            try:
                out.encode("latin-1")
            except UnicodeEncodeError:
                ascii_ = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
                out = ascii_ or "?"
                if warnings is not None and not ascii_:
                    warnings.append(f"'{ch}' (U+{ord(ch):04X}) cannot be shown in ChemDraw's text font; "
                                    "written as '?'.")
        if pieces and pieces[-1][1] == font:
            pieces[-1] = (pieces[-1][0] + out, font)
        else:
            pieces.append((out, font))
    return pieces


def runs_xml(runs: list[tuple[str, int]], size: float, warnings: list[str] | None = None) -> str:
    return "".join(f'<s font="{font}" size="{size:g}" face="{face}">{escape(chunk)}</s>'
                   for text, face in runs for chunk, font in encode_text(text, warnings))

_FORMULA_TOKEN = re.compile(r"^[A-Z][A-Za-z]*(?:\(?[A-Za-z]*\)?\d+[A-Za-z()]*)+$")


def _f(v: float) -> str:
    return f"{v:.2f}"


def text_width(text: str, size: float = LABEL_SIZE) -> float:
    return max((len(line) for line in text.split("\n")), default=0) * CHAR_W * size


def rich_runs(text: str) -> list[tuple[str, int]]:
    """Split free text into runs, subscripting digits only in formula-like tokens (H2SO4, Et3N)."""
    runs = []
    for tok in re.split(r"([\s,;:/]+)", text):
        if not tok:
            continue
        face = FORMULA if _FORMULA_TOKEN.match(tok) else PLAIN
        if runs and runs[-1][1] == face:
            runs[-1] = (runs[-1][0] + tok, face)
        else:
            runs.append((tok, face))
    return runs


# ------------------------------------------------------------ molecule prep

@dataclass
class PreparedMol:
    mol: Chem.Mol
    xy: list[tuple[float, float]]           # atom positions, pt, bbox-min at (0, 0)
    width: float
    height: float
    labels: dict[int, tuple[list, str]] = field(default_factory=dict)  # idx -> (runs, justification)


def _atom_label(atom: Chem.Atom, xy, mol) -> tuple[list, str] | None:
    sym = atom.GetSymbol()
    charge = atom.GetFormalCharge()
    iso = atom.GetIsotope()
    radicals = atom.GetNumRadicalElectrons()
    if sym == "C" and not charge and not iso and not radicals and atom.GetDegree() > 0:
        return None
    h = atom.GetTotalNumHs()
    hpart = "" if h == 0 else ("H" if h == 1 else f"H{h}")

    # Put H on the side away from the bonds ("HO-" vs "-OH")
    right = False
    if hpart and atom.GetDegree() > 0:
        x0 = xy[atom.GetIdx()][0]
        dx = sum(xy[n.GetIdx()][0] - x0 for n in atom.GetNeighbors())
        right = dx > 0.5

    # ChemDraw's own files write a charged label as one formula-style run ("N+", "O-", ASCII
    # hyphen). A charge of 2 or more needs an explicit superscript, or the digit would be
    # subscripted. Radicals are drawn by ChemDraw from the node's Radical attribute.
    sign = "" if not charge else ("+" if charge > 0 else "-")
    one = sign if abs(charge) == 1 else ""
    multi = [(f"{abs(charge)}{sign}", SUPERSCRIPT)] if abs(charge) > 1 else []
    isotope = [(str(iso), SUPERSCRIPT)] if iso else []
    if right:  # H2N-, H3(13)C-: the isotope sits directly before its element symbol
        runs = [(hpart, FORMULA)] + isotope + [(sym + one, FORMULA)] + multi
    else:
        runs = isotope + [(sym + hpart + one, FORMULA)] + multi
    return runs, ("Right" if right else "Left")


def prepare(mol: Chem.Mol) -> PreparedMol:
    """2D-lay out a molecule and convert it to ChemDraw point coordinates."""
    mol = Chem.Mol(mol)
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    conf = mol.GetConformer()
    Chem.WedgeMolBonds(mol, conf)
    Chem.Kekulize(mol, clearAromaticFlags=True)

    pts = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())]
    lengths = [math.dist(pts[b.GetBeginAtomIdx()], pts[b.GetEndAtomIdx()]) for b in mol.GetBonds()]
    scale = BOND_LENGTH / (sum(lengths) / len(lengths) if lengths else 1.5)
    xy = [(x * scale, -y * scale) for x, y in pts]

    labels = {}
    for atom in mol.GetAtoms():
        lab = _atom_label(atom, xy, mol)
        if lab:
            labels[atom.GetIdx()] = lab

    # Bounding box, padded where atom labels stick out
    xs0, xs1, ys0, ys1 = [], [], [], []
    for i, (x, y) in enumerate(xy):
        pad_x = 0.0
        if i in labels:
            pad_x = sum(len(t) for t, _ in labels[i][0]) * CHAR_W * LABEL_SIZE
        pad_y = 5.0 if i in labels else 0.0
        left = pad_x if i in labels and labels[i][1] == "Right" else (4.0 if i in labels else 0)
        right = pad_x if i in labels and labels[i][1] == "Left" else (4.0 if i in labels else 0)
        xs0.append(x - left); xs1.append(x + right); ys0.append(y - pad_y); ys1.append(y + pad_y)
    minx, miny = min(xs0), min(ys0)
    xy = [(x - minx, y - miny) for x, y in xy]
    return PreparedMol(mol, xy, max(xs1) - minx, max(ys1) - miny, labels)


# ---------------------------------------------------------------- document

class CDXMLDocument:
    def __init__(self, title: str = ""):
        self.title = title
        self._next_id = 1000
        self.objects: list[str] = []
        self.steps: list[dict] = []
        self.warnings: list[str] = []  # e.g. characters ChemDraw's fonts can't show
        self.x0 = self.y0 = math.inf
        self.x1 = self.y1 = -math.inf

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _grow(self, x0, y0, x1, y1):
        self.x0, self.y0 = min(self.x0, x0), min(self.y0, y0)
        self.x1, self.y1 = max(self.x1, x1), max(self.y1, y1)

    # --- structures
    def add_molecule(self, pm: PreparedMol, left: float, top: float) -> int:
        frag_id = self._id()
        atom_ids = {}
        parts = []
        for atom in pm.mol.GetAtoms():
            i = atom.GetIdx()
            aid = atom_ids[i] = self._id()
            x, y = pm.xy[i][0] + left, pm.xy[i][1] + top
            attrs = [f'id="{aid}"', f'p="{_f(x)} {_f(y)}"', 'Z="1"']
            if atom.GetAtomicNum() != 6:
                attrs.append(f'Element="{atom.GetAtomicNum()}"')
            if i in pm.labels or atom.GetAtomicNum() != 6:
                attrs.append(f'NumHydrogens="{atom.GetTotalNumHs()}"')
            if atom.GetFormalCharge():
                attrs.append(f'Charge="{atom.GetFormalCharge()}"')
            if atom.GetIsotope():
                attrs.append(f'Isotope="{atom.GetIsotope()}"')
            if atom.GetNumRadicalElectrons():
                attrs.append('Radical="Doublet"' if atom.GetNumRadicalElectrons() == 1 else 'Radical="Triplet"')
            if i in pm.labels:
                runs, just = pm.labels[i]
                lx = x - 3.25 if just == "Left" else x + 3.25
                label = runs_xml(runs, LABEL_SIZE, self.warnings)
                parts.append(f'<n {" ".join(attrs)} AS="N">'
                             f'<t p="{_f(lx)} {_f(y + 3.52)}" LabelJustification="{just}" '
                             f'LabelAlignment="{just}">{label}</t></n>')
            else:
                parts.append(f'<n {" ".join(attrs)}/>')

        for bond in pm.mol.GetBonds():
            b, e = atom_ids[bond.GetBeginAtomIdx()], atom_ids[bond.GetEndAtomIdx()]
            order = {Chem.BondType.SINGLE: "1", Chem.BondType.DOUBLE: "2",
                     Chem.BondType.TRIPLE: "3"}.get(bond.GetBondType(), "1")
            attrs = [f'id="{self._id()}"', 'Z="1"', f'B="{b}"', f'E="{e}"']
            if order != "1":
                attrs.append(f'Order="{order}"')
            display = {Chem.BondDir.BEGINWEDGE: "WedgeBegin",
                       Chem.BondDir.BEGINDASH: "WedgedHashBegin",
                       Chem.BondDir.UNKNOWN: "Wavy"}.get(bond.GetBondDir())
            if display:
                attrs.append(f'Display="{display}"')
            parts.append(f'<b {" ".join(attrs)}/>')

        box = (left, top, left + pm.width, top + pm.height)
        self._grow(*box)
        self.objects.append(f'<fragment id="{frag_id}" BoundingBox="{" ".join(map(_f, box))}" Z="1">'
                            + "".join(parts) + "</fragment>")
        return frag_id

    # --- text
    def add_text(self, cx: float, top: float, runs: list[tuple[str, int]],
                 size: float = LABEL_SIZE, justification: str = "Center") -> int:
        """Text block horizontally centred on cx (or left/right aligned to it), first line top at `top`."""
        tid = self._id()
        full = "".join(t for t, _ in runs)
        w = text_width(full, size)
        n_lines = full.count("\n") + 1
        h = n_lines * LINE_H * size
        x0 = {"Center": cx - w / 2, "Left": cx, "Right": cx - w}[justification]
        baseline = top + size * 0.9
        body = runs_xml(runs, size, self.warnings)
        self._grow(x0, top, x0 + w, top + h)
        self.objects.append(
            f'<t id="{tid}" p="{_f(cx)} {_f(baseline)}" BoundingBox="{_f(x0)} {_f(top)} {_f(x0 + w)} {_f(top + h)}" '
            f'Z="2" Justification="{justification}" LineHeight="auto" InterpretChemically="no">{body}</t>')
        return tid

    # --- arrows
    def add_arrow(self, x_tail: float, x_head: float, y: float) -> int:
        aid = self._id()
        mid = (x_tail + x_head) / 2
        half = (x_head - x_tail) / 2
        self._grow(x_tail, y - 4, x_head, y + 4)
        self.objects.append(
            f'<arrow id="{aid}" BoundingBox="{_f(x_tail)} {_f(y - 4)} {_f(x_head)} {_f(y + 4)}" Z="3" '
            f'FillType="None" ArrowheadHead="Full" ArrowheadType="Solid" HeadSize="1000" '
            f'ArrowheadCenterSize="875" ArrowheadWidth="250" '
            f'Head3D="{_f(x_head)} {_f(y)} 0" Tail3D="{_f(x_tail)} {_f(y)} 0" '
            f'Center3D="{_f(mid)} {_f(y)} 0" MajorAxisEnd3D="{_f(x_head)} {_f(y)} 0" '
            f'MinorAxisEnd3D="{_f(mid)} {_f(y + half)} 0"/>')
        return aid

    def add_step(self, reactants, products, arrow, above=(), below=()):
        self.steps.append(dict(reactants=reactants, products=products, arrow=arrow,
                               above=list(above), below=list(below)))

    # --- output
    def to_string(self) -> str:
        if not self.objects:
            raise ValueError("Empty document.")
        dx, dy = MARGIN - self.x0, MARGIN - self.y0
        body = "\n".join(self.objects)
        # Shift everything so content starts at the page margin
        body = _shift_coords(body, dx, dy)
        w = self.x1 - self.x0 + 2 * MARGIN
        h = self.y1 - self.y0 + 2 * MARGIN
        wp, hp = max(1, math.ceil(w / PAGE_W)), max(1, math.ceil(h / PAGE_H))

        scheme = ""
        if self.steps:
            steps = []
            for s in self.steps:
                a = [f'id="{self._id()}"',
                     f'ReactionStepReactants="{" ".join(map(str, s["reactants"]))}"',
                     f'ReactionStepProducts="{" ".join(map(str, s["products"]))}"',
                     f'ReactionStepArrows="{s["arrow"]}"']
                if s["above"]:
                    a.append(f'ReactionStepObjectsAboveArrow="{" ".join(map(str, s["above"]))}"')
                if s["below"]:
                    a.append(f'ReactionStepObjectsBelowArrow="{" ".join(map(str, s["below"]))}"')
                steps.append(f'<step {" ".join(a)}/>')
            scheme = f'<scheme id="{self._id()}">' + "".join(steps) + "</scheme>"

        bbox = f"{_f(MARGIN)} {_f(MARGIN)} {_f(w - MARGIN)} {_f(h - MARGIN)}"
        return (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            '<!DOCTYPE CDXML SYSTEM "http://www.cambridgesoft.com/xml/cdxml.dtd" >\n'
            f'<CDXML CreationProgram="cdx-tools" Name="{escape(self.title)}" BoundingBox="{bbox}" '
            f'WindowPosition="0 0" WindowSize="0 0" '
            f'FractionalWidths="yes" InterpretChemically="yes" ShowAtomQuery="yes" ShowAtomStereo="no" '
            f'ShowAtomEnhancedStereo="yes" ShowAtomNumber="no" ShowBondQuery="yes" ShowBondRxn="yes" '
            f'ShowBondStereo="no" ShowTerminalCarbonLabels="no" ShowNonTerminalCarbonLabels="no" '
            f'HideImplicitHydrogens="no" LabelFont="{FONT_ID}" LabelSize="{LABEL_SIZE:g}" LabelFace="96" '
            f'CaptionFont="{FONT_ID}" CaptionSize="{LABEL_SIZE:g}" HashSpacing="2.50" MarginWidth="1.60" '
            f'LineWidth="0.60" BoldWidth="2" BondLength="{BOND_LENGTH}" BondSpacing="18" ChainAngle="120" '
            f'LabelJustification="Auto" CaptionJustification="Left" AminoAcidTermini="HOH" '
            f'ShowSequenceTermini="yes" ShowSequenceBonds="yes" PrintMargins="36 36 36 36" '
            f'color="0" bgcolor="1">\n'
            '<colortable><color r="1" g="1" b="1"/><color r="0" g="0" b="0"/>'
            '<color r="1" g="0" b="0"/><color r="1" g="1" b="0"/><color r="0" g="1" b="0"/>'
            '<color r="0" g="1" b="1"/><color r="0" g="0" b="1"/><color r="1" g="0" b="1"/></colortable>\n'
            f'<fonttable><font id="{FONT_ID}" charset="iso-8859-1" name="Arial"/>'
            f'<font id="{SYMBOL_FONT_ID}" charset="Unknown" name="Symbol"/></fonttable>\n'
            f'<page id="{self._id()}" BoundingBox="0 0 {_f(wp * PAGE_W)} {_f(hp * PAGE_H)}" '
            f'HeaderPosition="36" FooterPosition="36" PrintTrimMarks="yes" '
            f'HeightPages="{hp}" WidthPages="{wp}">\n'
            f"{body}\n{scheme}\n</page>\n</CDXML>\n"
        )


_POINT_ATTRS = re.compile(r'\b(p|BoundingBox|Head3D|Tail3D|Center3D|MajorAxisEnd3D|MinorAxisEnd3D)="([^"]+)"')


def _shift_coords(xml: str, dx: float, dy: float) -> str:
    def repl(m):
        vals = [float(v) for v in m.group(2).split()]
        if m.group(1).endswith("3D"):
            vals = [vals[0] + dx, vals[1] + dy, vals[2]]
        else:
            vals = [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(vals)]
            return f'{m.group(1)}="{" ".join(_f(v) for v in vals)}"'
        return f'{m.group(1)}="{_f(vals[0])} {_f(vals[1])} 0"'
    return _POINT_ATTRS.sub(repl, xml)
