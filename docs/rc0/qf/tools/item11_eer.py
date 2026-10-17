#!/usr/bin/env python3
"""QF item 11: replay #208's EER compact matrix (W-EER-Q, PR #208 @ a5fa5429) on the frozen binaries.

Every case recorded in item_records/eer_208.json (from #208's evidence/cases, evidence/results and
evidence/batch_analysis.json) is re-run with the recorded options and arms, in the QF lane
(qual_lib.run_case: lane GPU flock per run, bench-lock probe, UUID pin, nvidia-smi witness,
/usr/bin/time -v). Binaries: $QF_W/build-nvcomp (CUDA cases); $QF_W/build-cpu vs Q1's CPU 1db86902
for #208's three CPU cases (#208 compared 0ac2726a with 1db86902). Not replayed by default:
o1n_NOGUARD, a guard-removed mutant build; `--noguard-binary` runs it, and the same control on o5,
as a powered control (item11_noguard_control.sh builds the mutant). The s00 smoke runs have no result.

Inputs. Corpus movies are hash-checked against docs/workload_corpus/corpus.md. Damaged copies are
regenerated with #208's eer_corrupt.py and must equal #208's recorded SHA-256. #208 did not record its
eer_synth.py parameters, so the synthetic movies follow the frozen recipe in SYNTH (generator, seed and
parameters) and must equal item_records/eer_synth_recipe.json: every run regenerates them and compares
hashes, never trusting files already on disk. The recipe file also records each fixture's encoding,
geometry and fraction count and, from an independent decode of its strips (synth_witness), the largest
per-pixel count of one group at each case's grouping and upsampling: o2 65532, o3 65535, o1/o4/o5 65536.

Grading per case (grade_case; products are graded before they are deleted):
  * each arm's exit status and --ingest_witness routes equal #208's; every rc-0 GPU arm is witnessed
    on the lane UUID only;
  * where #208 compared two arms, the complete-tree comparison (main's compare_output_trees.py, #208's
    log allowances) passes iff it passed then;
  * any arm that exits nonzero writes no completion (joint) STAR;
  * a refused pinned-compact arm (o1/o4/o5) prints the refusal and publishes no MRC or STAR; the auto arm
    of an overflowing case logs the uint16 guard line, a fitting case (o2/o3) does not;
  * batch cases b1-b6 (#208 section 5): per arm, the published MRC/STAR set, the joint-STAR presence, every
    MRC payload hash, every movie's frame count, the D6 skip warnings (count and frame numbers) and the
    error messages equal #208's; and auto vs float give identical MRC payloads and per-movie STARs;
  * c17 fails with `Unsupported gain size` and publishes nothing.
`--negative-controls` additionally mutates copies of real outputs and requires grade_case to fail:
b6 with a per-movie and joint STAR planted after the refusal, b2 with one float-arm MRC payload byte
flipped, o1 with an MRC planted in the refused compact arm, b3 with the skip warning removed.
PASS = every replayed case passes (and every negative control is rejected). Run:
  QF_W=... QF_CPUS=... QF_GPU_UUID=... QF_GPU_LOCK=... \\
    taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item11_eer.py [--only b,o1] [--skip-heavy] [--negative-controls]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from qual_lib import *  # noqa: F401,F403
import product_campaign as pc  # noqa: E402

RECORD = json.loads((HERE / 'item_records' / 'eer_208.json').read_text())
RECIPE_FILE = HERE / 'item_records' / 'eer_synth_recipe.json'
ROOT = W / 'item11-eer'
D = Path.home() / 'motioncorr-validation-20261011-vm' / 'corpus' / 'data-https'
CORPUS = {
    'f3': 'EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer',
    # #208's batches are healthy A, damaged copy of A, healthy B; B is the second Falcon3 movie in families.json
    'f3b': 'EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-57-59.233_eer_data_4096x4096.eer',
    'f4': 'EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer',
    'g': 'EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer',
    'g_gain': 'EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain',
}
# eer_corrupt.py arguments and #208's recorded output hash (evidence/fixture-sha256.txt)
CORRUPT = {
    'f3_trunc60': (['truncate', '0.6'], 'e23cd25ef3bb3600a057e36ddd3a091ceb20693fedaaf4fd910f4e2ed12ed8f7'),
    'f3_rand': (['random', '500', '4096'], 'e0cfbe1c7542de3a161ebe2ff139443c446fb33a4f166bd75f48470d602047da'),
    'f3_ff': (['ff', '700'], 'ebdb0e12dea7be0f059b230c7b6434ad62e9137f0cec6e9f0246f0e5aaf4099a'),
    'f3_zero': (['zero', '900'], 'c7cf6747e2b3d17c018ece718aff242ce8e765720da93a85bc816d052910ee54'),
}
# Frozen replacement recipe (harness_eer/eer_synth.py, #208's generator, unchanged). The codec movies cover
# #208's three encodings and two detector sizes with random electrons. The overflow movies carry hot pixels
# so one output pixel counts g (4 g at -1) per group. o5's movie uses one strip variant so the hot electron's
# sub-pixel symbol, and so its 8K output pixel, is the same in every fraction.
SYNTH = {
    'n65000_4k_n240': ['--det', '4096', '--nfrac', '240', '--codec', '65000', '--bg', '20000', '--variants', '2', '--seed', '1'],
    'n65001_2k_n240': ['--det', '2048', '--nfrac', '240', '--codec', '65001', '--bg', '20000', '--variants', '2', '--seed', '1'],
    'n65002_2k_n240': ['--det', '2048', '--nfrac', '240', '--codec', '65002', '--bg', '20000', '--variants', '2', '--seed', '1'],
    'ovf4k_n49152': ['--det', '4096', '--nfrac', '49152', '--codec', '65001', '--hot', '4', '--bg', '2000', '--variants', '2', '--seed', '1'],
    'ovf2k_n196608': ['--det', '2048', '--nfrac', '196608', '--codec', '65001', '--hot', '1', '--bg', '2000', '--variants', '2', '--seed', '1'],
    'ovf4k_n196608': ['--det', '4096', '--nfrac', '196608', '--codec', '65001', '--hot', '1', '--bg', '2000', '--variants', '1', '--seed', '1'],
}
# (fixture, grouping, upsampling) whose group maximum the recipe must reach, and the required value
OVERFLOW_WITNESS = {'o1': ('ovf4k_n49152', 16384, -1, 65536), 'o2': ('ovf4k_n49152', 16383, -1, 65532),
                    'o3': ('ovf2k_n196608', 65535, 1, 65535), 'o4': ('ovf2k_n196608', 65536, 1, 65536),
                    'o5': ('ovf4k_n196608', 65536, 2, 65536)}
ANGPIX = {'f3': 1.06, 'f4': 1.64, 'g': 0.97}  # #208 mkcase.py FAM
BATCH = {'b1': 'f3_trunc60', 'b5': 'f3_trunc60', 'b2': 'f3_rand', 'b3': 'f3_ff', 'b4': 'f3_zero'}
SYN_FOR = {'o1': 'ovf4k_n49152', 'o2': 'ovf4k_n49152', 'o3': 'ovf2k_n196608', 'o4': 'ovf2k_n196608',
           'o5': 'ovf4k_n196608', 'x1': 'n65000_4k_n240', 'x2': 'n65000_4k_n240', 'x3': 'n65002_2k_n240',
           'x4': 'n65002_2k_n240', 'x5': 'n65001_2k_n240'}
SKIP = {'o1n_NOGUARD_upm1_g16384': 'guard-removed mutant; run with --noguard-binary (item11_noguard_control.sh)'}
HEAVY = {'m1_f4_g40_up2_full', 'm2_f4_g40_up2_100groups', 'c15_f3_g200_up3', 'c16_g_g150_up3'}
ALLOW = ['Staging this movie as native', 'Released native uint', 'Materialized native uint', 'EER grouping']
COMPACT_REFUSAL = '--ingest compact was requested but the compact native staging did not apply'
GUARD_LINE = 'can exceed 65535 counts per pixel; using the float movie.'
EXPECT_ERROR = {'c17_g_g49_up-1_gain_expectfail': 'Unsupported gain size in EERRenderer::loadEERGain()'}
Q1_CPU = Path(os.environ.get('QF_REF_CPU_BIN', Q1 / 'build-cpu' / 'motioncorr'))


# ---------------------------------------------------------------- synthetic fixtures: recipe and witness

def _tiff_ifds(path):
    """(width, codec, strip offset, strip bytes) per directory of a classic little-endian TIFF."""
    out = []
    with open(path, 'rb') as f:
        head = f.read(8)
        assert head[:2] == b'II' and struct.unpack('<H', head[2:4])[0] == 42, 'not a classic LE TIFF'
        off = struct.unpack('<I', head[4:8])[0]
        while off:
            f.seek(off)
            n = struct.unpack('<H', f.read(2))[0]
            tags = {}
            for _ in range(n):
                t, ty, cnt, val = struct.unpack('<HHII', f.read(12))
                tags[t] = val & 0xFFFF if ty == 3 else val
            out.append((tags[256], tags[259], tags[273], tags[279]))
            off = struct.unpack('<I', f.read(4))[0]
    return out


def _decode_strip(raw, codec, total):
    """Electron (position, symbol) list of one strip, read as an LSB-first bitstream (renderEER semantics)."""
    rle, sbits, mask = (8, 4, 0x0A) if codec == 65000 else ((7, 2, 3) if codec == 65002 else (7, 4, 0x0A))
    skip = (1 << rle) - 1
    bits = int.from_bytes(raw, 'little')
    pos = npix = 0
    elec = []
    while True:
        gap = (bits >> pos) & skip
        pos += rle
        npix += gap
        if npix >= total:
            break
        if gap == skip:
            if codec == 65000:
                pos += sbits  # 8-bit stream: a skip unit still carries a (null) symbol
            continue
        s = ((bits >> pos) & ((1 << sbits) - 1)) ^ mask
        pos += sbits
        elec.append((npix, s))
        npix += 1
    return elec


def _out_pixel(p, s, det, up, codec):
    w = 4095 if det == 4096 else 2047
    sh = 12 if det == 4096 else 11
    x, y = p & w, p >> sh
    if up == 1:
        return x, y
    if up == -1:
        return x >> 1, y >> 1
    if up == 2 and det == 4096:
        return (x << 1) | ((s & 2) >> 1), (y << 1) | ((s & 8) >> 3)
    if up == 2 and det == 2048:
        return (x << 1) | (s & 1), (y << 1) | (s >> 1)
    if up == 3:
        return (x << 2) | (s & 3), (y << 2) | ((s & 12) >> 2)
    raise ValueError(up)


def synth_witness(path, groupings):
    """Encoding, geometry and fraction count from the file itself; group maxima by independent decode."""
    ifds = _tiff_ifds(path)
    det, codec = ifds[0][0], ifds[0][1]
    raw = open(path, 'rb').read(max(o + n for _, _, o, n in ifds) + 8)
    strips = {}
    for _, _, o, n in ifds:
        if o not in strips:
            strips[o] = _decode_strip(raw[o:o + n], codec, det * det)
    order = [o for _, _, o, _ in ifds]
    wit = {'detector': det, 'codec': codec, 'fractions': len(ifds), 'distinct_strips': len(strips),
           'electrons_per_strip': [len(v) for v in strips.values()], 'group_max': {}}
    for g, up in groupings:
        counts = {o: Counter(_out_pixel(p, s, det, up, codec) for p, s in e) for o, e in strips.items()}
        best = 0
        for j in range(len(order) // g):
            n_by_strip = Counter(order[j * g:(j + 1) * g])
            pix = set().union(*(counts[o] for o in n_by_strip))
            best = max(best, max(sum(n * counts[o][q] for o, n in n_by_strip.items()) for q in pix))
        wit['group_max'][f'g{g}_up{up}'] = best
    return wit


def make_synth(inp, write_recipe=False):
    """Regenerate every synthetic fixture from the frozen recipe and require the recorded hashes."""
    recipe = json.loads(RECIPE_FILE.read_text()) if RECIPE_FILE.exists() else {'fixtures': {}}
    info = {}
    for name, args in SYNTH.items():
        dst = inp / f'{name}.eer'
        tmp = inp / f'.{name}.regen'
        subprocess.run([PY, str(HERE / 'harness_eer' / 'eer_synth.py'), str(tmp), *args], check=True, capture_output=True)
        h = sha256_file(tmp)
        rec = recipe['fixtures'].get(name)
        if write_recipe:
            groupings = [(g, up) for fx, g, up, _ in OVERFLOW_WITNESS.values() if fx == name]
            recipe['fixtures'][name] = {'generator': 'harness_eer/eer_synth.py', 'generator_sha256':
                                        sha256_file(HERE / 'harness_eer' / 'eer_synth.py'), 'args': args, 'sha256': h,
                                        'witness': synth_witness(tmp, groupings)}
        elif rec is None or rec['args'] != args or rec['sha256'] != h:
            raise SystemExit(f'{name}: regenerated fixture {h} does not match the frozen recipe '
                             f'({(rec or {}).get("sha256")}); refusing to run on unbound inputs')
        os.replace(tmp, dst)
        info[name] = {'args': args, 'sha256': h, 'matches_recipe': True, 'pr208_sha256': None}
    if write_recipe:
        recipe['note'] = ('QF replacement fixtures for #208 x1-x5/o1-o5 (#208 did not record eer_synth.py parameters; '
                          'its historical hashes are in evidence/fixture-sha256.txt of PR #208 and are not these).')
        for case, (fx, g, up, want) in OVERFLOW_WITNESS.items():
            got = recipe['fixtures'][fx]['witness']['group_max'][f'g{g}_up{up}']
            recipe.setdefault('overflow_cases', {})[case] = {'fixture': fx, 'grouping': g, 'upsampling': up,
                                                             'group_max': got, 'required': want, 'ok': got == want}
        RECIPE_FILE.write_text(json.dumps(recipe, indent=1) + '\n')
    for case, c in recipe.get('overflow_cases', {}).items():
        if not c['ok']:
            raise SystemExit(f'recipe witness for {case}: group max {c["group_max"]} != {c["required"]}')
    return info


def ensure_inputs(log, write_recipe=False):
    inp = ROOT / 'inputs'
    inp.mkdir(parents=True, exist_ok=True)
    hashes = pc.parse_corpus_hashes()
    info = {}
    for key, rel in CORPUS.items():
        h = sha256_file(D / rel)
        exp = (hashes.get(rel) or {}).get('sha256')
        info[key] = {'path': str(D / rel), 'sha256': h, 'corpus_md': exp, 'match': h == exp}
        if exp and h != exp:
            raise SystemExit(f'{rel}: sha256 {h} != corpus.md {exp}')
    for name, (args, exp) in CORRUPT.items():
        dst = inp / f'{name}.eer'
        subprocess.run([PY, str(HERE / 'harness_eer' / 'eer_corrupt.py'), str(D / CORPUS['f3']), str(dst), *args],
                       check=True, capture_output=True)
        h = sha256_file(dst)
        info[name] = {'args': args, 'sha256': h, 'pr208_sha256': exp, 'match': h == exp}
        if h != exp:
            raise SystemExit(f'{name}: regenerated damaged movie differs from #208 ({h})')
    info.update(make_synth(inp, write_recipe))
    wrong = inp / 'gain_wrong_2048.mrc'
    hdr = bytearray(1024)
    struct.pack_into('<4i', hdr, 0, 2048, 2048, 1, 2)
    struct.pack_into('<3i', hdr, 28, 2048, 2048, 1)
    hdr[208:212] = b'MAP '
    struct.pack_into('<i', hdr, 212, 0x00004144)
    wrong.write_bytes(bytes(hdr) + struct.pack('<f', 1.0) * (2048 * 2048))
    info['gain_wrong_2048'] = {'sha256': sha256_file(wrong), 'note': 'QF-written 2048x2048 float32 ones'}
    dump(info, log)
    return inp, info


# ---------------------------------------------------------------- case setup and run

def case_inputs(name, opts, inp):
    tag = name.split('_')[0]
    gain = None
    if tag in BATCH:
        fam, movies, det = 'f3', [D / CORPUS['f3'], inp / f'{BATCH[tag]}.eer', D / CORPUS['f3b']], 4096
    elif tag == 'b6':
        fam, movies, det, gain = 'g', [D / CORPUS['g'], D / CORPUS['g']], 4096, inp / 'gain_wrong_2048.mrc'
    elif tag.rstrip('n') in SYN_FOR:
        fx = SYN_FOR[tag.rstrip('n')]
        fam, movies, det = None, [inp / f'{fx}.eer'], int(SYNTH[fx][SYNTH[fx].index('--det') + 1])
    else:  # c*, cc*, d*, m*: family token in the name
        fam = next(t for t in name.split('_')[1:] if t in ('f3', 'f4', 'g'))
        movies, det = [D / CORPUS[fam]], 4096
    if '--gainref' in opts and gain is None:
        gain = D / CORPUS['g_gain']
    defect = HERE / 'item_records' / 'eer_defects' / f'defect_{name}.txt' if '--defect_file' in opts else None
    up = int(opts[opts.index('--eer_upsampling') + 1])
    side = det // 2 if up == -1 else det << (up - 1)
    base = ANGPIX.get(fam, 1.0)  # as #208's mkcase.py: family pixel size scaled by the upsampling
    angpix = base / (2 ** (up - 1)) if up > 0 else base * 2
    return movies, gain, defect, side, angpix


def setup(name, rec, inp):
    opts = list(rec['options'])
    movies, gain, defect, side, angpix = case_inputs(name, opts, inp)
    d = ROOT / 'runs' / name
    if d.exists():
        shutil.rmtree(d)
    (d / 'in' / 'Movies').mkdir(parents=True)
    names = ['Movies/movie.eer'] if len(movies) == 1 else [f'Movies/movie{i + 1}.eer' for i in range(len(movies))]
    for n, src in zip(names, movies):
        os.symlink(Path(src).resolve(), d / 'in' / n)
    if gain:
        os.symlink(Path(gain).resolve(), d / 'in' / opts[opts.index('--gainref') + 1])
    if defect:
        shutil.copy(defect, d / 'in' / opts[opts.index('--defect_file') + 1])
    star = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
            '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5', '_rlnAmplitudeContrast #6',
            f'opticsGroup1 1 {angpix} 300 2.7 0.1', '', '# version 30001', '', 'data_movies', '', 'loop_',
            '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2'] + [f'{n} 1' for n in names] + ['']
    (d / 'in' / 'movies.star').write_text('\n'.join(star))
    dump({'schema_version': 1, 'expected_shape_xyz': [side, side, 1], 'joint_star': 'corrected_micrographs.star',
          'movies': names, 'input_star_sha256': sha256_file(d / 'in' / 'movies.star')}, d / 'in' / 'manifest.json')
    return d, opts


def compare(d, a, b):
    allow = []
    for p in ALLOW:
        allow += ['--allow-added-log-line', p]
    r = run_tool([PY, COMPARE_TREES, d / f'out-{a}', d / f'out-{b}', '--manifest', d / 'in' / 'manifest.json',
                  '--input-star', d / 'in' / 'movies.star', *allow, '--json-out', d / f'compare-{a}-vs-{b}.json'])
    return {'rc': r['rc'], 'tail': (r['stdout'] + r['stderr'])[-500:]}


# ---------------------------------------------------------------- grading

def payload16(path):
    """#208 analyse_batch.py: sha256[:16] of the MRC payload after the header and extended header."""
    with open(path, 'rb') as f:
        hd = f.read(1024)
        f.seek(1024 + struct.unpack('<i', hd[92:96])[0])
        h = hashlib.sha256()
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()[:16]


def inventory(out, text):
    """Published products, payload hashes, root-normalised STAR digests, frame counts, D6 warnings."""
    inv = {'products': {}, 'stars': {}, 'frames': {}, 'joint_star': (out / 'corrected_micrographs.star').exists()}
    if out.exists():
        for p in sorted(out.rglob('*')):
            if not p.is_file():
                continue
            rel = str(p.relative_to(out))
            if p.suffix == '.mrc':
                inv['products'][rel] = payload16(p)
            elif p.suffix == '.star':
                body = p.read_bytes().replace(str(out).encode(), b'<OUT>').replace(str(out.resolve()).encode(), b'<OUT>')
                inv['stars'][rel] = hashlib.sha256(body).hexdigest()
                if rel != 'corrected_micrographs.star':
                    inv['products'][rel] = 'star'
            elif p.suffix == '.log' and p.name.startswith('movie'):
                m = re.search(r'Movie size: X = (\d+) Y = (\d+) N = (\d+)', p.read_text(errors='replace'))
                inv['frames'][p.name] = int(m.group(3)) if m else None
    inv['skip_warning_frames'] = sorted(int(f) for f in re.findall(
        r'WARNING: The number of pixels is not right in \S+ frame (\d+)\. Probably', text))
    return inv


def grade_case(name, rec, d, arms_res, texts):
    """All product/publication predicates on the case directory as it stands (see module docstring)."""
    problems = []
    inv = {a: inventory(d / f'out-{a}', texts.get(a, '')) for a in arms_res}
    for a, r in arms_res.items():
        if r['rc'] not in (0, None) and inv[a]['joint_star']:
            problems.append(f'{a}: exited {r["rc"]} but wrote a completion (joint) STAR')
        if rec['arm_ingest'].get(a) == 'compact' and rec['recorded'].get(a, {}).get('rc') not in (0, None):
            if COMPACT_REFUSAL not in texts.get(a, ''):
                problems.append(f'{a}: refusal message missing')
            if inv[a]['products'] or inv[a]['stars']:
                problems.append(f'{a}: refused but published {sorted(inv[a]["products"]) + sorted(inv[a]["stars"])}')
    if name.startswith('o') and 'auto' in arms_res:
        logs = ''.join(p.read_text(errors='replace') for p in (d / 'out-auto').rglob('*.log'))
        overflow = rec['recorded']['auto']['routes'] == ['float']
        if overflow != (GUARD_LINE in logs):
            problems.append(f'auto: uint16 guard line {"missing" if overflow else "unexpected"}')
    if name in EXPECT_ERROR:
        for a in arms_res:
            if EXPECT_ERROR[name] not in texts.get(a, '') or inv[a]['products']:
                problems.append(f'{a}: expected explicit failure {EXPECT_ERROR[name]!r} with nothing published')
    batch = rec.get('batch')
    if batch:
        for a in ('auto', 'float'):
            want, have = batch[a], inv[a]
            if set(have['products']) != set(want['products']):
                problems.append(f'{a}: published {sorted(have["products"])} != #208 {sorted(want["products"])}')
            for rel, h in want['products'].items():
                if rel.endswith('.mrc') and rel in have['products'] and have['products'][rel] != h:
                    problems.append(f'{a}: {rel} payload {have["products"][rel]} != #208 {h}')
            if have['joint_star'] != want['joint_star']:
                problems.append(f'{a}: joint STAR {have["joint_star"]} != #208 {want["joint_star"]}')
            if have['frames'] != want['frames']:
                problems.append(f'{a}: frame counts {have["frames"]} != #208 {want["frames"]}')
            if have['skip_warning_frames'] != want['skip_warning_frames']:
                problems.append(f'{a}: D6 skip warnings at {have["skip_warning_frames"]} != #208 {want["skip_warning_frames"]}')
            for e in want['errors']:
                if e not in texts.get(a, ''):
                    problems.append(f'{a}: missing #208 error {e[:80]!r}')
        pa = {k: v for k, v in inv['auto']['products'].items() if k.endswith('.mrc')}
        pf = {k: v for k, v in inv['float']['products'].items() if k.endswith('.mrc')}
        sa = {k: v for k, v in inv['auto']['stars'].items()}
        sf = {k: v for k, v in inv['float']['stars'].items()}
        if pa != pf:
            problems.append(f'auto vs float MRC payloads differ: {sorted(k for k in set(pa) | set(pf) if pa.get(k) != pf.get(k))}')
        per_movie = lambda s: {k: v for k, v in s.items() if k != 'corrected_micrographs.star'}
        if per_movie(sa) != per_movie(sf):
            problems.append('auto vs float per-movie STARs differ')
    return problems, inv


def run_one(name, rec, inp, binary_override=None, expect_override=None):
    d, opts = setup(name, rec, inp)
    rec = dict(rec, **(expect_override or {}))
    res = {'case': name, 'desc': rec['desc'], 'recorded': rec['recorded'],
           'recorded_compare_rc': rec['recorded_compare_rc'], 'arms': {}, 'problems': []}
    if rec['binary_kind'] == 'cpu':
        i = opts.index('--gpu')
        del opts[i:i + 2]  # as #208's eer_cpu_compare.py: the CPU build has no GPU
        arms = [('ref_cpu_1db86902', Q1_CPU, None, 'base0ac2726a'), ('cpu', BIN['cpu'], None, 'cand1db86902')]
    else:
        arms = [(a, binary_override or BIN['nvcomp'], rec['arm_ingest'][a], a) for a in rec['arms']]
    texts = {}
    for arm, binary, ingest, rec_arm in arms:
        out = d / f'out-{arm}'
        out.mkdir()
        wit = d / f'{arm}.witness'
        args = ['--i', 'movies.star', '--o', f'{out}/', *opts]
        if ingest:
            args += ['--ingest', ingest, '--ingest_witness', wit]
        r = run_case(f'{name}-{arm}', binary, args, d / 'in', d / 'logs', gpu=rec['binary_kind'] != 'cpu', witness=wit)
        texts[arm] = Path(r['stdout']).read_text(errors='replace')
        routes = [l.split()[-1] for l in (r.get('ingest_witness') or [])]
        res['arms'][arm] = {'rc': r.get('rc'), 'routes': routes, 'binary_sha256': r['binary_sha256'],
                            'gpu_witness': r.get('gpu_witness'), 'max_rss_kib': r.get('max_rss_kib'), 'wall_s': r.get('wall_s')}
        want = rec['recorded'][rec_arm]
        if r.get('rc') != want['rc']:
            res['problems'].append(f'{arm}: rc {r.get("rc")} != recorded {want["rc"]}')
        if routes != want['routes']:
            res['problems'].append(f'{arm}: routes {routes} != recorded {want["routes"]}')
        w = r.get('gpu_witness') or {}
        if rec['binary_kind'] != 'cpu' and r.get('rc') == 0 and not w.get('on_lane_gpu_only'):
            res['problems'].append(f'{arm}: not witnessed on the lane GPU only ({w.get("uuids_seen_for_pid")})')
    pair = rec['compare'] or (['ref_cpu_1db86902', 'cpu'] if rec['binary_kind'] == 'cpu' else None)
    if pair and rec['recorded_compare_rc'] is not None:
        if all(res['arms'][x]['rc'] == 0 for x in pair):
            res['compare'] = compare(d, *pair)
            if (res['compare']['rc'] == 0) != (rec['recorded_compare_rc'] == 0):
                res['problems'].append(f'compare {pair}: rc {res["compare"]["rc"]}, recorded {rec["recorded_compare_rc"]}')
        else:
            res['problems'].append(f'compare {pair} not run: an arm failed')
    graded_arms = {a: v for a, v in res['arms'].items() if rec['binary_kind'] != 'cpu'}
    probs, inv = grade_case(name, rec, d, graded_arms, texts)
    res['problems'] += probs
    res['inventory'] = inv
    res['verdict'] = 'PASS' if not res['problems'] else 'FAIL'
    return res, d, texts


NEGATIVE = {  # case -> (description, mutation of a copy of the case directory)
    'b6_wronggain': 'per-movie and joint STAR planted after the refusal',
    'b2_randbytes': 'one payload byte flipped in the float arm\'s movie2.mrc',
    'o1_ovf_upm1_g16384': 'an MRC planted in the refused compact arm',
    'b3_stripff': 'D6 skip warning removed from the auto arm\'s output',
}


def negative_control(name, rec, d, res, texts):
    nd = d.parent / f'{name}.negative'
    if nd.exists():
        shutil.rmtree(nd)
    shutil.copytree(d, nd, symlinks=True)
    t = dict(texts)
    if name == 'b6_wronggain':
        (nd / 'out-auto' / 'Movies').mkdir(parents=True, exist_ok=True)
        (nd / 'out-auto' / 'Movies' / 'movie1.star').write_text('data_general\n')
        (nd / 'out-auto' / 'corrected_micrographs.star').write_text('data_micrographs\n')
    elif name == 'b2_randbytes':
        p = nd / 'out-float' / 'Movies' / 'movie2.mrc'
        b = bytearray(p.read_bytes())
        b[-5] ^= 0x01
        p.write_bytes(bytes(b))
    elif name == 'o1_ovf_upm1_g16384':
        src = next((nd / 'out-float').rglob('*.mrc'))
        (nd / 'out-compact' / 'Movies').mkdir(parents=True, exist_ok=True)
        shutil.copy(src, nd / 'out-compact' / 'Movies' / 'movie.mrc')
    elif name == 'b3_stripff':
        t['auto'] = re.sub(r'WARNING: The number of pixels is not right[^\n]*', '', t['auto'])
    probs, _ = grade_case(name, rec, nd, {a: v for a, v in res['arms'].items()}, t)
    shutil.rmtree(nd)
    return {'mutation': NEGATIVE[name], 'problems': probs, 'rejected': bool(probs)}


def finish(d):
    for p in list(d.rglob('*.mrc')) + list(d.rglob('*.pdf')):
        if p.is_file() and not p.is_symlink():
            p.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='', help='comma-separated case-name prefixes')
    ap.add_argument('--skip-heavy', action='store_true', help='skip up2-F4 and up3 cases (reported UNRUN)')
    ap.add_argument('--negative-controls', action='store_true', help='mutate real outputs of b6/b2/o1/b3; each must fail')
    ap.add_argument('--noguard-binary', default='', help='guard-removed build: run o1n and an o5 equivalent (powered control)')
    ap.add_argument('--write-synth-recipe', action='store_true', help='(recipe author only) record the frozen fixture recipe')
    a = ap.parse_args()
    inp, info = ensure_inputs(ROOT / 'inputs.json', a.write_synth_recipe)
    if a.write_synth_recipe:
        print(json.dumps(json.loads(RECIPE_FILE.read_text()).get('overflow_cases'), indent=1))
        return 0
    summary = {'record': RECORD['source'], 'recipe_sha256': sha256_file(RECIPE_FILE),
               'binaries': {'nvcomp': sha256_file(BIN['nvcomp']), 'cpu': sha256_file(BIN['cpu']),
                            'ref_cpu_1db86902': sha256_file(Q1_CPU)}, 'cases': {}, 'negative_controls': {}}
    if a.noguard_binary:
        # powered control: without the guard, the replacement fixtures must wrap uint16, so compact != float
        nb = Path(a.noguard_binary)
        summary['noguard_binary_sha256'] = sha256_file(nb)
        o5 = RECORD['cases']['o5_ovf_up2_g65536_8K']
        cases = {'o1n_NOGUARD_upm1_g16384': (RECORD['cases']['o1n_NOGUARD_upm1_g16384'], None),
                 'o5n_NOGUARD_up2_g65536_8K': (dict(o5, arms=['auto', 'float'], compare=['auto', 'float']),
                                                {'recorded': {'auto': {'rc': 0, 'routes': ['compact']},
                                                              'float': {'rc': 0, 'routes': ['float']}},
                                                 'recorded_compare_rc': 1})}
        for name, (rec, override) in cases.items():
            r, d, _ = run_one(name, rec, inp, binary_override=nb, expect_override=override)
            finish(d)
            summary['cases'][name] = {'verdict': r['verdict'], 'problems': r['problems'],
                                      'compare_rc': (r.get('compare') or {}).get('rc')}
            dump(r, ROOT / 'results' / f'{name}.json')
            print(f'{name}: {r["verdict"]} compare rc {(r.get("compare") or {}).get("rc")} {r["problems"]}', flush=True)
        dump(summary, ROOT / 'summary-noguard.json')
        return 0 if all(c['verdict'] == 'PASS' for c in summary['cases'].values()) else 1
    for name, rec in RECORD['cases'].items():
        if name in SKIP:
            summary['cases'][name] = {'verdict': 'N/A', 'reason': SKIP[name]}
            continue
        if a.only and not any(name.startswith(p) for p in a.only.split(',')):
            continue
        if a.skip_heavy and name in HEAVY:
            summary['cases'][name] = {'verdict': 'UNRUN', 'reason': '--skip-heavy'}
            continue
        t0 = time.time()
        r, d, texts = run_one(name, rec, inp)
        if a.negative_controls and name in NEGATIVE:
            nc = negative_control(name, rec, d, r, texts)
            summary['negative_controls'][name] = nc
            print(f'  negative control {name}: rejected={nc["rejected"]} {nc["problems"][:2]}', flush=True)
        finish(d)
        dump(r, ROOT / 'results' / f'{name}.json')
        summary['cases'][name] = {'verdict': r['verdict'], 'problems': r['problems']}
        print(f'{name}: {r["verdict"]} {r["problems"]} ({time.time() - t0:.0f}s)', flush=True)
        dump(summary, ROOT / 'summary.json')
    v = [c['verdict'] for c in summary['cases'].values()]
    summary['totals'] = {k: v.count(k) for k in ('PASS', 'FAIL', 'UNRUN', 'N/A')}
    nc_ok = all(n['rejected'] for n in summary['negative_controls'].values())
    summary['negative_controls_all_rejected'] = nc_ok
    dump(summary, ROOT / 'summary.json')
    print('item 11:', summary['totals'], 'negative controls rejected:', nc_ok)
    if v.count('FAIL') or not nc_ok:
        return 1
    return 2 if (v.count('UNRUN') or a.only) else 0


if __name__ == '__main__':
    sys.exit(main())
