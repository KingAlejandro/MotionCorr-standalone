"""Stage a synthetic 24-movie runroot so the integrated screen's STAR metadata
assertion can be exercised without a GPU and without the tutorial dataset.

This is a *harness-contract* exercise, not the integrated candidate. The 24
movies are one generated known-motion fixture under 24 names, so nothing here
says anything about the RELION tutorial data. What it does establish is that
``run_all24_schedules.expected_star_metadata`` names fields the runner actually
writes, and that asserting them does not fail a run that is in fact correct.
Until this ran, that assertion had never executed anywhere.

Usage::

    python3 stage_synthetic_runroot.py <runroot> <fixtures-dir>

Then point ``run_all24_schedules.py --runroot <runroot>`` at the result. The
record it produces must be read as a contract check; it is not evidence about
24 distinct micrographs, and it is not a source for any published integrated
claim.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402

MOVIES = 24
FIXTURE = "km_global_hisnr"
GEOMETRY = {"nx": 512, "ny": 512, "angpix": 0.885, "voltage": 300.0}


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    work, fixtures = Path(argv[1]), Path(argv[2])
    work.mkdir(parents=True, exist_ok=True)

    dataset = rm.build_dataset(work, FIXTURE, fixtures, MOVIES, GEOMETRY)
    aux = rm.build_aux_fixtures(work / "aux", GEOMETRY["nx"], GEOMETRY["ny"])
    shutil.copyfile(aux["@GAIN_UNITY@"], work / "Movies" / "gain.mrc")

    print(f"runroot {work}")
    print(f"movies  {len(dataset['stems'])} (one fixture under {MOVIES} names)")
    print(f"star    {dataset['star']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
