#!/usr/bin/env python3
"""Field metrics for a results directory: #269's evaluate_final.py logic, any results name, any count.

usage: eval_field.py ROOT RESULTS_NAME [workers]    (needs <arm>/runtime.json: diag builds only)
"""
import concurrent.futures, json, pathlib, re, sys
REPO = pathlib.Path(sys.argv[0]).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
import check_realistic_motion as check


def read_model(runtime, star):
    """JSON capture (#269 overlay) or the afba50a4 text capture. The text form has the full-precision
    polynomial but no global shifts: those come from the STAR global_shift table (6 significant digits)."""
    text = runtime.read_text()
    if text.lstrip().startswith('{'): return json.loads(text)
    lines = text.splitlines(); enabled = lines[1].split()[1] == '1'
    cx, cy = [0.]*18, [0.]*18
    if enabled:
        for ln in lines[2:20]:
            i, a, b = ln.split(); cx[int(i)] = float(a); cy[int(i)] = float(b)
    block = star.read_text().split('data_global_shift', 1)[1].split('data_', 1)[0]
    rows = [ln.split() for ln in block.splitlines() if re.match(r'\s*\d+\s+[-+0-9.eE]+\s+[-+0-9.eE]+\s*$', ln)]
    return dict(**{'global': [[float(r[1]), float(r[2])] for r in sorted(rows, key=lambda r: int(r[0]))]}, coeff_x=cx, coeff_y=cy, local_enabled=enabled)


def one(args):
    root, run = args; out = run.parent; row = json.loads(run.read_text())
    receipt = root/'fixtures'/out.parent.name/'RECEIPT.json'; r = json.loads(receipt.read_text())['recipe']
    if row['exit']: raise ValueError((run, 'native process failure', row['exit']))
    star = out/'output/movie.star'; check.validate_star_rows(star, r); s = check.read_motion_star(star)
    model = read_model(out/'runtime.json', star); m = check.evaluate(r, model, s)
    m['convergence'] = check.convergence(out/'output/movie.log')
    m['identity'] = {str(p.relative_to(root)): check.gen.digest(p) for p in [run, out/'runtime.json', star, out/'output/movie.log']}
    (out/'metrics.json').write_text(json.dumps(m, indent=2, allow_nan=False)+'\n'); return out.name

if __name__ == '__main__':
    root = pathlib.Path(sys.argv[1]).resolve(); runs = sorted((root/sys.argv[2]).glob('*/*/RUN.json'))
    runs = [x for x in runs if not (x.parent/'metrics.json').exists()]
    with concurrent.futures.ProcessPoolExecutor(max_workers=int(sys.argv[3]) if len(sys.argv) > 3 else 4) as pool: rows = list(pool.map(one, [(root, x) for x in runs]))
    print('evaluated', len(rows))
