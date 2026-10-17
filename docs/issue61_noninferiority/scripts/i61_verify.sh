#!/bin/bash
# Issue 61: matched-design verification.
#
# The original positional-column implementation was replaced after PR #65 review findings
# r4119264419 (hashed only seven columns by position, omitting _rlnAnglePsi) and r4119264433
# (covered five of six arms).  The check now resolves every field by header name, asserts
# each one is present, hashes the whole data_particles block as a catch-all, and digests
# every particle stack of every movie in every arm.  See i61_verify.py.
set -u
ROOT=${ROOT:-/home/alex/mc-issue61}
PY=${PY:-/home/alex/relion-container-tests/venvs/pipeliner-onedep-adapter/bin/python}
ARMS=${ARMS:-"cpu default allfftw ctrl_noise_f005 ctrl_noise_f020 ctrl_envelope_b20"}
exec $PY "$(dirname "$0")/i61_verify.py" "$ROOT" $ARMS
