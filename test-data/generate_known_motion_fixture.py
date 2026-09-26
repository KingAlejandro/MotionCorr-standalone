#!/usr/bin/env python3
"""Generate reproducible synthetic movies with a known global *and* local motion field.

Unlike ``generate_synthetic_fixture.py``, which rolls one image by a per-frame integer or
Fourier shift, this generator injects a spatially varying displacement field and records the
field itself -- not just a per-frame trajectory -- as ground truth.

Two properties make the fixture usable as a truth standard:

* The base image is an analytic sum of Gaussians, so a warped frame is produced by evaluating
  the Gaussians at the warped coordinates. No image is ever resampled, so the fixture carries
  no interpolation error of its own.
* The injected local field lies inside the span of the third-order polynomial motion model
  that MotionCorr fits (``ThirdOrderPolynomialModel``), so any residual is estimation error
  rather than model-mismatch error.

Conventions are documented in ``agents/designs/issue_59_known_motion_local_field_gates.md``
and restated in the emitted ground-truth JSON.

Sign convention, stated once:
    injected_motion  = displacement of the specimen content in frame f, relative to the first
                       frame, in pixels, +x = increasing column, +y = increasing row.
    expected_applied_field = -injected_motion
                       = the displacement MotionCorr must apply to the frame to correct it,
                         which is what it reports via Micrograph::getShiftAt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

import numpy as np

SCHEMA_VERSION = "known-motion-fixture/1"

# --- injected motion, in pixels -------------------------------------------------------------
# Global: fast doming relaxation plus steady drift. z is 0-based frame index.
GLOBAL_SPEC = {
    "x": {"amp": 3.20, "tau": 1.7, "drift": 0.28},
    "y": {"amp": -2.40, "tau": 1.3, "drift": -0.10},
}

# Local: terms of the form coeff * tau**p * (u**a * v**b), tau = z / (n_frames - 1),
# u = ix/nx - 0.5, v = iy/ny - 0.5. Every term carries a positive power of tau, so the local
# field is exactly zero on the first frame -- matching the motion model, whose basis is
# {z, z^2, z^3} x {1, u, u^2, v, v^2, uv} and which therefore also vanishes at z = 0.
LOCAL_TERMS_X = [
    # (coeff, power of tau, power of u, power of v)
    (2.40, 1, 1, 0),
    (1.40, 1, 0, 1),
    (1.10, 2, 2, 0),
    (-0.90, 2, 1, 1),
]
LOCAL_TERMS_Y = [
    (-1.90, 1, 0, 1),
    (1.20, 1, 1, 0),
    (0.80, 2, 0, 2),
    (0.70, 2, 1, 1),
]

CASES = {
    # name: nx, ny, n_frames, local_scale, noise_rel, n_hot, patch_x, patch_y
    # role="gate": must meet the declared tolerances; safe for CI.
    # role="characterization": measured and reported in full, deliberately probing a regime
    # where the estimator, not the implementation, is the limit. See Amendment 1 of the design
    # record for why the two roles exist and what evidence separated them.
    "km_global_hisnr": dict(nx=512, ny=512, n_frames=12, local_scale=0.0,
                            noise_rel=0.05, n_hot=0, patch_x=1, patch_y=1,
                            skip_defect=True, role="gate"),
    "km_local_hisnr": dict(nx=512, ny=512, n_frames=12, local_scale=1.0,
                           noise_rel=0.05, n_hot=0, patch_x=4, patch_y=4,
                           skip_defect=True, role="gate"),
    # 768x512 rather than 384x256: the non-square case exists to catch a swap of the nx/ny
    # normalisation, which it can do at any size, and 4x4 patches on 384x256 carry only 61k
    # pixel-frames -- too few for the estimator floor to sit under the declared tolerance.
    "km_local_nonsquare": dict(nx=768, ny=512, n_frames=12, local_scale=1.0,
                               noise_rel=0.05, n_hot=0, patch_x=4, patch_y=4,
                               skip_defect=True, role="gate"),
    "km_local_noisy": dict(nx=512, ny=512, n_frames=12, local_scale=1.0,
                           noise_rel=10.0, n_hot=6, patch_x=4, patch_y=4,
                           skip_defect=False, role="characterization"),
    # Same field and same per-pixel SNR as km_local_noisy, at a scale whose patch information
    # content approaches a tutorial micrograph. 400 MB and ~2 min to build, so it is opt-in:
    # it answers "is the noisy failure a defect or information starvation?", it is not a
    # per-commit regression case.
    "km_local_realscale": dict(nx=2048, ny=2048, n_frames=24, local_scale=1.0,
                               noise_rel=10.0, n_hot=6, patch_x=5, patch_y=5,
                               skip_defect=False, heavy=True, role="gate"),
}
HEAVY = {name for name, cfg in CASES.items() if cfg.get("heavy")}

BASE_SEED = 20260925
PIXEL_SIZE = 0.885   # A/px, deliberately not 1.0 so px/A confusion is visible
VOLTAGE = 300.0
DOSE_PER_FRAME = 1.277
GRID_N = 9           # declared evaluation grid, GRID_N x GRID_N positions
PARTICLE_DENSITY = 400.0 / (512.0 * 512.0)


# --- the injected field ---------------------------------------------------------------------

def global_motion(z: np.ndarray) -> np.ndarray:
    """Global injected motion in px for 0-based frame indices z. Shape (len(z), 2)."""
    gx = GLOBAL_SPEC["x"]
    gy = GLOBAL_SPEC["y"]
    mx = gx["amp"] * (1.0 - np.exp(-z / gx["tau"])) + gx["drift"] * z
    my = gy["amp"] * (1.0 - np.exp(-z / gy["tau"])) + gy["drift"] * z
    # Anchor at frame 0 exactly: motion is defined relative to the first frame.
    mx = mx - mx[0]
    my = my - my[0]
    return np.stack([mx, my], axis=-1)


def local_motion(tau, u, v, local_scale: float):
    """Local injected motion in px. tau, u, v broadcast together; returns (..., 2)."""
    lx = np.zeros(np.broadcast(tau, u, v).shape, dtype=np.float64)
    ly = np.zeros_like(lx)
    for coeff, pt, pu, pv in LOCAL_TERMS_X:
        lx = lx + coeff * tau ** pt * u ** pu * v ** pv
    for coeff, pt, pu, pv in LOCAL_TERMS_Y:
        ly = ly + coeff * tau ** pt * u ** pu * v ** pv
    return local_scale * np.stack([lx, ly], axis=-1)


def injected_motion(frames, ix, iy, nx, ny, n_frames, local_scale):
    """Injected motion in px at 0-based frame indices `frames` and pixel coords (ix, iy).

    frames: (F,) ; ix, iy: broadcastable arrays of pixel coordinates.
    Returns (F, ..., 2).
    """
    frames = np.asarray(frames, dtype=np.float64)
    u = np.asarray(ix, dtype=np.float64) / nx - 0.5
    v = np.asarray(iy, dtype=np.float64) / ny - 0.5
    tau = (frames / (n_frames - 1.0)).reshape((-1,) + (1,) * np.ndim(u))
    g = global_motion(frames).reshape((-1,) + (1,) * np.ndim(u) + (2,))
    l = local_motion(tau, u[None, ...], v[None, ...], local_scale)
    return g + l


# --- base image -----------------------------------------------------------------------------

def make_particles(rng, nx, ny):
    n_particles = max(20, int(round(PARTICLE_DENSITY * nx * ny)))
    cx = rng.uniform(0.0, nx, n_particles)
    cy = rng.uniform(0.0, ny, n_particles)
    sigma = rng.uniform(2.0, 6.0, n_particles)
    # Signed contrast: protein density in a CTF-modulated micrograph varies about the mean in
    # both directions. An all-positive blob field is strongly skewed and unrealistic.
    amp = rng.uniform(10.0, 30.0, n_particles) * rng.choice([-1.0, 1.0], n_particles)
    return cx, cy, sigma, amp


CUTOFF_SIGMA = 8.0   # exp(-32) ~ 1.3e-14: below float32 resolution against a background of 100
PERIODIC_TILES = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0), (1, 1)]


def render(cx, cy, sigma, amp, xw, yw, nx, ny, background=100.0, boxes=None):
    """Evaluate the analytic base image at (possibly warped) coordinates xw, yw.

    The base image is **periodic**: every particle is rendered together with its eight
    neighbouring image tiles. This matters more than it looks. A Fourier shift is cyclic, so an
    aligner that estimates a shift from the whole frame implicitly assumes the content wraps. If
    the fixture's content does not wrap, a band of width |shift| along two edges has content in
    one frame and nothing in the other, and the cross-correlation optimum is dragged toward
    zero. Measured on an earlier non-periodic version of this fixture, that alone biased the
    apparent global shift low by 1.2 % -- an artefact that would have been charged to MotionCorr.
    Cropping 20 px of border recovered the declared truth to 1.5e-4 px, which is how the artefact
    was identified.

    ``boxes`` restricts each (particle, tile) pair to its support. Outside ``CUTOFF_SIGMA`` a
    Gaussian contributes exp(-32) times its amplitude, below the float32 resolution of the
    stored image, so restricted and unrestricted rendering agree bit-for-bit after the cast.
    """
    out = np.full(xw.shape, background, dtype=np.float64)
    k = 0
    for c0, c1, s, a in zip(cx, cy, sigma, amp):
        for tx, ty in PERIODIC_TILES:
            ccx, ccy = c0 + tx * nx, c1 + ty * ny
            if boxes is None:
                dx = xw - ccx
                dy = yw - ccy
                out += a * np.exp(-(dx * dx + dy * dy) / (2.0 * s * s))
            else:
                y0, y1, x0, x1 = boxes[k]
                k += 1
                if y0 >= y1 or x0 >= x1:
                    continue
                dx = xw[y0:y1, x0:x1] - ccx
                dy = yw[y0:y1, x0:x1] - ccy
                out[y0:y1, x0:x1] += a * np.exp(-(dx * dx + dy * dy) / (2.0 * s * s))
    return out


def particle_boxes(cx, cy, sigma, shift_xy, nx, ny, slack=3.0):
    """Output-array slices enclosing each (particle, periodic tile) pair for one frame.

    A particle at ``c`` contributes at output pixel ``p`` where ``p - M(f, p) ~= c``, so the
    support sits near ``c + M(f, c)``. ``slack`` covers the variation of ``M`` across the box.
    """
    boxes = []
    bx, by = shift_xy
    for c0, c1, s in zip(cx, cy, sigma):
        h = CUTOFF_SIGMA * s + slack
        for tx, ty in PERIODIC_TILES:
            ccx, ccy = c0 + tx * nx, c1 + ty * ny
            x0 = int(np.floor(ccx + bx - h)); x1 = int(np.ceil(ccx + bx + h)) + 1
            y0 = int(np.floor(ccy + by - h)); y1 = int(np.ceil(ccy + by + h)) + 1
            boxes.append((max(0, y0), min(ny, y1), max(0, x0), min(nx, x1)))
    return boxes


# --- MRC ------------------------------------------------------------------------------------

def write_mrc_stack(path: Path, stack: np.ndarray, pixel_size: float) -> None:
    ny, nx = stack.shape[1], stack.shape[2]
    nz = stack.shape[0]
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, nz, 2)
    struct.pack_into("<3i", header, 16, 0, 0, 0)
    struct.pack_into("<3i", header, 28, nx, ny, nz)
    struct.pack_into("<3f", header, 40, nx * pixel_size, ny * pixel_size, nz * pixel_size)
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<3f", header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
    struct.pack_into("<2i", header, 88, 0, 0)
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))
    struct.pack_into("<f", header, 216, float(stack.std()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(header)
        stack.astype("<f4").tofile(fh)


STAR_TEMPLATE = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 {pixel_size:.6f} {voltage:.1f} 2.7 0.1


# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
{movie} 1
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


# --- generation -----------------------------------------------------------------------------

def generate_case(name: str, outdir: Path, repo_root: Path,
                  noise_rel: float | None = None, noise_seed_offset: int = 0,
                  label: str | None = None) -> dict:
    """Generate one case.

    ``noise_rel`` and ``noise_seed_offset`` exist for the noise response curve and the
    bias-versus-variance replicate study: they change only the detector noise, never the
    injected motion field or the particle layout, so the ground truth is bit-identical across
    replicates. ``label`` renames the output files so replicates do not collide.
    """
    cfg = dict(CASES[name])
    if noise_rel is not None:
        cfg["noise_rel"] = noise_rel
    out_name = label or name
    nx, ny = cfg["nx"], cfg["ny"]
    n_frames = cfg["n_frames"]
    local_scale = cfg["local_scale"]
    if nx % 2 or ny % 2:
        raise ValueError("MotionCorr requires even image dimensions")

    # Deterministic per-case seed from a stable digest of the case name: independent of Python
    # hash randomisation, and unchanged when other cases are added or renamed. An index into
    # sorted(CASES) would silently re-roll every existing fixture the moment a case is added.
    seed = BASE_SEED + int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % 100000
    rng = np.random.default_rng(seed)

    cx, cy, sig, amp = make_particles(rng, nx, ny)

    iy_grid, ix_grid = np.mgrid[0:ny, 0:nx].astype(np.float64)
    clean0 = render(cx, cy, sig, amp, ix_grid, iy_grid, nx, ny,
                    boxes=particle_boxes(cx, cy, sig, (0.0, 0.0), nx, ny))
    base_std = float(clean0.std())
    noise_sigma = cfg["noise_rel"] * base_std

    # Fixed detector-coordinate hot pixels (not warped: a detector defect does not move).
    hot_rng = np.random.default_rng(seed + 977)
    hot_x = hot_rng.integers(8, nx - 8, cfg["n_hot"])
    hot_y = hot_rng.integers(8, ny - 8, cfg["n_hot"])
    hot_val = float(clean0.mean() + 40.0 * base_std)

    frames = np.arange(n_frames)
    field = injected_motion(frames, ix_grid, iy_grid, nx, ny, n_frames, local_scale)

    stack = np.empty((n_frames, ny, nx), dtype=np.float32)
    noise_rng = np.random.default_rng(seed + 31337 + noise_seed_offset)
    for f in range(n_frames):
        # frame(p) = base(p - M(f, p)): content displaced by +M.
        wx = ix_grid - field[f, :, :, 0]
        wy = iy_grid - field[f, :, :, 1]
        shift = (float(field[f, :, :, 0].mean()), float(field[f, :, :, 1].mean()))
        span = max(float(np.abs(field[f, :, :, 0] - shift[0]).max()),
                   float(np.abs(field[f, :, :, 1] - shift[1]).max()))
        boxes = particle_boxes(cx, cy, sig, shift, nx, ny, slack=span + 3.0)
        warped = render(cx, cy, sig, amp, wx, wy, nx, ny, boxes=boxes)
        if noise_sigma > 0:
            warped = warped + noise_rng.normal(0.0, noise_sigma, warped.shape)
        for hx, hy in zip(hot_x, hot_y):
            warped[hy, hx] = hot_val
        stack[f] = warped.astype(np.float32)

    outdir.mkdir(parents=True, exist_ok=True)
    mrcs = outdir / f"{out_name}.mrcs"
    write_mrc_stack(mrcs, stack, PIXEL_SIZE)
    star = outdir / f"{out_name}.star"
    star.write_text(STAR_TEMPLATE.format(pixel_size=PIXEL_SIZE, voltage=VOLTAGE,
                                         movie=mrcs.name))

    # Declared evaluation grid: endpoint-inclusive, so the four corners and all four edges are
    # sampled. Corners are where the local polynomial is largest and where a sign or axis defect
    # is loudest; they are also inside the interpolation-clamped margin, so they are classified
    # as "border" by the checker and reported separately rather than gated.
    gx = np.linspace(0.0, nx - 1.0, GRID_N)
    gy = np.linspace(0.0, ny - 1.0, GRID_N)
    gyy, gxx = np.meshgrid(gy, gx, indexing="ij")
    grid_x = gxx.ravel()
    grid_y = gyy.ravel()
    grid_field = injected_motion(frames, grid_x, grid_y, nx, ny, n_frames, local_scale)

    gt = {
        "schema": SCHEMA_VERSION,
        "case": out_name,
        "base_case": name,
        "movie_file": mrcs.name,
        "input_star": star.name,
        "movie_sha256": sha256(mrcs),
        "source_commit": git_commit(repo_root),
        "generator": Path(__file__).name,
        "seed": seed,
        "noise_seed_offset": noise_seed_offset,
        "geometry": {
            "nx": nx, "ny": ny, "n_frames": n_frames,
            "pixel_size_angstrom": PIXEL_SIZE,
            "voltage_kv": VOLTAGE,
            "dose_per_frame": DOSE_PER_FRAME,
        },
        "recommended_run": {
            "patch_x": cfg["patch_x"], "patch_y": cfg["patch_y"],
            "bin_factor": 1, "first_frame_sum": 1,
            # Hot-pixel replacement draws from rand(); on the defect-free cases it would only
            # mangle bright particle centres, so it is switched off there. km_local_noisy keeps
            # it on so the defect path is exercised against six known injected hot pixels.
            "skip_defect": bool(cfg["skip_defect"]),
            "heavy": bool(cfg.get("heavy", False)),
            "role": cfg.get("role", "gate"),
            "expected_hot_pixels_detected": 0 if cfg["skip_defect"] else int(cfg["n_hot"]),
        },
        "conventions": {
            "frame_index": "0-based z in this file; the output STAR uses 1-based "
                           "rlnMicrographFrameNumber, z = frame - rlnMicrographStartFrame",
            "axes": "x = column = fast axis, y = row = slow axis, origin at pixel (0,0)",
            "normalised_position": "u = ix/nx - 0.5, v = iy/ny - 0.5",
            "units": "pixels of the unbinned grid; angstrom = pixel * pixel_size_angstrom",
            "injected_motion": "displacement of specimen content in frame f relative to frame 0",
            "expected_applied_field": "-injected_motion; equals MotionCorr's "
                                      "globalShift[f] + ThirdOrderPolynomialModel(z,u,v)",
        },
        "motion_spec": {
            "global": GLOBAL_SPEC,
            "local_terms_x": LOCAL_TERMS_X,
            "local_terms_y": LOCAL_TERMS_Y,
            "local_scale": local_scale,
            "tau": "z / (n_frames - 1)",
            "term_form": "coeff * tau**p_tau * u**p_u * v**p_v",
        },
        "noise": {
            "relative_sigma": cfg["noise_rel"],
            "absolute_sigma": noise_sigma,
            "noise_free_image_std": base_std,
            "per_pixel_snr": (1.0 / cfg["noise_rel"]) if cfg["noise_rel"] > 0 else None,
            "model": "i.i.d. Gaussian in detector coordinates, not warped",
        },
        "periodicity": {
            "base_image_periodic": True,
            "why": "a Fourier shift is cyclic; non-wrapping content puts a mismatched band of "
                   "width |shift| along two edges and biases any full-frame cross-correlation "
                   "toward zero shift (measured at 1.2 % on a non-periodic build of this "
                   "fixture)",
        },
        "defects": {
            "n_hot_pixels": int(cfg["n_hot"]),
            "hot_pixels_xy": [[int(a), int(b)] for a, b in zip(hot_x, hot_y)],
            "hot_pixel_value": hot_val,
        },
        "grid": {
            "n_per_axis": GRID_N,
            "layout": "endpoint-inclusive: linspace(0, n-1, GRID_N) on each axis",
            "x": grid_x.tolist(),
            "y": grid_y.tolist(),
        },
        # [frame][position][x,y], in pixels
        "injected_motion_field": np.round(grid_field, 12).tolist(),
        "expected_applied_field": np.round(-grid_field, 12).tolist(),
    }
    gt_path = outdir / f"{out_name}_ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2) + "\n")

    return {
        "case": out_name, "mrcs": str(mrcs), "star": str(star), "ground_truth": str(gt_path),
        "sha256": gt["movie_sha256"], "bytes": mrcs.stat().st_size,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", choices=sorted(CASES) + ["all"], default="all")
    ap.add_argument("--outdir", type=Path,
                    default=repo_root / "test-data" / "known_motion")
    ap.add_argument("--noise-rel", type=float, default=None,
                    help="override the per-pixel noise sigma (multiple of the noise-free image "
                         "std); for the noise response curve")
    ap.add_argument("--noise-seed-offset", type=int, default=0,
                    help="change only the detector-noise stream; for replicate studies")
    ap.add_argument("--label", default=None, help="output file stem (defaults to the case name)")
    ap.add_argument("--include-heavy", action="store_true",
                    help=f"with --case all, also build the large opt-in cases: "
                         f"{', '.join(sorted(HEAVY))}")
    args = ap.parse_args()

    if (args.noise_rel is not None or args.noise_seed_offset) and args.case == "all":
        ap.error("--noise-rel / --noise-seed-offset require an explicit --case")

    if args.case == "all":
        names = [n for n in sorted(CASES) if args.include_heavy or n not in HEAVY]
    else:
        names = [args.case]
    infos = []
    for name in names:
        info = generate_case(name, args.outdir, repo_root, noise_rel=args.noise_rel,
                             noise_seed_offset=args.noise_seed_offset, label=args.label)
        infos.append(info)
        print(f"{info['case']}: {info['mrcs']} ({info['bytes']} bytes, "
              f"sha256 {info['sha256'][:16]}...)")
        print(f"    star: {info['star']}")
        print(f"    truth: {info['ground_truth']}")

    # The .mrcs files are not versioned -- they are reproducible from this script in seconds.
    # The manifest is, so a regenerated fixture that does not match the recorded hash is a
    # visible change rather than a silent one.
    if args.case == "all" and args.noise_rel is None and not args.noise_seed_offset:
        manifest = args.outdir / "MANIFEST.json"
        existing = json.loads(manifest.read_text()) if manifest.exists() else {"cases": {}}
        existing.setdefault("cases", {})
        for info in infos:
            existing["cases"][info["case"]] = {
                "movie_sha256": info["sha256"],
                "movie_bytes": info["bytes"],
                "ground_truth_sha256": hashlib.sha256(
                    Path(info["ground_truth"]).read_bytes()).hexdigest(),
            }
        existing["generator"] = Path(__file__).name
        existing["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        existing["source_commit"] = git_commit(repo_root)
        existing["note"] = ("regenerate with: python3 test-data/generate_known_motion_fixture.py "
                            "[--include-heavy]; hashes must match on any platform with the same "
                            "NumPy IEEE-754 double arithmetic")
        manifest.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
        print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
