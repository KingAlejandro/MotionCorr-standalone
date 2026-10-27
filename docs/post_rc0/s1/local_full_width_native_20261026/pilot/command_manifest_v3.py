"""Write COMMANDS_DRAFT_v3.json from ADMISSION_DRAFT_v3.json; never launches a process."""
from pathlib import Path
import json, sys
sys.dont_write_bytecode = True
p = Path(__file__).resolve().parent
adm = json.loads((p / 'ADMISSION_DRAFT_v3.json').read_text())
assert adm['status'].startswith('HELD_') and len(adm['rows']) == 8 and adm['version'] == 'v3'
out = []
for row in adm['rows']:
    case = row['case']; px, py = row['patch_grid']
    for arm in ['OFF', 'ON']:
        d = Path('/tmp/motioncorr-local-full-width-native-20261026/evidence') / case / arm
        argv = ['<PINNED_LINUX_BINARY>', '--i', case + '.star', '--o', str(d / 'output'), '--use_own', '--j', '2', '--patch_x', str(px),
                '--patch_y', str(py), '--group_frames', '1', '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW',
                '--first_frame_sum', '1', '--last_frame_sum', '5', '--skip_logfile', '--max_iter', '5', '--experimental_coupled_peak', 'all']
        if arm == 'ON': argv += ['--experimental_local_full_width_weight']
        out.append({'case': case, 'arm': arm, 'argv': argv, 'cwd': str(d / 'input'), 'input_files': [case + '.star', case + '.mrcs'],
                    'environment': {'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                                    'MC_EXPERIMENT_CCF_DC_ARM': 'both', 'MC_DIAG_MODEL_OUT': str(d / 'runtime.json'),
                                    'PYTHONDONTWRITEBYTECODE': '1'},
                    'environment_cleanup': ['remove inherited MC_DIAG_* and MC_EXPERIMENT_* before installing the listed values'],
                    'status': 'UNRUN_HELD',
                    'expected_local_weight_witness_lines': row['expected_local_weight_witness_lines'][arm]})
assert len(out) == 16
(p / 'COMMANDS_DRAFT_v3.json').write_text(json.dumps(out, indent=2) + '\n')
print('prepared16commands v3; no execution path exists in this helper')
