"""Write a synthetic 256x128x256 6-field fp64 plotfile with the repo's fixture generator."""

import importlib.util
import sys
from pathlib import Path

gen_path = Path(sys.argv[1])
out = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("gen", gen_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.write_fixture(root=out, shape=(256, 128, 256), dx=(0.03125, 0.03125, 0.03125))
print("wrote", out)
