# Design: harden-field-corpus-requests

Code comments in this change cite these sections as "`harden-field-corpus-requests` D*n*". A bare
"design.md D1" already refers to the archived `add-field-surrogate-reader` change.

## D1. Inverted requests raise: a second divergence from the legacy adapter

The archived `add-field-surrogate-reader` D1 records one deliberate divergence from the frozen
pre-refactor `extract_eulerian_box`, "halo is reach". This change adds a second.

### Before

Both legacy and the current reader pad the request to `[floor(lo) − halo, ceil(hi) + halo)` and then
apply `i_hi = max(i_hi, i_lo + 1)`. An inverted request therefore never errors. It returns a region
built from the padded indices:

- one cell at `halo = 0`;
- up to `2·halo + 1` cells when the inversion is smaller than the padding;
- none, after domain clipping.

Values from the 6³ fixture, computed with `_region_bounds`; legacy agrees on every row:

| `lo` | `hi` | `halo` | cells per axis |
|---|---|---|---|
| 4 | 2 | 0 | 1 |
| 4 | 2 | 1 | 1 (index 3, not the cell containing `lo`) |
| 4 | 3.5 | 1 | 2 |
| 4 | 3 | 2 | 3 |
| 2.6 | 2.4 | 0 | 1 |
| 9 | −9 | 0 | 0 |

So a swapped corner pair, or a negative margin in `centre ± margin`, gives back a small,
plausible-looking region instead of an error.

### After

`read_field_snapshot` raises `ValueError` if `lo[i] > hi[i]` on any axis. The check uses the raw
corners, not the padded indices. Because of that, the `halo ≥ 1` rows above raise too, even though
their padded range is non-empty.

The check runs immediately after the two `_corner` calls, before `import yt`, so the outcome cannot
depend on the contents of the plotfile. That is why the real-plotfile A/B script needs no replacement
check.

The message lists only the inverted axes, in a fixed format: `inverted region request (lo > hi): axis
y: lo=4.0 > hi=2.0`. Values are formatted with `float()`, never `repr`, because numpy 2 would print
`np.float64(4.0)`.

The comparison is strict `>`:

- `lo == hi` is the documented zero-width point query and is accepted.
- `lo = hi = ±inf` is not inverted.
- `lo = +inf` with `hi = −inf` is rejected.
- NaN was already rejected by `_corner`.

### Where the check lives

The check is in the public reader, not in `_region_bounds`. The helper stays bit-identical to legacy.
Its one-cell floor is still needed for `lo == hi`, for example when a point query lies on a cell face.
The helper-vs-legacy sweep keeps its inverted triples, and they still agree.

### Parity-matrix bookkeeping

Two test lists iterate `REGION_CASES`: the oracle differential test and `scripts/verify_eulerian_box_ab.py`.
Both require the reader and the frozen oracle to agree on every entry. So `inverted` and
`inverted_halo1` cannot stay in `REGION_CASES`.

They cannot move to `DIVERGENCE_CASES` either. Every entry there is a call the reader completes,
returning a recorded cell count (possibly zero) that `_check_divergence` compares with legacy. An
inverted request raises instead.

So both cases leave the matrix and become two things:

- a reader rejection test;
- an `("inverted", …)` entry in `NARROWED_REQUESTS`. That table already checks both sides: legacy
  accepts the request, and the wrapper raises.

No count literal depends on `len(REGION_CASES)`. The script computes its count at run time.

### Callers audited

| caller | can it pass `lo > hi`? | after the change |
|---|---|---|
| `sphere_cv_drag_cd` | no: rejects `x_inlet >= x_outlet` first | unchanged |
| `sphere_cv_steadiness_fraction` | yes: its two box reads come before its `sphere_cv_drag_cd` call. Today an inverted pair still raises, but later, from `sphere_cv_drag_cd`, naming `x_inlet` | gains the same `x_inlet >= x_outlet` guard, so the error still names the caller's arguments (the D3 reasoning) |
| `check_field_capture_velocity`, `wing_lev_report` | caller-supplied box. No in-repo caller outside the tests | now raises |
| `examples/flapping_wing/make_lev_figure.py` | no: ordered constants `_LO`/`_HI` | unchanged |
| `FieldCorpus.snapshot` | caller-supplied, passed through | now raises |
| `flow_video._full_domain_box`, `scripts/check_plotfile_velocity.py` | no: `±inf` defaults | unchanged |
| `scripts/verify_eulerian_box_ab.py` | `REGION_CASES` plus ordered boxes | loses the two inverted cases |
| `flow_video._near_field_box` | yes, when `box_margin ≤ 0` | validated upstream (D3) |

## D2. The `plotfile()` fast path trusts the canonical name

AMReX names plotfiles `plt` followed by the step, zero-padded to at least five digits. That is
`f"plt{step:05d}"`, so step 100000 is `plt100000`. Every plotfile name in the repo and its decks
follows this pattern.

The fast path runs in this order:

1. Validate `step` (D4).
2. Run `_config` (an in-memory lookup once the manifest is cached).
3. Call `(runs_dir / config / f"plt{step:05d}").is_dir()`.
4. If that returns True, return the path.

Otherwise the method calls `run_dir()` and the scan (D5). A regular *file* with the canonical name
also falls through to the scan. A hit costs one `is_dir()`. Today the method makes one `is_dir()` on
the run directory, lists the directory, and calls `is_dir()` on each matching name up to the first
hit.

**Trade-off (chosen by the user).** A fast-path hit does not list the directory, so it cannot detect a
non-canonical twin. With `plt100` and `plt00100` both present, `plotfile(c, 100)` returns `plt00100`,
while `steps(c)` raises. A test pins this, so changing the behaviour later is a visible decision.

Two alternatives were rejected:

- **Also probe the plausible twins** (`plt100`, `plt0100`, …). This costs extra stats on every call,
  still misses twins with more padding than the canonical name, and guards against a state the solver
  does not produce.
- **No fast path, leaving it to #112.** That leaves #121.1 undone.

On a case-insensitive filesystem (NTFS, the `Z:` mount), the fast path also accepts a directory named
`PLT00100`, which the case-sensitive scan regex rejects. AMReX never writes upper-case names, so no
test depends on this.

## D3. `box_margin` is validated where the caller passed it

`build_flow_video` validates `box_margin` right after the `fps` check, before any I/O or `Figure`
creation. The rules:

- It must be a real number (`numbers.Real`): `int`, `float`, `fractions.Fraction`, or a numpy integer
  or floating scalar. `bool` and `np.bool_` are rejected; so is `decimal.Decimal`, which is not a
  `numbers.Real`.
- It must convert to a finite `float` `> 0`. An `int` too large for a `float` (`10**400`) fails here.
- The validated `float` is what the rest of the function uses.

On failure it raises `ValueError: box_margin must be an int, float, Fraction or numpy real scalar
that converts to a finite float > 0, got <value>`. The type list is in the message so that it is true
of every rejected value, including `Decimal("3")` and `10**400`, which are finite and positive. Without
this check, the caller would get the reader's `lo`/`hi` error, which names values they never wrote. A
non-numeric value such as `"3"` raises the same `ValueError`, not a `TypeError`.

The check covers all four field modes, although only `lev-3d` uses the value. The default (3.0) is
valid, so a bad value is always an explicit mistake. Zero is rejected because `center ± 0` is a point
query, not a box. The docstring and the `--box-margin` help text say "used by lev-3d; validated in
every mode".

## D4. `step` validation mirrors `_validate_halo`

`step` must be an `int` or `np.integer`, and must be `>= 0`. Step 0 is valid, because `plt00000` is
written at initialization.

- `bool` is rejected, because it is an `int` subclass.
- `np.bool_` is rejected by the type test, because it is not an `np.integer`.

The message uses `repr(step)`, so `'100'` (a string) can be told apart from `100`. Validation runs
before `_config`, so a bad `step` is reported as a bad `step` even when the manifest is also broken.

## D5. One scan helper for `steps()` and the fallback

`steps()` and `plotfile()`'s fallback both call a private `_scan(run) -> dict[int, Path]`. It applies
`_PLT_PATTERN` and the `is_dir()` filter first, and only then checks for duplicates. So a regular file
`plt100` beside a directory `plt00100` is not a duplicate.

On a duplicate it raises, naming both directory basenames in sorted order:
`ambiguous plotfiles under <run>: two plotfile directories parse to step 100: plt00100, plt100`.

A duplicate anywhere in the run directory makes the fallback raise, even when the duplicate is a
different step from the one requested. Every listing operation gives the same verdict on the same
directory.

The miss error ("no plotfile for step N …; available steps: […]") takes its list from the same `_scan`
result. Today `plotfile()` lists the directory once, then calls `steps()`, which repeats the manifest
lookup and the run-directory stat and lists the directory again. After this change, a miss lists once.

## Implementation notes (reconciled after implementation)

### Why the duplicate-step message names the run directory

D5 originally showed only `two plotfile directories parse to step 100: plt00100, plt100`. The
implemented message prefixes `ambiguous plotfiles under <run>: `, matching the existing "no plotfile
for step N … under <run>" error. A duplicate is a property of one run directory, and the corpus
has 27 of them. Tests anchor on the sorted-name suffix with `$`, so the path cannot satisfy them.

### Why task 4.3's test forces the listing order

As first written, the non-directory test left the listing order to the filesystem. The mutant
"duplicate check before the `is_dir` filter" fires only when the directory is listed before the
same-step file, so that mutant is only caught when the order is pinned. The test now forces the adverse
order with the same `Path.iterdir` patch used for the duplicate test.

### Why the mutation table gained a row

"`is_dir` filter dropped" was added beside "duplicate check before the `is_dir` filter". The two fail
differently: the first lets files count as steps, the second only mis-orders the checks.

### Pre-PR review round (`/review-pr`, branch mode): what changed

Five reviewers found no blocking issue. These fixes were made before the PR was opened:

- **`box_margin=10**400` raised `TypeError`, not `ValueError`.** D3 says a bad value is always a
  `ValueError`, but `np.isfinite` cannot coerce an int beyond float64 range. The finiteness test
  now treats `TypeError`/`OverflowError` as "not finite".
- **`step` messages printed numpy reprs** (`got np.int64(-1)`), unlike `_validate_box_margin`.
  numpy scalars are now shown as plain values. (This entry first said "unlike `_validate_halo`" too;
  that was false, and the #140 round below fixes `_validate_halo`.) `repr` still tells `'100'`
  apart from `100`.
- **A NaN `x_inlet`/`x_outlet` got past `x_inlet >= x_outlet`,** because NaN compares False both
  ways. It then reached the reader, whose error names `lo`/`hi`. Both `sphere_cv_steadiness_fraction`
  and `sphere_cv_drag_cd` now test `not (x_inlet < x_outlet)`. The `sphere_cv_drag_cd` half
  fixes behaviour that predates this change. It is included because the D1 rationale (report bad
  input in the caller's terms) applies equally.
- **Tests:** `plotfile()` is now also checked on the first non-directory layout, and the
  before-`yt.load` and before-`import yt` tests run over the whole inverted matrix.
- **CHANGELOG:** the entry carries **BREAKING**, matching the proposal.

Recorded here rather than changed:

- **D1, zero tolerance.** The inversion check has no tolerance, so a 1-ULP inversion
  (`lo = nextafter(2, 3)`, `hi = 2`) raises where legacy returned one cell. This is deliberate. No
  committed call site builds corners that should coincide from separately rounded terms; `center ±
  box_margin` cannot invert, because rounding is monotone.
- **D2, cost of non-canonical names.** A hit on a non-canonical name such as `plt1500` now pays a
  full scan: the canonical miss, the `run_dir()` stat, and every matching entry's `is_dir()`. The
  old loop stopped at the first match. That full scan is the price of the duplicate check. AMReX
  never writes such names.
- **D2, case-insensitive mounts.** On NTFS or the `Z:` mount, a directory named `PLT00100` is
  served as `.../plt00100`, so `FieldSnapshot.source` records the canonical spelling rather than
  the on-disk one.
- **A/B total.** `scripts/verify_eulerian_box_ab.py`'s expected total on the six real plotfiles
  falls from 171 to 159 (15 `REGION_CASES` plus 9 `DIVERGENCE_CASES`, each run on 6 plotfiles, plus
  the per-file boxes). The earlier archived run with a different case set also totalled 159, so a
  log reading 159 is not by itself evidence of which case set ran.

Left as follow-ups, not done here:

- `_PLT_PATTERN`'s `\d` matches non-ASCII digits. This predates the change (#145).
- `os.scandir` in `_scan`, which belongs to #112.
- A shared `_run_path` helper for the run-directory path.

### PR review round (`/review-pr` on #140): what changed

Five reviewers found no blocking issue and five important ones, all fixed here:

- **No test showed that a valid `box_margin` is accepted.** Four mutants survived the whole suite:
  dropping `np.integer` or `np.floating` from the accepted types, and tightening `> 0` to `> 1e-3` or
  `>= 1`. A second scenario now requires `1e-9`, `0.5`, `2`, `np.int64(2)`, `np.float32(0.5)` and
  `Fraction(1, 2)` to pass validation in every mode.
- **The `box_margin` message was false for some values it rejected.** `Fraction(3)`, `Decimal("3")`
  and `10**400` are finite and positive, yet the message said "must be a finite number > 0". D3 now
  accepts any `numbers.Real` (so `Fraction` passes) and names the accepted types in the message.
- **A comment claimed `_validate_halo` unwraps numpy scalars; it did not.** `halo=np.float64(1.9)`
  was reported as `got np.float64(1.9)`. One helper, `mosquito_cfd._messages.plain_repr`, now formats
  the value in the `step`, `halo` and `box_margin` messages, replacing two copies of the expression.
- **The `sphere_cv_*` `Raises:` docstrings still said `x_inlet >= x_outlet`,** though the guard also
  rejects NaN. The guard was also copied into both functions. It is now one helper,
  `_require_upstream`, and both docstrings say "not strictly less than (NaN included)".
- **The inlet/outlet guard had tests but no spec scenario.** A `force-extraction` delta adds one to
  the existing "Robust input validation for the control-volume tools" requirement.

Recorded here rather than changed:

- **Infinite inlet/outlet planes** (`x_inlet=-inf`) still pass the guard and return a silent result.
  This predates the change and is filed as #143.
- **`flow_video` globs `plt?????`,** so steps of 100000 or more are skipped. This predates the change
  and is filed as #144.
