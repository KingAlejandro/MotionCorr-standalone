<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Retrospective provenance (added after the runs; not captured at run time)

Everything below was computed on 2026-10-22 at about 21:41Z (22:41 local, +0100), after the iteration-1, iteration-2 and follow-up runs
(21:27Z to 21:28Z), by hashing scratch files under `/tmp/mc265-oracle-20261022/` that still existed. The hash lines are read-only
observations of the scratch state at that later time. They are not a record taken when each run executed, and the committed run-time receipts
from bb08502e are unchanged. This file exists because those receipts omitted these identifiers (independent review R1, finding L4).

## Follow-up (`receipts/followup_subnormal/`)

The committed follow-up receipt has only `argv.txt`, `stdout.txt`, `stderr.txt`, `exit.txt`, `summary.json`, `coefficients.csv`. Not recorded then:

| item | value now | basis |
|---|---|---|
| binary run | `/tmp/mc265-oracle-20261022/out/roundtrip_oracle`, sha256 `d1ccb52a088908f15c211a28e9e8c84d29e9afd5fc18d5cccf24c1c750ea5636` | same hash as `receipts/iteration2/hashes.txt`. File mtime 21:27:50Z, follow-up exit file 21:27:55Z; no rebuild in between is known, but the hash at run time was not captured |
| source | `3691374061f782bc84531fd1c79d017ddcb5a7c2` | scratch `src.sha`, and `receipts/iteration2/source_head.txt` for the build the binary came from |
| library | `libmotioncorr_core.a` `2c237ae5eb8b394a2762071f7f030d9efe4c738ced0232f92aae6d46400d07f4` | same as iteration 2 `hashes.txt` |
| harness source | `5e69f974b4f44aaddfa2894bde55107a1e7327cbd8bc2b7559421c6b6b2f0235` | frozen in `receipts/FROZEN_FOLLOWUP.txt` before the run |
| fixtures | `fixtures_followup_subnormal.txt` `df86b048c81b7502a319db2248952b156e3fb6a6736d89a2880bd790fa3100b9` | same file |
| build options | those in `receipts/iteration2/build_options.txt` | the binary is the iteration-2 binary; `run.sh` was not used for the follow-up |
| scratch outputs | `summary.json` `05a7e79b708b85673a2e6d655300bb12fa451dace5aa86d053a2b041855a4978`, `coefficients.csv` `39777644a15e2e6be810a25783845e29f91ed7b1cb45dc24912e1a999e9bca21` | equal to the committed files in `receipts/followup_subnormal/` |
| run environment | `OMP_NUM_THREADS=1`, same Mac and toolchain as `receipts/iteration2/host.txt` | the one-thread setting was set on the command line, not logged |

## Iteration 1 versus iteration 2 CSV identity

The README states that iteration 1's sample and coefficient CSVs equal iteration 2's. The iteration-1 receipt directory does not record those hashes. Scratch
`iter1_csv.sha` (written 21:27Z, before the directory was renamed to `out_iter1`) held the first two lines below; the third was added at the retrospective check.

| file | sha256 | iteration 1 | iteration 2 |
|---|---|---|---|
| `samples_full.csv` | `6da068ed224f427dce048e8e96b5f8103773006e611b91315fcb2b8183e2ee5e` | equal | equal (committed: `receipts/iteration2/samples_full.csv.sha256`) |
| `coefficients.csv` | `720f1663759b0f9f9076d6a6de2329cb16a5b4bcb4515314ee97ab0f71bc9eff` | equal | equal (equals committed `receipts/iteration2/coefficients.csv`) |
| `per_frame_max_vec.csv` | `26f618b89c38a18a16fd3e5b95e993eb864243827bf6fc422ca39b6e4bd451b4` | equal | equal (equals committed `receipts/iteration2/per_frame_max_vec.csv`) |

Iteration-1 harness binary `9bdf53cafd20a8e95a242670d586a5f204c8ab0dd5ee9b7cc4fb15fcb0cdc584` matches the committed
`receipts/iteration1_json_escape_defect/hashes.txt`. Iteration-1 `summary.json` `64233df5…dd3a` equals the committed `summary_INVALID_JSON.json`.
Reviewer R1 independently found the same CSV hashes and identical `written_star/` and `fullprecision_star/` trees in scratch (see its report).

## Independent review R1 files

`review/R1_opus/` holds the reviewer's `REVIEW.md` (sha256 `ee42f060036a852382cc95570a5f51b6ab1b23cc5c030fcdb13a22947e968617`),
`independent_check.json` and `scripts/independent_check.py`, copied byte for byte (`SHA256SUMS.txt`) and not edited. They are reviewer-authored; no licence header was
added to them. The review was of bb08502e; the README and DESIGN_NOTE corrections that followed are listed in `README.md` under "Corrections after review R1".
