"""``FieldCorpus``: address plotfiles by ``(config_id, step)`` against a caller-supplied root.

The root is caller-supplied because the real 27-config corpus lives on cluster NFS, not in the
repository. Steps are discovered from the ``plt*`` directories actually present on disk rather
than assumed from a deck's ``plot_int`` -- a run can be truncated.
"""
