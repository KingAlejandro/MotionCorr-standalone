#!/bin/bash
# P6: reviewer guard mutants on a /tmp copy (guard + its test); each must make the authors' guard suite fail.
W=$1; PY=$2; OUT=$3
mut() {  # name sed-expression
  d=$(mktemp -d); cp "$W/tools/stageC_guard.sh" "$W/tools/test_ccf_dc_stagec_guard.py" "$d/"
  sed -i '' -e "$2" "$d/stageC_guard.sh"
  if cmp -s "$W/tools/stageC_guard.sh" "$d/stageC_guard.sh"; then echo "$1: MUTATION NOT APPLIED"; rm -rf "$d"; return; fi
  "$PY" -I "$d/test_ccf_dc_stagec_guard.py" > "$OUT/mutant-$1.out" 2>&1; rc=$?
  echo "$1: suite rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED))"; rm -rf "$d"
}
mut no_other_app_stop   's/^  \[ -n "\$others" \] && die 11.*$/  :/'
mut no_util_range       's/numeric "\$gutil" && \[ "\$gutil" -le 100 \]/numeric "$gutil"/'
mut no_df_headroom      's/^\[ "\$avail" -ge \$((CAP - used)) \].*$/:/'
mut run_swallows_fail   's/"\$@" >"\$tmp\/\$name.out" 2>"\$tmp\/\$name.err" || die 14/"$@" >"$tmp\/$name.out" 2>"$tmp\/$name.err" || true/'
mut free_unchecked      's/^numeric "\$mt" && numeric "\$ma".*$/:/'
