"""Input-feature variants for the Track B ablations. The default is the repo's ``build_features``."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

KINEMATIC = ("stroke_amp_deg", "frequency_fstar", "pitch_amp_deg")


def make_feature_fn(
    *, drop: tuple[str, ...] = (), use_re: bool = False, harmonics: int = 1
) -> Callable[[pd.DataFrame], tuple[np.ndarray, list[str]]]:
    """Feature builder: kinematic inputs (minus ``drop``; ``frequency_fstar`` swapped for ``reynolds`` if
    ``use_re``) followed by sin/cos of the first ``harmonics`` multiples of the phase."""

    def fn(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        cols, names = [], []
        for k in KINEMATIC:
            if k in drop:
                continue
            src = "reynolds" if (use_re and k == "frequency_fstar") else k
            cols.append(df[src].to_numpy(dtype=float))
            names.append(src)
        phase = df["phase"].to_numpy(dtype=float)
        for h in range(1, harmonics + 1):
            suffix = "" if h == 1 else str(h)
            cols += [np.sin(2.0 * np.pi * h * phase), np.cos(2.0 * np.pi * h * phase)]
            names += [f"phase_sin{suffix}", f"phase_cos{suffix}"]
        return np.column_stack(cols), names

    return fn
