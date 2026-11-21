#!/usr/bin/env python3
"""Execute only the exact namespace-check block of a frozen prerequisite.

No substitute validator and no numerical/fixture code. Used behind the real
wrapper and unchanged c1_stage.sh in isolated control roots.
"""
import hashlib
import json
import sys
from pathlib import Path

prereq, root, output = map(Path, sys.argv[1:])
source = prereq.read_text()
start = source.index('# Launch markers' if '# Launch markers' in source else '# the stage wrapper')
end = source.index('text = Path(sys.argv[1])', start)
block = source[start:end]
checks = {}
def check(name, ok, detail=None):
    checks[name] = {'ok': bool(ok), 'detail': detail}
exec(compile(block, str(prereq), 'exec'), {'SC': root, 'check': check})
result = {'prereq_sha256': hashlib.sha256(prereq.read_bytes()).hexdigest(),
          'executed_block_sha256': hashlib.sha256(block.encode()).hexdigest(),
          'checks': checks, 'entries': sorted(p.name for p in (root / 'logs').iterdir())}
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
sys.exit(0 if checks['fresh_stage_names']['ok'] else 1)
