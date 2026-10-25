#!/bin/sh
# usage: pack_phase_b.sh PHASE_A_DIAG_JSON  -> writes phaseB-inputs.tar next to this script, prints sha256
set -eu
K=$(cd "$(dirname "$0")" && pwd); B=$K/phaseB-staging
test ! -e "$B/diag/w4_fixture_diag.json"
cp "$1" "$B/diag/w4_fixture_diag.json"
cd "$B" && find scripts src805 fixtures r275 ref diag -type f ! -name '._*' | LC_ALL=C sort | COPYFILE_DISABLE=1 tar --no-mac-metadata -cf "$K/phaseB-inputs.tar" -T -
shasum -a 256 "$K/phaseB-inputs.tar"
