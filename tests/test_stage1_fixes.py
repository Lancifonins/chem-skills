"""Regression tests for the 1.1.0 fixes: inputs are never silently misread, files are never
silently overwritten, and ChemDraw text uses ChemDraw's own conventions."""

import re

import pytest

# ---------------------------------------------------------------- #1 abbreviations


def test_reagent_abbreviations_resolve_to_the_reagent(cdx):
    out = cdx.ok("draw_structures", {"compounds": ["NBS", "NIS", "BOP"], "caption": "none"})
    got = {c["input"]: (c["interpreted_as"], c["formula"]) for c in out["compounds"]}
    assert got == {"NBS": ("abbreviation", "C4H4BrNO2"), "NIS": ("abbreviation", "C4H4INO2"),
                   "BOP": ("abbreviation", "C12H22F6N6OP2")}
    assert any("N-bromobutanimide" in n for n in out["notes"])  # the reading is reported


@pytest.mark.parametrize("text, reason", [
    ("CBS", "(R)- or (S)"),          # stereo-ambiguous reagent
    ("CO", "carbon monoxide"),       # formula that is also valid SMILES (methanol)
    ("CN", "cyanide"),
    ("CBN", "looks like an abbreviation"),  # unknown all-letter string with boron
])
def test_ambiguous_inputs_are_refused(cdx, text, reason):
    assert reason in cdx.error("draw_structures", {"compounds": [text]})


def test_explicit_smiles_bypasses_guessing(cdx):
    out = cdx.ok("draw_structures", {"compounds": [{"smiles": "CO"}, {"smiles": "NBS"}], "caption": "none"})
    assert [c["formula"] for c in out["compounds"]] == ["CH4O", "H4BNS"]


def test_plain_smiles_still_works_and_is_reported(chem):
    out = chem.ok("calculate_properties", {"identifier": "CCO"})
    assert out["formula"] == "C2H6O" and out["interpreted_as"] == "smiles"
    assert "read as SMILES (C2H6O)" in out["note"]


def test_file_structures_are_never_reguessed(cdx):
    (cdx.workdir / "tricky.smi").write_text("CO methanol\nCN methylamine\n")
    out = cdx.ok("convert_to_chemdraw", {"path": "tricky.smi"})
    assert [c["formula"] for c in out["compounds"]] == ["CH4O", "CH5N"]


@pytest.mark.network
def test_compound_info_uses_the_reagent_table(chem):
    out = chem.ok("get_compound_info", {"identifier": "NIS"})
    assert out["name"] == "N-Iodosuccinimide" and out["cas_number"] == "516-12-1"
    assert out["interpreted_as"] == "abbreviation"


# ------------------------------------------------------------- #4 broken SMILES


def test_broken_smiles_report_rdkit_reason(chem, cdx):
    assert "not valid SMILES: extra open parentheses" in cdx.error("draw_structures", {"compounds": ["C1CC(=O"]})
    assert "Explicit valence" in chem.error("calculate_properties", {"identifier": "CN(C)(C)(C)C"})


# ---------------------------------------------------------- #3 file names


def test_stereoisomers_get_distinct_files(cdx):
    out = cdx.ok("draw_structures", {"compounds": ["C[C@H](N)C(=O)O", "C[C@@H](N)C(=O)O"],
                                     "separate_files": True, "caption": "none"})
    names = [p.rsplit("/", 1)[1] for p in out["paths"]]
    assert len(set(names)) == 2 and all(n.startswith("QNAYBMKLOCPYGJ-") for n in names)


def test_existing_files_are_never_overwritten(cdx, chem):
    first = cdx.ok("draw_structures", {"compounds": [{"smiles": "CCO"}], "filename": "fig"})["path"]
    second = cdx.ok("draw_structures", {"compounds": [{"smiles": "CCC"}], "filename": "fig"})["path"]
    third = cdx.ok("draw_structures", {"compounds": [{"smiles": "CCN"}], "filename": "fig", "overwrite": True})["path"]
    assert first.endswith("fig.cdxml") and second.endswith("fig-2.cdxml") and third == first
    a = chem.ok("export_reaction", {"reactants": ["CCO"], "products": ["CC=O"], "filename": "r"})
    b = chem.ok("export_reaction", {"reactants": ["CCO"], "products": ["CC=O"], "filename": "r"})
    assert a["rxn_path"].endswith("r.rxn") and b["rxn_path"].endswith("r-2.rxn")
    assert b["image_path"].endswith("r-2.png")  # .rxn and its preview keep one stem


# ------------------------------------------------- #2 ChemDraw labels and text


def _labels(xml: str) -> set[tuple]:
    return {tuple(re.findall(r'face="(\d+)">([^<]*)<', t))
            for t in re.findall(r"<t p[^>]*>((?:<s [^>]*>[^<]*</s>)+)</t>", xml)}


def test_charges_isotopes_and_radicals_follow_chemdraw(cdx):
    cdx.ok("draw_structures", {"compounds": [{"smiles": s} for s in
                                             ("C[N+](C)(C)C", "C[O-]", "[Fe+2]", "[13CH3]C(=O)O", "C[CH]C")],
                               "caption": "none", "filename": "labels"})
    xml = (cdx.workdir / "exports/labels.cdxml").read_text(encoding="utf-8")
    labels = _labels(xml)
    assert (("96", "N+"),) in labels and (("96", "O-"),) in labels      # one formula-style run
    assert (("96", "Fe"), ("64", "2+")) in labels                       # 64 = superscript
    assert (("96", "H3"), ("64", "13"), ("96", "C")) in labels          # H3(13)C, not (13)H3C
    assert 'Radical="Doublet"' in xml and "•" not in xml          # ChemDraw draws the dot


def test_text_fits_chemdraw_fonts(cdx):
    out = cdx.ok("draw_structures", {"compounds": [{"smiles": "CC1=CCC(CC1)C(C)=C",
                                                    "name": "α-terpinene → β, −78 °C ✓"}],
                                     "caption": "name", "filename": "greek"})
    xml = (cdx.workdir / "exports/greek.cdxml").read_text(encoding="utf-8")
    assert not [c for c in xml if ord(c) > 255]                          # all Latin-1
    assert '<s font="7" size="10" face="0">a</s>' in xml                # α via the Symbol font
    assert "-78 °C" in xml and "-&gt;" in xml
    assert out["warnings"] == ["'✓' (U+2713) cannot be shown in ChemDraw's text font; written as '?'."]
