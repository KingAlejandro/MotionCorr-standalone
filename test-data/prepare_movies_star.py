"""Prepare RELION's SPA tutorial TIFF movies for standalone MotionCorr."""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="extracted relion30_tutorial directory")
    parser.add_argument("--limit", type=int, default=0, help="use only this many movies")
    args = parser.parse_args()

    movies = sorted(args.dataset.glob("Movies/*.tif*"))
    if not movies:
        parser.error(f"no TIFF movies found in {args.dataset / 'Movies'}")
    if args.limit:
        if args.limit < 0:
            parser.error("--limit must be positive")
        movies = movies[: args.limit]

    names = [movie.relative_to(args.dataset).as_posix() for movie in movies]
    content = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 0.885 200 1.4 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
""" + "\n".join(f"{name} 1" for name in names) + "\n"
    output = args.dataset / "movies.star"
    output.write_text(content)
    print(f"Wrote {output} with {len(movies)} movie(s)")


if __name__ == "__main__":
    main()
