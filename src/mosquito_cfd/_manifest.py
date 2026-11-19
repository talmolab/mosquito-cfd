"""The guarded sweep-manifest reader, shared by the field and force surrogates.

Standard library only, by contract (share-light-corpus-helpers, #160): ``FieldCorpus`` reads the
manifest on its first call, inside every training data-loader worker, and importing
``mosquito_cfd.force_surrogate`` there would load pandas, pyarrow and ``matplotlib.pyplot`` and
switch the process's matplotlib backend. ``mosquito_cfd.force_surrogate.dataset`` re-exports
everything here as the same objects, so its callers are unchanged.

Every rejection is a ``ValueError`` naming the manifest path, except a missing file, which stays
``FileNotFoundError``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

# Manifest config keys build_dataset (and FieldCorpus.global_params) read.
_REQUIRED_CONFIG_KEYS = frozenset(
    {
        "name",
        "index",
        "stroke_amp_deg",
        "frequency_fstar",
        "pitch_amp_deg",
        "reynolds",
        "split",
    }
)


def _validate_configs(configs: object) -> None:
    """Validate the manifest config list before any extraction (clear errors, no KeyError)."""
    if not isinstance(configs, list):
        raise ValueError(
            f"manifest 'configs' must be a list, got {type(configs).__name__}"
        )
    seen: set[str] = set()
    for i, config in enumerate(configs):
        if not isinstance(config, Mapping):
            raise ValueError(f"manifest config {i} is not a mapping: {config!r}")
        missing = sorted(_REQUIRED_CONFIG_KEYS - set(config))
        if missing:
            raise ValueError(
                f"manifest config {i} is missing required key(s) {missing}; "
                f"expected at least {sorted(_REQUIRED_CONFIG_KEYS)}"
            )
        name = str(config["name"])
        if name in seen:
            raise ValueError(
                f"duplicate config name {name!r} in manifest (config {i}); names must be "
                "unique so each maps to one CSV and one split"
            )
        seen.add(name)


def load_manifest_configs(manifest_path: Path | str) -> list[dict]:
    """Read a sweep manifest and return its validated ``configs`` list.

    Validation happens here so **both** the driver (which resolves CSV paths from the config
    names) and ``build_dataset`` (and ``FieldCorpus``) go through the same guarded reader -- a
    malformed manifest never surfaces as a bare ``KeyError``/``TypeError`` on any path.

    Args:
        manifest_path: Path to the sweep manifest JSON.

    Returns:
        The validated ``configs`` list.

    Raises:
        FileNotFoundError: If the manifest does not exist.
        ValueError: If the file is not valid UTF-8 or not valid JSON (including JSON the parser
            refuses with ``ValueError`` or ``RecursionError``: an integer beyond Python's digit
            limit, or nesting deeper than the recursion limit); if its top level is not a JSON
            object; if it has no ``configs`` key or ``configs`` is not a list; or if a config is
            malformed or has a duplicate name.
    """
    path = Path(manifest_path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"sweep manifest {path} is not valid UTF-8: {exc}") from exc
    try:
        manifest = json.loads(text)
    except (ValueError, RecursionError) as exc:
        # JSONDecodeError is a ValueError; so is the int-digit limit, and deep nesting raises
        # RecursionError -- all are "not valid JSON" (as in mosquito_cfd._provenance).
        raise ValueError(f"sweep manifest {path} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(
            f"manifest {path} top level is a {type(manifest).__name__}, not an object; "
            "not a sweep manifest"
        )
    if "configs" not in manifest:
        raise ValueError(f"manifest {path} has no 'configs' key; not a sweep manifest")
    configs = manifest["configs"]
    _validate_configs(configs)
    return configs
