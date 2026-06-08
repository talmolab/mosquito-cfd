## Why

The RunAI workflow routinely requires running commands *inside* an already-running
workspace — executing IAMReX simulations, copying files, reading logs — via
`runai workspace exec`. The `runai-cluster-skill` spec documented submit / list / logs /
describe / delete but never the `exec` lifecycle operation, even though it is relied on in
practice (and `kubectl exec` must NOT be used because RunAI manages its own auth layer).
This change captures that scenario in the spec through the proper change→archive flow,
rather than as an undocumented direct edit.

## What Changes

- Add an "Execute command in running workspace" scenario to the existing
  **Workspace Management Commands** requirement of `runai-cluster-skill`, documenting
  `runai workspace exec <name> -p talmo-lab -- <command>`, the `kubectl exec` caveat, and
  usage examples (list files, run a simulation, read a file, interactive shell).

## Impact

- Modified spec: `runai-cluster-skill` (Workspace Management Commands requirement)
- No code changes — documentation / skill-template only
