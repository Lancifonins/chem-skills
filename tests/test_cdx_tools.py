import json
import re

import pytest
from rdkit import Chem

TESTOSTERONE = "C[C@]12CC[C@H]3[C@@H](CCC4=CC(=O)CC[C@]34C)[C@@H]1CC[C@@H]2O"
L_ALANINE = "C[C@H](N)C(=O)O"
ZWITTERION = "C[N+](C)(C)CC(=O)[O-]"


def canon(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def test_version_and_check(cdx):
    assert json.loads(cdx.raw("version").stdout) == {"skill": "cdx-tools", "version": "1.0.0"}
    report = json.loads(cdx.raw("check").stdout)
    assert report["ready"] and report["rdkit"]["ok"], report


def test_structures_round_trip_with_stereo_and_charges(cdx):
    inputs = [TESTOSTERONE, L_ALANINE, ZWITTERION]
    out = cdx.ok("draw_structures", {"compounds": [{"structure": s, "name": f"c{i}"} for i, s in enumerate(inputs)],
                                     "caption": "number_name_formula", "filename": "rt"})
    back = cdx.ok("read_chemdraw", {"path": "exports/rt.cdxml"})
    assert sorted(s["smiles"] for s in back["structures"]) == sorted(canon(s) for s in inputs)
    assert out["path"].endswith("rt.cdxml")
    assert "1\nc0\nC19H28O2" in back["text"]  # bold number, name and formula caption


def test_custom_labels(cdx):
    out = cdx.ok("draw_structures", {"compounds": [{"structure": "CCO", "label": "3a", "name": "ethanol"}],
                                     "caption": "number_name"})
    assert out["compounds"][0]["label"] == "3a"
    assert "3a\nethanol" in cdx.ok("read_chemdraw", {"path": "exports/structures.cdxml"})["text"]


def test_multistep_scheme_metadata(cdx):
    cdx.ok("draw_reaction", {
        "reactants": ["O=Cc1ccc(Br)cc1"],
        "steps": [{"reagents": ["NaBH4"], "conditions": "MeOH, 0 °C", "yield": "95%", "products": ["OCc1ccc(Br)cc1"]},
                  {"reagents": ["Pd(PPh3)4"], "conditions": "90 °C; 12 h", "products": ["OCc1ccc(-c2ccccc2)cc1"]}],
        "filename": "route"})
    xml = (cdx.workdir / "exports/route.cdxml").read_text()
    steps = re.findall(r"<step [^>]*ReactionStepReactants=\"(\d+)\" ReactionStepProducts=\"(\d+)\"", xml)
    assert len(steps) == 2 and steps[0][1] == steps[1][0]  # intermediate shared between steps
    assert xml.count("<arrow ") == 2
    assert 'face="96">Pd(PPh3)4<' in xml  # formula text gets ChemDraw's auto-subscript style


def test_convert_smiles_file(cdx):
    (cdx.workdir / "two.smi").write_text("CCO ethanol\nOc1ccccc1 phenol\n")
    out = cdx.ok("convert_to_chemdraw", {"path": "two.smi"})
    assert [c["smiles"] for c in out["compounds"]] == ["CCO", "Oc1ccccc1"]


def test_input_errors(cdx):
    assert "Unknown caption fields" in cdx.error("draw_structures", {"compounds": ["CCO"], "caption": "smiles"})
    assert "outside the working directory" in cdx.error("read_chemdraw", {"path": "../../etc/hosts"})
    assert "reactants and products" in cdx.error("draw_reaction", {"reactants": ["CCO"]})


@pytest.mark.network
def test_draw_by_name(cdx):
    out = cdx.ok("draw_structures", {"compounds": ["caffeine"], "caption": "name_cas"})
    assert out["compounds"][0]["formula"] == "C8H10N4O2"
    assert "caffeine\nCAS 58-08-2" in cdx.ok("read_chemdraw", {"path": "exports/structures.cdxml"})["text"]
