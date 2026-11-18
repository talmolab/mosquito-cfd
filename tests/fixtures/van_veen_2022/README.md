# van Veen et al. (2022) supplementary dataset: two files

Test fixtures for `tests/test_van_veen_dataset.py`. They are the paper's own CFD results, used to
check that `mosquito_cfd.benchmarks.van_veen_model` reproduces them.

## Source

W. G. van Veen, J. L. van Leeuwen, B. W. van Oudheusden and F. T. Muijres (2022). The unsteady
aerodynamics of insect wings with rotational stroke accelerations, a systematic numerical study.
*Journal of Fluid Mechanics* 936, A3. https://doi.org/10.1017/jfm.2022.31

The files come from the article's supplementary material ("supplementary database S1"), one zip
downloaded on 2026-11-17 from the "Supplementary materials" tab of the article page. The zip
holds 15 MATLAB v5 files; the two here are copied from it unmodified.

| File | SHA-256 |
|---|---|
| `fruitfly.mat` | `839ee1d0e344dee38c2093c20e499fe78f9a94991748bee25a6bbe12a12026db` |
| `wing_geometry_DB.mat` | `2625e24c99526f503a763782f7e7ed0b0773959472c47f0e70341a7c32144766` |
| the source zip (not committed) | `562ba94286121c688192f48840dc5d8c2ca0a35a5aef57810a7ab70d980f5a5b` |

## Licence

The article is open access under CC BY 4.0, and its data-availability statement says the data
"are openly available" at the article DOI. The zip itself carries no licence file. The files are
redistributed here with attribution on that basis; the authors have been asked to confirm
(issue #156).

## Contents

- `fruitfly.mat`: 1,089 rows for the fruit-fly wing. `aoa` is the angle of attack in
  degrees (uint8), `sr` the stroke rate in rad/s (uint16), `sa` the stroke acceleration in
  rad/s² (int32), and `Fx`, `Fy`, `Fz` the forces in N at the end of each simulation.
  - The rows are 566 distinct simulations: each non-steady one is stored twice, byte for byte.
    Distinct rows: 43 steady (`sa = 0`), 477 accelerating, 46 decelerating. (The paper's §2.6
    counts 568.)
  - All decelerating rows are at 36°.
- `wing_geometry_DB.mat`: 14 wings (fruit fly, mosquito, 12 ellipses). For each: `wing` (name),
  `outline`, the chord profile `c` at spanwise stations `y`, `span`, `chord_max`, `chord_mean`,
  and the area moments `Syy`, `Scy`, `Swe` (SI units).

## Reading them

Read with `scipy.io.loadmat` only, and cast every column to `float64` first: `sr**2` overflows
in uint16. The comparison in the tests takes the fluid density as 1; the paper's value is not in
the text available to this project (issue #156). With that density, a fit to the rows with
non-negative acceleration returns the paper's printed coefficients to the digits printed.

## What the data does not support

The model's tangential force on a decelerating wing. On the decelerating rows its error is larger
than the force itself. The paper's figure for decelerating wings (fig 4d) shows the normal
force.
