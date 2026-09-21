"""Plotfile -> ``FieldSnapshot`` reader: the repository's single Eulerian-box covering-grid read.

``yt`` is imported lazily inside the reader, never at module scope, so importing this module (or
``benchmarks.stress_integral``, which delegates to it) stays cheap.
"""
