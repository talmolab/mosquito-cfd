"""Geometry generation for immersed boundary markers.

This module provides tools for generating Lagrangian marker positions
for wing planforms and reading/writing .vertex files.
"""

from mosquito_cfd.geometry.parametric_planform import (
    PlanformShape,
    generate_planform,
)
from mosquito_cfd.geometry.vertex_io import (
    read_vertex_file,
    write_vertex_file,
)

__all__ = [
    "PlanformShape",
    "generate_planform",
    "read_vertex_file",
    "write_vertex_file",
]