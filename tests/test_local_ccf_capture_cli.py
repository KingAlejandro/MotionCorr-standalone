# SPDX-License-Identifier: GPL-2.0-or-later
"""Pre-pixel refusal tests; no native movie producer."""
import argparse, os, subprocess, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--binary',required=True);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='ccf-cli-') as d:
 root=Path(d)/'capture'
 base=[a.binary,'--i',str(Path(d)/'absent.star'),'--o',str(Path(d)/'out'),'--use_own','--j','2','--patch_x','3','--patch_y','3','--group_frames','1','--bin_factor','1','--skip_defect','--first_frame_sum','1','--last_frame_sum','5','--experimental_coupled_peak','all']
 env=dict(os.environ,MC_DIAG_LOCAL_CCF_DIR=str(root),MC_EXPERIMENT_CCF_DC_ARM='both')
 for extra,needle in [(['--gpu','0'],'GPU refused'),(['--experimental_local_b2'],'unsupported scope'),(['--j','3'],'unsupported scope'),(['--group_frames','2'],'unsupported scope'),(['--max_iter','6'],'unsupported scope')]:
  cmd=base.copy()
  if extra[0] in cmd: cmd[cmd.index(extra[0])+1]=extra[1]
  else: cmd+=extra
  r=subprocess.run(cmd,env=env,capture_output=True,text=True)
  assert r.returncode!=0 and needle in r.stdout+r.stderr,(extra,r.returncode,r.stdout,r.stderr)
  assert not root.exists()
 print('PASS diagnostic CPU/scope guards before movie access')
