# Full-census numerical-reference results

R is CPU double with DC retained. Every table includes both e10216-01 grids unless explicitly labelled otherwise. S1 screen = product relRMSE ≥0.1; this is descriptive, not a scientific gate.

## Product and patch-set comparison, all 60

| Arm | Positive configs /60 | Movies any grid /30 | Accepted sets equal /60 | Median relRMSE | Worst relRMSE |
|---|---:|---:|---:|---:|---:|
| R′ (CPU double, both) | 0 | 0 | 60 | 3.078887e-06 | 0.00034075275 |
| CPU float, none | 16 | 13 | 51 | 0.037279848 | 1.2504577 |
| CPU float, global | 10 | 8 | 53 | 0.014994589 | 1.0739941 |
| CPU float, local | 13 | 9 | 54 | 0.029085215 | 1.2504577 |
| CPU float, both | 0 | 0 | 60 | 3.854687e-05 | 0.0013794214 |
| CUDA float, none | 20 | 16 | 49 | 0.045136483 | 1.2492611 |
| CUDA float, global | 13 | 12 | 53 | 0.022354912 | 0.97014769 |
| CUDA float, local | 11 | 7 | 55 | 0.029613784 | 1.2492611 |
| CUDA float, both | 0 | 0 | 60 | 0.00043533427 | 0.0016306304 |

## Native trajectory and applied local field, all 60

All errors are vector magnitudes in original pixels. Median max/RMS are medians over the per-config maxima/RMS values. Local fields use full-precision applied coefficients, a 33×33 endpoint-inclusive normalized grid [-0.5,0.5]² and every integer frame z=0…N−1. A disabled local model contributes a zero applied field; active-model status is retained per row.

| Arm | Global median max / RMS | Global worst max | Local median max / RMS | Local worst max |
|---|---:|---:|---:|---:|
| R′ (CPU double, both) | 1.0404881e-09 / 4.3765254e-10 | 0.00022266594 | 2.6868194e-06 / 7.0295277e-07 | 4.2680133e-05 |
| CPU float, none | 0.054819011 / 0.024333521 | 166.245 | 0.16714033 / 0.047335279 | 163.89018 |
| CPU float, global | 4.2681308e-06 / 2.1425431e-06 | 0.0045133555 | 0.10818699 / 0.026100927 | 272.46658 |
| CPU float, local | 0.054819011 / 0.024333521 | 166.245 | 0.041547443 / 0.022999478 | 124.5046 |
| CPU float, both | 4.2681308e-06 / 2.1425431e-06 | 0.0045133555 | 9.3756367e-06 / 3.7306321e-06 | 0.00180443 |
| CUDA float, none | 0.05208565 / 0.026456954 | 150.64127 | 0.16232163 / 0.041687346 | 33.910784 |
| CUDA float, global | 4.6712689e-06 / 2.4096439e-06 | 0.033394098 | 0.16424567 / 0.039636208 | 99.298122 |
| CUDA float, local | 0.05208565 / 0.026456954 | 150.64127 | 0.053674501 / 0.02582704 | 124.51218 |
| CUDA float, both | 4.6712689e-06 / 2.4096439e-06 | 0.033394098 | 2.0888155e-05 / 6.8562732e-06 | 0.001571154 |

## Same errors excluding the two known failure configs

| Arm | Global median max / RMS | Global worst max | Local median max / RMS | Local worst max | Median / worst relRMSE |
|---|---:|---:|---:|---:|---:|
| R′ (CPU double, both) | 1.0159099e-09 / 4.0581658e-10 | 3.5018014e-08 | 2.8220643e-06 / 7.1880624e-07 | 4.2680133e-05 | 3.9535364e-06 / 0.00034075275 |
| CPU float, none | 0.053786018 / 0.023079043 | 0.41826752 | 0.17465519 / 0.049475284 | 163.89018 | 0.036730333 / 1.0027064 |
| CPU float, global | 4.2654824e-06 / 2.1099602e-06 | 0.00017640007 | 0.11166266 / 0.028209292 | 272.46658 | 0.016632735 / 1.0739941 |
| CPU float, local | 0.053786018 / 0.023079043 | 0.41826752 | 0.042882834 / 0.023942175 | 124.5046 | 0.028105822 / 1.0419922 |
| CPU float, both | 4.2654824e-06 / 2.1099602e-06 | 0.00017640007 | 9.9986533e-06 / 3.8525222e-06 | 0.00180443 | 4.0764428e-05 / 0.0013794214 |
| CUDA float, none | 0.05128461 / 0.024221374 | 0.40987195 | 0.19741651 / 0.049959969 | 33.910784 | 0.040492981 / 0.80428771 |
| CUDA float, global | 4.5964152e-06 / 2.1059607e-06 | 0.00031261464 | 0.17601703 / 0.041185265 | 99.298122 | 0.023506604 / 0.97014769 |
| CUDA float, local | 0.05128461 / 0.024221374 | 0.40987195 | 0.064483838 / 0.029423362 | 124.51218 | 0.028685554 / 0.98295213 |
| CUDA float, both | 4.5964152e-06 / 2.1059607e-06 | 0.00031261464 | 2.1218843e-05 / 7.3293891e-06 | 0.001571154 | 0.00043908006 / 0.0016306304 |

## Exact McNemar against R-screen positives

Cells are (both positive, baseline-only, conditioned-only, neither). Config p values treat rows as independent and are descriptive because the two grids are correlated. Movie sensitivity collapses the grids with “at least one positive”; movies within a collection can also be correlated. No positive-only selection or threshold changes.

| Transition | Config cells | Config exact p | Movie cells | Movie exact p |
|---|---|---:|---|---:|
| C_none->C_global | [8, 8, 2, 42] | 0.109375 | [7, 6, 1, 16] | 0.125 |
| C_none->C_local | [10, 6, 3, 41] | 0.5078125 | [8, 5, 1, 16] | 0.21875 |
| C_none->C_both | [0, 16, 0, 44] | 3.0517578e-05 | [0, 13, 0, 17] | 0.00024414062 |
| G_none->G_global | [10, 10, 3, 37] | 0.092285156 | [10, 6, 2, 12] | 0.2890625 |
| G_none->G_local | [10, 10, 1, 39] | 0.01171875 | [7, 9, 0, 14] | 0.00390625 |
| G_none->G_both | [0, 20, 0, 40] | 1.9073486e-06 | [0, 16, 0, 14] | 3.0517578e-05 |

## Family and grid screen counts versus R

| Arm | 10216 p5 / p3 | 12963 p5 / p3 | Falcon 3 p5 / p3 |
|---|---:|---:|---:|
| R′ (CPU double, both) | 0 / 0 | 0 / 0 | 0 / 0 |
| CPU float, none | 4 / 2 | 7 / 2 | 1 / 0 |
| CPU float, global | 5 / 1 | 3 / 1 | 0 / 0 |
| CPU float, local | 5 / 3 | 3 / 1 | 1 / 0 |
| CPU float, both | 0 / 0 | 0 / 0 | 0 / 0 |
| CUDA float, none | 6 / 4 | 7 / 2 | 1 / 0 |
| CUDA float, global | 4 / 1 | 6 / 1 | 1 / 0 |
| CUDA float, local | 4 / 3 | 2 / 2 | 0 / 0 |
| CUDA float, both | 0 / 0 | 0 / 0 | 0 / 0 |

## CPU-versus-CUDA continuity screen, matched DC arms

| DC arm | Positive configs /60 | Movies any grid /30 |
|---|---:|---:|
| none | 19 | 13 |
| global | 13 | 11 |
| local | 11 | 8 |
| both | 0 | 0 |

| Matching-DC backend transition | Config cells | Exact p | Movie cells | Exact p |
|---|---|---:|---|---:|
| none->global | [9, 10, 4, 37] | 0.17956543 | [7, 6, 4, 13] | 0.75390625 |
| none->local | [9, 10, 2, 39] | 0.038574219 | [7, 6, 1, 16] | 0.125 |
| none->both | [0, 19, 0, 41] | 3.8146973e-06 | [0, 13, 0, 17] | 0.00024414062 |

## e10216-01, retained in all counts

Both grids share their global trajectory. These runs exhaust the global iteration budget; exit 0 does not imply convergence.

| Arm | Last global increment RMSD | Max global gap vs R | p5 / p3 relRMSE vs R |
|---|---:|---:|---:|
| R | 58.569082 | 0 | 0 / 0 |
| R′ (CPU double, both) | 58.569084 | 0.00022266594 | 1.4868437e-06 / 1.4868437e-06 |
| CPU float, none | 51.622251 | 166.245 | 1.2504577 / 1.2504577 |
| CPU float, global | 58.569114 | 0.0045133555 | 2.7499648e-05 / 2.7499648e-05 |
| CPU float, local | 51.622251 | 166.245 | 1.2504577 / 1.2504577 |
| CPU float, both | 58.569114 | 0.0045133555 | 2.7499648e-05 / 2.7499648e-05 |
| CUDA float, none | 61.918271 | 150.64127 | 1.2492611 / 1.2492611 |
| CUDA float, global | 58.568824 | 0.033394098 | 0.00020186834 / 0.00020186834 |
| CUDA float, local | 61.918271 | 150.64127 | 1.2492611 / 1.2492611 |
| CUDA float, both | 58.568824 | 0.033394098 | 0.00020186834 / 0.00020186834 |

## First-divergence classifications

Every comparison has a retained first-integer-change and first >0.5 px candidate-event record (or an explicit absence). The table below summarizes the ≥0.1 product disagreements. The first event is iteration-major within a selected S1-relevant call, preferring global before local; smaller arithmetic/input errors can precede it. Same-integer witnesses have different samples and are not a same-sample scalar-fit defect. CUDA same-map tie-order differences are labelled separately.

| Arm | Positive-comparison classifications |
|---|---|
| R′ (CPU double, both) | none |
| CPU float, none | different integer ordering: 13; known e10216-01 global nonconvergence: 2; same integer, different samples/fit: 1 |
| CPU float, global | different integer ordering: 9; same integer, different samples/fit: 1 |
| CPU float, local | different integer ordering: 10; known e10216-01 global nonconvergence: 2; no >0.5-px candidate event: 1 |
| CPU float, both | none |
| CUDA float, none | different integer ordering: 11; different integer; CUDA same-map tie order also differs: 6; known e10216-01 global nonconvergence: 2; same integer, different samples/fit: 1 |
| CUDA float, global | different integer ordering: 9; different integer; CUDA same-map tie order also differs: 3; same integer, different samples/fit: 1 |
| CUDA float, local | different integer ordering: 6; known e10216-01 global nonconvergence: 2; same integer, different samples/fit: 3 |
| CUDA float, both | none |

## All configurations

Counts below are screen positives among the two grid rows, against R. Complete continuous measurements and provenance are in `census.csv` and `results/rows.json`.

| Movie | R′ | CPU none/global/local/both | CUDA none/global/local/both |
|---|---:|---|---|
| e10216-00 | 0 | 0/0/2/0 | 1/0/0/0 |
| e10216-01 | 0 | 2/0/2/0 | 2/0/2/0 |
| e10216-02 | 0 | 1/1/0/0 | 1/1/0/0 |
| e10216-03 | 0 | 1/1/1/0 | 1/1/1/0 |
| e10216-04 | 0 | 0/1/0/0 | 0/1/0/0 |
| e10216-05 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10216-06 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10216-07 | 0 | 1/1/1/0 | 2/1/0/0 |
| e10216-08 | 0 | 1/2/2/0 | 1/1/2/0 |
| e10216-09 | 0 | 0/0/0/0 | 2/0/2/0 |
| e10474f3-00 | 0 | 1/0/1/0 | 0/0/0/0 |
| e10474f3-01 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-02 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-03 | 0 | 0/0/0/0 | 1/1/0/0 |
| e10474f3-04 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-05 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-06 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-07 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-08 | 0 | 0/0/0/0 | 0/0/0/0 |
| e10474f3-09 | 0 | 0/0/0/0 | 0/0/0/0 |
| e12963-00 | 0 | 1/0/0/0 | 1/1/0/0 |
| e12963-01 | 0 | 1/1/0/0 | 1/0/0/0 |
| e12963-02 | 0 | 0/0/0/0 | 1/0/0/0 |
| e12963-03 | 0 | 1/1/1/0 | 1/1/1/0 |
| e12963-04 | 0 | 2/0/0/0 | 0/1/0/0 |
| e12963-05 | 0 | 2/2/2/0 | 2/2/2/0 |
| e12963-06 | 0 | 1/0/0/0 | 1/1/0/0 |
| e12963-07 | 0 | 1/0/1/0 | 1/1/0/0 |
| e12963-08 | 0 | 0/0/0/0 | 0/0/0/0 |
| e12963-09 | 0 | 0/0/0/0 | 1/0/1/0 |
