#!/bin/sh
# usage: pack_phase_c.sh RETAINED_DECOMPOSITION_V2_1_JSON RETAINED_SHRINKAGE_JSON
# Both files are the outputs retained in the failed Phase B v2.1 namespace; exact hashes required.
set -eu
K=$(cd "$(dirname "$0")" && pwd); C=$K/phaseC-staging
echo "8b0a71a01fd4bc9ba9f5f880f057963952e92305a43182513623f48868e04fe2  $1" | shasum -a 256 -c -
echo "0a2d16d25cbcf3e9a14b43fbd6b331079356bc13e31dc8d80b40f2cc91c54629  $2" | shasum -a 256 -c -
test ! -e "$C/retained/w4_allpatch_decomposition_v2.json" && test ! -e "$C/retained/w4_shrinkage.json"
cp "$1" "$C/retained/w4_allpatch_decomposition_v2.json"; cp "$2" "$C/retained/w4_shrinkage.json"
cd "$C" && find scripts ref retained -type f ! -name '._*' | LC_ALL=C sort | COPYFILE_DISABLE=1 tar --no-mac-metadata -cf "$K/phaseC-inputs.tar" -T -
shasum -a 256 "$K/phaseC-inputs.tar"
