#!/usr/bin/env python3
"""Bounded static control: only the frozen test wiring may differ.

SPDX-License-Identifier: GPL-2.0-or-later
No native algorithm or design-matrix implementation is reproduced here.
"""
import hashlib
import json
from pathlib import Path
import sys


def main():
    specification = json.loads((Path(__file__).parent/'frozen_axis_semantics.json').read_text())
    source = Path(sys.argv[1]).read_text()
    for name in ['fit', 'query']:
        assert source.count(specification['new_'+name]) == 1, 'frozen '+name+' wiring missing'
    # Inverting precisely the two approved blocks must recover the historical
    # entire source. Thus observations, admission, expectations, bounds and all
    # other modes are unchanged, and fit geometry is unconditionally 128x96.
    historical = source.replace(specification['new_fit'], specification['old_fit'])
    historical = historical.replace(specification['new_query'], specification['old_query'])
    assert hashlib.sha256(historical.encode()).hexdigest() == specification['old_test_sha256']
    assert hashlib.sha256(source.encode()).hexdigest() == specification['new_test_sha256']
    prefix = source[:source.index(specification['new_fit'])]
    assert prefix.count('"axis-normalization"') == 1, 'axis mutant changes fit inputs'
    print('PASS frozen fit inputs/128x96 geometry identical; only query normalization mutates')


if __name__ == '__main__':
    main()
