"""Stage-2 field-surrogate reader (see ``docs/field_surrogate/roadmap.md``, row F2).

Turns AMReX plotfiles into framework-neutral flow-field snapshots for the future encoder (F3):
a dense :class:`~mosquito_cfd.field_surrogate.snapshot.FieldSnapshot`, a
:class:`~mosquito_cfd.field_surrogate.snapshot.PointCloud` view, ``FieldCorpus`` addressing by
``(config_id, step)``, and a bounded DoMINO volume-half adapter.

**This module intentionally imports none of its submodules.** ``benchmarks/__init__`` imports
``stress_integral``, which after ``add-field-surrogate-reader`` imports ``snapshot``, so whatever
this ``__init__`` imported eagerly would load on every ``benchmarks`` import, and any submodule
that ever reached ``force_surrogate`` again would re-arm the
``benchmarks -> field_surrogate -> force_surrogate -> benchmarks`` cycle that change's
``design.md`` D4 describes. Import the submodules directly. (``corpus`` no longer reaches
``force_surrogate`` at all: it reads the manifest through the stdlib-only
``mosquito_cfd._manifest``; share-light-corpus-helpers, #160.)

Out of scope here and deferred to F3: ``geometry_coordinates``, ``sdf_grid``/``sdf_nodes``, the
``surface_mesh_*`` arrays, corpus-wide ``.npy`` export, and any multi-level/AMR handling (CC-F3
is an open decision).
"""
