"""Vertex file I/O for Lagrangian markers.

The .vertex format is a simple text format:
    <number_of_markers>
    x1 y1 z1
    x2 y2 z2
    ...

Coordinates are in scientific notation for precision.
"""

import numpy as np


def write_vertex_file(markers: np.ndarray, filepath: str) -> None:
    """Write markers to .vertex format.

    Parameters
    ----------
    markers : np.ndarray
        Array of marker positions with shape (N, 3)
    filepath : str
        Output file path
    """
    with open(filepath, "w") as f:
        f.write(f"{len(markers)}\n")
        for m in markers:
            f.write(f"{m[0]:.10e} {m[1]:.10e} {m[2]:.10e}\n")


def read_vertex_file(filepath: str) -> np.ndarray:
    """Read markers from .vertex file.

    Parameters
    ----------
    filepath : str
        Input file path

    Returns
    -------
    markers : np.ndarray
        Array of marker positions with shape (N, 3)
    """
    with open(filepath) as f:
        n_markers = int(f.readline().strip())
        markers = np.zeros((n_markers, 3))
        for i in range(n_markers):
            line = f.readline().strip().split()
            markers[i] = [float(x) for x in line[:3]]
    return markers
