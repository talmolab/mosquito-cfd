# Fix digest validation to reject overlong hex runs

## Why

`validate_image_digest`'s regex (`sha256:[0-9a-f]{64}`, matched via `.search`, no end-anchor)
only checks that 64 consecutive hex characters appear *somewhere* after `sha256:` — it does not
check that the hex run is *exactly* 64 characters. A digest string with one or more extra trailing
hex characters (`sha256:` + 65 hex chars) is accepted as valid today, even though it is not a real
SHA-256 digest. Found during PR #73's second adversarial review round for the unrelated
`add-visualization-tooling` change (which merely *calls* `validate_image_digest`); fixed here as
its own small, separately-tracked change to the `run-metadata` capability this function actually
belongs to, bundled into the same PR at the user's request rather than deferred to a follow-up.

## What Changes

- `sidecar._DIGEST_RE` gains a negative lookahead (`(?![0-9a-f])`) immediately after the 64-char
  hex run, so a 65th (or later) hex character immediately following the run fails the match. This
  does not change acceptance of any currently-valid digest (a real digest is never followed by
  another hex character when embedded in an image reference — the next character, if any, is a
  reference-syntax separator like `:` or nothing) and does not require `.fullmatch` (which would
  break the documented use case of passing a full `repo@sha256:<64hex>` reference, not a bare
  digest).

## Impact

- **Affected specs**: `run-metadata` (MODIFIED — the existing "malformed digest is rejected"
  scenario's coverage is extended with an explicit overlong-hex-run case).
- **Affected code**: `src/mosquito_cfd/force_surrogate/sidecar.py` (`_DIGEST_RE`),
  `tests/test_force_surrogate_sidecar.py`.
- **Not affected**: any already-captured run-metadata artifact (a real digest was never affected
  by this gap; the gap only concerns whether an *invalid* overlong string was wrongly accepted,
  and no code path in this repo currently constructs such a string).
