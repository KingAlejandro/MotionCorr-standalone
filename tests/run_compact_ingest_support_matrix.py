#!/usr/bin/env python3
"""Native support matrix for the Issue #85 lane C compact uint16 TIFF ingest.

What this establishes, and what it deliberately does not:

* Every row runs the real production binary on a real device. A row PASSES only
  if that movie's own log shows `Released native uint16 host staging after
  device forward FFT.` -- the one literal that is reachable only after the
  staging buffer was allocated, every frame was uploaded as uint16,
  convertGainAndAccumulateU16Kernel ran, and the resident forward FFT
  succeeded. The `Staging this movie as native unsigned 16-bit` line is printed
  before the session is even constructed (motioncorr_runner.cpp:1472 versus
  :1584), so it is checked but never accepted as proof that the path ran.
* Each eligible row is paired with a float32-TIFF arm carrying byte-identical
  sample values. uint16 -> float32 is exact, so the two arms must produce
  identical products; the float arm additionally proves the ineligibility
  predicate by NOT showing the staging release. This is same-backend equality
  on one device. It is not a CPU/CUDA agreement result, not a motion-truth
  result, and not scientific validation.
* Products are graded by docs/issue85_laneC/compare_output_trees.py against a
  manifest that declares the complete expected product set per movie, each
  product's geometry, and the STAR associations the run must record. Counting
  and validating each arm independently is what makes a missing _noDW.mrc or a
  dropped _rlnCtfPowerSpectrum association a failure rather than a smaller
  inventory that happens to match on both sides.
* The run is bound to physical silicon by UUID: CUDA_VISIBLE_DEVICES pins the
  named device and nvidia-smi --query-compute-apps is sampled during the run and
  joined on the process's own PID. Ordinals identify nothing.

Fixtures are generated here, so no external data is required.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compact_ingest_fixtures as fixtures  # noqa: E402

SOURCE_ROOT = Path(__file__).resolve().parents[1]
COMPARATOR_PATH = SOURCE_ROOT / "docs" / "issue85_laneC" / "compare_output_trees.py"

STAGED = "Staging this movie as native unsigned 16-bit"
RELEASED = "Released native uint16 host staging after device forward FFT."
MATERIALIZED = "Materialized native uint16 frames as float for CPU fallback."
NO_SESSION = "No resident CUDA session; widening the native uint16 movie to float."
SESSION_READY = "Movie FFT: batch=1"
RESIDENT_RECON = "Reconstruction Profile (Resident VRAM)]"
REFUSAL = "Refusing CPU fallback after a fatal device error."


def _load_comparator():
    spec = importlib.util.spec_from_file_location("compact_ingest_comparator", COMPARATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


comparator = _load_comparator()


class CaseFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseFailure(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Geometry and case declarations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Geometry:
    name: str
    nx: int
    ny: int
    n_frames: int
    seed: int

    @property
    def shape(self) -> List[int]:
        return [self.nx, self.ny, 1]


# G1 and G2 differ in aspect orientation, in both extents and in frame count, so
# a second geometry is a genuinely different launch shape and a different cuFFT
# plan, not a rescaling of the first. Both extents stay even: odd end-to-end
# dimensions are reported unrun, not silently claimed.
G1 = Geometry("g1_64x48x6", 64, 48, 6, seed=11)
G2 = Geometry("g2_54x72x8", 54, 72, 8, seed=29)

ANGPIX = 1.4          # equals CTFFIND's target pixel size, so _PS.mrc needs no crop step
PS_SIZE = 32
DOSE_PER_FRAME = 1.277
VOLTAGE = 300.0
GAIN_VALUE = 1.5      # exactly representable, so the gain multiply stays bit-exact


@dataclass
class Case:
    case_id: str
    requirement: str
    geometries: List[Geometry]
    options: List[str]
    products: List[Dict[str, Any]] = field(default_factory=lambda: [{"suffix": ""}])
    gain: bool = True
    defects: bool = False
    forbidden_joint_tags: List[str] = field(default_factory=list)
    expect_u16: bool = True
    float_twin: bool = True
    repeat: bool = False
    resume_non_prefix: bool = False
    damaged_frames: Optional[int] = None
    failing_movie: Optional[int] = None
    failure_message: Optional[str] = None
    start_frame: int = 1
    note: str = ""


SUM_ONLY = [{"suffix": ""}]
NODW = [{"suffix": ""}, {"suffix": "_noDW", "joint_tag": "_rlnMicrographNameNoDW"}]
PS = [{"suffix": ""}, {"suffix": "_PS", "shape_xyz": [PS_SIZE, PS_SIZE, 1],
                       "joint_tag": "_rlnCtfPowerSpectrum"}]
EVNODD = [{"suffix": ""}, {"suffix": "_EVN"}, {"suffix": "_ODD"}]
ALL_PRODUCTS = NODW + [{"suffix": "_EVN"}, {"suffix": "_ODD"},
                       {"suffix": "_PS", "shape_xyz": [PS_SIZE, PS_SIZE, 1],
                        "joint_tag": "_rlnCtfPowerSpectrum"}]
DW = ["--dose_weighting", "--dose_per_frame", str(DOSE_PER_FRAME)]
PS_OPTS = ["--grouping_for_ps", "2", "--ps_size", str(PS_SIZE)]
EVNODD_TAGS = ["_rlnMicrographNameEven", "_rlnMicrographNameOdd"]

CASES: List[Case] = [
    Case("base_gain", "gain applied, compact ingest on the primary geometry",
         [G1], [], defects=True,
         note="carries --defect_file so the host neighbour read of the uint16 staging "
              "(motioncorr_runner.cpp:1937-1938) is exercised, not only the device kernel"),
    Case("base_nogain", "no gain: the U16 kernel's unconditional d_Iframes store",
         [G1], [], gain=False),
    Case("save_nodw", "--dose_weighting --save_noDW keeps both sums and associates the noDW image",
         [G1], DW + ["--save_noDW"], products=NODW),
    Case("power_spectrum", "--grouping_for_ps/--ps_size writes a _PS.mrc at its own geometry",
         [G1], PS_OPTS, products=PS),
    Case("even_odd", "--even_odd_split writes _EVN/_ODD and records no association outside tomography",
         [G1], ["--even_odd_split"], products=EVNODD, forbidden_joint_tags=EVNODD_TAGS),
    Case("all_output_modes", "noDW + even/odd + power spectrum together",
         [G1], DW + ["--save_noDW", "--even_odd_split"] + PS_OPTS,
         products=ALL_PRODUCTS, forbidden_joint_tags=EVNODD_TAGS),
    Case("selected_unequal_groups",
         "--first_frame_sum 2 --last_frame_sum 8 --group_frames 2 over 8 frames: groups 2,2,3",
         [G2], ["--first_frame_sum", "2", "--last_frame_sum", "8", "--group_frames", "2"],
         start_frame=2),
    Case("second_geometry", "a second, differently shaped nonsquare movie",
         [G2], []),
    Case("successive_same_geometry", "three movies of one geometry in one process",
         [G1, G1, G1], []),
    Case("successive_mixed_geometry",
         "consecutive movies of different geometry in one process",
         [G1, G2, G1], [], gain=False,
         note="no gain reference: one --gainref is bound to one geometry, which "
              "gain_geometry_mismatch covers as its own row"),
    Case("gain_geometry_mismatch",
         "a gain reference that does not match the second movie fails closed",
         [G1, G2], [], failing_movie=1, float_twin=False,
         failure_message="size of the image and the size of the gain reference do not match"),
    Case("repeat_all_output_modes", "repeat of the full output-mode run must be byte-exact",
         [G1], DW + ["--save_noDW", "--even_odd_split"] + PS_OPTS,
         products=ALL_PRODUCTS, forbidden_joint_tags=EVNODD_TAGS, repeat=True,
         float_twin=False),
    Case("resume_non_prefix",
         "--only_do_unfinished after deleting a middle movie's products",
         [G1, G1, G1], DW + ["--save_noDW"] + PS_OPTS,
         products=NODW + [{"suffix": "_PS", "shape_xyz": [PS_SIZE, PS_SIZE, 1],
                           "joint_tag": "_rlnCtfPowerSpectrum"}],
         resume_non_prefix=True, float_twin=False),
    Case("ineligible_float_tiff", "float32 TIFF never enters the compact path",
         [G1], [], expect_u16=False, float_twin=False),
    Case("ineligible_early_binning",
         "--bin_factor 2 with early binning leaves a uint16 TIFF on the float path",
         [G1], ["--bin_factor", "2"], expect_u16=False, float_twin=False),
    Case("damaged_movie_named",
         "a truncated uint16 movie beside healthy ones fails closed and is named",
         [G1, G1, G1], [], damaged_frames=3, failing_movie=1, float_twin=False),
]


# --------------------------------------------------------------------------
# Device identity
# --------------------------------------------------------------------------

def nvidia_smi(*args: str) -> str:
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, check=True).stdout


def pick_device(requested: Optional[str]) -> Dict[str, str]:
    rows = [line.split(", ") for line in
            nvidia_smi("--query-gpu=index,uuid,name,memory.used",
                       "--format=csv,noheader").strip().splitlines()]
    catalogue = [{"index": r[0], "uuid": r[1], "name": r[2], "memory_used": r[3]} for r in rows]
    require(bool(catalogue), "nvidia-smi reported no devices")
    if requested is None:
        # Honour a device the caller or the scheduler already pinned. nvidia-smi
        # ignores CUDA_VISIBLE_DEVICES, so without this a CTest inside a
        # one-GPU allocation would pick the node's physical device 0 -- someone
        # else's GPU -- and then fail its own UUID witness.
        inherited = [v for v in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if v]
        requested = inherited[0] if inherited else None
    if requested is None:
        chosen = catalogue[0]
    else:
        matches = [d for d in catalogue if requested in (d["uuid"], d["index"])]
        require(len(matches) == 1, f"--device {requested!r} did not match exactly one GPU")
        chosen = matches[0]
    topology = subprocess.run(["nvidia-smi", "topo", "-m"], capture_output=True, text=True)
    chosen = dict(chosen)
    chosen["topology"] = topology.stdout
    chosen["catalogue"] = catalogue
    return chosen


class ComputeAppWatcher(threading.Thread):
    """Sample nvidia-smi compute-apps and join on our own PID.

    nvidia-smi ignores CUDA_VISIBLE_DEVICES and enumerates physical devices, so
    the UUID it reports for our PID is the silicon that actually ran the
    kernels. A run that never appears here has no physical-device witness.
    """

    def __init__(self, pid: int, interval: float = 0.12) -> None:
        super().__init__(daemon=True)
        self.pid = pid
        self.interval = interval
        self.samples: List[str] = []
        self.sample_count = 0
        # Not _stop: threading.Thread uses that name for an internal method, and
        # shadowing it makes the interpreter call an Event when the thread ends.
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                out = nvidia_smi("--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader")
            except Exception:
                out = ""
            self.sample_count += 1
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2 and parts[0] == str(self.pid) and parts[1] not in self.samples:
                    self.samples.append(parts[1])
            self._halt.wait(self.interval)

    def stop(self) -> List[str]:
        self._halt.set()
        self.join(timeout=5)
        return self.samples


# --------------------------------------------------------------------------
# Running one arm
# --------------------------------------------------------------------------

@dataclass
class ArmResult:
    name: str
    out: Path
    returncode: int
    stdout: str
    stderr: str
    logs: Dict[str, str]
    identity: Dict[str, Any]


def run_arm(binary: Path, cwd: Path, out: Path, options: Sequence[str], device: Dict[str, str],
            *, name: str, threads: int, timeout: int, uuid_required: bool) -> ArmResult:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), "--i", "movies.star", "--o", str(out) + "/", "--use_own",
           "--gpu", "0", "--j", str(threads), "--max_io_threads", "2",
           "--patch_x", "2", "--patch_y", "2", "--max_iter", "2", "--bfactor", "150",
           "--seed", "1", "--angpix", str(ANGPIX), "--voltage", str(VOLTAGE),
           *options]
    env = dict(os.environ)
    # Pin the process to one physical device by UUID. --gpu 0 then means exactly
    # this GPU regardless of how the driver orders the others.
    env["CUDA_VISIBLE_DEVICES"] = device["uuid"]
    env["OMP_NUM_THREADS"] = str(threads)
    for key in ("MC_FAULT_ORDINAL", "MC_FAULT_CODE", "MC_U16_FAULT", "MC_PREPROCESS_FAULT",
                "MC_COUNT_FAULT_ORDINAL", "MC_COUNT_FAULT_CODE"):
        env.pop(key, None)
    started = time.time()
    process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    watcher = ComputeAppWatcher(process.pid)
    watcher.start()
    proc = Path("/proc") / str(process.pid)
    identity: Dict[str, Any] = {"pid": process.pid, "wall_start": started}
    try:
        identity["executable"] = os.readlink(proc / "exe")
        identity["start_ticks"] = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
        identity["cpus_allowed"] = sorted(os.sched_getaffinity(process.pid))
    except OSError:
        # The process can exit before /proc is read on a very short arm; the
        # binary hash and the compute-apps join still identify what ran.
        identity["executable"] = str(binary)
        identity["start_ticks"] = None
        identity["cpus_allowed"] = sorted(os.sched_getaffinity(0))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        watcher.stop()
        raise CaseFailure(f"{name}: exceeded {timeout}s")
    observed = watcher.stop()
    identity["wall_seconds"] = round(time.time() - started, 3)
    identity["compute_app_uuids"] = observed
    identity["compute_app_samples"] = watcher.sample_count
    identity["cuda_visible_devices"] = device["uuid"]
    identity["command"] = cmd
    identity["cwd"] = str(cwd)
    if uuid_required:
        require(observed == [device["uuid"]],
                f"{name}: nvidia-smi compute-apps did not witness PID {process.pid} on "
                f"{device['uuid']} (saw {observed or 'nothing'} over "
                f"{watcher.sample_count} samples)")
    logs = {p.relative_to(out).as_posix(): p.read_text(errors="replace")
            for p in sorted(out.rglob("*.log"))}
    (out.parent / f"{name}.stdout.txt").write_text(stdout)
    (out.parent / f"{name}.stderr.txt").write_text(stderr)
    return ArmResult(name, out, process.returncode, stdout, stderr, logs, identity)


def assert_witnesses(arm: ArmResult, *, expect_u16: bool, movies: Sequence[str]) -> Dict[str, Any]:
    """Per-movie native-stage verdict, from that movie's own log."""
    verdicts: Dict[str, Any] = {}
    for movie in movies:
        rel = f"Movies/{Path(movie).stem}.log"
        require(rel in arm.logs, f"{arm.name}: no per-movie log for {movie}")
        text = arm.logs[rel]
        staged = STAGED in text
        released = RELEASED in text
        fell_back = MATERIALIZED in text or NO_SESSION in text
        verdicts[movie] = {
            "selected_compact_ingest": staged,
            "released_after_device_forward_fft": released,
            "host_fallback": fell_back,
            "session_initialized": SESSION_READY in text,
            "resident_reconstruction": RESIDENT_RECON in text,
        }
        if expect_u16:
            require(staged, f"{arm.name}/{movie}: compact ingest was not selected")
            require(released,
                    f"{arm.name}/{movie}: no '{RELEASED}' witness; the compact path did not "
                    f"complete on the device")
            require(not fell_back, f"{arm.name}/{movie}: fell back to host float frames")
            require(SESSION_READY in text, f"{arm.name}/{movie}: no resident session witness")
            require(RESIDENT_RECON in text,
                    f"{arm.name}/{movie}: no resident reconstruction witness")
        else:
            require(not staged,
                    f"{arm.name}/{movie}: compact ingest was selected for an ineligible input")
            require(not released, f"{arm.name}/{movie}: unexpected compact-ingest release")
    return verdicts


# --------------------------------------------------------------------------
# Case execution
# --------------------------------------------------------------------------

def movie_names(case: Case) -> List[str]:
    return [f"Movies/mov{i:02d}_{geom.name}.tiff" for i, geom in enumerate(case.geometries)]


def build_manifest(case: Case, movies: Sequence[str], *, input_star: Path,
                   gain_name: Optional[str], defect_name: Optional[str]) -> Dict[str, Any]:
    entries: List[Any] = []
    for movie, geom in zip(movies, case.geometries):
        tags = {
            "_rlnMicrographOriginalPixelSize": ANGPIX,
            "_rlnVoltage": VOLTAGE,
            "_rlnMicrographStartFrame": case.start_frame,
            "_rlnMicrographBinning": 2.0 if "--bin_factor" in case.options else 1.0,
            "_rlnImageSizeX": geom.nx,
            "_rlnImageSizeY": geom.ny,
            # The movie's own frame count, not the selected count: the runner
            # records the selection in _rlnMicrographStartFrame alone, and
            # --last_frame_sum leaves no trace in the metadata at all. That is a
            # support limitation of the STAR contract, recorded rather than
            # worked around; only pixel comparison can see a changed last frame.
            "_rlnImageSizeZ": geom.n_frames,
        }
        if "--dose_weighting" in case.options:
            tags["_rlnMicrographDoseRate"] = DOSE_PER_FRAME
        if gain_name:
            tags["_rlnMicrographGainName"] = gain_name
        if defect_name:
            tags["_rlnMicrographDefectFile"] = defect_name
        shape = product_shape(case, geom)
        entries.append({"movie": movie, "shape_xyz": shape,
                        "products": case.products, "general_tags": tags,
                        "optics_group": 1})
    manifest: Dict[str, Any] = {
        "schema_version": 2,
        "movies": entries,
        "expected_shape_xyz": product_shape(case, case.geometries[0]),
        "joint_star": "corrected_micrographs.star",
        "input_star_sha256": sha256_file(input_star),
    }
    if case.forbidden_joint_tags:
        manifest["forbidden_joint_tags"] = case.forbidden_joint_tags
    return manifest


def product_shape(case: Case, geom: Geometry) -> List[int]:
    if "--bin_factor" in case.options:
        factor = int(case.options[case.options.index("--bin_factor") + 1])
        return [geom.nx // factor, geom.ny // factor, 1]
    return geom.shape


def prepare_inputs(case: Case, root: Path, *, floating: bool) -> Tuple[Path, List[str], Optional[str], Optional[str]]:
    movies = movie_names(case)
    for movie, geom in zip(movies, case.geometries):
        frames = fixtures.synthetic_movie(geom.nx, geom.ny, geom.n_frames, geom.seed)
        fixtures.write_movie(root / movie, frames, geom.nx, geom.ny, floating=floating)
    if case.damaged_frames is not None:
        target = root / movies[case.failing_movie]
        healthy = target.with_suffix(".healthy")
        shutil.move(str(target), str(healthy))
        fixtures.truncate_after_frame(healthy, target, case.damaged_frames)
        healthy.unlink()
    gain_name = None
    if case.gain:
        geom = case.geometries[0]
        mixed = len({(g.nx, g.ny) for g in case.geometries}) != 1
        require(not mixed or case.failure_message is not None,
                f"{case.case_id}: one gain reference cannot cover mixed geometry")
        gain_name = "gain.mrc"
        fixtures.write_gain(root / gain_name, geom.nx, geom.ny, GAIN_VALUE)
    defect_name = None
    if case.defects:
        defect_name = "defects.txt"
        (root / defect_name).write_text("10 12 2 2\n")
    star = root / "movies.star"
    fixtures.write_star(star, movies, angpix=ANGPIX, voltage=VOLTAGE)
    return star, movies, gain_name, defect_name


def case_options(case: Case, gain_name: Optional[str], defect_name: Optional[str]) -> List[str]:
    options = list(case.options)
    if gain_name:
        options += ["--gainref", gain_name]
    if defect_name:
        options += ["--defect_file", defect_name]
    return options


def execute_case(case: Case, binary: Path, work: Path, device: Dict[str, str],
                 *, threads: int, timeout: int, uuid_required: bool) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "case_id": case.case_id, "requirement": case.requirement, "note": case.note,
        "geometries": [g.name for g in case.geometries],
        "declared_products": [p["suffix"] or "sum" for p in case.products],
        "expect_compact_ingest": case.expect_u16,
        "status": "FAIL", "arms": {}, "comparisons": {}, "witnesses": {},
    }
    base = work / case.case_id
    u16_root = base / "input-u16"
    star, movies, gain_name, defect_name = prepare_inputs(case, u16_root, floating=not case.expect_u16)
    options = case_options(case, gain_name, defect_name)
    record["options"] = options
    record["input_sha256"] = {m: sha256_file(u16_root / m) for m in movies}
    if gain_name:
        record["input_sha256"][gain_name] = sha256_file(u16_root / gain_name)

    manifest = build_manifest(case, movies, input_star=star,
                              gain_name=gain_name, defect_name=defect_name)
    record["manifest"] = manifest

    if case.failing_movie is not None:
        return execute_failing_movie_case(case, record, binary, base, u16_root, movies, options,
                                          device, threads=threads, timeout=timeout,
                                          uuid_required=uuid_required)

    primary = run_arm(binary, u16_root, base / "out-primary", options, device,
                      name=f"{case.case_id}:primary", threads=threads, timeout=timeout,
                      uuid_required=uuid_required)
    record["arms"]["primary"] = arm_record(primary)
    require(primary.returncode == 0,
            f"{case.case_id}: primary arm exited {primary.returncode}\n{primary.stderr[-2000:]}")
    record["witnesses"]["primary"] = assert_witnesses(primary, expect_u16=case.expect_u16,
                                                      movies=movies)
    comparator.validate_input_star(star, manifest)
    primary_tree = comparator.validate_tree(primary.out, manifest)
    record["product_stats"] = assert_non_constant(primary.out, primary_tree)
    record["tree"] = summarize(primary_tree)

    if case.float_twin:
        f32_root = base / "input-f32"
        f32_star, f32_movies, f32_gain, f32_defect = prepare_inputs(case, f32_root, floating=True)
        twin = run_arm(binary, f32_root, base / "out-float", case_options(case, f32_gain, f32_defect),
                       device, name=f"{case.case_id}:float", threads=threads, timeout=timeout,
                       uuid_required=uuid_required)
        record["arms"]["float"] = arm_record(twin)
        require(twin.returncode == 0, f"{case.case_id}: float arm exited {twin.returncode}")
        record["witnesses"]["float"] = assert_witnesses(twin, expect_u16=False, movies=f32_movies)
        # Both arms declare the same movie names in different input roots, so
        # the twin satisfies the identical manifest -- including the input STAR
        # hash, since the STAR text is byte-identical. Only the TIFF sample
        # format differs, which is the whole point of the pairing.
        require(f32_movies == movies and sha256_file(f32_star) == manifest["input_star_sha256"],
                f"{case.case_id}: the float twin does not share the uint16 arm's contract")
        record["float_input_sha256"] = {m: sha256_file(f32_root / m) for m in f32_movies}
        twin_tree = comparator.validate_tree(twin.out, manifest)
        assert_non_constant(twin.out, twin_tree)
        record["float_tree"] = summarize(twin_tree)
        report = compare_products(primary.out, twin.out, manifest, manifest)
        record["comparisons"]["u16_vs_float32_tiff"] = report
        require(report["status"] == "PASS",
                f"{case.case_id}: compact ingest products differ from the float32 twin: "
                f"{report['different_products']}")

    if case.repeat:
        repeat = run_arm(binary, u16_root, base / "out-repeat", options, device,
                         name=f"{case.case_id}:repeat", threads=threads, timeout=timeout,
                         uuid_required=uuid_required)
        record["arms"]["repeat"] = arm_record(repeat)
        require(repeat.returncode == 0, f"{case.case_id}: repeat arm exited {repeat.returncode}")
        record["witnesses"]["repeat"] = assert_witnesses(repeat, expect_u16=case.expect_u16,
                                                         movies=movies)
        report = comparator.compare_trees(primary.out, repeat.out, manifest,
                                          compare_auxiliary=True)
        record["comparisons"]["repeat"] = summarize_comparison(report)
        require(report["status"] == "PASS",
                f"{case.case_id}: repeat differs: {report['different_files']}")

    if case.resume_non_prefix:
        resumed = base / "out-resume"
        shutil.copytree(primary.out, resumed)
        middle = Path(movies[1]).stem
        removed = sorted(p.relative_to(resumed).as_posix()
                         for p in resumed.rglob(f"{middle}*") if p.is_file())
        for rel in removed:
            (resumed / rel).unlink()
        record["resume_removed_products"] = removed
        require(len(removed) >= len(case.products) + 1,
                f"{case.case_id}: resume control removed too little ({removed})")
        # Copied logs make log presence useless as a recomputation signal, so the
        # untouched movies are identified by their products' inode timestamps.
        before = {p.relative_to(resumed).as_posix(): p.stat().st_mtime_ns
                  for p in resumed.rglob("*") if p.is_file()}
        arm = run_arm(binary, u16_root, resumed, options + ["--only_do_unfinished"], device,
                      name=f"{case.case_id}:resume", threads=threads, timeout=timeout,
                      uuid_required=uuid_required)
        record["arms"]["resume"] = arm_record(arm)
        require(arm.returncode == 0, f"{case.case_id}: resume arm exited {arm.returncode}")
        after = {p.relative_to(resumed).as_posix(): p.stat().st_mtime_ns
                 for p in resumed.rglob("*") if p.is_file()}
        rewritten = sorted(rel for rel, stamp in after.items()
                           if rel in before and before[rel] != stamp)
        record["resume_rewritten_existing_products"] = rewritten
        surviving = {Path(movies[i]).stem for i in (0, 2)}
        # A completed movie that is rewritten is a full rerun wearing a resume's
        # name; only the withheld movie's own products may reappear.
        offenders = [rel for rel in rewritten
                     if any(Path(rel).name.startswith(stem) for stem in surviving)]
        require(not offenders,
                f"{case.case_id}: --only_do_unfinished rewrote completed products {offenders}")
        record["witnesses"]["resume"] = assert_witnesses(arm, expect_u16=case.expect_u16,
                                                         movies=[movies[1]])
        report = comparator.compare_trees(primary.out, resumed, manifest, compare_auxiliary=False)
        record["comparisons"]["non_prefix_resume"] = summarize_comparison(report)
        require(report["status"] == "PASS",
                f"{case.case_id}: resumed tree differs: {report['different_products']}")

        # Powered control for the detector itself. An mtime comparison that
        # silently saw nothing would pass the row above just as happily, so run
        # the same arm without --only_do_unfinished and require it to trip.
        control = base / "out-resume-control"
        shutil.copytree(primary.out, control)
        control_before = {p.relative_to(control).as_posix(): p.stat().st_mtime_ns
                          for p in control.rglob("*") if p.is_file()}
        control_arm = run_arm(binary, u16_root, control, options, device,
                              name=f"{case.case_id}:resume-control", threads=threads,
                              timeout=timeout, uuid_required=uuid_required)
        require(control_arm.returncode == 0,
                f"{case.case_id}: resume control arm exited {control_arm.returncode}")
        control_after = {p.relative_to(control).as_posix(): p.stat().st_mtime_ns
                         for p in control.rglob("*") if p.is_file()}
        control_rewritten = sorted(
            rel for rel, stamp in control_after.items()
            if rel in control_before and control_before[rel] != stamp
            and any(Path(rel).name.startswith(stem) for stem in surviving))
        record["resume_control_rewritten"] = control_rewritten
        require(control_rewritten,
                f"{case.case_id}: without --only_do_unfinished the detector still saw no "
                f"rewrite, so it cannot observe a full rerun")

    record["status"] = "PASS"
    return record


def execute_failing_movie_case(case: Case, record: Dict[str, Any], binary: Path, base: Path,
                               root: Path, movies: Sequence[str], options: Sequence[str],
                               device: Dict[str, str], *, threads: int, timeout: int,
                               uuid_required: bool) -> Dict[str, Any]:
    """One movie in the batch must fail, be named, publish nothing, and leave the
    healthy movies' products and their joint-STAR rows intact."""
    damaged = movies[case.failing_movie]
    arm = run_arm(binary, root, base / "out-failing", options, device,
                  name=f"{case.case_id}:failing", threads=threads, timeout=timeout,
                  uuid_required=uuid_required)
    record["arms"]["failing"] = arm_record(arm)
    diagnostics = arm.stdout + arm.stderr
    require(arm.returncode != 0,
            f"{case.case_id}: a damaged movie exited 0")
    require(arm.returncode > 0,
            f"{case.case_id}: process died on signal {-arm.returncode}")
    require(Path(damaged).name in diagnostics,
            f"{case.case_id}: the failing movie was not named in the diagnostics")
    if case.failure_message:
        require(case.failure_message in diagnostics,
                f"{case.case_id}: diagnostics did not state {case.failure_message!r}")
    stems = {Path(m).stem for m in movies}
    published = sorted(p.relative_to(arm.out).as_posix()
                       for p in arm.out.rglob("*") if p.suffix in (".mrc", ".star"))
    record["published_products"] = published
    damaged_stem = Path(damaged).stem
    require(not any(Path(rel).stem.startswith(damaged_stem) for rel in published),
            f"{case.case_id}: the failed movie published a product: {published}")
    healthy_stems = sorted(stems - {damaged_stem})
    for stem in healthy_stems:
        require(f"Movies/{stem}.mrc" in published,
                f"{case.case_id}: healthy movie {stem} lost its image")
    joint = arm.out / "corrected_micrographs.star"
    record["joint_star_written"] = joint.exists()
    if joint.exists():
        rows = comparator._parse_joint_micrographs(joint)
        named = sorted(Path(r[0]).stem for r in rows)
        record["joint_star_rows"] = named
        require(damaged_stem not in named,
                f"{case.case_id}: the failed movie appears in the joint STAR")
    # The healthy movies still had to take the compact path.
    record["witnesses"]["failing"] = assert_witnesses(
        arm, expect_u16=True, movies=[m for m in movies if m != damaged])
    record["status"] = "PASS"
    return record


def compare_products(primary: Path, twin: Path, manifest: Dict[str, Any],
                     twin_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Compare the two arms' products after validating each against its own
    manifest. Logs are excluded on purpose: the compact arm's log carries the
    staging lines by design, and those lines are asserted separately."""
    comparator.validate_tree(primary, manifest)
    comparator.validate_tree(twin, twin_manifest)
    report = comparator.compare_trees(primary, twin, manifest, compare_auxiliary=False)
    return summarize_comparison(report)


def assert_non_constant(root: Path, info: Dict[str, Any]) -> Dict[str, Any]:
    """Every declared product must carry signal.

    Byte equality between two arms is satisfied just as well by two identically
    blank images, and the comparator's header check only rejects dmin > dmax. A
    row that produced a constant image would otherwise pass everything.
    """
    stats: Dict[str, Any] = {}
    for rel in sorted(info["mrc"]):
        header = (root / rel).read_bytes()[:1024]
        dmin, dmax, dmean = struct.unpack_from("<3f", header, 76)
        rms = struct.unpack_from("<f", header, 216)[0]
        stats[rel] = {"dmin": dmin, "dmax": dmax, "dmean": dmean, "rms": rms}
        require(dmax > dmin and rms > 0.0,
                f"{root / rel}: constant product (dmin={dmin}, dmax={dmax}, rms={rms}); "
                f"equality between two blank images proves nothing")
    return stats


def summarize(info: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the file listing, keep every product's identity.

    A row that is not part of a pairwise comparison would otherwise retain no
    hash at all, so its "complete expected products" claim could not be checked
    against anything later."""
    out = {k: v for k, v in info.items() if k not in ("mrc", "files")}
    out["product_sha256"] = {
        rel: {"header": m.header_sha256, "extended": m.extended_sha256,
              "payload": m.payload_sha256, "dimensions": list(m.dimensions),
              "mode": m.mode, "bytes": m.file_bytes}
        for rel, m in sorted(info["mrc"].items())
    }
    return out


def summarize_comparison(report: Dict[str, Any]) -> Dict[str, Any]:
    trimmed = dict(report)
    trimmed["base"] = {k: v for k, v in report["base"].items() if k != "files"}
    trimmed["candidate"] = {k: v for k, v in report["candidate"].items() if k != "files"}
    return trimmed


def arm_record(arm: ArmResult) -> Dict[str, Any]:
    return {"exit_code": arm.returncode, "identity": arm.identity,
            "logs": sorted(arm.logs)}


# --------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--device", default=None,
                        help="GPU UUID (preferred) or index; defaults to the first device")
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--cases", default=None, help="comma-separated case ids")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--allow-missing-uuid-witness", action="store_true",
                        help="record the compute-apps join instead of requiring it")
    opts = parser.parse_args(argv)

    binary = opts.binary.resolve()
    require(binary.is_file(), f"missing binary: {binary}")
    work = (opts.workdir or Path(os.environ.get("TMPDIR", "/tmp")) / "mc-compact-support").resolve()
    work.mkdir(parents=True, exist_ok=True)
    device = pick_device(opts.device)
    selected = [c for c in CASES
                if opts.cases is None or c.case_id in opts.cases.split(",")]
    require(bool(selected), "no cases selected")

    session = {
        "source_root": str(SOURCE_ROOT),
        "binary": str(binary),
        "binary_sha256": sha256_file(binary),
        "comparator_sha256": sha256_file(COMPARATOR_PATH),
        "fixtures_sha256": sha256_file(Path(__file__).resolve().parent / "compact_ingest_fixtures.py"),
        "harness_sha256": sha256_file(Path(__file__).resolve()),
        "host": os.uname().nodename,
        "workdir": str(work),
        "device": {k: v for k, v in device.items() if k != "catalogue"},
        "device_catalogue": device["catalogue"],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "cpus_allowed": sorted(os.sched_getaffinity(0)),
        "threads": opts.threads,
        "uuid_witness": "recorded" if opts.allow_missing_uuid_witness else "required",
        "cases": [],
    }

    failures = 0
    for case in selected:
        print(f"[case] {case.case_id}: {case.requirement}", flush=True)
        try:
            record = execute_case(case, binary, work, device, threads=opts.threads,
                                  timeout=opts.timeout,
                                  uuid_required=not opts.allow_missing_uuid_witness)
        except CaseFailure as exc:
            record = {"case_id": case.case_id, "requirement": case.requirement,
                      "status": "FAIL", "reason": str(exc)}
            failures += 1
            print(f"  FAIL {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001 - an error must not be a silent pass
            record = {"case_id": case.case_id, "requirement": case.requirement,
                      "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
            failures += 1
            print(f"  ERROR {type(exc).__name__}: {exc}", flush=True)
        else:
            print("  PASS", flush=True)
        session["cases"].append(record)
        if opts.json:
            opts.json.parent.mkdir(parents=True, exist_ok=True)
            opts.json.write_text(json.dumps(session, indent=2, sort_keys=False) + "\n")

    session["summary"] = {
        "selected": len(selected),
        "passed": sum(1 for c in session["cases"] if c["status"] == "PASS"),
        "failed": failures,
    }
    if opts.json:
        opts.json.write_text(json.dumps(session, indent=2, sort_keys=False) + "\n")
    print(f"\ncompact-ingest support matrix: {session['summary']}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CaseFailure as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)
