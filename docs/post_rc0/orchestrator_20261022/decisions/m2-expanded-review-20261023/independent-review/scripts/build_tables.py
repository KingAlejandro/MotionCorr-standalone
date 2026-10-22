#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Assemble COMPONENT_TABLE.csv/.md and DOCS_REFS_TABLE.md from the retained JSON outputs (no Git access)."""
import csv, json, os, sys
OUT = sys.argv[1]
J = lambda n: json.load(open(os.path.join(OUT, 'out', n)))
arch = {a['oid']: a for a in J('archives_and_refs.json')['archives']}
rec = {r['oid']: r for r in J('recorded_digests.json')}
def A(prefix):
    o = [k for k in arch if k.startswith(prefix)][0]; a = arch[o]
    return o, a, rec[o]
def fmt(prefix):
    o, a, r = A(prefix)
    t = a.get('tar') or {}
    mem = f"{t['members']} members" if t.get('is_tar') else f"gzip->{a['gzip']['decompressed_bytes']}B"
    rd = 'digest recorded: ' + (r['full_digest_recorded_in'][0].replace('docs/', '') if r['full_digest_recorded'] else 'NOT recorded in repo')
    return f"{o[:8]} / {a['bytes']:,} B / sha256 {a['sha256'][:12]} / {mem} / {rd}"

rows = []
def row(comp, digest, where, dep, req, evid):
    rows.append(dict(component=comp, digest_size=digest, tip_or_history=where, dependency_classification=dep,
                     retention_requirement=req, retrieval_evidence_or_gap=evid))
LOC = 'local: commit present, blob re-hashed OK; remote not checked'
row('docs/post_rc0/s1/km_truth tree (48 files)', 'tree 1a0118ec / 40,290,016 B (identical tree oid at 1b29b7f9, e77, bbf)',
    'tip of #269 (1b29b7f9), C1 e77 and bbf; absent from main; 15 history-only blob versions (1,966,508 B) also reachable',
    'EVIDENCE + docs-hosted tools. No src/tests/tools/CMake/CI read (only docstring test-data/generate_realistic_motion.py:5). Exception: integration_20261022/verify_composition.py (manual, unregistered)',
    'Preserve tree as committed or a verified retrieval path; contains code (analyze_live.py, build_report.py, pack_evidence.py ...) and RESULT.json file list',
    'Tree oid equality verified locally (git rev-parse). ' + LOC)
row('km_truth/raw.tar.gz', fmt('bc962a97'), 'tip e77/bbf/#269/#273; introduced by commit 678b0453 (one blob, no other versions)',
    'BULKY RAW EVIDENCE ARCHIVE. 9,198 regular files under raw/ (153,433,730 B uncompressed): json 3597, star 1928, log 1832, lst 911, txt 904, py 12; no image/movie members, no links, no exec bits. Read by NO test, CMake, CI or docs script (pack_evidence.py only writes/verifies it at creation). Names equal raw.sha256 (9,198 entries). Holds 2 scripts that exist nowhere else in the tree (generate_campaign.py, transfer_direct_zstd.py) and 3 older script versions (digest-level comparison from raw.sha256)',
    'Evidence record; not a test input. Retention = decision for maintainer. If left off main, keep a verified pinned retrieval (blob bc962a97 / sha256 4b0afb90... / branch or release asset)',
    'Equal to selected #269: same blob oid at 1b29b7f9 (and tree oid). Recorded digest in ARTIFACTS.sha256:35 == recomputed. Member-level digests NOT recomputed (headers only); only the recorded raw.sha256 was name-compared. ' + LOC)
row('km_truth/native_v2_raw.tar.gz', fmt('f058c937'), 'tip e77/bbf/#269/#273',
    'EXECUTABLE FIXTURE DEPENDENCY (docs-internal): verify_composition.py:98-107 opens it with tarfile, checks every member against native_v2_raw_index.json, then replays STARs. Manual script, not CI/ctest',
    'Must stay co-located with native_v2_raw_index.json and verify_composition.py (path ROOT=parents[5])', 'Digest recorded ARTIFACTS.sha256:25 and RESULT.json:87 == recomputed. ' + LOC)
row('km_truth/SUMMARY.json.gz', fmt('dd5c038d'), 'tip e77/bbf/#269/#273',
    'REPORT-GENERATOR INPUT (docs-internal): build_report.py:8, export_tables.py:6 gzip.decompress it. Not CI/ctest', 'Keep with generators', 'Digest recorded ARTIFACTS.sha256:5 == recomputed. ' + LOC)
row('km_truth non-archive bulk (raw.sha256 1,038,553; rendered-products.sha256 635,358; time_errors.csv 1,311,583; ...)', 'in the 40,290,016 B tree; history-only time_errors.csv version 1,315,184 B',
    'tip + history', 'EVIDENCE tables/manifests', 'Preserve with tree', 'Same tree oid as #269.')
row('rc0/issue226 d2/raw-logs.tgz', fmt('9420e5f2'), 'tip e77/bbf/#274', 'RAW EVIDENCE ARCHIVE; no reader; referenced from d2/README.md:87',
    'Evidence; maintainer decision', 'GAP: no archive-level sha256 recorded anywhere in docs (full or 16-hex); this review supplies the first record. ' + LOC)
row('rc0/issue226 d3/raw-logs.tgz', fmt('9ee8eb75'), 'tip e77/bbf/#274', 'RAW EVIDENCE ARCHIVE; no reader; referenced from d3/README.md:71',
    'Evidence; maintainer decision', 'GAP: no archive-level sha256 recorded in docs. ' + LOC)
row('rc0/issue226 d2/native_retry_20261022/raw-logs.tgz', fmt('ce874507'), 'tip e77/bbf/#274',
    'EXECUTABLE FIXTURE DEPENDENCY (docs-internal): support/verify.py:7-14 reads it by path (D=parents[1]) with archive.sha256 and raw-index.json; 1 exec-bit member (not executed)',
    'Keep with archive.sha256, raw-index.json, support/verify.py', 'archive.sha256 == recomputed. ' + LOC)
row('rc0/issue226 d3/classifier_cleanup_20261022/receipts.tgz', fmt('ba82712b'), 'tip e77/bbf/#274', 'RAW RECEIPTS; no reader; README.md:18,109', 'Evidence', 'receipts.sha256 == recomputed. ' + LOC)
row('post_rc0/issue253/raw.tar.gz', fmt('ebd0d216'), 'tip e77/bbf/#273', 'RAW EVIDENCE; no reader; README.md:188', 'Evidence', 'archive-verification.json:4 == recomputed. ' + LOC)
row('post_rc0/issue253/review-20261021/raw.tar.gz', fmt('b862b62e'), 'tip e77/bbf/#273', 'RAW EVIDENCE written by collect-evidence.sh:21-22; no reader; includes 6 .cu, 5 .sh member copies', 'Evidence', 'README.md:206 / raw-index.json:2 == recomputed. ' + LOC)
row('post_rc0/issue257/raw.tar.gz', fmt('e7962d0f'), 'tip e77/bbf/#273', 'RAW EVIDENCE; no reader', 'Evidence', 'archive-verification.json:2 == recomputed. ' + LOC)
row('issue215/evidence/raw-evidence.tar.gz', fmt('a3d0c24d'), 'tip e77/bbf', 'RAW EVIDENCE; linked from issue215/README.md:111. Verifiers (native_20261022/verify_evidence.py:14, verify_attempt04.py:16) read /tmp download copies, NOT this committed path',
    'Evidence', 'GAP: no archive-level sha256 recorded in docs; README says round-trip checked. ' + LOC)
row('c1-20261022 evidence archives (bbf only): source-files.sha256.gz 348,265; c1-evidence-e77a51a2.tgz 107,712; c1-evidence-iteration3.tgz 104,742; cpu1d startup-controls-attempt1.tgz 24,514; remote-startup-snapshot.tgz 11,692',
    '5 blobs / 596,925 B (not in e77)', 'tip bbf only (parent-published C1 head)',
    'RAW RECEIPTS; no reader. startup-controls-attempt1.tgz has 1 symlink member to an absolute remote path (dangling; listed only)', 'Evidence (C1 qualification record)',
    'All five digests recorded in sidecars == recomputed. ' + LOC)
row('#273 unique tree (36 files, 3 archives)', '2,748,458 B: native-receipts.tar.gz 1,390,257 (536 members, 16 tiny .mrc); host-receipts 12,226; composition.patch.gz 24,731',
    'tip of #273 (805d9de2) only; NOT in C1; history vs C1: 41 blobs/3,025,652 B; vs main: 298/48,447,241',
    'EVIDENCE + remote drivers (build/run/collect/check_host/summarize .py). collect_remote.py writes native-receipts; no committed reader found',
    'Question M2 asks about: stay on branch vs land', 'Digests recorded in archive-verification.json / composition-receipt.json == recomputed. Local refs: cuda-numeric-fixes-integration, c1/pr273, origin/cuda-numeric-fixes-integration at 805d9de2. ' + LOC)
row('#274 unique tree (32 files, 1 archive)', '1,328,117 B: raw-logs.tgz 695,240 (647 members)', 'tip of #274 (a1036901) only; NOT in C1; history vs C1: 38/1,825,744 B; vs main 132/7,026,217',
    'EXECUTABLE FIXTURE DEPENDENCY (docs-internal): support/verify.py:7-10 reads raw-logs.tgz + archive.sha256', 'Question M2 asks about', 'archive.sha256:1 == recomputed. Local refs: integration/226-d2-d3-20261022, c1/pr274, origin/... at a1036901. ' + LOC)
row('docs/post_rc0/s1/synth_combined (37 files)', 'tree 4ce7b7c7 / 376,409 B (eval_v2.py 3,202 B)', 'tip e77/bbf; ABSENT FROM MAIN',
    'ACTIVE CI DEPENDENCY: tools/test_combined_eval.py:16 runs docs/.../eval_v2.py via subprocess (ci.yml:105). Missing file => CI step fails', 'MUST remain reproducible with C1 tests (at minimum eval_v2.py)',
    'Present at e77 and bbf (same tree oid). Not run here.')
row('docs/issue213/evidence (92 files)', 'tree bbf98b2c / 322,972 B (4 files read: control-{cuda,nvcomp}-final/{single,multi}.txt 3,028/6,708/3,123/6,831 B)', 'tip e77/bbf; ABSENT FROM MAIN (new in C1)',
    'ACTIVE ctest DEPENDENCY: tests/test_sticky_cuda_process_lifecycle.py:245 (StickyCudaProcessLifecycle, UNIX, CPU build, run by CI ctest) reads them as retained records; missing => FileNotFoundError',
    'MUST remain reproducible with C1 tests', 'Present at e77 and bbf. Not run here.')
row('docs hosts read by tests/tools that C1 did NOT change: issue85_laneC (2 files, 26,454 B), rc0/qf/tools (38 files, 376,319 B), issue69/evidence/ownership-20260929 (1 file), profiling_20261001/data24 (3 files, 5,095,476 B), cuda_24_movies_gate2_rerun.json, spa_24_movies_manifest.json',
    'tree oids identical main/e77/bbf', 'on main already', 'ACTIVE: OutputTreeComparator (CI ctest), CUDA hardware ctests (3), opt-in CudaU16FailurePaths, manual tools', 'Already on main; unaffected by any C1 docs choice unless a docs-compaction touches them', 'Same oids at main/e77/bbf.')
row('Reachable history main..e77 (pinned by PR281)', '102 commits (24 merges); 947 blobs 60,411,705 B (docs-name-hint 53,455,930); 730/49,466,987 in tip, 217/10,944,718 history-only; local packed 40,633,122 B (machine-specific)', 'history',
    'History-only blobs are earlier versions of repeatedly edited files (e.g. CMakeLists.txt 32 versions 2.28 MB, RC0_ACCEPTANCE_REPORT.md 26, SUPPORT.md 22, src/*) plus 15 km_truth versions. verify_composition.py needs commits 677abcfa/66952415/88b34ae0 (ancestors of C1, not of main)',
    'Normal merge keeps all reachable; squash/extraction would drop these SHAs from main ancestry (UNAPPROVED; no savings promised)', 'Re-run of PR281 recipe reproduces committed JSON byte-for-byte (tree) and results (history). ' + LOC)
row('Reachable history main..bbf (current published C1)', '118 commits (24 merges); 1,099 blobs 61,752,600 B (docs-name-hint 54,796,825); 869/50,703,396 in tip, 230/11,049,204 history-only; local packed 41,510,257 B (machine-specific)', 'history',
    'Delta vs e77: +16 commits, +152 blobs, +1,340,895 B; production tree unchanged (0 non-docs paths differ e77..bbf)', 'as above', 'New values from this review; NOT PR281-pinned values. ' + LOC)
fields = ['component', 'digest_size', 'tip_or_history', 'dependency_classification', 'retention_requirement', 'retrieval_evidence_or_gap']
with open(os.path.join(OUT, 'COMPONENT_TABLE.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
with open(os.path.join(OUT, 'COMPONENT_TABLE.md'), 'w') as f:
    f.write('| ' + ' | '.join(fields) + ' |\n|' + '---|' * len(fields) + '\n')
    for r in rows:
        f.write('| ' + ' | '.join(str(r[k]).replace('|', '/').replace('\n', ' ') for k in fields) + ' |\n')
d = J('docs_refs_classified.json')
with open(os.path.join(OUT, 'DOCS_REFS_TABLE.md'), 'w') as f:
    f.write(f"# docs reference classification at e77a51a2 (identical scoped tree at bbf24607)\n\nSummary: {json.dumps(d['summary']['by_class_lines'])}\n\n")
    f.write('| file:line | class | referenced path(s) [main/e77/bbf] | scenario |\n|---|---|---|---|\n')
    for r in d['rows']:
        tg = '; '.join(f"`{t['path']}` [{'Y' if t['main'] else 'N'}/{'Y' if t['e77'] else 'N'}/{'Y' if t['bbf'] else 'N'}]" for t in r['targets']) or '-'
        f.write(f"| {r['file']}:{r['line']} | {r['class']} | {tg} | {r['scenario'].replace('|','/')} |\n")
print(len(rows), 'component rows')
