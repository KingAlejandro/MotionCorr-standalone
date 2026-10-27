#!/usr/bin/env python3
"""Read-only regrade of one c1_tutorial24.py `dataset` arm whose products comparison failed only because merged/ carries the producer's worker archive.

Why: tools/multi_gpu/merge_workers.py stages every worker's fixed-name aggregates under merged/_workers/w<k>/ (and writes _workers/merge.log) as provenance.
compare_output_trees.validate_tree rglob()s *.star/*.mrc over the whole root, so the archived worker joint STAR makes "STAR inventory differs" before any
product is compared. This helper separates the two populations instead of ignoring a prefix:

  1. archive: merged/_workers/** must equal EXACTLY the set the producer derives from the retained workers/w<k>/ trees (every worker file that is not a
     movie product, each also a merge_workers.is_aggregate name) plus _workers/merge.log; no symlinks; only corrected_micrographs.star may be a STAR, no MRC;
     every archived file is byte-equal to its original worker file, and corrected_micrographs.star also equals the launcher's exit digest;
     aggregate.json per_worker_aggregates_preserved must list the same files.
  2. products: only after (1) passes, the UNMODIFIED compare_output_trees.compare_trees(compare_auxiliary=False) runs on merged/ against the standalone tree
     with the already-verified _workers/ subtree hidden from that one root's rglob; its report goes through the unmodified c1_tutorial24.classify.
     Any other extra/missing STAR or MRC, wrong path, mode/header/extension/payload difference is still found by the comparator itself.

Nothing under the dataset arm is written. The report goes to a NEW --out-dir. The historical DATASET.json (FAIL) is bound by hash and left in place.
Needs the c1_env.sh variables (C1_SCR, C1_TUTORIAL, C1_FROZEN_RC0, QF_*) like c1_tutorial24.py, and numpy (the comparator's).

usage: c1_ds_archive_regrade.py DS_ARM_DIR --out-dir NEW_DIR      exit 0 PASS, 1 FAIL/DIFFERENT, 2 INVALID
DS_ARM_DIR is $T24/<arm>-ds-<cfg>, spelled as c1_tutorial24.py spelled it and NOT resolved: the comparator replaces the lexical and the resolved root in
STAR text, and a symlinked prefix must keep its lexical spelling (run_dataset.py prints its own resolved --out, c1_tutorial24 passes the lexical one).
"""
import argparse, contextlib, hashlib, importlib.util, json, os, pathlib, sys
from pathlib import Path

VERSION = 'c1-ds-archive-regrade-v1'
ARCHIVE_STAR = 'corrected_micrographs.star'
MERGE_LOG = '_workers/merge.log'
HERE = Path(__file__).resolve().parent


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''): h.update(c)
    return h.hexdigest()


def load(p):
    try: return json.loads(Path(p).read_text())
    except (OSError, ValueError): return None


def inventory(root):
    """Every entry under root, symlinks and directories included, without following links."""
    rows = []
    for d, dirs, files in os.walk(root, followlinks=False):
        for n in sorted(dirs + files):
            p = Path(d) / n
            kind = 'symlink' if p.is_symlink() else ('dir' if p.is_dir() else 'file')
            rows.append({'path': p.relative_to(root).as_posix(), 'kind': kind, 'size': p.stat().st_size if kind == 'file' else None})
    return sorted(rows, key=lambda r: r['path'])


def archive_expectation(out, ws, sm, mw, star_io):
    """{archive rel: {...}} the producer's _workers/ contents, derived only from the retained workers/ trees and their exit digests."""
    problems, exp = [], {}
    roots = {star_io.worker_relative_root(star_io.output_root(m)) for m in sm['canonical_movies']}
    plots = {star_io.shift_plot_path(m) for m in sm['canonical_movies']}
    workers = ws.get('workers') or []
    if len(workers) != ws.get('n_workers') or len(workers) != len(sm['shards']): problems.append('worker count differs between status and shard manifest')
    for k, w in enumerate(workers):
        wdir = out / 'workers' / f'w{k}'
        if not wdir.is_dir(): problems.append(f'worker {k}: retained directory missing'); continue
        rec = (w.get('exit_digest') or {})
        outs = rec.get('outputs') if rec.get('status') == 'complete' and isinstance(rec.get('outputs'), dict) else None
        if outs is None: problems.append(f'worker {k}: no complete exit digest'); continue
        for f in sorted(wdir.rglob('*')):
            if f.is_symlink(): problems.append(f'worker {k}: symlink {f.relative_to(wdir)}'); continue
            if not f.is_file(): continue
            rel = f.relative_to(wdir)
            if str(rel) in plots or star_io.split_output_path(str(rel), roots) is not None: continue        # a movie product: merged/ comparison owns it
            if not mw.is_aggregate(rel): problems.append(f'worker {k}: {rel} is neither a movie product nor a producer aggregate'); continue
            if rel.suffix == '.mrc' or (rel.suffix == '.star' and rel.as_posix() != ARCHIVE_STAR):
                problems.append(f'worker {k}: {rel} is an MRC/STAR outside the pinned archive allow-list'); continue
            exit_sha = (outs.get(rel.as_posix()) or {}).get('sha256')
            if rel.as_posix() == ARCHIVE_STAR and not exit_sha: problems.append(f'worker {k}: no exit digest for {rel}'); continue
            exp[f'_workers/w{k}/{rel.as_posix()}'] = {'worker': k, 'source': str(f), 'source_sha256': sha(f), 'exit_sha256': exit_sha}
        if f'_workers/w{k}/{ARCHIVE_STAR}' not in exp: problems.append(f'worker {k}: no {ARCHIVE_STAR} to archive')
    return exp, problems


def archive_check(cand, exp, agg):
    problems, entries = [], {}
    actual = {}
    for r in inventory(cand):
        if r['path'] == '_workers' or r['path'].startswith('_workers/'): actual[r['path']] = r
    for p, r in actual.items():
        if r['kind'] == 'symlink': problems.append(f'archive symlink {p}')
    files = {p for p, r in actual.items() if r['kind'] == 'file'}
    want = set(exp) | {MERGE_LOG}
    if files != want: problems.append(f'archive inventory differs: missing={sorted(want - files)[:5]} unexpected={sorted(files - want)[:5]}')
    for p in sorted(files & set(exp)):
        e = exp[p]; got = sha(cand / p)
        entries[p] = {'worker': e['worker'], 'archived_sha256': got, 'worker_original_sha256': e['source_sha256'], 'exit_sha256': e['exit_sha256']}
        if got != e['source_sha256']: problems.append(f'{p}: archived bytes differ from the worker original')
        if e['exit_sha256'] and e['exit_sha256'] != e['source_sha256']: problems.append(f'{p}: worker original differs from its exit digest')
    if MERGE_LOG in files: entries[MERGE_LOG] = {'archived_sha256': sha(cand / MERGE_LOG), 'note': 'aggregate binary stdout/stderr; no worker original'}
    if sorted(agg.get('per_worker_aggregates_preserved') or []) != sorted(exp):
        problems.append('aggregate.json per_worker_aggregates_preserved differs from the derived archive set')
    return problems, entries


@contextlib.contextmanager
def hide_verified_archive(root):
    """Hide merged/_workers from rglob for exactly this one root, and only inside the with-block (entered after archive_check passed)."""
    real, orig = Path(root).resolve(), pathlib.Path.rglob

    def rglob(self, *a, **k):
        for p in orig(self, *a, **k):
            if self == real and p.relative_to(self).parts[0] == '_workers': continue
            yield p
    pathlib.Path.rglob = rglob
    try: yield
    finally: pathlib.Path.rglob = orig


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ds_arm_dir', type=Path); ap.add_argument('--out-dir', type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out_dir.exists(): raise SystemExit(f'{a.out_dir} exists; refusing to overwrite')
    sys.path.insert(0, str(Path(os.environ.get('C1_TOOLS', HERE))))
    import c1_tutorial24 as t24
    src = t24.SRC
    sys.path.insert(0, str(src / 'tools/multi_gpu'))
    import merge_workers as mw, star_io
    cot = load_module('compare_output_trees_ro', t24.CMP)

    arm = a.ds_arm_dir.absolute(); out = arm / 'out'; cand = out / 'merged'
    ds_json = load(arm / 'DATASET.json') or {}
    cfg = ds_json.get('cfg'); cls0 = ds_json.get('products_vs_standalone') or {}
    problems, invalid = [], []
    # 1. the historical result must be exactly "everything passed except the products comparison", and is kept as it is
    if ds_json.get('verdict') != 'FAIL' or cfg not in ('G', 'L'): invalid.append(f'retained DATASET.json is not a FAIL for cfg G/L: {ds_json.get("verdict")}/{cfg}')
    other = [p for p in ds_json.get('problems') or [] if not p.startswith('products vs the standalone')]
    if other: invalid.append(f'retained DATASET.json has other problems, not only the products comparison: {other}')
    base = Path(cls0.get('base') or '')
    if Path(cls0.get('candidate') or '').resolve() != cand.resolve() or not base.is_dir(): invalid.append('retained comparison does not bind this merged tree and an existing standalone tree')
    ds, ws, agg = (load(out / n) for n in ('dataset_status.json', 'workers/status.json', 'aggregate.json'))
    sm_path = out / 'workers/shards/shard_manifest.json'; sm = load(sm_path)
    if not (ds and ws and agg and sm): invalid.append('dataset_status.json, workers/status.json, aggregate.json or shard_manifest.json missing')
    else:
        if not (ds.get('verdict') == 'PASS' and ds.get('dataset_ready') and ds.get('workers_complete')): invalid.append('dataset_status is not PASS/ready/complete')
        if ws.get('verdict') != 'PASS' or ws.get('n_workers') != 1 or [w.get('returncode') for w in ws.get('workers') or []] != [0]: invalid.append('workers/status.json is not a PASS of one worker with rc 0')
        if agg.get('verdict') != 'PASS' or not agg.get('dataset_ready') or agg.get('n_movies_expected') != 24: invalid.append('aggregate.json is not a PASS of 24 movies')
        if ws.get('manifest_sha256') != sha(sm_path): invalid.append('shard manifest differs from the hash the launcher recorded')
    mp = t24.FROZEN / f'multigpu/{cfg}/manifest.json'; manifest = load(mp)
    if not isinstance(manifest, dict): invalid.append('frozen manifest missing')
    exp, archive_entries, state, reasons, products, report = {}, {}, 'INVALID', [], [], None
    if not invalid:
        exp, ap_ = archive_expectation(out, ws, sm, mw, star_io); invalid += ap_
    if not invalid:
        ap_, archive_entries = archive_check(cand, exp, agg); invalid += ap_
    # 2. the unmodified comparator and classifier, only after the archive is proven
    cmp_rc = None
    if not invalid:
        try:
            cman = cot.load_manifest(mp)
            if cman.get('input_star_sha256') and not (t24.DATA / 'movies.star').is_file(): raise cot.ValidationError('input STAR missing')
            cot.validate_input_star(t24.DATA / 'movies.star', cman)
            with hide_verified_archive(cand):
                report = cot.compare_trees(base, cand, cman, compare_auxiliary=False)
            cmp_rc = 0 if report['status'] == 'PASS' else 1
        except cot.ValidationError as e:
            report, cmp_rc = {'status': 'FAIL', 'reason': str(e)}, 1
        cls = t24.classify(cmp_rc, report, manifest)
        state, reasons, products = cls['state'], cls['reasons'], cls['products']
    else:
        reasons = invalid
    prior = (load(arm.parent / 'compare' / f'{cls0.get("label")}.json') or {}).get('reason') if cls0.get('label') else None
    verdict = 'PASS' if state == 'IDENTICAL' else ('FAIL' if state == 'DIFFERENT' else 'INVALID')
    rec = {'version': VERSION, 'verdict': verdict, 'state': state, 'cfg': cfg, 'reasons': reasons, 'different_products': products,
           'ds_arm_dir': str(arm), 'merged': str(cand), 'base': str(base), 'comparison_label': cls0.get('label'),
           'historical': {'DATASET.json_sha256': sha(arm / 'DATASET.json') if (arm / 'DATASET.json').is_file() else None, 'verdict': ds_json.get('verdict'),
                          'comparator_reason': prior, 'note': 'historical FAIL is retained; this regrade supersedes only its products comparison'},
           'binding': {'regrader_sha256': sha(__file__), 'c1_tutorial24_sha256': sha(t24.__file__), 'comparator_sha256': sha(t24.CMP), 'merge_workers_sha256': sha(mw.__file__),
                       'manifest_sha256': sha(mp) if mp.is_file() else None, 'input_star_sha256': sha(t24.DATA / 'movies.star'),
                       **{n: sha(out / n) for n in ('dataset_status.json', 'workers/status.json', 'aggregate.json', 'workers/shards/shard_manifest.json') if (out / n).is_file()}},
           'archive_allow_list': sorted(exp) + [MERGE_LOG], 'archive': archive_entries,
           'canonical_products': sorted(t24.expected_products(manifest)) if isinstance(manifest, dict) else None,
           'comparator': {'rc': cmp_rc, 'scope': (report or {}).get('comparison_scope'), 'mrc_sha256': (report or {}).get('mrc_sha256'),
                          'different_files': (report or {}).get('different_files'), 'archive_hidden_from_comparator': cmp_rc is not None},
           'merged_inventory': inventory(cand) if cand.is_dir() else None}
    a.out_dir.mkdir(parents=True)
    (a.out_dir / 'REGRADE.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(verdict, state, reasons or f'{len(products)} differing products')
    return {'PASS': 0, 'FAIL': 1}.get(verdict, 2)


if __name__ == '__main__':
    sys.exit(main())
