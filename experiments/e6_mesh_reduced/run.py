"""E6: train PhysicsNeMo's Mesh_Reduced as an encoder-decoder on the near-wing velocity patch and
compare its held-out reconstruction with POD at the same latent size (plan Task 8).

    --stage data   (Windows) block-average the cached patch to a small grid -> outputs/patch_ds<d>.npy
    --stage train  (WSL2/GPU, E6 environment) one model; writes outputs/run_<tag>.json

Error definition, shared with E5: || x - x_hat || / || x - training mean ||, pooled over snapshots,
on velocities divided by each config's reference speed.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import holdout_configs
from experiments.common.record import write_run_record
from experiments.common.splits import carve_validation
from experiments.field import pod

OUT = Path(__file__).parent / "outputs"
E5 = Path(__file__).parents[1] / "e5_pod" / "outputs"
PATCH_SHAPE = (192, 128, 96, 3)


def data(down: int) -> None:
    from experiments.field import cache

    OUT.mkdir(exist_ok=True)
    mm = np.load(cache.CACHE_ROOT / "matrices" / "patch_u.npy", mmap_mode="r")
    nx, ny, nz, _ = PATCH_SHAPE
    out = np.empty((mm.shape[0], nx // down, ny // down, nz // down, 3), dtype=np.float32)
    for i in range(mm.shape[0]):
        a = np.asarray(mm[i]).reshape(PATCH_SHAPE)
        out[i] = a.reshape(nx // down, down, ny // down, down, nz // down, down, 3).mean(axis=(1, 3, 5))
    np.save(OUT / f"patch_ds{down}.npy", out)
    print(out.shape, flush=True)


def rel_error(x: np.ndarray, xhat: np.ndarray, mean: np.ndarray) -> float:
    return float(np.sqrt(((x - xhat) ** 2).sum() / ((x - mean) ** 2).sum()))


def train(args) -> None:
    import torch
    from torch_geometric.data import Data

    from experiments.e6_mesh_reduced.probe import grid_graph, pivotal_lattice
    from physicsnemo.models.mesh_reduced.mesh_reduced import Mesh_Reduced

    tag = f"ds{args.down}_enc{args.encode_dim}_piv{args.pivot_stride}_p{args.processor_size}_h{args.hidden}_s{args.seed}"
    if args.epochs != 150:
        tag += f"_e{args.epochs}"
    idx = pd.read_parquet(E5 / "index.parquet")
    raw = np.load(OUT / f"patch_ds{args.down}.npy")
    grid = raw.shape[1:4]
    x_all = raw.reshape(len(idx), -1, 3) / idx.u_ref.to_numpy()[:, None, None]  # (N, nodes, 3)

    test_cfg = list(holdout_configs())
    pool = sorted(set(idx.config) - set(test_cfg))
    train_cfg, val_cfg = carve_validation(pool, seed=1234)
    tr, va, te = (np.flatnonzero(idx.config.isin(c).to_numpy()) for c in (train_cfg, val_cfg, test_cfg))
    pool_rows = np.concatenate([tr, va])
    mean_field = x_all[pool_rows].mean(axis=0)  # reference mean for the error definition (21 configs, as in E5)
    ch_mean, ch_std = x_all[tr].mean(axis=(0, 1)), x_all[tr].std(axis=(0, 1))

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    dev = torch.device("cuda")
    pos, edge_index, edge_feat = grid_graph(grid)
    piv = pivotal_lattice(grid, args.pivot_stride)
    n_nodes, n_edges = len(pos), edge_index.shape[1]
    model = Mesh_Reduced(input_dim_nodes=3, input_dim_edges=4, output_decode_dim=3, output_encode_dim=args.encode_dim,
                         processor_size=args.processor_size, hidden_dim_processor=args.hidden).to(dev)
    pm, pp = torch.as_tensor(pos, device=dev), torch.as_tensor(piv, device=dev)
    ei, ef = torch.as_tensor(edge_index, device=dev), torch.as_tensor(edge_feat, device=dev)
    xs = torch.as_tensor((x_all - ch_mean) / ch_std, dtype=torch.float32)

    def batch_graph(b: int):
        offsets = (torch.arange(b, device=dev) * n_nodes).repeat_interleave(n_edges)
        g = Data(edge_index=ei.repeat(1, b) + offsets, num_nodes=b * n_nodes)
        g.batch = torch.arange(b, device=dev).repeat_interleave(n_nodes)
        return g, ef.repeat(b, 1)

    graphs = {}

    def forward(rows: np.ndarray, encode_only: bool = False):
        b = len(rows)
        if b not in graphs:
            graphs[b] = batch_graph(b)
        g, e = graphs[b]
        x = xs[rows].to(dev).reshape(b * n_nodes, 3)
        z = model.encode(x, e, g, pm, pp)
        if encode_only:
            return z
        return model.decode(z, e, g, pm, pp), x, z

    def evaluate(rows: np.ndarray) -> tuple[float, np.ndarray]:
        model.eval()
        outs = []
        with torch.no_grad():
            for i in range(0, len(rows), args.batch):
                out, _, _ = forward(rows[i : i + args.batch])
                outs.append(out.reshape(-1, n_nodes, 3).cpu().numpy())
        xhat = np.concatenate(outs) * ch_std + ch_mean
        return rel_error(x_all[rows], xhat, mean_field), xhat

    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs, eta_min=args.lr / 20)
    history, best_val, best_state, t_start = [], float("inf"), None, time.time()
    rng = np.random.default_rng(args.seed)
    result = {"tag": tag, "args": vars(args), "grid": grid, "n_nodes": n_nodes, "n_edges": int(n_edges),
              "n_pivotal": int(len(piv)), "latent_size": int(len(piv) * args.encode_dim),
              "n_params": int(sum(p.numel() for p in model.parameters())), "train_configs": train_cfg,
              "val_configs": val_cfg, "test_configs": test_cfg, "n_train": int(len(tr)), "n_val": int(len(va)),
              "n_test": int(len(te)), "status": "running"}
    try:
        torch.cuda.reset_peak_memory_stats()
        for epoch in range(args.epochs):
            model.train()
            perm, losses, t0 = rng.permutation(tr), [], time.time()
            for i in range(0, len(perm) - args.batch + 1, args.batch):
                opt.zero_grad()
                out, x, _ = forward(perm[i : i + args.batch])
                loss = torch.nn.functional.mse_loss(out, x)
                loss.backward()
                opt.step()
                losses.append(float(loss))
            sched.step()
            val_err, _ = evaluate(va)
            history.append({"epoch": epoch, "train_mse": float(np.mean(losses)), "val_rel_error": val_err,
                            "seconds": time.time() - t0})
            if val_err < best_val:
                best_val = val_err
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            if epoch % 5 == 0:
                print(history[-1], flush=True)
            if (time.time() - t_start) / 3600 > args.max_hours:
                result["stopped_early"] = f"time limit {args.max_hours} h at epoch {epoch}"
                break
        result["peak_gib"] = torch.cuda.max_memory_allocated() / 2**30
        model.load_state_dict(best_state)
        result["val_rel_error"], _ = evaluate(va)
        result["test_rel_error"], xhat = evaluate(te)
        result["train_rel_error"], _ = evaluate(tr)
        result["test_rel_error_per_config"] = {
            c: rel_error(x_all[r], xhat[np.isin(te, r)], mean_field)
            for c, r in ((c, np.flatnonzero((idx.config == c).to_numpy())) for c in test_cfg)}
        # encode latency
        model.eval()
        lat = {}
        with torch.no_grad():
            for b in (1, min(64, args.batch * 8)):
                try:
                    rows = np.resize(te, b)
                    forward(rows, encode_only=True)
                    torch.cuda.synchronize()
                    t0 = time.perf_counter()
                    for _ in range(5):
                        forward(rows, encode_only=True)
                    torch.cuda.synchronize()
                    lat[str(b)] = (time.perf_counter() - t0) / 5
                except Exception as exc:
                    lat[str(b)] = f"failed: {type(exc).__name__}"
        result["encode_seconds_per_batch"] = lat
        result["status"] = "done"
        torch.save(best_state, OUT / f"model_{tag}.pt")
    except Exception as exc:  # a failed run is a result
        result |= {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:400]}"}
    result["history"] = history
    result["hours"] = (time.time() - t_start) / 3600

    # POD comparator on the same downsampled, normalized data
    flat = x_all.reshape(len(idx), -1)
    comp = {}
    for name, rows in (("pod_21_configs", pool_rows), ("pod_same_training_configs", tr)):
        p = pod.fit(flat[rows])
        # error about the same reference mean as the model's
        def err(r, rows_eval=te, p=p):
            xh = pod.decode(p, pod.encode(p, flat[rows_eval], r))
            return rel_error(flat[rows_eval], xh, mean_field.ravel())
        comp[name] = {str(r): err(r) for r in sorted({8, 32, 64, 128, 256, result["latent_size"]}) if r <= len(p.sing)}
    result["pod"] = comp
    (OUT / f"run_{tag}.json").write_text(json.dumps(result, indent=2, default=str))
    write_run_record(OUT / f"record_{tag}", seed=args.seed, tag=tag,
                     environment="~/.venvs/mosquito-explore-e6: torch 2.12.1+cu126, torch_geometric 2.8.1, "
                                 "torch_scatter 2.1.2+pt211cu126, torch_cluster 1.6.3+pt211cu126")
    print({k: v for k, v in result.items() if k not in ("history", "args", "train_configs")}, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["data", "train"], required=True)
    ap.add_argument("--down", type=int, default=8)
    ap.add_argument("--encode-dim", type=int, default=3)
    ap.add_argument("--pivot-stride", type=int, default=4)
    ap.add_argument("--processor-size", type=int, default=15)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--max-hours", type=float, default=3.0)
    a = ap.parse_args()
    data(a.down) if a.stage == "data" else train(a)
