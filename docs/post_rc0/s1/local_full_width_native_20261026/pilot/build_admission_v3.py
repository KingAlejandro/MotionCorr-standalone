"""Write ADMISSION_DRAFT_v3.json from the unchanged ADMISSION_DRAFT.json. Launches nothing; run after the tools are final."""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/experiment-local-full-width-weight-20261026')
CONSUMER = Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
v1 = json.loads((HERE / 'ADMISSION_DRAFT.json').read_text())
tools = []
for root, base, names in [
    ('consumer_source', CONSUMER, ['tools/check_motion_diagnostics.py', 'tools/check_realistic_motion.py', 'tools/motion_field.py',
                                   'test-data/generate_motion_diagnostics.py', 'test-data/generate_realistic_motion.py',
                                   'test-data/generate_known_motion_fixture.py']),
    ('repo', REPO, ['docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py',
                    'docs/post_rc0/s1/native_b2_20261026/scripts/lane.py',
                    'docs/post_rc0/s1/native_b2_upstream_factorial_20261026/scripts/factorial_common.py']),
    ('pilot', HERE, ['score_fields_v2.py', 'score_fields_v3.py', 'tests/test_score_fields_v3.py', 'build_admission_v3.py',
                     'command_manifest_v3.py', 'tests/mutation_controls_v3.py'])]:
    for n in names:
        tools.append({'root': root, 'path': n, 'sha256': sha(base / n)})
assert any(t['path'].endswith('compare_products.py') and t['sha256'] == '53449d2da682305c8c11e3ed3efb91103530196e481ac075b00f90e3d5ea0f47' for t in tools)
v3 = dict(v1)
v3.update({
    'schema': 'local-full-width-admission-v3',
    'version': 'v3',
    'status': 'HELD_SOURCE_REVIEW_AND_VENUE_INPUTS_PENDING',
    'supersedes': {'file': 'ADMISSION_DRAFT.json', 'sha256': sha(HERE / 'ADMISSION_DRAFT.json')},
    'manifest_sha256': '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc',
    'fixed_roi_y0y1x0x1': [12, 84, 12, 116],
    'tools': tools,
    'scorer': {'entry': 'score_fields_v3.admit_producer / score_admitted', 'plan': 'SCORER_V3_PLAN.md',
               'numerical_operators': 'score_fields_v2.py unchanged (pinned)'},
    'retained_baseline': {'production_commit': '326f03a073aec0d26c9cd585ce4f701d1c808245',
                          'binary_sha256': '531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb'},
    'candidate_source_commit': v1['candidate_source_commit'],
    'candidate_branch_head_with_unchanged_src': '215c37b0743dd63a793650e8f0cfda4a2778ace9',
    'staged_input_deviation': 'cwd holds exactly <case>.star and <case>.mrcs; retained producers used the 33-file fixture directory',
    'candidate_binary': None, 'source_archive': None, 'compiler_and_config': None, 'shared_libraries': None,
    'venue_identity': None, 'fresh_venue_resource_admission': None, 'independent_source_clearance': None,
    'native_started': False,
})
for row in v3['rows']:
    row['expected_output_names'] = sorted(k[len('output/'):] for k in row['baseline_files'] if k.startswith('output/'))
    row['expected_local_weight_witness_lines'] = {'OFF': 0, 'ON': 9 if row['patch_grid'] == [3, 3] else 0}
(HERE / 'ADMISSION_DRAFT_v3.json').write_text(json.dumps(v3, indent=2, allow_nan=False) + '\n')
print('wrote ADMISSION_DRAFT_v3.json; tools pinned:', len(tools))
