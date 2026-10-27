"""Writes the frozen CAPTURE_RUN_PINS.json (staged as RUN_PINS.json at release) and COMMANDS_CAPTURE.json from the read-only cpu64 records, the sealed
native pilot baseline receipt and the repository copies of the prep files. Reads and hashes files only; launches nothing."""
import hashlib, json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; PREP = HERE.parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rec = (PREP / 'receipts/records_readonly_1.txt').read_text()
SRC = 'f473fbc9c380c7bb8cc1533f19461fbf70dde485'; ROOT = '/tmp/motioncorr-lfw-capture-20261027'
bundle = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/runs/noisy/ON')
run = json.loads((bundle / 'RUN.json').read_text())
assert sha(bundle / 'RUN.json') == re.search(r'([0-9a-f]{64})  \./RUN\.json', rec).group(1), 'durable RUN.json differs from the cpu64 baseline RUN.json'
for rel, h in run['publication'].items():
    assert re.search(h['sha256'] + r'  \./output/' + re.escape(rel) + '\n', rec), ('baseline product hash differs on cpu64', rel)
def cpu64_hash(rel): return re.search(r'([0-9a-f]{64})  \./' + re.escape(rel) + r'\n', rec).group(1)
assert cpu64_hash('runtime.json') == run['runtime']['sha256'] and cpu64_hash('stdout.log') == run['stdout']['sha256']
libs = {m.group(2): m.group(3) for m in re.finditer(r'^(/lib/\S+) -> (\S+)  ([0-9a-f]{64})$', rec, re.M)}
binary = re.search(r'([0-9a-f]{64})  /tmp/motioncorr-lfw-capture-20261027/build/motioncorr\n', rec).group(1)
loader = re.search(r'ld-linux-x86-64.so.2\n([0-9a-f]{64})\n', rec).group(1)
numpy_init = re.search(r'numpy/__init__.py ([0-9a-f]{64})', rec).group(1)
prep = {n: sha(p) for n, p in {'run_capture_fw.py': HERE / 'run_capture_fw.py', 'capture_witness.py': HERE / 'capture_witness.py', 'weight_oracle.py': PREP / 'scripts/weight_oracle.py', 'guard.py': PREP / 'scripts/guard.py',
        'lane.py': PREP / 'scripts/lane.py', 'verify_source.py': PREP / 'scripts/verify_source.py'}.items()}
locks = ['b2-cpu32-47', 'cpu64-bench', 'damping-cpu32-47', 'dc-oracle-cpu-32-39', 'dc-oracle-cpu-40-47', 'dc-tierc-cpu32-47', 'w6-cpu40-47', 'w7-cpu40-47']
pins = {
    'schema': 'lfw-capture-run-pins/1', 'release_id': 'lfw-capture-v1', 'status': 'FROZEN_HELD_NOT_RELEASED',
    'source_commit': SRC, 'source_tree': 'f23ed001a7785ad2944f27dcce6bc321b4bcc4f9', 'blob_list_sha256': '3d885a21bdaac53ca61e623e7f036f4770f23a7f151ba887b51f059a64147c41',
    'git_archive_tar_sha256_no_prefix': '6b4c72a44f5ff6539c8d045f6fa0d14547ea03fe66da33c4dd5572f9162f3f85',
    'independent_source_review': {'verdict': 'CLEAR', 'source_commit': SRC, 'report_sha256': 'bdea0d803b50b25ed44d12fea34f856c17390098b46f28a14c24f36b9cc00f00',
                                  'report_path': '/tmp/mc-fullwidth-ccf-capture-opus-review-20261027-r1/REPORT.md', 'durable_copy': '~/Documents/MotionCorr-evidence/20261026/Native-fullwidth-ccf-capture-opus-source-review-r1/original/REPORT.md'},
    'binary_path': ROOT + '/build/motioncorr', 'binary_sha256': binary, 'libs': libs, 'loader_sha256': loader,
    'build': {'cmake': '/home/ubuntu/.mc-venv/bin/cmake 4.4.3', 'compiler': 'g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0', 'config': 'Release -O3 -DNDEBUG, MC_EXPERIMENT_CCF_DC=ON, CUDA=OFF, BUILD_TESTING=ON, -j2', 'cmake_cache_sha256': re.search(r'([0-9a-f]{64})  /tmp/motioncorr-lfw-capture-20261027/build/CMakeCache.txt', rec).group(1)},
    'interpreter': {'path': '/home/ubuntu/.mc-venv/bin/python3', 'version': '3.12.3', 'numpy': '2.5.3', 'numpy_init_sha256': numpy_init},
    'comparator': {'path': ROOT + '/source/docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py', 'sha256': '53449d2da682305c8c11e3ed3efb91103530196e481ac075b00f90e3d5ea0f47'},
    'baseline': {'dir': run['run_dir'], 'run_json_sha256': sha(bundle / 'RUN.json'), 'argv': run['argv'], 'environment': run['environment'], 'products': {k: v['sha256'] for k, v in run['publication'].items()},
                 'other_files': {'runtime.json': run['runtime']['sha256'], 'stdout.log': run['stdout']['sha256']}, 'binary_sha256_of_baseline_producer': run['binary_sha256']},
    'input_files': {'noisy.mrcs': cpu64_hash('input/noisy.mrcs'), 'noisy.star': cpu64_hash('input/noisy.star')},
    'prep_files': prep, 'lane_locks': ['/tmp/motioncorr-' + n + '.lock' for n in locks],
    'scratch_cap_roots': ['/tmp/motioncorr-b2-native-20261026', '/tmp/motioncorr-b2-factorial-20261026', '/tmp/motioncorr-lfw-v5-20261026', '/tmp/motioncorr-local-ccf-20261026', '/tmp/mc-w8-common-mean-screen-20261026', ROOT],
    'jobs': ['OFF', 'ON'], 'resources': {'cpus': '32-47', 'native_threads': 2, 'OMP_NUM_THREADS': 2, 'BLAS_threads': 1, 'build_jobs': 2, 'memory_floor_bytes': 4 * 1024 ** 3, 'scratch_cap_bytes': 25 * 1024 ** 3},
    'capture_on_expectations': {'schema': 'local-ccf-capture/2', 'capture_mode': 'local_full_width_pair', 'selected_centres': [[104, 15], [62, 79]], 'weight_x_norm': 42, 'weight_map_oracle': 'weight_oracle.weight_map(42), exact float32 equality, also required to differ from the x_norm 22 map', 'log_witness_lines': 9,
                                'log_witness': ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22', 'iterations': 'actually executed (1..5), 5 frames per iteration', 'static_note': 'CLI tests cannot catch a wrong runner mode wiring; these four witnesses do'},
}
(HERE / 'CAPTURE_RUN_PINS.json').write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
def command(label):
    cmd = list(run['argv']); cmd[0] = pins['binary_path']; cmd[cmd.index('--o') + 1] = f'{ROOT}/evidence/runs/{label}/output'
    env = dict(run['environment']); env['MC_DIAG_MODEL_OUT'] = f'{ROOT}/evidence/runs/{label}/runtime.json'; env['PATH'] = '/usr/bin:/bin'
    if label == 'ON': env['MC_DIAG_LOCAL_CCF_DIR'] = f'{ROOT}/evidence/runs/ON/capture'
    return {'label': label, 'argv': cmd, 'cwd': ROOT + '/native-input', 'environment': env, 'wrapped_by': ['/usr/bin/time', '-v']}
(HERE / 'COMMANDS_CAPTURE.json').write_text(json.dumps({'schema': 'lfw-capture-commands/1', 'jobs': [command('OFF'), command('ON')], 'only_difference_between_jobs': 'MC_DIAG_LOCAL_CCF_DIR and the run directory paths'}, indent=2, sort_keys=True) + '\n')
print('pins', sha(HERE / 'CAPTURE_RUN_PINS.json')[:16], 'commands', sha(HERE / 'COMMANDS_CAPTURE.json')[:16], 'libs', len(libs))
