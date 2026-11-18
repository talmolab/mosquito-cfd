## ADDED Requirements

### Requirement: `flow_video` discovers plotfile frames with the corpus's own listing

`flow_video` SHALL discover the frames of a run with
`mosquito_cfd.field_surrogate.corpus.scan_plotfiles`, the same object `FieldCorpus` uses, so that the
two agree on which plotfiles exist.

- **Names.** A frame directory name SHALL be `plt` followed by one or more ASCII digits, of any
  width. AMReX writes `plt{step:05d}`, which has six digits from step 100000 on, and the previous
  `plt?????` glob silently dropped those frames and every later one (#144).
- **Order.** Frames SHALL be ordered by their integer step, not by name.
- **Non-directories.** Entries that are not directories SHALL be skipped.
- **Duplicates.** Two directories that parse to the same step SHALL raise the corpus's
  `ValueError` naming both, rather than rendering the same instant twice.
- **Missing or empty directory.** A `plotfile_dir` that does not exist or is not a directory, and
  a directory with no plotfile, SHALL each raise `ValueError` naming the directory, as before. The
  message SHALL say which: "does not exist" only for a missing path, "is not a directory" for one
  that exists, and the no-plotfile message SHALL describe the accepted name as `plt<digits>`.

`build_flow_video`'s documentation and the `make_flow_video.py --plotfile-dir` help SHALL describe
the accepted names as `plt<digits>` of any width.

#### Scenario: Frames at step 100000 and beyond are rendered, in step order

- **GIVEN** a plotfile directory holding `plt99999`, `plt100000` and `plt00100`, a regular file
  named `plt00200`, a directory `plt00300.old`, and a directory `plt١٠٠` (non-ASCII digits)
- **WHEN** `flow_video`'s frame discovery runs on it
- **THEN** it returns exactly the paths for `plt00100`, `plt99999` and `plt100000`, in that order,
  which differs from lexical order (`plt100000` sorts before `plt99999` as a string); and
  `flow_video`'s `scan_plotfiles` is the same object as `corpus.scan_plotfiles`

#### Scenario: Duplicate, missing and empty directories are reported

- **GIVEN** a directory holding `plt100` and `plt00100`; a path that does not exist; a regular file;
  and an empty directory
- **WHEN** frame discovery runs on each
- **THEN** the first raises `ValueError` naming `plt00100` and `plt100`, and each of the others
  raises exactly `ValueError` naming the path, the empty-directory message naming `plt<digits>`
