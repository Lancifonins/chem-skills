# SMARTS patterns for `search_substructure`

Pass these with `"query_type": "smarts"`. Every pattern below was checked with RDKit against
positive and negative examples. PubChem returns hits in its own relevance order, so large
classes (esters, amides) return common compounds first. Raise `max_results` (≤ 50) for variety.

| Class | SMARTS | Notes |
|---|---|---|
| α-amino acid | `[NX3;!$(N-C=O)][CX4][CX3](=O)[OX2H1,OX1-]` | Excludes N-acyl / peptide N; allows carboxylate |
| Carboxylic acid | `[CX3](=O)[OX2H1]` | |
| Ester | `[#6][CX3](=O)[OX2][#6]` | |
| Amide | `[CX3](=O)[NX3]` | Includes lactams and peptides |
| Primary aliphatic amine | `[NX3;H2;!$(NC=O)][CX4]` | |
| Aniline (1° or 2°) | `[NX3;H2,H1;!$(NC=O)]c` | |
| Phenol | `c[OX2H]` | |
| Aliphatic alcohol | `[CX4][OX2H]` | |
| Aldehyde | `[CX3H1](=O)[#6]` | Excludes formaldehyde |
| Ketone | `[#6][CX3](=O)[#6]` | |
| Nitrile | `[CX2]#[NX1]` | |
| Nitro | `[$([NX3](=O)=O),$([NX3+](=O)[O-])]` | Both charge conventions |
| Aryl halide | `c[F,Cl,Br,I]` | |
| Alkyl halide | `[CX4][F,Cl,Br,I]` | |
| Sulfonamide | `[SX4](=O)(=O)[NX3]` | |
| Boronic acid | `[BX3]([OX2H])[OX2H]` | Free acid only, not pinacol esters |
| β-lactam | `O=C1CCN1` | |
| Indole | `c1ccc2[nH]ccc2c1` | N-H indoles only |
| Pyridine | `n1ccccc1` | |
| Steroid core | `[#6]1~[#6]~[#6]~[#6]2~[#6](~[#6]~1)~[#6]~[#6]~[#6]1~[#6]~2~[#6]~[#6]~[#6]2~[#6]~[#6]~[#6]~[#6]~1~2` | Any bond order, so it matches aromatic A-rings (estradiol) |

## Writing your own

- A plain SMILES fragment also works as a substructure query (`"query_type": "smiles"`), e.g.
  `c1ccc2ncccc2c1` for quinolines.
- `[#6]` is any carbon, `~` is any bond, `X3` means three connections, and `H1` means one
  attached hydrogen. `!$(...)` excludes an environment, e.g. `!$(NC=O)` rules out amide N.
- An invalid pattern is caught before any network call: `search_substructure` returns an error
  for SMARTS that RDKit cannot parse.
