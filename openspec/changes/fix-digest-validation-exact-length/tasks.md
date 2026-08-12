## Tasks

1. [x] Write `tests/test_force_surrogate_sidecar.py::test_validate_image_digest_rejects_overlong_hex_run`
   — `validate_image_digest("repo@sha256:" + "a" * 65)` must raise `ValueError` matching
   `"content-addressable"`. Must fail (digest wrongly accepted, no exception raised) against the
   current `_DIGEST_RE` before the fix.
2. [x] Fix `_DIGEST_RE` in `src/mosquito_cfd/force_surrogate/sidecar.py`: add a negative lookahead
   `(?![0-9a-f])` immediately after `[0-9a-f]{64}`. Run task 1's test green.
3. [x] Confirm no regression: `test_validate_image_digest_accepts_and_strips` and
   `test_validate_image_digest_rejects_mutable_or_empty` (pre-existing) still pass unchanged.
4. [x] `uv run ruff check` / `uv run ruff format --check`.
5. [x] `openspec validate fix-digest-validation-exact-length --strict`.
