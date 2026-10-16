#!/usr/bin/env python3
"""Build per-family run directories: corpus/<id>/{Movies/*, gain.*, movies.star}.

Movies and gains are symlinks into the data root, so the STAR holds short relative
paths ("Movies/<name>") and MotionCorr products land at <out>/Movies/<name>.mrc
(memory note: output paths mirror the input path). MRC movies named .mrc are linked
as .mrcs, which main requires for MRC stacks.

Usage: setup_corpus.py FAMILIES_JSON DATA_ROOT CORPUS_ROOT
"""
import json
import os
import sys
from pathlib import Path


def main():
    fam_json, data, corpus = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    for fam in json.loads(fam_json.read_text())['families']:
        d = corpus / fam['id']
        (d / 'Movies').mkdir(parents=True, exist_ok=True)
        names = []
        for rel in fam['movies']:
            src = data / rel
            if not src.is_file() or src.stat().st_size == 0:
                raise SystemExit('missing movie: %s' % src)
            name = src.name
            if fam.get('link_rename') and name.endswith('.mrc'):
                name = name[:-4] + fam['link_rename']
            link = d / 'Movies' / name
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(src, link)
            names.append('Movies/' + name)
        if fam.get('gain'):
            src = data / fam['gain']
            if not src.is_file():
                raise SystemExit('missing gain: %s' % src)
            link = d / fam['gain_link']
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(src, link)
        star = ['# version 30001', '', 'data_optics', '', 'loop_',
                '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2', '_rlnMicrographOriginalPixelSize #3',
                '_rlnVoltage #4', '_rlnSphericalAberration #5', '_rlnAmplitudeContrast #6',
                'opticsGroup1 1 %s %s %s 0.1' % (fam['angpix'], fam['voltage'], fam['cs']), '',
                '# version 30001', '', 'data_movies', '', 'loop_',
                '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2'] + ['%s 1' % n for n in names] + ['']
        (d / 'movies.star').write_text('\n'.join(star))
        print(fam['id'], len(names), 'movies')


if __name__ == '__main__':
    main()
