#!/usr/bin/env python3
"""Compare two MotionCorr output trees product by product.

usage: compare_products.py ROOT_A ROOT_B OUT.json [--expect-differ]

MRC: header bytes 0-223 and pixels (1024+) separately; the label block at 224-1023 holds a
timestamp and is reported but not gated. STAR and EPS: text after replacing each tree's own
root with a placeholder (the output path is embedded in EPS and in joint STARs). Logs and PDFs
are inventoried only (timing values and Ghostscript dates differ between identical runs).
Exit 0 when the file sets are equal and every gated comparison is equal (or, with
--expect-differ, when at least one gated comparison differs: the negative control).
"""
import hashlib, json, pathlib, sys

a, b, out = (pathlib.Path(x).resolve() for x in sys.argv[1:4])
expect_differ = '--expect-differ' in sys.argv[4:]
sha = lambda x: hashlib.sha256(x).hexdigest()

def files(root):
    return {str(p.relative_to(root)): p for p in sorted(root.rglob('*')) if p.is_file()}

fa, fb = files(a), files(b)
rows, gated_diff = [], 0
for rel in sorted(set(fa) | set(fb)):
    row = dict(file=rel, in_a=rel in fa, in_b=rel in fb, gated=False, equal=None)
    if rel in fa and rel in fb:
        x, y = fa[rel].read_bytes(), fb[rel].read_bytes()
        if rel.endswith('.mrc'):
            row.update(gated=True, header_0_223_equal=x[:224] == y[:224], pixels_equal=x[1024:] == y[1024:],
                       label_block_equal=x[224:1024] == y[224:1024], pixels_sha256=sha(x[1024:]), size=len(x))
            row['equal'] = row['header_0_223_equal'] and row['pixels_equal'] and len(x) == len(y)
        elif rel.endswith(('.star', '.eps')):
            xt = x.replace(str(a).encode(), b'@ROOT@'); yt = y.replace(str(b).encode(), b'@ROOT@')
            row.update(gated=True, equal=xt == yt, normalised_sha256=sha(xt))
        else:
            row['note'] = 'inventory only'
        if row['gated'] and not row['equal']: gated_diff += 1
    elif row['in_a'] != row['in_b']:
        gated_diff += 1; row['equal'] = False
    rows.append(row)
n_gated = sum(r['gated'] for r in rows)
identical = gated_diff == 0
verdict = ('DIFFERS_AS_EXPECTED' if gated_diff else 'NEGATIVE_CONTROL_SAW_NOTHING') if expect_differ else ('IDENTICAL' if identical else 'DIFFERENT')
out.write_text(json.dumps(dict(root_a=str(a), root_b=str(b), n_files=len(rows), n_gated=n_gated, n_gated_differing=gated_diff, verdict=verdict, rows=rows), indent=1) + '\n')
print(verdict, f'files={len(rows)} gated={n_gated} differing={gated_diff}')
sys.exit(0 if (verdict in ('IDENTICAL', 'DIFFERS_AS_EXPECTED')) else 1)
