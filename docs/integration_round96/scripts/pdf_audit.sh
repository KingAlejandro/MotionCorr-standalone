#!/usr/bin/env bash
# PR110 bounded retained-evidence audit: are the four PDF differences metadata/
# serialization only, or do they carry rendered content or plot data?
#
# Uses ONLY retained main/candidate output pairs. MotionCorr is not re-run.
# Tooling on this host is ghostscript + numpy; no poppler, no pypdf.
set -uo pipefail
VENV=/home/ubuntu/.mc-venv
export PATH=$VENV/bin:$PATH
R=/home/ubuntu/mc-i96-pdfaudit
PAIR_A=/home/ubuntu/mc-i96-final/ab24/out_main-4c952b3_j8
PAIR_B=/home/ubuntu/mc-i96-final/ab24/out_integrate-round96-final_j8
rm -rf "$R"; mkdir -p "$R"; cd "$R"
exec > >(tee -a "$R/pdf_audit.log") 2>&1

echo "################ PROVENANCE ################"
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
numactl --show | grep -E "policy|physcpubind|membind"
echo "SMT thread(s)/core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}'); node1 = CPUs 32-63"
cat /proc/loadavg
for p in $(pgrep -x ctffind); do echo "interference ctffind pid=$p cpus=$(awk '/Cpus_allowed_list/{print $2}' /proc/$p/status) (recorded, untouched)"; done
gs --version | sed 's/^/ghostscript /'
python3 -c "import numpy;print('numpy',numpy.__version__)"
echo "retained pair (MotionCorr NOT re-run):"
echo "  main      $PAIR_A"
echo "  candidate $PAIR_B"
echo "  produced by the cpu64 all-24 A/B at final head; trees retained since"

echo; echo "################ ARTIFACT IDENTITY ################"
for f in all_batches.pdf batch.pdf header.pdf logfile.pdf; do
  printf "%-18s main=%s  cand=%s  bytes %s / %s\n" "$f" \
    "$(sha256sum "$PAIR_A/$f" | cut -c1-16)" "$(sha256sum "$PAIR_B/$f" | cut -c1-16)" \
    "$(stat -c%s "$PAIR_A/$f")" "$(stat -c%s "$PAIR_B/$f")"
done

echo; echo "################ PAGE COUNTS ################"
for f in all_batches.pdf batch.pdf header.pdf logfile.pdf; do
  for side in A B; do
    d=$([ $side = A ] && echo "$PAIR_A" || echo "$PAIR_B")
    n=$(gs -q -dNODISPLAY -dNOSAFER -c "($d/$f) (r) file runpdfbegin pdfpagecount = quit" 2>/dev/null)
    echo -n "$f $side=$n  "
  done; echo
done

echo; echo "################ RAW METADATA STRINGS (the suspected cause) ################"
for f in all_batches.pdf batch.pdf header.pdf logfile.pdf; do
  echo "--- $f"
  for side in A B; do
    d=$([ $side = A ] && echo "$PAIR_A" || echo "$PAIR_B")
    strings "$d/$f" | grep -aoE "/(CreationDate|ModDate) ?\([^)]*\)|/Producer ?\([^)]*\)|/Creator ?\([^)]*\)" | sed "s/^/    $side /"
  done
done

echo; echo "################ EXTRACTED TEXT (gs txtwrite) ################"
mkdir -p txt
for f in all_batches.pdf batch.pdf header.pdf logfile.pdf; do
  gs -q -dNOSAFER -dBATCH -dNOPAUSE -sDEVICE=txtwrite -o "txt/${f%.pdf}.A.txt" "$PAIR_A/$f" >/dev/null 2>&1
  gs -q -dNOSAFER -dBATCH -dNOPAUSE -sDEVICE=txtwrite -o "txt/${f%.pdf}.B.txt" "$PAIR_B/$f" >/dev/null 2>&1
  if diff -q "txt/${f%.pdf}.A.txt" "txt/${f%.pdf}.B.txt" >/dev/null 2>&1; then
    echo "$f  TEXT IDENTICAL  ($(wc -c < "txt/${f%.pdf}.A.txt") bytes)"
  else
    echo "$f  TEXT DIFFERS -- first differing lines:"
    diff "txt/${f%.pdf}.A.txt" "txt/${f%.pdf}.B.txt" | head -20 | sed 's/^/    /'
  fi
done

echo; echo "################ FULL-PAGE RENDER COMPARISON (150 dpi, png16m) ################"
echo "This is the load-bearing check: it compares what a reader actually sees,"
echo "including every plotted point. No normalisation is applied."
mkdir -p png
for f in all_batches.pdf batch.pdf header.pdf logfile.pdf; do
  gs -q -dNOSAFER -dBATCH -dNOPAUSE -sDEVICE=png16m -r150 -o "png/${f%.pdf}.A.%04d.png" "$PAIR_A/$f" >/dev/null 2>&1
  gs -q -dNOSAFER -dBATCH -dNOPAUSE -sDEVICE=png16m -r150 -o "png/${f%.pdf}.B.%04d.png" "$PAIR_B/$f" >/dev/null 2>&1
done
python3 - <<'PY'
import glob, hashlib, os, re, sys
import numpy as np
def load_png(p):
    # minimal PNG reader via gs output is awkward; use zlib-based decode through numpy+struct
    import zlib, struct
    d = open(p,'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', p
    pos, idat, w=h=None, b'', None
    pos = 8; w = h = None; bitd = ct = None
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]; typ = d[pos+4:pos+8]
        body = d[pos+8:pos+8+ln]
        if typ == b'IHDR':
            w,h,bitd,ct = struct.unpack('>IIBB', body[:10])
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12+ln
    raw = zlib.decompress(idat)
    ch = {0:1,2:3,3:1,4:2,6:4}[ct]
    stride = w*ch
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.uint8)
    i = 0
    for y in range(h):
        ft = raw[i]; i += 1
        line = np.frombuffer(raw[i:i+stride], dtype=np.uint8).copy(); i += stride
        if ft == 1:
            for x in range(ch, stride): line[x] = (int(line[x]) + int(line[x-ch])) & 0xFF
        elif ft == 2:
            line = (line.astype(int) + prev.astype(int)).astype(np.uint8)
        elif ft == 3:
            for x in range(stride):
                a = int(line[x-ch]) if x >= ch else 0
                line[x] = (int(line[x]) + ((a + int(prev[x]))>>1)) & 0xFF
        elif ft == 4:
            for x in range(stride):
                a = int(line[x-ch]) if x >= ch else 0
                b = int(prev[x]); c = int(prev[x-ch]) if x >= ch else 0
                pp = a+b-c; pa,pb,pc = abs(pp-a),abs(pp-b),abs(pp-c)
                pr = a if (pa<=pb and pa<=pc) else (b if pb<=pc else c)
                line[x] = (int(line[x]) + pr) & 0xFF
        out[y] = line; prev = line
    return out.reshape(h, w, ch)

total_pages = 0; total_diff_pages = 0
for stem in ["all_batches","batch","header","logfile"]:
    A = sorted(glob.glob(f"png/{stem}.A.*.png")); B = sorted(glob.glob(f"png/{stem}.B.*.png"))
    if not A or not B:
        print(f"{stem:14s} RENDER FAILED (A={len(A)} B={len(B)} pages) -- UNVERIFIED"); continue
    if len(A) != len(B):
        print(f"{stem:14s} PAGE COUNT DIFFERS A={len(A)} B={len(B)} -- CONTENT DIFFERENCE"); continue
    ndiff = 0; worst = 0; worstpx = 0
    for a,b in zip(A,B):
        ia, ib = load_png(a), load_png(b)
        if ia.shape != ib.shape:
            print(f"{stem:14s} page shape differs {ia.shape} vs {ib.shape} -- CONTENT DIFFERENCE"); ndiff += 1; continue
        d = np.abs(ia.astype(np.int16) - ib.astype(np.int16))
        if d.any():
            ndiff += 1; worst = max(worst, int(d.max())); worstpx = max(worstpx, int((d.any(axis=2)).sum()))
    total_pages += len(A); total_diff_pages += ndiff
    verdict = "RENDER IDENTICAL" if ndiff == 0 else f"RENDER DIFFERS on {ndiff}/{len(A)} pages (max channel delta {worst}, max differing pixels/page {worstpx})"
    print(f"{stem:14s} {len(A)} page(s)  {verdict}")
print(f"\nTOTAL: {total_pages} rendered pages compared, {total_diff_pages} differing")
PY

echo; echo "################ SUPPORTING (not a substitute): EPS and STAR ################"
epsd=0; epst=0
for f in "$PAIR_A"/Movies/*_shifts.eps; do
  n=$(basename "$f"); epst=$((epst+1))
  cmp -s "$f" "$PAIR_B/Movies/$n" || epsd=$((epsd+1))
done
echo "EPS shift plots: $epst compared, $epsd differing byte-for-byte"
std=0; stt=0
for f in $(cd "$PAIR_A" && find . -name "*.star"); do
  stt=$((stt+1)); cmp -s "$PAIR_A/$f" "$PAIR_B/$f" || std=$((std+1))
done
echo "STAR files:      $stt compared, $std differing byte-for-byte"

echo; echo "################ DONE ################"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
