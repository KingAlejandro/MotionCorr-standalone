# Independent parent review: relocated R12 helper binding

Sonnet5.5 owns the bounded tooling repair; 6.1Sol independently inspected the patch against a406983b and reran the five controls on macOS Python3.15. Result:5/5 PASS. The discriminating relocation control restores the old lookup and fails at qual_lib import; wrong C1_SCR refuses without fallback; repository use without C1_SCR still works; regeneration is byte-identical. No production or numerical code, gate, expectation, lease, fault/recovery or publication behavior changed. The HERE binding also supplies qf_fault_by_uuid.sh; its original location is retained.

Source paths are frozen by existing c1_env.sh. Deployment must be a new tools packet/manifest, not an in-place edit of tools-v2.3-run. Earlier tools and all records stay byte-exact. The actual R12 and12ds rows are still UNRUN, not failed. Linux import-only qualification remains pending at this checkpoint; no native/GPU/build was invoked by these tests. Tests load the real qual_lib and stop at argparse --help before ROOT.mkdir or native calls. New tests are stdlib-only and compatible with project licensing; upstream notices and existing QF helpers remain untouched.

The original harvest report's blanket W1-unrun wording is corrected by the parent: tutorial nvCOMP G/L route-audit-20261023 is already PASS. The newly harvested CPU1/5/2 truth counts are one backend; historical2/10/4 is prior evidence, not a fresh CUDA run or an inferred doubling. Raw harvest is retained with these corrections, not rewritten.

The author source-manifest reference records the original scratch package, not a manifest for this smaller retained review directory; regenerate from the committed patch/test for portable reproduction. The upstream raw scratch remains intact.
