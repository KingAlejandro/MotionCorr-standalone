#!/usr/bin/env python3
"""Derive c1_item12.py from the committed QF driver docs/rc0/qf/tools/item12_retry.py with explicit, asserted replacements.

The original is not edited. Adaptations are (1) task-local resources: --j 2 and OMP_NUM_THREADS=2 for the 2-CPU C1 lane; (3) task-local lease/health handling through c1_lane.run_case_nb (tools v2); (2) expectations for a
numerically changed candidate: the retried-patch count is derived from C1's own frozen-arm run (#254/#260/#270 legitimately change CUDA local
alignment, so #207's recorded 41/30 and 9/25 and exact output identity with the 1db86902 reference are obsolete as pass criteria); the legacy
comparisons are still computed and kept under 'legacy_*' keys, never counted as problems and never relabelled as passes. Internal-consistency
rules (count == frozen, recoverable fault gives identical products plus one warning, fatal fault refuses without publication, shim ownership)
are unchanged. Usage: make_c1_item12.py  (writes c1_item12.py and c1_item12.diff beside this file; tools v2).
"""
import difflib, sys
from pathlib import Path
here = Path(__file__).resolve().parent
orig = (here.parents[2] / 'rc0/qf/tools/item12_retry.py').read_text()
s = orig
def rep(a, b, count=1):
    global s
    assert s.count(a) == count, (a, s.count(a))
    s = s.replace(a, b)

rep("HERE = Path(__file__).resolve().parent\n",
    "# C1: QF helpers are read in place. Deployed under $C1_SCR/tools-*-run, so bind to the scratch checkout; in the repo (C1_SCR unset) use docs/rc0/qf/tools.\n"
    "HERE = (Path(os.environ['C1_SCR']) / 'src' / 'docs' / 'rc0' / 'qf' / 'tools' if os.environ.get('C1_SCR')\n"
    "        else Path(__file__).resolve().parents[3] / 'rc0' / 'qf' / 'tools')\n"
    "if not (HERE / 'qual_lib.py').is_file():\n"
    "    raise SystemExit(f'c1_item12: QF helpers not found at {HERE}')\n")
rep("ROOT = W / 'item12-retry'", "ROOT = W / 'c1-item12'")
rep("'--j', '8', '--gpu', '0']", "'--j', '2', '--gpu', '0']   # C1: 2-CPU lane (QF used 8)")
rep("gpu=True, extra_env=env, witness=wit)", "gpu=True, extra_env={**env, 'OMP_NUM_THREADS': '2'}, witness=wit)")
rep("'--patch_x', '5', '--patch_y', '5', '--j', '8']\n    e = base_env(False)\n    e.update(env)\n",
    "'--patch_x', '5', '--patch_y', '5', '--j', '2']\n    e = base_env(False)\n    e.update(env)\n    e['OMP_NUM_THREADS'] = '2'   # C1: 2-CPU lane\n")
rep("""            want = RECORDED_RETRIED[(fam, g)]
            if A['frozen']['accounting'] and A['frozen']['accounting']['retried'] != want:
                case['problems'].append(f'frozen retried {A["frozen"]["accounting"]["retried"]} != #207 {want}')
""", """            # C1: the expected retried count is C1's own frozen-arm count; #207's record is kept as a legacy comparison only.
            want = (A['frozen']['accounting'] or {}).get('retried')
            case['legacy_recorded_207_retried'] = RECORDED_RETRIED[(fam, g)]
            case['legacy_c1_retried'] = want
            case['legacy_ref_1db_retried'] = (A['ref_1db']['accounting'] or {}).get('retried')
            if not want:
                case['problems'].append(f'frozen retried {want}: no retried patch, so the retry/fault controls were not exercised')
""")
rep("for name in ('frozen', 'ref_1db', 'count') + (('rec',) if g == 1 else ()):", "for name in ('frozen', 'count') + (('rec',) if g == 1 else ()):   # C1: ref_1db rc is legacy-only\n                if name == 'frozen' and A['ref_1db']['rc'] != 0:\n                    case['legacy_ref_1db_rc'] = A['ref_1db']['rc']")
rep("""                    if full or prod:
                        case['problems'].append(f'{a} vs {b}: full rc {full}, products rc {prod}')""",
    """                    if (full or prod) and a == 'ref_1db':
                        case['legacy_ref_1db_vs_frozen_differs'] = True    # expected: #254/#260/#270 change CUDA local alignment; attributed in T24
                    elif full or prod:
                        case['problems'].append(f'{a} vs {b}: full rc {full}, products rc {prod}')""")
rep("from qual_lib import *  # noqa: F401,F403\n", "from qual_lib import *  # noqa: F401,F403\nsys.path.insert(0, str(Path(__file__).resolve().parent))\nimport c1_lane; c1_lane.install()   # C1 v2: bench lock probed, not waited on (#198 policy)\nrun_case = c1_lane.run_case_nb   # C1 v2: nonblocking GPU3 lease, stop on foreign process, mandatory pre/post health under the lease\n")
Path(here / 'c1_item12.py').write_text(s)
Path(here / 'c1_item12.diff').write_text(''.join(difflib.unified_diff(orig.splitlines(True), s.splitlines(True), 'item12_retry.py', 'c1_item12.py')))
print('written', len(s))
