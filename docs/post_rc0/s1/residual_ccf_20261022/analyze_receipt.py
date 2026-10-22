#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reconcile first completed analysis, then verify reproducibility with an exit receipt."""
import datetime,hashlib,json,os,pathlib,subprocess,sys
r=pathlib.Path(sys.argv[1]);pid=int((r/'analysis.pid').read_text())
assert not (pathlib.Path('/proc')/str(pid)).exists(),'first analysis still live; no retry'
assert (r/'analysis.json').is_file() and not (r/'analysis.log').read_text()
a=json.loads((r/'analysis.json').read_text());assert a['controls']['status']=='PASS' and len(a['rows'])==300
(r/'analysis-first-reconciliation.json').write_text(json.dumps(dict(pid=pid,process_present=False,artifact_complete=True,log_empty=True,exit='UNOBSERVED',reason='initial detached analysis launcher omitted durable exit wrapper; native application receipts unaffected',utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
argv=['taskset','-c','10-13','/home/alex/.mc-venv/bin/python3',str(r/'replay.py'),str(r),str(r/'analysis-verified.json')]
with (r/'analysis-verification.log').open('w') as f:
 p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1'))
 (r/'analysis-verification.pid').write_text(str(p.pid)+'\n');rc=p.wait()
(r/'analysis-verification.exit').write_text(str(rc)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(argv=argv,exit=rc,pid=p.pid,affinity=sorted(os.sched_getaffinity(0)),original_sha256=sha(r/'analysis.json'),verified_sha256=sha(r/'analysis-verified.json'))
result['identical']=result['original_sha256']==result['verified_sha256']
(r/'analysis-verification.json').write_text(json.dumps(result,indent=2)+'\n');assert rc==0 and result['identical'];print('analysis replay exit 0; exact JSON reproduction PASS')
