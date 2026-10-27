"""Write ADMISSION_V5.json and COMMANDS_V5.json from the frozen v3 files and the cpu64 build receipts, then set the two anchors in
pair_decision_v5.py. Launches nothing. The release module, driver and tests are bound out of band, not pinned here."""
from pathlib import Path
import hashlib, json, re, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PILOT = HERE.parent
NS = '/tmp/motioncorr-lfw-v5-20261026'
REC = HERE / 'receipts_cpu64' / 'receipts'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
canon = lambda o: json.dumps(o, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
v3 = json.loads((PILOT / 'ADMISSION_DRAFT_v3.json').read_text())
cmds = json.loads((PILOT / 'COMMANDS_DRAFT_v3.json').read_text())
br = json.loads((REC / 'build_receipt.json').read_text())
venue = (HERE / 'receipts_cpu64' / 'venue_and_scratch.txt').read_text()
prior = sum(int(l.split()[2]) for l in venue.splitlines() if l.startswith('SIZE '))
adm = dict(v3)
adm.update({
    'schema': 'local-full-width-admission-v5', 'version': 'v5', 'status': 'FROZEN_PENDING_OPUS_DELTA_REVIEW',
    'supersedes': {'file': 'ADMISSION_DRAFT_v3.json', 'sha256': sha(PILOT / 'ADMISSION_DRAFT_v3.json')},
    'candidate_source_commit': br['source_archive']['commit'],
    'candidate_branch_head_with_unchanged_src': None,
    'candidate_binary': br['binary'],
    'source_archive': dict(br['source_archive'], git_archive_command='git archive --format=tar d1c498b87123b324c027c2d8957736b9954e6326',
                           src_tests_cmake_sha256_list={'path': NS + '/receipts/source_src_tests_cmake.sha256', 'sha256': sha(REC / 'source_src_tests_cmake.sha256')},
                           note='src = 634e4b48, CMake = 5bcfa987; identical to the reviewed worktree (391 files compared)'),
    'build_receipt': {'path': NS + '/receipts/build_receipt.json', 'sha256': sha(REC / 'build_receipt.json')},
    'compiler_and_config': {'compiler': br['compiler'], 'cmake': br['cmake'], 'cmake_args': br['cmake_args'], 'jobs': br['jobs'], 'env': br['env']},
    'shared_libraries': br['shared_libraries'],
    'venue_identity': {'ssh_alias': 'cpu64', 'text': venue},
    'fresh_venue_resource_admission': {
        'cpus': '32-47', 'max_foreign_busy_cores': 1.5, 'min_available_mem_mb': 8192, 'campaign_root': NS,
        'prior_scratch_bytes': prior, 'scratch_cap_bytes': 25 * 1024 ** 3, 'native_threads': 2, 'omp_blas_caps': '<=2',
        'lane_sha256': br['lane_sha256'], 'lane_command': 'python3 lane.py <driver command>',
        'receipts_sha256': {n: sha(REC / n) for n in sorted(p.name for p in REC.iterdir()) if n.startswith(('occupancy', 'configure', 'build', 'ctest', 'lane'))},
        'note': 'a snapshot from the build step; not a lease entitlement: the driver re-runs the guard before every launch'},
    'independent_source_clearance': {
        'report': '~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-source-review-r1/REPORT.md',
        'sha256': 'ONFILE', 'verdict': 'no BLOCK, no MATERIAL; conditional, source-only; reviewed commit 634e4b48'},
    'evidence_root': NS + '/evidence',
    'baseline_root': '/home/ubuntu/motioncorr-evidence/native-b2-upstream-factorial-20261026/task/evidence/runs',
    'fixture_dir': '/tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures',
    'tool_roots': {'consumer_source': '/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6', 'repo': NS + '/source', 'pilot': NS + '/pilot'},
    'native_started': False,
})
adm['independent_source_clearance']['sha256'] = hashlib.sha256(Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-source-review-r1/REPORT.md').read_bytes()).hexdigest()
adm['staged_input_deviation'] = v3['staged_input_deviation']
# frozen resolved command rows: real binary path, evidence root, environment
sys.path.insert(0, str(PILOT))
import score_fields_v3 as V3
resolved = {}
for r in cmds:
    exp = V3.resolve_expected_row(cmds, adm, r['case'], r['arm'], adm['evidence_root'], adm['candidate_binary']['path'], adm['candidate_binary']['sha256'])
    resolved['%s/%s' % (r['case'], r['arm'])] = hashlib.sha256(canon({k: exp[k] for k in ('argv', 'cwd', 'environment', 'input_files')})).hexdigest()
adm['resolved_commands_sha256'] = resolved
(HERE / 'ADMISSION_V5.json').write_text(json.dumps(adm, indent=2, allow_nan=False) + '\n')
(HERE / 'COMMANDS_V5.json').write_bytes((PILOT / 'COMMANDS_DRAFT_v3.json').read_bytes())
mod = (HERE / 'pair_decision_v5.py').read_text()
mod = re.sub(r"ADMISSION_V5_SHA256 = '[^']*'", "ADMISSION_V5_SHA256 = '%s'" % sha(HERE / 'ADMISSION_V5.json'), mod)
mod = re.sub(r"COMMANDS_V5_SHA256 = '[^']*'", "COMMANDS_V5_SHA256 = '%s'" % sha(HERE / 'COMMANDS_V5.json'), mod)
(HERE / 'pair_decision_v5.py').write_text(mod)
print('admission', sha(HERE / 'ADMISSION_V5.json'), 'commands', sha(HERE / 'COMMANDS_V5.json'), 'prior_scratch_bytes', prior)
