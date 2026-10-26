#!/usr/bin/env python3
"""Native runs of the rendered W5 phase-ramp movies. usage: run_ncontrols.py ROOT BINARY CPUS
ROOT/movies holds the rendered movies; outputs go to ROOT/runs/<arm>-<stop>-<weight>/<movie>/.
Same command line as the K267 driver (c1_run_v2_cases.py) except --patch_x/--patch_y 1 (global only) and --last_frame_sum N.
Arms: a (flags off), DCg (MC_EXPERIMENT_CCF_DC_ARM=global), H2g (--experimental_coupled_peak global), DCg+H2g.
Stops: prod (default 5 / 0.5 px) and long (--max_iter 50 --experimental_align_tolerance 1e-9). Weights: prod, iso (--experimental_isotropic_weight).
The hook binary is required (MC_EXPERIMENT_CCF_DC_ARM is set on every run, 'none' for non-DC arms); MC_DIAG_MODEL_OUT captures the runtime field.
"""
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path(sys.argv[1]).resolve(); binary = pathlib.Path(sys.argv[2]).resolve(); cpus = sys.argv[3]
movies = root/'movies'; runs = root/'runs'; runs.mkdir(exist_ok=False)
ARMS = {'a': ('none', []), 'DCg': ('global', []), 'H2g': ('none', ['--experimental_coupled_peak', 'global']),
        'DCg+H2g': ('global', ['--experimental_coupled_peak', 'global'])}
STOPS = {'prod': [], 'long': ['--max_iter', '50', '--experimental_align_tolerance', '1e-9']}
WEIGHTS = {'prod': [], 'iso': ['--experimental_isotropic_weight']}
rows = []
for arm, (dc, aextra) in ARMS.items():
    for stop, sextra in STOPS.items():
        for wt, wextra in WEIGHTS.items():
            tag = f'{arm}-{stop}-{wt}'; out = runs/tag; out.mkdir()
            for iv in (0, 1):
                for N in (5, 9, 13, 20):
                    name = f'vel{iv}_N{N}'
                    cmd = ['taskset', '-c', cpus, str(binary), '--i', name+'.star', '--o', str(out/name), '--use_own', '--j', '2', '--patch_x', '1', '--patch_y', '1',
                           '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW', '--first_frame_sum', '1', '--last_frame_sum', str(N), '--skip_logfile'] + aextra + sextra + wextra
                    env = os.environ.copy(); env['OMP_NUM_THREADS'] = '2'
                    for k in list(env):
                        if k.startswith('MC_DIAG_') or k.startswith('MC_EXPERIMENT_'): del env[k]
                    env['MC_EXPERIMENT_CCF_DC_ARM'] = dc; env['MC_DIAG_MODEL_OUT'] = str(out/(name+'.runtime.json'))
                    t = time.time()
                    with (out/(name+'.stdout')).open('w') as f: rc = subprocess.run(cmd, cwd=movies, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
                    rows.append(dict(tag=tag, movie=name, arm=arm, stop=stop, weight=wt, dc_arm=dc, argv=cmd, exit=rc, seconds=time.time()-t))
(runs/'runs.json').write_text(json.dumps(rows, indent=1)+'\n')
print('runs', len(rows), 'nonzero exits', sum(r['exit'] != 0 for r in rows))
