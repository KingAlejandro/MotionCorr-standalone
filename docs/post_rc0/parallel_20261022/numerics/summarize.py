#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarize retained eight-case reports and native convergence logs."""
import hashlib
import json
from pathlib import Path
import re
import sys

root=Path(sys.argv[1]).resolve()
rows=[]
for backend in ['cpu','cuda']:
    reports=json.loads((root/'validation'/('evaluation-'+backend+'.json')).read_text())
    runs={r['case']:r for r in json.loads((root/('cases-'+backend)/'runs.json').read_text())}
    for report in reports:
        name=report['case']
        log_path=root/('cases-'+backend)/name/(name+'.log')
        log=log_path.read_text()
        # Each explicit Patch line starts a different local trajectory. A
        # repeated Iteration 1 inside a block starts the existing native retry.
        blocks=re.split(r'(?m)^Patch \(',log)
        global_part=blocks[0].split('Global alignment:',1)[1]
        def classify(text):
            iterations=[dict(iteration=int(i),rmsd_px=float(v)) for i,v in
                re.findall(r'Iteration\s+(\d+): RMSD = ([+\-\deE.]+) px',text)]
            explicit=re.findall(r'completed; converged=(yes|no)',text)
            if explicit:
                status='CONVERGED' if explicit[-1]=='yes' else 'ITERATION_LIMIT'
                basis='explicit native CUDA verdict'
            elif iterations:
                final=iterations[-1]['rmsd_px']
                status='CONVERGED' if final<.5 else 'ITERATION_LIMIT' if final>.5 else 'ROUNDED_THRESHOLD_AMBIGUOUS'
                basis='printed RMSD versus unchanged 0.5 px threshold'
            else:
                status='NO_ITERATIONS_RECORDED';basis='no alignment log'
            return dict(status=status,basis=basis,iterations=iterations,
                        attempts=sum(x['iteration']==1 for x in iterations),explicit_cuda_verdicts=explicit)
        g=classify(global_part)
        patches=[classify(b) for b in blocks[1:]]
        # A polynomial fit and its STAR model version remain observable even
        # if the trajectory count is too small to construct a local model.
        star=root/('cases-'+backend)/name/(name+'.star')
        model=re.search(r'_rlnMotionModelVersion\s+(\d+)',star.read_text())
        rows.append(dict(backend=backend,case=name,native_exit=runs[name]['exit'],
            checker_exit=report['checker_exit'],checker_status=report['checker_status'],
            sampling_status=report.get('sampling_status'),field_gate=report['field_gate'],
            field_px=report['field_px'],field_angstrom=report['field_angstrom'],
            global_alignment=g,patch_alignment=patches,
            patch_converged=sum(p['status']=='CONVERGED' for p in patches),
            patch_total=len(patches),motion_model_version=int(model[1]) if model else None,
            local_fit_missing_warning='too few valid local trajectories' in
                (root/'validation'/('case-'+backend+'-'+name+'.log')).read_text(),
            native_log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest(),
            star_sha256=hashlib.sha256(star.read_bytes()).hexdigest()))
result=dict(source='d751ff28594902eca75d665ff116e662653481aa',
    schema='motion-diagnostics/2',native_arms=len(rows),
    native_process_exit_zero=sum(r['native_exit']==0 for r in rows),
    checker_status_counts={k:sum(r['checker_status']==k for r in rows)
        for k in sorted({r['checker_status'] for r in rows})},
    sampling_status_counts={k:sum(r['sampling_status']==k for r in rows)
        for k in sorted({r['sampling_status'] for r in rows})},
    global_status_counts={k:sum(r['global_alignment']['status']==k for r in rows)
        for k in sorted({r['global_alignment']['status'] for r in rows})},
    no_scientific_aggregate_pass=True,no_timing_claim=True,rows=rows)
(root/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
for r in rows:
    print(r['backend'],r['case'],r['checker_status'],r['sampling_status'],
          'rms_px='+format(r['field_px']['rms'],'.9g'),
          r['global_alignment']['status'],
          'patches='+str(r['patch_converged'])+'/'+str(r['patch_total']))
