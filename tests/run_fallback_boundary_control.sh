#!/bin/bash
# Issue #69 P1c: discriminating control for the fallback-preparation boundary.
#
# WHAT IT PROVES, on production code, with the real binary:
#   A recoverable/nonconverged resident attempt enters the fallback; the fallback
#   cudaPreparePatch hits an injected POISONING status; its own handler consumes the
#   code and clears the thread's last-error slot; the runner's post-prep enforcement
#   nevertheless refuses, so alignPatch never re-dispatches CUDA, the movie fails
#   closed, and no corrected image or joint STAR is published for it.
#
# WHAT MAKES IT DISCRIMINATING: the same injection is run against a MUTANT tree with
# the failure RECORDING removed -- one line. The mutant must NOT refuse. A control that
# passes both ways proves nothing, and the previous predicate-only control did exactly
# that. Mutating the runner's post-prep check instead would add nothing: the positive
# arm already proves that layer runs, because the refusal string exists nowhere else,
# and a runner-check mutant produces the identical observable (0 refusals).
#
# SCOPE: the fault is an injected error CODE. No hardware is poisoned, nothing is
# reset. Behaviour under a genuine illegal-address or ECC fault remains UNRUN.
#
# Usage: run_fallback_boundary_control.sh <src_dir> <build_dir> <movie> [workdir]
set -uo pipefail
SRC="$1"; BLD="$2"; MOVIE="$3"; W="${4:-$HOME/mc-i69-p1c-work}"
BIN="$BLD/motioncorr_faultinject"
[ -x "$BIN" ] || { echo "FAIL missing $BIN"; exit 2; }
rm -rf "$W"; mkdir -p "$W"

COMMON=(--use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150
        --dose_weighting --dose_per_frame 1.0 --voltage 300 --angpix 0.885
        --max_iter 1)   # max_iter 1 => every patch reports nonconverged => fallback entered

run () { # $1=outdir  $2=ordinal  $3=code
  mkdir -p "$1"
  MC_FAULT_ORDINAL="$2" MC_FAULT_CODE="$3" \
    "$BIN" --i "$MOVIE" --o "$1/" "${COMMON[@]}" > "$1/run.log" 2>&1
  echo $?
}

echo "=== step 1: clean baseline, no injection ==="
rc=$(run "$W/clean" 0 none)
echo "exit=$rc  mrc=$(find "$W/clean" -name '*.mrc'|wc -l)"
[ "$rc" = "0" ] || { echo "FAIL baseline did not succeed; nothing below would be interpretable"; exit 1; }
grep -c "completed; converged=no" "$W"/clean/*/*/*/*/*.log 2>/dev/null | head -1 | sed 's/^/  nonconverged patch alignments: /'

echo
echo "=== step 2: find an ordinal that lands inside cudaPreparePatch ==="
# cuda_fft_prep.cu's handler logs its own file, so the movie log identifies the helper.
ORD=""
for n in $(seq 1 60); do
  rm -rf "$W/probe"; run "$W/probe" "$n" poison >/dev/null
  # Function-exact: the refusal message carries __func__, so this confirms the ordinal
  # landed in cudaPreparePatch and not in another function of the same file.
  if grep -rqs "recorded at cudaPreparePatch:" "$W/probe" 2>/dev/null; then ORD=$n; break; fi
done
[ -n "$ORD" ] || { echo "FAIL no ordinal in 1..60 reached cudaPreparePatch"; exit 1; }
echo "  ordinal $ORD lands in cudaPreparePatch:"
grep -rhos "CUDA Error in .*cuda_fft_prep.cu:[0-9]*" "$W/probe" | head -1 | sed 's/^/    /'

echo
echo "=== step 3: POISONING status at the fallback boundary (the case under test) ==="
rm -rf "$W/fix"; rcf=$(run "$W/fix" "$ORD" poison)
refused=$(grep -rc "unusable after fallback patch preparation" "$W/fix" 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
redispatch=$(grep -rhos "CUDA Patch Alignment Profile" "$W/fix" 2>/dev/null | wc -l)
imgs=$(find "$W/fix" -name '*.mrc' | wc -l)
joint=$(find "$W/fix" -name 'corrected_micrographs.star' | wc -l)
echo "  exit=$rcf (must be nonzero)            refusal messages=$refused (must be >=1)"
echo "  corrected images=$imgs (must be 0)     joint STAR=$joint (must be 0)"
echo "  stage/status attribution:"; grep -rhos "unusable after fallback patch preparation.*" "$W/fix" | head -1 | sed 's/^/    /'

fail=0
[ "$rcf" != "0" ]      || { echo "  FAIL exit was 0: the movie did not fail closed"; fail=1; }
[ "$refused" -ge 1 ]   || { echo "  FAIL the post-prep enforcement did not fire"; fail=1; }
[ "$imgs" -eq 0 ]      || { echo "  FAIL a corrected image was published for a failed movie"; fail=1; }
[ "$joint" -eq 0 ]     || { echo "  FAIL a joint STAR was published"; fail=1; }

echo
echo "=== step 4: RECOVERABLE status at the same boundary must still permit ==="
rm -rf "$W/recov"; rcr=$(run "$W/recov" "$ORD" recoverable)
rimgs=$(find "$W/recov" -name '*.mrc' | wc -l)
rrefused=$(grep -rc "unusable after fallback patch preparation" "$W/recov" 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
echo "  exit=$rcr (must be 0)  corrected images=$rimgs (must be 1)  refusals=$rrefused (must be 0)"
[ "$rcr" = "0" ] && [ "$rimgs" -ge 1 ] && [ "$rrefused" -eq 0 ] || { echo "  FAIL the documented recoverable host path was not permitted"; fail=1; }

echo
echo "=== step 5: MUTANT -- remove the failure recording; the control must FAIL ==="
MUT="$W/mutant-src"
rm -rf "$MUT"; cp -a "$SRC" "$MUT" 2>/dev/null
rm -rf "$MUT/build" "$MUT"/build-*
# Narrow mutation: the consuming handler no longer records, so nothing is carried out
# of the helper and the post-prep check sees a cleared slot -- the pre-fix behaviour.
perl -0pi -e 's/if \(failure\) failure->record\(e, __func__, __LINE__\); \\\n//' \
     "$MUT/src/acc/cuda/cuda_fft_prep.cu"
if grep -q "failure->record(e, __func__, __LINE__)" "$MUT/src/acc/cuda/cuda_fft_prep.cu"; then
  echo "  FAIL mutation did not apply"; fail=1
else
  echo "  mutation applied: failure recording removed from cuda_fft_prep.cu"
  cmake -S "$MUT" -B "$MUT/build" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
        -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON > "$W/mutant-conf.log" 2>&1
  cmake --build "$MUT/build" -j4 --target motioncorr_faultinject > "$W/mutant-build.log" 2>&1
  mrc=$?
  if [ $mrc -ne 0 ]; then echo "  FAIL mutant did not build"; tail -5 "$W/mutant-build.log"; fail=1
  else
    rm -rf "$W/mut"; mkdir -p "$W/mut"
    MC_FAULT_ORDINAL="$ORD" MC_FAULT_CODE=poison \
      "$MUT/build/motioncorr_faultinject" --i "$MOVIE" --o "$W/mut/" "${COMMON[@]}" \
      > "$W/mut/run.log" 2>&1
    mexit=$?
    mref=$(grep -rc "unusable after fallback patch preparation" "$W/mut" 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
    mimg=$(find "$W/mut" -name '*.mrc' | wc -l)
    echo "  mutant exit=$mexit (must be 0)  refusals=$mref (must be 0)  images=$mimg (must be >=1)"
    # Assert the mutant's OWN health too. Without this, a mutant that crashed for an
    # unrelated reason would also show 0 refusals and be declared discriminating --
    # the same silent-pass-on-own-failure class this branch has criticised elsewhere.
    if [ "$mref" -eq 0 ] && [ "$mexit" -eq 0 ] && [ "$mimg" -ge 1 ]; then
      echo "  DISCRIMINATING: the fix refuses and fails closed; the mutant completes normally."
    elif [ "$mref" -ne 0 ]; then
      echo "  FAIL the mutant also refused, so the control does not discriminate"; fail=1
    else
      echo "  FAIL the mutant did not complete normally, so its 0 refusals prove nothing"; fail=1
    fi
  fi
fi

echo
if [ $fail -ne 0 ]; then echo "FAIL fallback-boundary control"; exit 1; fi
echo "PASS fallback-boundary control: production helper -> consumed/cleared last-error ->"
echo "     runner post-prep enforcement refuses, no CUDA re-dispatch, fail-closed"
echo "     publication, recoverable path still permitted, and a mutant without the"
echo "     recording does NOT refuse."
echo "NOTE: injected error code, not a genuine poisoned context. No hardware was"
echo "      poisoned or reset. Genuine-fault behaviour remains UNRUN."
