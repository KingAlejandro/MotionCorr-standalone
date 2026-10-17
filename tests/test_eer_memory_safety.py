#!/usr/bin/env python3
"""Generated EER/header regressions for #221; no external data or TIFF writer needed."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import subprocess
import tempfile


def encode(compression, width, electrons):
    """Independent scalar LSB-first encoder; skip codes omit symbols only in 7-bit."""
    rle, sym = (8, 4) if compression == 65000 else (7, 2 if compression == 65002 else 4)
    bits = []
    def put(v, n):
        bits.extend((v >> b) & 1 for b in range(n))
    def code(p, s):
        put(p, rle)
        if rle == 8 or p != 127:
            put(s, sym)
    prev = 0
    for pos, symbol in electrons:
        gap = pos - prev
        while gap >= (1 << rle) - 1:
            code((1 << rle) - 1, 0)
            gap -= (1 << rle) - 1
        code(gap, symbol ^ (10 if sym == 4 else 3))
        prev = pos + 1
    gap = width * width - prev
    while gap > (1 << rle) - 1:
        code((1 << rle) - 1, 0)
        gap -= (1 << rle) - 1
    code(gap, 0)
    return bytes(sum(bits[k + b] << b for b in range(min(8, len(bits) - k)))
                 for k in range(0, len(bits), 8))


def write_eer(path, compression, strips, width=4096, omit=(), counts=None, offsets=None):
    # BigTIFF, one raw strip per IFD, with IFDs before the strips.
    tags = [256, 257, 258, 259, 273, 277, 278, 279]
    if compression == 65002:
        tags += [65007, 65008, 65009]
    tags = [t for t in tags if t not in omit]
    size = 16 + 20 * len(tags)
    offset = 16 + len(strips) * size
    out = bytearray(struct.pack('<2sHHHQ', b'II', 43, 8, 0, 16))
    for i, strip in enumerate(strips):
        values = {256: width, 257: width, 258: 8, 259: compression,
                  273: offset if offsets is None else offsets[i], 277: 1, 278: width,
                  279: len(strip) if counts is None else counts[i], 65007: 7, 65008: 1, 65009: 1}
        out += struct.pack('<Q', len(tags))
        for tag in tags:
            kind = 16 if tag in (273, 279) else 4 if tag in (256, 257, 278) else 3
            out += struct.pack('<HHQQ', tag, kind, 1, values[tag])
        out += struct.pack('<Q', 16 + (i + 1) * size if i + 1 < len(strips) else 0)
        offset += len(strip)
    path.write_bytes(out + b''.join(strips))


def run(cmd, cwd, expected=0):
    p = subprocess.run([str(x) for x in cmd], cwd=cwd, capture_output=True, text=True, timeout=90)
    log = p.stdout + p.stderr
    assert p.returncode == expected, (cmd, p.returncode, log[-6000:])
    assert not any(x in log for x in ('AddressSanitizer', 'runtime error:', 'LeakSanitizer')), log
    return log


def expected_image(width, up, groups, electrons):
    size = width // 2 if up == -1 else width << (up - 1)
    out = bytearray(struct.pack('<qqq', size, size, len(groups)))
    for group in groups:
        pixels = Counter()
        for f in group:
            for pos, sym in electrons[f]:
                x, y = pos % width, pos // width
                if up == -1:
                    x, y = x >> 1, y >> 1
                elif up == 2:
                    if width == 4096:
                        x, y = 2*x + ((sym & 2) >> 1), 2*y + ((sym & 8) >> 3)
                    else:
                        x, y = 2*x + (sym & 1), 2*y + (sym >> 1)
                pixels[y * size + x] += 1
        out += struct.pack('<q', len(pixels))
        for pos, count in sorted(pixels.items()):
            out += struct.pack('<qf', pos, count)
    return bytes(out)


def main():
    if not __debug__:
        raise RuntimeError("EerMemorySafety requires Python assertions enabled")
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', type=Path, required=True)
    ap.add_argument('--helper', type=Path, required=True)
    args = ap.parse_args()
    binary, helper = args.binary.resolve(), args.helper.resolve()
    with tempfile.TemporaryDirectory(prefix='eer-safety-') as td:
        root = Path(td)
        run([helper, 'integer_to_string'], root)
        for comp in (65000, 65001, 65002):
            width = 2048 if comp == 65002 else 4096
            electrons = [[(0, 0), (131 + i, i % (4 if comp == 65002 else 16)),
                          (width*width - 1, 3 if comp == 65002 else 15)] for i in range(3)]
            strips = [encode(comp, width, e) for e in electrons]
            movie = root / f'valid-{comp}.eer'
            write_eer(movie, comp, strips, width)
            for up in ((1, 2) if comp == 65002 else (-1, 1, 2)):
                for grouping in (1, 3):
                    dest = root / 'render.bin'
                    log = run([helper, 'render_eer', movie, dest, up, grouping, 2], root)
                    assert 'This frame is skipped' not in log, log
                    groups = [list(range(g, g + grouping)) for g in range(0, 3, grouping)]
                    assert dest.read_bytes() == expected_image(width, up, groups, electrons)
            # A short first fraction must never borrow bits from its neighbour.
            # Grouping 3 tests a corrupt fraction after a larger vector as well.
            for where in (0, 1, 2):
                bad = strips.copy()
                bad[where] = bytes(1 if comp == 65000 else 3)
                write_eer(root / 'short.eer', comp, bad, width)
                for grouping in (1, 3):
                    log = run([helper, 'render_eer', 'short.eer', 'render.bin', 1, grouping, 2], root)
                    assert 'This frame is skipped' in log, log
                    filtered = [e if i != where else [] for i, e in enumerate(electrons)]
                    groups = [list(range(g, g + grouping)) for g in range(0, 3, grouping)]
                    assert (root/'render.bin').read_bytes() == expected_image(width, 1, groups, filtered)
            write_eer(root/'zero.eer', comp, [bytes(len(s)) for s in strips], width)
            log = run([helper, 'render_eer', 'zero.eer', 'render.bin', 1, 3, 2], root)
            assert 'This frame is skipped' in log
            assert (root/'render.bin').read_bytes() == expected_image(width, 1, [[0, 1, 2]], [[], [], []])

        # The actual runner must continue after container/header failure, publish
        # the healthy second movie, and withhold joint completion STAR (#205).
        width = 2048
        strip = encode(65002, width, [(100, 0), (10000, 3), (100000, 1)])
        write_eer(root/'healthy.eer', 65002, [strip]*12, width)
        damaged = []
        for tag in (256, 257, 259, 65007, 65008):
            path = root/f'missing-{tag}.eer'
            write_eer(path, 65002, [strip]*12, width, omit=(tag,))
            damaged.append(path)
        for name, counts, offsets in [('oversized', [1 << 63]*12, None),
                                      ('past-eof', None, [1 << 40]*12),
                                      ('zero-count', [0]*12, None)]:
            path = root/f'{name}.eer'
            write_eer(path, 65002, [strip]*12, width, counts=counts, offsets=offsets)
            damaged.append(path)
        path = root/'truncated.eer'
        write_eer(path, 65002, [strip]*12, width)
        path.write_bytes(path.read_bytes()[:-100])
        damaged.append(path)
        for n in (0, 1, 16, 23, 24, 31):
            path = root/f'legacy-{n}.eer'
            path.write_bytes(bytes(n))
            damaged.append(path)
        for words in (-1, 0, 1 << 62):
            path = root/f'legacy-words-{words}.eer'
            path.write_bytes(struct.pack('<q', words) + b'ThermoFisherECComprOK000\0')
            damaged.append(path)
        for field in (0, 3):
            head = bytearray(1024)
            struct.pack_into('<4i', head, 0, 64, 64, 3, 2)
            struct.pack_into('<i', head, field*4, -(1 << 31))
            path = root/f'int-min-{field}.mrcs'
            path.write_bytes(head)
            damaged.append(path)
        for i, path in enumerate(damaged):
            out = root/f'out-{i}'
            (root/'movies.star').write_text('data_movies\n\nloop_\n_rlnMicrographMovieName #1\n' + path.name + '\nhealthy.eer\n')
            log = run([binary, '--i', 'movies.star', '--o', str(out)+'/', '--use_own',
                       '--eer_grouping', 4, '--j', 2, '--bin_factor', 8, '--angpix', 1,
                       '--skip_report_pdf'], root, expected=1)
            assert path.name in log and 'Failed' in log, log
            assert (out/'healthy.star').is_file() and (out/'healthy.mrc').is_file(), log
            assert not (out/'corrected_micrographs.star').exists(), log
            assert not list(out.glob(path.stem + '.*')), list(out.iterdir())
    print('PASS EerMemorySafety: scalar valid identity, isolated corrupt fractions, clean per-movie failures')


if __name__ == '__main__':
    main()
