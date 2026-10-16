#!/usr/bin/env python3
"""Build steady-state replay run directories: replay/<id>/{Movies/r<k>_<name>, gain.*, movies.star}.

Each family's FIRST movie is listed N times (default 6) under distinct symlink names
r1_..rN_ (the aliasing used by docs/multi_gpu/startup_costs and #174's stage.sh), so one
process sees N consecutive movies of identical content. These are replayed rows, not N
distinct inputs: they give the per-movie steady time and the first-movie overhead.

Usage: setup_replay.py FAMILIES_JSON DATA_ROOT CORPUS_ROOT REPLAY_ROOT [N]
CORPUS_ROOT is the setup_corpus.py output; its movies.star optics line is reused verbatim.
"""
import json
import os
import sys
from pathlib import Path


def main():
    fam_json, data, corpus, replay = (Path(x) for x in sys.argv[1:5])
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 6
    data = data.resolve()
    for fam in json.loads(fam_json.read_text())['families']:
        d = replay / fam['id']
        (d / 'Movies').mkdir(parents=True, exist_ok=True)
        src = data / fam['movies'][0]
        base = src.name
        if fam.get('link_rename') and base.endswith('.mrc'):
            base = base[:-4] + fam['link_rename']
        names = []
        for k in range(1, n + 1):
            link = d / 'Movies' / ('r%d_%s' % (k, base))
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(src, link)
            names.append('Movies/' + link.name)
        if fam.get('gain'):
            link = d / fam['gain_link']
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(data / fam['gain'], link)
        ref = (corpus / fam['id'] / 'movies.star').read_text().splitlines()
        head = ref[:ref.index('_rlnMicrographMovieName #1')]
        (d / 'movies.star').write_text('\n'.join(head + ['_rlnMicrographMovieName #1', '_rlnOpticsGroup #2']
                                                  + ['%s 1' % x for x in names] + ['']))
        print(fam['id'], n, 'replayed rows of', base)


if __name__ == '__main__':
    main()
