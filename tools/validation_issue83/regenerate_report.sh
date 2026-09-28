#!/bin/sh
# Regenerate docs/issue83/support-report.md from the preserved raw records.
#
# The published report is assembled from six records. Writing the recipe out by
# hand in prose got it wrong -- an earlier revision of provenance.md listed five
# of the six options, omitting the one that produces the entire input-provenance
# section, and named working paths from a superseded run rather than the
# preserved records. This script is the recipe, committed next to the tool it
# drives, so the document and the command cannot drift apart again.
#
# Four of the six now come from a single GPU allocation, job 3511210 on gn3000
# at `4c2305b`, which is the first GPU run at a commit whose runners carry the
# per-schedule witness and the STAR metadata assertion. The other two are a
# different host and a different run and say so: the CPU-backend diagnostic
# from cpu64, and the capacity datapoint from gn0005, which names no host or
# binary and is rendered as unattributable.
#
# Nothing here recomputes a verdict. Every number in the report is read out of
# these files; the tool's job is to render them and to refuse to let one run's
# provenance speak for another's numbers.
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
raw="$root/docs/issue83/raw"

python3 "$root/tools/validation_issue83/report.py" \
  --matrix-json          "$raw/scarf-gn3000-3511210/matrix-summary.json" \
  --all24-json           "$raw/scarf-gn3000-3511210/all24-summary.json" \
  --truth-json           "$raw/scarf-gn3000-3511210/truth-summary.json" \
  --cpu-diagnostic-json  "$raw/cpu64-cb587bd/matrix.json" \
  --capacity-json        "$raw/scarf-gn0005/capacity.json" \
  --fixture-verify-json  "$raw/scarf-gn3000-3511210/verify_fixtures.json" \
  --out                  "$root/docs/issue83/support-report.md"
