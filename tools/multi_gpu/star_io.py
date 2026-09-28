#!/usr/bin/env python3
"""Minimal STAR reader that mirrors what MotionCorr's own C++ reader observes.

This exists so that partitioning a movies STAR can *identify* rows the same way
the binary will, without ever re-serializing one. Shards are built from the
original bytes; the parse is used only for identification, collision preflight
and round-trip assertions. That keeps optics, pre-exposure, quoting and numeric
formatting preserved structurally rather than by a serializer's fidelity.

Semantics deliberately copied from the C++ side, with the source cited so a
reviewer can check each one:

  * CR+LF input is rejected outright (src/metadata_table.cpp:1225-1230).
  * A block starts at any line containing "data_"; the block name is everything
    after the first "data_" (`:1241-1245`). A block is a loop table if a line
    containing "loop_" follows (`:1252`), otherwise a list (`:1256`).
  * Label lines start with "_" and the label is taken up to a "#"
    (src/metadata_table.cpp:1054-1061).
  * Every data line is passed through simplify() before tokenization
    (`:1088`), and the row block ends at the first empty line (`:1091`).
  * simplify() (src/strings.cpp:122) first unescapes: it *drops* \\n \\v \\b \\r
    \\f and \\a, and turns \\t into a space (src/strings.cpp:63-85). It then
    strips leading spaces and collapses every run of spaces to one.
  * nextTokenInSTAR() (src/strings.cpp:595) then splits on spaces, honours a
    leading ' or " as a quoted token, and treats a leading # as end-of-line.

Two consequences of that order are load-bearing and are asserted, not assumed:

  * Because simplify() strips \\a before tokenization, the "\\a-escaped quote"
    lookback in nextTokenInSTAR (src/strings.cpp:628) can never match on a line
    that came from a file. RELION's own escapeStringForSTAR (src/strings.cpp:87)
    writes \\a for an embedded quote, so such a value does not round-trip through
    its own reader. That is an upstream defect, out of scope to fix here; this
    parser reproduces the reader's actual behaviour rather than the writer's
    intent, and refuses any input that would hit it.
  * Runs of spaces are collapsed *inside* quoted values too, so 'a  b.tif' and
    'a b.tif' are the same movie to the binary. Partitioning must therefore treat
    them as colliding, which it does because it compares parsed names.

Multiline semicolon blocks are not supported by the C++ reader
(src/strings.cpp:613) and are rejected here rather than guessed at.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path


class StarFormatError(ValueError):
    """Input uses a construct the MotionCorr C++ reader does not handle."""


def unescape(line: str) -> str:
    """Port of unescape(), src/strings.cpp:63."""
    out = []
    for ch in line:
        if ch == "\t":
            out.append(" ")
        elif ch not in ("\n", "\v", "\b", "\r", "\f", "\a"):
            out.append(ch)
    return "".join(out)


def simplify(line: str) -> str:
    """Port of simplify(), src/strings.cpp:122."""
    s = unescape(line).lstrip(" ")
    out = []
    i = 0
    while i < len(s):
        out.append(s[i])
        if s[i] == " ":
            while i < len(s) and s[i] == " ":
                i += 1
        else:
            i += 1
    if out and out[-1] == " ":
        out.pop()
    return "".join(out)


def tokenize(simplified: str) -> list[str]:
    """Port of the nextTokenInSTAR() loop, src/strings.cpp:595.

    `simplified` must already have been through simplify(), exactly as
    readStarLoop() does before tokenizing (src/metadata_table.cpp:1088).
    """
    tokens: list[str] = []
    i = 0
    n = len(simplified)
    while i < n:
        start = -1
        for k in range(i, n):
            if simplified[k] not in " \t\n":
                start = k
                break
        if start < 0:
            break
        if simplified[start] == "#":
            break
        if simplified[start] in ("'", '"'):
            quote = simplified[start]
            start += 1
            pos = start
            end = -1
            value = []
            while pos < n:
                # The C++ lookback is `str[pos - 1] != '\a'`, but simplify() has
                # already removed every \a, so the guard can never fire here.
                if simplified[pos] == quote:
                    nxt = pos + 1
                    if nxt == n or simplified[nxt] in " \t\n":
                        end = pos
                        break
                value.append(simplified[pos])
                pos += 1
            if end < 0:
                raise StarFormatError(
                    "unterminated quoted token, which the C++ reader reports as "
                    f"'Could not find closing quote': {simplified!r}"
                )
            tokens.append("".join(value))
            i = pos + 1
        else:
            end = simplified.find(" ", start + 1)
            if end < 0:
                end = n
            tokens.append(simplified[start:end])
            i = end + 1
    return tokens


@dataclasses.dataclass
class Row:
    index: int          # index into StarFile.lines
    raw: str            # original bytes of the line, newline included
    values: list[str]


@dataclasses.dataclass
class Block:
    name: str
    is_loop: bool
    start: int          # index of the "data_" line
    labels: list[str]
    rows: list[Row]
    row_start: int      # first data-row line index
    row_end: int        # one past the last data-row line index

    def column(self, label: str) -> int:
        try:
            return self.labels.index(label)
        except ValueError as exc:
            raise StarFormatError(
                f"block data_{self.name} has no column {label}; found {self.labels}"
            ) from exc


@dataclasses.dataclass
class StarFile:
    path: Path
    lines: list[str]
    blocks: list[Block]

    def block(self, name: str) -> Block:
        for b in self.blocks:
            if b.name == name:
                return b
        raise StarFormatError(f"{self.path}: no data_{name} block")

    def block_with_label(self, label: str) -> Block:
        hits = [b for b in self.blocks if b.is_loop and label in b.labels]
        if not hits:
            raise StarFormatError(f"{self.path}: no loop block carries {label}")
        if len(hits) > 1:
            raise StarFormatError(
                f"{self.path}: {label} appears in several blocks: "
                + ", ".join("data_" + b.name for b in hits)
            )
        return hits[0]

    def render(self) -> str:
        """Reproduce the original file byte for byte."""
        return "".join(self.lines)

    def render_with_rows(self, block: Block, rows: list[Row]) -> str:
        """Original bytes with `block`'s data rows replaced by `rows`, verbatim.

        Everything outside the row span -- the version comment, the optics block,
        the loop header, the label lines, and any trailing content -- is copied
        unchanged, so no metadata passes through a serializer.
        """
        prefix = "".join(self.lines[: block.row_start])
        suffix = "".join(self.lines[block.row_end :])
        return prefix + "".join(r.raw for r in rows) + suffix


def parse(path: str | Path) -> StarFile:
    path = Path(path)
    # Read bytes and decode explicitly: Path.read_text() applies universal-newline
    # translation, which would silently turn a CR+LF file -- the one thing the C++
    # reader refuses outright -- into a clean LF file here.
    text = path.read_bytes().decode()
    lines = text.splitlines(keepends=True)

    for n, raw in enumerate(lines, start=1):
        if raw.rstrip("\n").endswith("\r"):
            raise StarFormatError(
                f"{path}:{n}: CR+LF line ending; the C++ reader rejects these "
                "(src/metadata_table.cpp:1225)"
            )
        if raw.lstrip().startswith(";"):
            raise StarFormatError(
                f"{path}:{n}: semicolon multiline block; the C++ reader does not "
                "support these (src/strings.cpp:613)"
            )
        if "\a" in raw:
            raise StarFormatError(
                f"{path}:{n}: contains a \\a escape byte. simplify() strips it before "
                "tokenization, so the C++ reader cannot recover the intended value "
                "(src/strings.cpp:63, :628); refusing to guess."
            )

    blocks: list[Block] = []
    i = 0
    n_lines = len(lines)
    while i < n_lines:
        stripped = lines[i].strip()
        if "data_" not in stripped:
            i += 1
            continue
        name = stripped[stripped.find("data_") + 5 :]
        start = i
        i += 1
        # Look for loop_ or the first _label, exactly as readStar() does.
        is_loop = False
        while i < n_lines:
            s = lines[i].strip()
            if "loop_" in s:
                is_loop = True
                i += 1
                break
            if s.startswith("_"):
                break
            if "data_" in s:
                break
            i += 1
        if not is_loop:
            # A list block, or an empty block. Skip to the next data_ line; its
            # bytes are preserved verbatim and nothing here needs its contents.
            while i < n_lines and "data_" not in lines[i].strip():
                i += 1
            blocks.append(Block(name, False, start, [], [], start, start))
            continue

        labels: list[str] = []
        while i < n_lines:
            s = simplify(lines[i])
            if s == "" or s[0] in ("#", ";"):
                i += 1
                continue
            if s[0] != "_":
                break
            hashpos = s.find("#")
            labels.append(s[1:hashpos].strip() if hashpos >= 0 else s[1:].strip())
            i += 1

        row_start = i
        rows: list[Row] = []
        while i < n_lines:
            s = simplify(lines[i])
            if s == "":
                break
            values = tokenize(s)
            if len(values) > len(labels):
                raise StarFormatError(
                    f"{path}:{i + 1}: {len(values)} columns for {len(labels)} labels; "
                    "the C++ reader reports 'more columns than the number of labels'"
                )
            legacy_empty = len(labels) == 2 and len(values) == 1
            if len(values) < len(labels) and not legacy_empty:
                raise StarFormatError(
                    f"{path}:{i + 1}: {len(values)} columns for {len(labels)} labels; "
                    "the C++ reader reports 'fewer columns than the number of labels'"
                )
            rows.append(Row(i, lines[i], values))
            i += 1
        blocks.append(Block(name, True, start, labels, rows, row_start, i))

    if not blocks:
        raise StarFormatError(f"{path}: no data_ block found")
    return StarFile(path, lines, blocks)


MOVIE_LABEL = "rlnMicrographMovieName"
OPTICS_GROUP_LABEL = "rlnOpticsGroup"


def movie_block(star: StarFile) -> Block:
    return star.block_with_label(MOVIE_LABEL)


def output_root(movie_name: str) -> str:
    """Port of MotioncorrRunner::getOutputFileNames, src/motioncorr_runner.cpp:491.

    Strips the extension and replaces every remaining '.' with '_'. Two distinct
    movies can therefore share one output root, which is a silent overwrite; the
    partitioner preflights for it.
    """
    stem = movie_name
    slash = stem.rfind("/")
    dot = stem.rfind(".")
    if dot > slash:
        stem = stem[:dot]
    return stem.replace(".", "_")
