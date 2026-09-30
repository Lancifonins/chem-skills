import json

import pytest

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
MOLFILE_ETHANOL = """ethanol
     RDKit          2D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0
    1.2990    0.7500    0.0000 C   0  0
    2.5981   -0.0000    0.0000 O   0  0
  1  2  1  0
  2  3  1  0
M  END
$$$$
"""


def test_version_and_check(chem):
    assert json.loads(chem.raw("version").stdout) == {"skill": "chem-tools", "version": "1.0.0"}
    report = json.loads(chem.raw("check").stdout)
    assert report["ready"] and report["rdkit"]["ok"], report


def test_calculate_properties_offline(chem):
    out = chem.ok("calculate_properties", {"identifier": ASPIRIN})
    assert out["formula"] == "C9H8O4"
    assert out["lipinski_violations"] == 0
    assert out["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"


def test_read_structure_file_and_path_guard(chem):
    (chem.workdir / "ethanol.sdf").write_text(MOLFILE_ETHANOL)
    out = chem.ok("read_structure_file", {"path": "ethanol.sdf"})
    assert out["structures"][0]["smiles"] == "CCO"
    assert "outside the working directory" in chem.error("read_structure_file", {"path": "../../etc/hosts"})


def test_export_structures_from_smiles(chem):
    out = chem.ok("export_structures", {"compounds": [ASPIRIN, "CCO"], "filename": "../x"})
    assert out["path"].endswith("exports/x.sdf")  # traversal in filename is stripped


def test_invalid_smarts_rejected_before_network(chem):
    assert "Invalid SMARTS" in chem.error("search_substructure", {"query": "[C", "query_type": "smarts"})


def test_failures_are_logged(chem):
    chem.error("get_compound_info", {"identifier": ASPIRIN, "include": ["price"]})
    chem.error("calculate_properties", {"wrong_argument": 1})
    kinds = [e["kind"] for e in chem.log_entries()]
    assert kinds == ["error", "bug"]  # bad arguments carry a traceback
    assert "bug report" in chem.raw("report").stdout


@pytest.mark.network
def test_compound_lookup(chem):
    out = chem.ok("get_compound_info", {"identifier": "64-17-5", "include": ["safety"]})
    assert out["name"] == "Ethanol" and out["cas_number"] == "64-17-5"
    assert out["safety"]["signal_word"] == "Danger"


@pytest.mark.network
def test_unknown_compound(chem):
    assert "no compound matching" in chem.error("get_compound_info", {"identifier": "notarealchemicalxyz"})
