#!/bin/bash
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-i99
E=$R/evidence; rm -rf "$E"; mkdir -p "$E"
exec > >(tee "$E/evidence.log") 2>&1
echo "=== provenance ==="; date -Is; hostname; grep Cpus_allowed_list /proc/self/status
echo "head  motioncorr: $(sha256sum $R/src-head/build-cpu/motioncorr)"
echo "neg   motioncorr: $(sha256sum $R/src-neg/build-cpu/motioncorr)"

STARBODY='# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.000 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
'
ARGS="--use_own --j 2 --skip_defect --angpix 1.0 --voltage 300 --patch_x 1 --patch_y 1 --bfactor 150 --skip_logfile"

body () {
echo
echo "############ 1. HEALTHY BYTE PARITY, identical relative paths ############"
for arm in neg head; do
  W=$E/par-$arm; rm -rf "$W"; mkdir -p "$W/mov" "$W/out"
  cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/p.tiff"
  printf '%smov/p.tiff 1\n' "$STARBODY" > "$W/p.star"
  ( cd "$W" && taskset -c 32-63 "$R/src-$arm/build-cpu/motioncorr" --i p.star --o out/ $ARGS > run.log 2>&1 )
  echo "arm $arm exit=$?"
done
echo "input movie: $(sha256sum $E/par-head/mov/p.tiff)"
echo "--- byte-for-byte comparison of every produced file ---"
( cd "$E" && diff -r --brief par-neg/out par-head/out \
    && echo "IDENTICAL: every output file matches byte for byte" )
echo "--- explicit hashes ---"
for f in mov/p.mrc mov/p.star corrected_micrographs.star; do
  printf '%-32s neg=%s head=%s\n' "$f" \
    "$(sha256sum $E/par-neg/out/$f  | cut -c1-16)" \
    "$(sha256sum $E/par-head/out/$f | cut -c1-16)"
done
echo -n "mov/p.mrc size: "; stat -c %s "$E/par-head/out/mov/p.mrc"

echo
echo "############ 2. PRE-FIX FALSE COMPLETION (executed reproducer) ############"
W=$E/prefix; rm -rf "$W"; mkdir -p "$W/mov" "$W/out"
cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/a.tiff"
cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/b.tiff"
printf '%smov/a.tiff 1\n' "$STARBODY" > "$W/a.star"
printf '%smov/a.tiff 1\nmov/b.tiff 1\n' "$STARBODY" > "$W/ab.star"
( cd "$W" && taskset -c 32-63 "$R/src-neg/build-cpu/motioncorr" --i a.star --o out/ $ARGS > p1.log 2>&1 )
echo "phase 1 (a alone, unlimited) exit=$?  a.mrc=$(stat -c %s $W/out/mov/a.mrc) bytes"
( cd "$W" && trap '' XFSZ; ulimit -f 585 ; \
  taskset -c 32-63 "$R/src-neg/build-cpu/motioncorr" --i ab.star --o out/ $ARGS --only_do_unfinished > p2.log 2>&1 )
rc=$?
echo "phase 2 (a+b, RLIMIT_FSIZE=599040 bytes) exit=$rc   <-- 0 means the failure was swallowed"
echo -n "  b.mrc on disk: "; stat -c %s "$W/out/mov/b.mrc" 2>&1
echo -n "  b.star completion record present: "; test -f "$W/out/mov/b.star" && echo YES || echo no
echo "  joint STAR after the failed write:"
grep -n 'mrc' "$W/out/corrected_micrographs.star" | sed 's/^/    /'
echo "  stderr/stdout tail:"; tail -6 "$W/p2.log" | sed 's/^/    /'

echo
echo "############ 3. POST-FIX BEHAVIOUR, same injected fault ############"
W=$E/postfix; rm -rf "$W"; mkdir -p "$W/mov" "$W/out"
cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/a.tiff"
cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/b.tiff"
printf '%smov/a.tiff 1\n' "$STARBODY" > "$W/a.star"
printf '%smov/a.tiff 1\nmov/b.tiff 1\n' "$STARBODY" > "$W/ab.star"
( cd "$W" && taskset -c 32-63 "$R/src-head/build-cpu/motioncorr" --i a.star --o out/ $ARGS > p1.log 2>&1 )
echo "phase 1 (a alone, unlimited) exit=$?  a.mrc=$(stat -c %s $W/out/mov/a.mrc) bytes"
A_BEFORE=$(sha256sum "$W/out/mov/a.mrc" | cut -d' ' -f1)
J_BEFORE=$(sha256sum "$W/out/corrected_micrographs.star" | cut -d' ' -f1)
( cd "$W" && trap '' XFSZ; ulimit -f 585 ; \
  taskset -c 32-63 "$R/src-head/build-cpu/motioncorr" --i ab.star --o out/ $ARGS --only_do_unfinished > p2.log 2>&1 )
rc=$?
echo "phase 2 (a+b, RLIMIT_FSIZE=599040 bytes) exit=$rc   <-- nonzero, not a signal"
echo -n "  b.mrc on disk: "; stat -c %s "$W/out/mov/b.mrc" 2>&1
echo -n "  b.star completion record present: "; test -f "$W/out/mov/b.star" && echo YES || echo no
echo -n "  a.mrc unchanged: "; [ "$(sha256sum $W/out/mov/a.mrc|cut -d' ' -f1)" = "$A_BEFORE" ] && echo yes || echo NO
echo -n "  joint STAR unchanged (b withheld): "; [ "$(sha256sum $W/out/corrected_micrographs.star|cut -d' ' -f1)" = "$J_BEFORE" ] && echo yes || echo NO
echo "  reported failure:"; grep -iE 'ERROR|Failed to write|failed for' "$W/p2.log" | sed 's/^/    /'
( cd "$W" && taskset -c 32-63 "$R/src-head/build-cpu/motioncorr" --i ab.star --o out/ $ARGS --only_do_unfinished > p3.log 2>&1 )
echo "phase 3 (repaired retry) exit=$?"
echo -n "  b.mrc now: "; stat -c %s "$W/out/mov/b.mrc"
echo -n "  b.star present: "; test -f "$W/out/mov/b.star" && echo yes || echo NO
echo -n "  a.mrc still unchanged: "; [ "$(sha256sum $W/out/mov/a.mrc|cut -d' ' -f1)" = "$A_BEFORE" ] && echo yes || echo NO
echo "  joint STAR now lists:"; grep -n 'mrc' "$W/out/corrected_micrographs.star" | sed 's/^/    /'

echo
echo "############ 4. NEW TESTS, verbose, on the fixed build ############"
cd "$R/src-head/build-cpu" && taskset -c 32-63 ctest -V -R 'ImageWriteFaults|WriteFaults' 2>&1 \
  | grep -vE '^UpdateCTestConfiguration|^Parse|^ *Test *#?[0-9]*: *$|^Add|^Constructing|^Checking|^Test project' | tail -45
}

echo "### acquiring validation lock"
flock /tmp/motioncorr-issue96-cpu-validation.lock bash -c "
  R=$R; E=$E; STARBODY='$STARBODY'; ARGS='$ARGS'
  $(declare -f body); body
"
echo "=== EVIDENCE DONE ==="; date -Is
