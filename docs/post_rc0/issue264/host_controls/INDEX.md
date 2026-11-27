# Host controls index (`../verify_model_controls.py`)

| Attempt | Driver commit | Status | Note |
| --- | --- | --- | --- |
| `attempt01-INVALID/` | `46381b2a` | **INVALID** | Two mutant rows ran the previous binary (make missed the header rewrite): `mutant_uncentred` reused the `>=` binary `6cb57029…`, `mutant_x_component_only` reused the swapped-dimensions binary `f46c4dc4…`. Its raw `model_controls.json` says `all_expected: true`; that field is not a valid result and the file is kept unedited as the record of the failure. |
| `attempt02/` | `52affe31` | valid | A distinct binary per case was asserted. All rows met their expectations; the counts are in `../review-round1/RESPONSE.md`. `ci-fail-closed.log`: 8/8. |

macOS arm64, Apple clang, CPU Release. Host evidence only.
