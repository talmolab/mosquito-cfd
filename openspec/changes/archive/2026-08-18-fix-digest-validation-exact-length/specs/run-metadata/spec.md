## MODIFIED Requirements

### Requirement: docker image identity is a single unambiguous, digest-validated field

The metadata generator SHALL record the docker image identity under one field, validated to match
the `sha256:[0-9a-f]{64}` digest format **exactly** (not a 64-character hex run embedded within a
longer hex sequence), and SHALL NOT split image identity across two inconsistent fields (a mutable
tag under one key and the digest under another).

#### Scenario: digest-only image identity

- **GIVEN** a pod-side `run_metadata.json` with a validated `sha256:...` docker image digest
- **WHEN** the generator assembles the committed metadata file
- **THEN** exactly one field, named `docker_image`, carries the image identity, its value matches
  the digest regex, and no separate mutable-tag field is present

#### Scenario: malformed digest is rejected

- **GIVEN** a pod-side `run_metadata.json` whose docker image field does not match
  `sha256:[0-9a-f]{64}` (e.g. a bare tag like `ghcr.io/talmolab/mosquito-cfd:fp64`, or a
  truncated/malformed digest)
- **WHEN** the generator attempts to assemble metadata from it
- **THEN** it raises a clear validation error naming the offending value, rather than passing the
  invalid identity through to the committed output

#### Scenario: an overlong hex run is rejected, not truncated and accepted

- **GIVEN** a candidate digest of the form `sha256:` followed by 65 or more consecutive hex
  characters (one or more characters longer than a real SHA-256 digest)
- **WHEN** `validate_image_digest` checks it
- **THEN** it raises `ValueError` — the validator does not match only the first 64 characters of
  the hex run and silently accept the rest as valid
