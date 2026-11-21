#!/bin/bash
# Re-run test_c1_ingest_poison.py on the committed tools and on three reverted-item mutants of c1_ingest_poison.py.
# usage: ingest_test_mutants.sh C1_TOOLS_DIR   (docs/post_rc0/c1-20261022/native-final-20261025/tools)
set -u
S=$1; T=$(mktemp -d); cp "$S/c1_ingest_poison.py" "$S/test_c1_ingest_poison.py" "$T/"
echo "== committed"; python3 -I "$T/test_c1_ingest_poison.py" 2>&1 | grep -E '^(OK|FAILED|Ran)'
for m in A B C; do
  mkdir -p "$T/$m"; cp "$S/test_c1_ingest_poison.py" "$T/$m/"
  python3 -I - "$S/c1_ingest_poison.py" "$T/$m/c1_ingest_poison.py" "$m" <<'PY'
import sys
s = open(sys.argv[1]).read(); m = sys.argv[3]
edits = {'A': ("[^\\n]*Movies/control\\.tiff: [^\\n]*Refusing CPU fallback after a fatal device error\\.')",      # v3c regex: re.S and '.*'
               "[^\\n]*Movies/control\\.tiff: .*Refusing CPU fallback after a fatal device error\\.', re.S)"),
         'B': ("require((witness or '') == '',", "require(not (witness or '').strip(),"),                              # v3c witness check
         'C': ("    except Exception as exc:     # a verdict bug", "    except ZeroDivisionError as exc:     # a verdict bug")}  # handler disabled
a, b = edits[m]; assert s.count(a) == 1, m; open(sys.argv[2], 'w').write(s.replace(a, b))
PY
  echo "== mutant $m"; python3 -I "$T/$m/test_c1_ingest_poison.py" 2>&1 | grep -E '^(OK|FAILED|Ran)'
done
