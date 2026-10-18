"""Record keys and verdicts shared by the item 13 recorder and grader (#204 harness JSON layouts)."""

SYNTH_KEYS = {
    'matrix': lambda r: r['case']['name'],
    'refuse': lambda r: f"mode{r['mode']}",
    'compressed': lambda r: r['label'],
    'damaged': lambda r: r['label'],
    'errors': lambda r: f"m{r['mode']} {r['variant']}",
    'options': lambda r: f"m{r['mode']} {r['option_set']}",
}


def verdict(r):
    """synth_mrc_matrix.py's own rule: `pass`, else `rc0` (CPU matrix), else True."""
    return 'PASS' if r.get('pass', r.get('rc0', True)) else 'FAIL'


def synth_verdicts(doc):
    out = {}
    for section, key in SYNTH_KEYS.items():
        for r in doc.get(section, []):
            out[f'{section}: {key(r)}'] = verdict(r)
    return out


def real_verdicts(records, tag=''):
    return {f"real{('/' + tag) if tag else ''}: {r['family']} {r['config']}{(' cpu' if r.get('cpu') else '')}": verdict(r)
            for r in records}
