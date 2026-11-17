"""E6 step 2: does stock Mesh_Reduced run here at all, and how does its cost grow with graph size?

One encode -> decode -> backward pass on a regular 3-D grid graph, for several sizes. Reports time
and peak GPU memory, so the patch size for training is chosen from measurements.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

OUT = Path(__file__).parent / "outputs"


def grid_graph(shape: tuple[int, int, int], spacing: float = 1.0):
    """6-neighbour grid graph: positions (N, 3), bidirectional edge_index (2, E), edge features (E, 4)."""
    nx, ny, nz = shape
    idx = np.arange(nx * ny * nz).reshape(shape)
    pos = np.stack(np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij"), axis=-1).reshape(-1, 3) * spacing
    pairs = [
        (idx[:-1, :, :].ravel(), idx[1:, :, :].ravel()),
        (idx[:, :-1, :].ravel(), idx[:, 1:, :].ravel()),
        (idx[:, :, :-1].ravel(), idx[:, :, 1:].ravel()),
    ]
    src = np.concatenate([a for a, b in pairs] + [b for a, b in pairs])
    dst = np.concatenate([b for a, b in pairs] + [a for a, b in pairs])
    rel = pos[dst] - pos[src]
    edge_feat = np.concatenate([rel, np.linalg.norm(rel, axis=1, keepdims=True)], axis=1)
    return pos.astype(np.float32), np.stack([src, dst]).astype(np.int64), edge_feat.astype(np.float32)


def pivotal_lattice(shape: tuple[int, int, int], stride: int, spacing: float = 1.0) -> np.ndarray:
    """Pivotal nodes on a regular sub-lattice, offset to sit at block centres."""
    axes = [np.arange(stride / 2 - 0.5, n, stride) for n in shape]
    return (np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3) * spacing).astype(np.float32)


def main() -> None:
    from torch_geometric.data import Data

    from physicsnemo.models.mesh_reduced.mesh_reduced import Mesh_Reduced

    ap = argparse.ArgumentParser()
    ap.add_argument("--processor-size", type=int, default=15)
    ap.add_argument("--hidden", type=int, default=128)
    args = ap.parse_args()
    dev = torch.device("cuda")
    results = []
    for shape, stride in (((12, 12, 12), 4), ((24, 16, 12), 4), ((48, 32, 12), 4), ((48, 32, 24), 4), ((96, 64, 24), 8)):
        rec = {"shape": shape, "n_nodes": int(np.prod(shape)), "stride": stride,
               "processor_size": args.processor_size, "hidden": args.hidden}
        try:
            pos, edge_index, edge_feat = grid_graph(shape)
            piv = pivotal_lattice(shape, stride)
            rec |= {"n_edges": int(edge_index.shape[1]), "n_pivotal": int(len(piv))}
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            model = Mesh_Reduced(input_dim_nodes=3, input_dim_edges=4, output_decode_dim=3, output_encode_dim=3,
                                 processor_size=args.processor_size, hidden_dim_processor=args.hidden).to(dev)
            rec["n_params"] = int(sum(p.numel() for p in model.parameters()))
            graph = Data(edge_index=torch.as_tensor(edge_index), num_nodes=len(pos)).to(dev)
            graph.batch = torch.zeros(len(pos), dtype=torch.long, device=dev)
            x = torch.randn(len(pos), 3, device=dev)
            ef, pm, pp = torch.as_tensor(edge_feat, device=dev), torch.as_tensor(pos, device=dev), torch.as_tensor(piv, device=dev)
            opt = torch.optim.Adam(model.parameters(), lr=1e-4)
            times = []
            for _ in range(4):
                t0 = time.perf_counter()
                opt.zero_grad()
                z = model.encode(x, ef, graph, pm, pp)
                out = model.decode(z, ef, graph, pm, pp)
                loss = torch.nn.functional.mse_loss(out, x)
                loss.backward()
                opt.step()
                torch.cuda.synchronize()
                times.append(time.perf_counter() - t0)
            rec |= {"ok": True, "latent_shape": tuple(z.shape), "latent_size": int(z.numel()),
                    "seconds_per_step": float(np.median(times[1:])), "peak_gib": torch.cuda.max_memory_allocated() / 2**30,
                    "loss_finite": bool(torch.isfinite(loss))}
            del model, graph, x, ef, pm, pp, z, out, loss, opt
        except Exception as exc:  # out of memory or a dependency failure is the result, not a crash
            rec |= {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        results.append(rec)
        print(rec, flush=True)
    OUT.mkdir(exist_ok=True)
    tag = f"p{args.processor_size}_h{args.hidden}"
    (OUT / f"probe_{tag}.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
