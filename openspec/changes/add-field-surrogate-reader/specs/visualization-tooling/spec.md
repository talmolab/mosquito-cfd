## MODIFIED Requirements

### Requirement: Optional visualization dependencies are lazily imported

`scipy`, `scikit-image`, and `imageio_ffmpeg` SHALL be imported inside the specific functions that
need them, not at module import time, **in every `visualization/` module that uses one of
them** — `wing_render.py` (`scipy.spatial.ConvexHull`), `flow_video.py`
(`scipy`/`skimage`/`imageio_ffmpeg`), and `kinematics_video.py` (`imageio_ffmpeg`) — following the
existing lazy-`yt`-import convention, which is implemented in
`mosquito_cfd.field_surrogate.snapshot.read_field_snapshot` and preserved through its
`stress_integral.extract_eulerian_box` wrapper.

#### Scenario: every visualization module is importable without the `viz` dependency group installed

- **GIVEN** a Python environment with the repo's base dependencies installed but not the `viz`
  group (no `scipy`/`scikit-image`/`imageio-ffmpeg`)
- **WHEN** `import mosquito_cfd.visualization.wing_render`,
  `import mosquito_cfd.visualization.flow_video`, and
  `import mosquito_cfd.visualization.kinematics_video` are each executed
- **THEN** every import succeeds; only calling a function that actually needs one of those packages
  (`wing_outline`, any `flow_video` rendering function, `kinematics_video`'s video-writing function)
  raises `ImportError`

