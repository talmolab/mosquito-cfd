## MODIFIED Requirements

### Requirement: Video and figure generators resolve parameters from a named config or an explicit override, never a hardcoded constant

`flow_video.py` and `kinematics_video.py` SHALL accept either `--config <name> --corpus-dir <dir>`
(resolving hinge, center, and kinematics from that config's own generated deck) or explicit
`--hinge`, `--center`, `--stroke-amp-deg`, `--pitch-amp-deg`, `--frequency-fstar` overrides. No
plotfile path, hinge value, or kinematic parameter SHALL be a hardcoded module-level constant
reachable only by editing source.

#### Scenario: any of the 27 sweep configs can be rendered without editing source

- **GIVEN** a sweep corpus directory containing `sweep_manifest.json` and a generated deck for
  config `s35_f085_p30`
- **WHEN** `make_flow_video.py` is invoked with `--config s35_f085_p30 --corpus-dir <dir>
  --field-mode wake-slice --plotfile-dir <plt-dir> --out-dir <out> --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex>
  --timestamp <iso8601>`
- **THEN** the video is rendered using that config's own hinge/center/kinematics read from its deck,
  with no source-code edit required

#### Scenario: an explicit override takes precedence over the config's own deck values

- **GIVEN** config `s45_f115_p60`'s own deck records the as-run hinge `(4.0, 2.0, 2.5)`
- **WHEN** `make_kinematics_video.py` is invoked with `--config s45_f115_p60 --corpus-dir <dir>
  --hinge 4.0 0.5 4.0`
- **THEN** the rendered video uses the explicit override hinge `(4.0, 0.5, 4.0)`, not the deck's own
  `(4.0, 2.0, 2.5)`
