"""Stage-2 field-surrogate reader (see ``docs/field_surrogate/roadmap.md``, row F2).

Turns AMReX plotfiles into framework-neutral flow-field snapshots for the future encoder (F3):
a dense :class:`~mosquito_cfd.field_surrogate.snapshot.FieldSnapshot`, a
:class:`~mosquito_cfd.field_surrogate.snapshot.PointCloud` view, ``FieldCorpus`` addressing by
``(config_id, step)``, and a bounded DoMINO volume-half adapter.

**This module intentionally imports none of its submodules.** Importing ``corpus`` reaches
``force_surrogate.dataset`` and therefore ``pandas``, and -- because
``benchmarks/__init__`` imports ``stress_integral``, which after ``add-field-surrogate-reader``
imports ``snapshot`` -- an eager re-export would also arm a
``benchmarks -> field_surrogate -> force_surrogate -> benchmarks`` import cycle whose survival
depends only on statement order inside two ``__init__`` files. Import the submodules directly
(see that change's ``design.md`` D4).

Out of scope here and deferred to F3: ``geometry_coordinates``, ``sdf_grid``/``sdf_nodes``, the
``surface_mesh_*`` arrays, corpus-wide ``.npy`` export, and any multi-level/AMR handling (CC-F3
is an open decision).
"""
