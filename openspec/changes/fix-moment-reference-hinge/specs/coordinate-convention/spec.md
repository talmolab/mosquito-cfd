# coordinate-convention — moment reference point

## ADDED Requirements

### Requirement: The canonical convention page states the moment reference point

The canonical convention page SHALL state the **moment reference point** alongside the axis
assignments it already carries. That page is `docs/coordinate-convention.md`, the single canonical
narrative source for the wing convention, and the statement SHALL live in a `## Moments` section
sibling to the existing `## Forces` section. The omission of such a section is
what allowed the force-surrogate extractor to inherit the immersed-boundary particle's own origin
(the wing's mid-span point) as its moment origin, undetected, while this page already declared a
hinge origin.

The section SHALL state:

- that repository moments are **lab-frame components taken about the wing hinge**;
- that the axes are **not** rotated into the wing frame, so these are not van Veen wing-frame
  moments — that would additionally require rotating by `R(t)ᵀ` (GitHub issue #1);
- that raw solver-written moment columns are about the solver's own particle origin, while derived
  moment **coefficients** are about the hinge;
- the centre-of-mass alternative appropriate to a future body-in-the-loop model, recorded as a
  deliberate deferral rather than left implicit.

Per the existing DRY requirement, in-repo locations SHALL **cross-reference** this section rather
than restate the reference point's justification or citation, so the copies cannot drift.

The hinge-origin statement SHALL carry a **verbatim** citation from van Veen et al. (2022) on the
same footing as the axis-direction quotation already on the page. Where a claim cannot be sourced
verbatim, it SHALL be narrowed to what the source supports rather than asserted unquoted.

#### Scenario: The canonical page documents the moment reference point

- **Given** `docs/coordinate-convention.md`
- **When** it is read
- **Then** it contains a `## Moments` section naming the wing hinge as the reference point, stating that the axes remain lab axes, and recording the centre-of-mass deferral

#### Scenario: The hinge origin is sourced verbatim

- **Given** the `## Moments` section's citation of van Veen et al. (2022)
- **When** it is checked against the paper
- **Then** the origin claim is supported by a verbatim quotation, as the axis-direction claim already is — and any part not so supported (for example a claim about the *world*-frame origin) is either quoted or removed rather than asserted

#### Scenario: Downstream statements cross-reference rather than restate

- **Given** the force-surrogate module documentation and the corpus READMEs
- **When** they refer to the moment reference point
- **Then** they name it and point at `docs/coordinate-convention.md`, without restating its justification or its van Veen citation
