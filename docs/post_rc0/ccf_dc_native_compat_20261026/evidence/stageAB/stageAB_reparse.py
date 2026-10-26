#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline re-parse of the retained Stage A logs (no venue access). `unittest -v` prints a test's result on the next
line when the test has a docstring, which the first checker's one-line regex missed for one test; this parser accepts both."""
import re, sys

REQ_NATIVE = ("test_n_score_reproduces_all_16_retained_rows test_n_score_percentile_is_over_the_dense_roi_not_the_frames "
              "test_witness_selectivity_on_every_reached_site test_n_control_generator test_run_env_thread_pins test_pinned_commands "
              "test_positive_affine_both test_absent_tap_fails_closed test_n_tap_with_a_local_model_is_invalid "
              "test_invalid_tap_rows_are_not_labelled_scored test_def_build_row_is_star_only_by_declaration "
              "test_two_failed_runs_are_not_an_identity test_global_only_row_cannot_claim_local_coverage "
              "test_skip_logfile_does_not_change_the_products test_n_control_row test_identity_report "
              "test_failed_exit_is_not_rescued_by_a_complete_tap test_placeholder_tap_and_tap_star_disagreement").split()


def parse(path):
    text = open(path, errors="replace").read()
    res = {}
    for m in re.finditer(r"^(test_\w+) \([^)]*\)(?:\n[^\n]*?)? \.\.\. (.+)$", text, re.M):
        res[m.group(1)] = m.group(2).strip()
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    return res, int(ran.group(1)) if ran else None, bool(re.search(r"^OK", text, re.M)), re.findall(r"skipped=(\d+)", text)


ok = True
for tag, native in (("pure", False), ("exp", True), ("iso", True)):
    res, ran, final_ok, skipped = parse(f"{sys.argv[1]}/A-{tag}.stderr")
    req = REQ_NATIVE if native else [t for t in REQ_NATIVE if t in ("test_n_score_reproduces_all_16_retained_rows",
        "test_n_score_percentile_is_over_the_dense_roi_not_the_frames", "test_witness_selectivity_on_every_reached_site",
        "test_n_control_generator", "test_run_env_thread_pins", "test_pinned_commands")]
    missing = [t for t in req if res.get(t) != "ok"]
    n_ok = sum(v == "ok" for v in res.values())
    n_skip = sum(v.startswith("skipped") for v in res.values())
    print(f"A-{tag}: ran={ran} final_OK={final_ok} parsed={len(res)} ok={n_ok} skipped={n_skip} (log skipped={skipped or [0]}) required_missing_or_not_ok={missing}")
    ok &= final_ok and not missing and (n_skip == 0 if native else True) and ran == len(res)
print("REPARSE_ALL_REQUIRED_OK" if ok else "REPARSE_PROBLEM")
