"""The bench package imports no heavy dependency, and its scope names three limits (3b.1).

Scenarios "Importing the bench pulls in no heavy dependency" and "The scope names all three
limits" (surrogate-comparison-bench spec).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BLOCKED = ("torch", "physicsnemo", "scipy", "sklearn")


def test_importing_the_bench_imports_no_heavy_dependency():
    """A meta-path hook raises on any blocked import, so the check holds with or without them."""
    script = textwrap.dedent(
        f"""
        import importlib.abc, sys
        BLOCKED = {BLOCKED!r}
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("blocked import: " + name)
                return None
        sys.meta_path.insert(0, Block())
        import mosquito_cfd.surrogate_bench
        import mosquito_cfd.surrogate_bench.splits
        print("imported")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "imported" in result.stdout


def test_the_scope_names_all_three_limits():
    from mosquito_cfd.surrogate_bench import BENCH_SCOPE

    for phrase in (
        "3 × 3 × 3",
        "held-out outer layer",
        "2-beat",
        "has not settled",
        "#142",
    ):
        assert phrase in BENCH_SCOPE, phrase


def test_the_bench_seeds_are_the_shipped_seeds():
    from mosquito_cfd.surrogate_bench import BENCH_SEEDS

    assert BENCH_SEEDS == (1234, 1235, 1236, 1237, 1238)


def test_the_bench_mlp_recipe_is_the_shipped_trainers_defaults():
    """mlp_h1 must reproduce the shipped recipe, so the bench reads it from run_training."""
    import inspect

    from mosquito_cfd.force_surrogate import train
    from mosquito_cfd.surrogate_bench import BENCH_SEEDS, metrics, runner, splits

    defaults = {
        name: p.default
        for name, p in inspect.signature(train.run_training).parameters.items()
    }
    assert runner.MLP_HYPERPARAMETERS == {
        "hidden": defaults["hidden"],
        "num_layers": defaults["num_layers"],
        "lr": defaults["lr"],
    }
    assert (
        inspect.signature(runner.run_bench).parameters["epochs"].default
        == (defaults["epochs"])
    )
    assert splits.N_VAL_CONFIGS == defaults["n_val_configs"]
    assert BENCH_SEEDS == tuple(range(defaults["seed"], defaults["seed"] + 5))
    assert metrics.MIN_SEEDS == len(BENCH_SEEDS)


def test_the_window_start_follows_the_grid():
    import math

    from mosquito_cfd.surrogate_bench import gate
    from mosquito_cfd.surrogate_bench.ridge import N_GRID

    assert gate.WINDOW_START == math.ceil(gate.WINDOW_PHASE * N_GRID)
    assert (
        gate.WINDOW_START / N_GRID
        >= gate.WINDOW_PHASE
        > (gate.WINDOW_START - 1) / N_GRID
    )


def test_fit_seed_and_predict_frame_use_a_public_result_type():
    from mosquito_cfd import force_surrogate
    from mosquito_cfd.force_surrogate import train

    assert force_surrogate.SeedFit is train.SeedFit
    assert "SeedFit" in force_surrogate.__all__
