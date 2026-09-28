#!/usr/bin/env python3
"""Self-test for compare_aux_outputs.py, with old-source negative controls.

PR #88 review (discussion r4119254472) found that the comparator walked only the
reference tree, so a file the candidate emitted but the reference did not was
silently accepted -- the exact unintended side effect the gate exists to catch.

A fix is worth little without a test that *discriminates*: one that fails on the
old source and passes on the new one. So each extra/missing case below is run
twice, once against the current comparator and once against the pre-fix source
recovered with `git show`. A case is only credited as discriminating if the old
source really did accept what the new source rejects. If the old source cannot
be recovered, those controls are reported SKIP with the reason rather than
quietly counted as wins.

CPU-only, no fixtures, no GPU, a fraction of a second.

Usage: python3 test_compare_aux_outputs.py [--old-source FILE]
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARATOR = HERE / "compare_aux_outputs.py"
PRE_FIX_SHA = "735523a972bb9c8c678a18cf85e3d1836883db2b"
PRE_FIX_PATH = "docs/issue74/compare_aux_outputs.py"

LOG = """\
 Reading movie
 Hot pixels detected: 17
 [CUDA Global Alignment Profile]
   Host-to-Device transfer time: 0.00 ms (not measured; frames stay resident, but 4 shift uploads totalling 192 B did occur)
   Custom kernel execution time: 0.14 ms
   Total GPU alignment time:     2.62 ms
   Peak GPU memory allocated:    17.36 MiB (this call's buffers, not the process peak)
   Detailed event profiling:     on
 Polynomial fit RMSD: 0.0413
 [CUDA Global Alignment] completed; converged=yes
 Full movie wall time: 1.799 s
"""

EPS = "%!PS-Adobe-3.0 EPSF-3.0\n%%CreationDate: Sun Sep 27 14:59:01 2026\n1 setlinewidth\n"
STAR = "data_\nloop_\n_rlnMicrographName #1\nMovies/a.mrc\n"


def make_tree(root):
    """A minimal but representative output tree."""
    (root / "Movies").mkdir(parents=True)
    (root / "Movies" / "a.log").write_text(LOG)
    (root / "Movies" / "a_shifts.eps").write_text(EPS)
    (root / "Movies" / "a.mrc").write_bytes(b"\x01\x02pixels")
    (root / "Movies" / "a.star").write_text(STAR)
    (root / "corrected_micrographs.star").write_text(STAR)
    (root / "logfile.pdf").write_bytes(b"%PDF-1.4 ghostscript stamped\n")
    return root


def run(script, ref, test, *extra):
    p = subprocess.run([sys.executable, str(script), "--ref", str(ref), "--test", str(test), *extra],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def fetch_pre_fix(dest):
    """Recover the reviewed pre-fix comparator, or return None with a reason."""
    try:
        blob = subprocess.run(["git", "show", f"{PRE_FIX_SHA}:{PRE_FIX_PATH}"],
                              cwd=HERE, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git unavailable: {exc}"
    if blob.returncode != 0:
        return None, f"git show {PRE_FIX_SHA[:8]} failed: {blob.stderr.strip()[:120]}"
    dest.write_text(blob.stdout)
    return dest, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-source", help="pre-fix comparator; default recovers it via git show")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="i74-auxtest-"))
    fails = discriminating = skipped = 0

    if a.old_source:
        old, old_why = Path(a.old_source), None
    else:
        old, old_why = fetch_pre_fix(tmp / "pre_fix_comparator.py")

    def case(label, mutate, want_pass, old_should_accept=False):
        """Build ref/test, mutate test, assert the new comparator's verdict.

        old_should_accept marks a case that the pre-fix source got wrong; we
        assert it really did, so the test is proven to discriminate.
        """
        nonlocal fails, discriminating, skipped
        d = Path(tempfile.mkdtemp(dir=tmp))
        ref, test = make_tree(d / "ref"), make_tree(d / "test")
        # write_text returns a char count, so only an explicit tuple is taken
        # as extra CLI flags.
        mutated = mutate(test)
        extra = mutated if isinstance(mutated, tuple) else ()
        rc, out = run(COMPARATOR, ref, test, *extra)
        ok = (rc == 0) if want_pass else (rc != 0)
        print(f"{'ok  ' if ok else 'FAIL'} {label}: rc={rc} expected={'PASS' if want_pass else 'FAIL'}")
        if not ok:
            fails += 1
            print("      " + "\n      ".join(out.strip().splitlines()[-6:]))

        if old_should_accept:
            if old is None:
                skipped += 1
                print(f"     SKIP old-source control ({old_why})")
            else:
                orc, _ = run(old, ref, test)
                if orc == 0:
                    discriminating += 1
                    print("     ok  old-source control: pre-fix comparator accepted this (rc=0) -- case discriminates")
                else:
                    fails += 1
                    print(f"     FAIL old-source control: pre-fix comparator also rejected it (rc={orc}); "
                          "this case does not prove the fix")

    # Baseline: identical trees must pass, or every failure below is meaningless.
    case("identical trees", lambda t: None, True)

    # The reviewed defect, in its two shapes: a comparable file and a file whose
    # content is deliberately excluded. The second matters because excluding
    # content must not excuse a file from existing.
    case("extra .log in test", lambda t: (t / "Movies" / "b.log").write_text(LOG), False,
         old_should_accept=True)
    case("extra .mrc in test (content covered by Gate C)",
         lambda t: (t / "Movies" / "b.mrc").write_bytes(b"\x01"), False, old_should_accept=True)
    case("extra .pdf in test (content excluded)",
         lambda t: (t / "extra.pdf").write_bytes(b"%PDF-1.4\n"), False, old_should_accept=True)
    case("extra directory in test", lambda t: (t / "Unexpected").mkdir(), False,
         old_should_accept=True)

    # The old source checked existence only *after* skipping excluded content,
    # so it missed disappearances too, not just the extra files the review
    # named. Only the plain .log direction actually worked before.
    case("missing .log in test", lambda t: (t / "Movies" / "a.log").unlink(), False)
    case("missing .mrc in test", lambda t: (t / "Movies" / "a.mrc").unlink(), False,
         old_should_accept=True)
    case("missing .pdf in test", lambda t: (t / "logfile.pdf").unlink(), False,
         old_should_accept=True)
    case("missing per-movie .star in test", lambda t: (t / "Movies" / "a.star").unlink(), False,
         old_should_accept=True)

    # Normalisation must survive the rewrite: volatile lines still tolerated,
    # real differences still caught.
    case("timing-only difference", lambda t: (t / "Movies" / "a.log").write_text(
        LOG.replace("2.62 ms", "9.99 ms").replace("1.799 s", "2.501 s")), True)
    case("profiling mode difference", lambda t: (t / "Movies" / "a.log").write_text(
        LOG.replace("profiling:     on", "profiling:     off")), True)
    case("eps creation date difference", lambda t: (t / "Movies" / "a_shifts.eps").write_text(
        EPS.replace("Sun Sep 27 14:59:01 2026", "Mon Sep 28 06:11:02 2026")), True)
    case("real science difference (polynomial fit RMSD)", lambda t: (t / "Movies" / "a.log").write_text(
        LOG.replace("0.0413", "0.0414")), False)
    case("execution marker removed", lambda t: (t / "Movies" / "a.log").write_text(
        LOG.replace(" [CUDA Global Alignment] completed; converged=yes\n", "")), False)
    case("corrected_micrographs.star difference", lambda t: (
        t / "corrected_micrographs.star").write_text(STAR + "Movies/b.mrc\n"), False)

    # Label corrections: rejected by default, tolerated only when the caller
    # says the reference came from a pre-change binary.
    case("label change, not allowed", lambda t: (t / "Movies" / "a.log").write_text(
        LOG.replace("Peak GPU memory allocated:    17.36 MiB (this call's buffers, not the process peak)",
                    "Peak GPU memory allocated:    17.36 MiB")), False)
    def relabel_and_allow(t):
        (t / "Movies" / "a.log").write_text(
            LOG.replace("Peak GPU memory allocated:    17.36 MiB (this call's buffers, not the process peak)",
                        "Peak GPU memory allocated:    17.36 MiB"))
        return ("--allow-label-changes",)

    case("label change, allowed", relabel_and_allow, True)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print(f"discriminating old-source controls: {discriminating} proven, {skipped} skipped")
    if fails:
        print(f"AUX COMPARATOR SELF-TEST: FAIL ({fails})")
        return 1
    if discriminating == 0:
        print("AUX COMPARATOR SELF-TEST: INCONCLUSIVE (no old-source control ran; "
              "the fix is untested against the source it replaces)")
        return 2
    print("AUX COMPARATOR SELF-TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
