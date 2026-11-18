"""Module-level torch ``Dataset`` and collate for the DataLoader worker test.

Imported only after ``pytest.importorskip("torch")``: torch is in the Linux-gated ``train``
dependency group, absent from CI and from the default sync. Everything here is module-level so a
``spawn`` worker can unpickle it.
"""

from __future__ import annotations

from torch.utils.data import Dataset

from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

_FULL = {"lo": (-float("inf"),) * 3, "hi": (float("inf"),) * 3}


class SnapshotDataset(Dataset):
    """Four samples, each a full-extent read of one plotfile."""

    def __init__(self, path: str) -> None:
        """Bind the dataset to a plotfile path (a ``str``, so it pickles trivially)."""
        self.path = path

    def __len__(self) -> int:
        """Return the fixed sample count."""
        return 4

    def __getitem__(self, index: int):
        """Return a :class:`FieldSnapshot`; the worker queue pickles it back to the parent."""
        return read_field_snapshot(self.path, **_FULL)


def identity(batch):
    """Pass-through ``collate_fn`` (module-level, so ``spawn`` can pickle it)."""
    return batch
