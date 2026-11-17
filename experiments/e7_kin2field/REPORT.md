# E7: flow field from kinematics alone

Run 2026-11-17 on `explore-surrogate-experiments`. Figure: `figures/kin2field_error.png`.

## Question

Can a model that sees only the wing kinematics (stroke amplitude, frequency, pitch amplitude) and
the phase within the beat produce the near-wing velocity field of a config it was never shown?

## Data

The Gram matrices saved by E5 follow-up 2 (`e5_pod/outputs/gram_*.npy`): fine corpus
(256 × 128 × 256, re-extracted after #146 and #71), second wingbeat, 558 snapshots over 27 configs.
The corpus's 6 holdout configs (128 snapshots) are the test set; the other 21 (430 snapshots) train
both the POD basis and the model. No field data was read and no CFD was run.

## Method

1. POD of the training snapshots, in three descriptions of the flow: the wing-fixed box in wing
   axes, the same fluid in lab axes, and the whole near-wing patch in lab axes.
2. The E4 ridge model (Fourier harmonics in phase × polynomial in the three kinematic inputs) is
   fitted to the training snapshots' POD coefficients. Its size is chosen by leave-one-config-out
   inside the training configs, at 64 modes: 8 harmonics, degree 2 in every case.
3. The model predicts the holdout configs' coefficients. The error of the decoded field is exact
   from the coefficients, because the modes are orthonormal.
4. Two yardsticks: the same modes given the holdout snapshot's own coefficients (the floor for any
   model writing through this basis), and reusing the training snapshot nearest in kinematics and
   phase (no model).

Errors are root-sum-square over the 128 holdout snapshots, relative to the fluctuation about the
training-mean field (so predicting the mean field scores 100%).

## Result

| Description of the flow | Modes | Predicted from kinematics | Rebuilt from the CFD snapshot | Nearest training snapshot |
|---|---|---|---|---|
| Wing-fixed box, wing axes | 64 | **8.1%** | 4.3% | 19.2% |
| Wing-fixed box, wing axes | 256 | 7.8% | 1.4% | 19.2% |
| Same fluid, lab axes | 64 | 35.9% | 27.4% | 66.3% |
| Whole near-wing patch, lab axes | 64 | 23.9% | 16.5% | 52.2% |

- In the wing frame the prediction is within a factor of two of the floor and better than the
  no-model baseline by more than a factor of two. Per config it ranges from 7.0% to 10.5%; per
  snapshot from 3.8% to 13.0%.
- On the same fluid, the wing-frame prediction's absolute error is 5 times smaller than the
  lab-frame one.
- Beyond 64 modes the prediction stops improving (8.1% → 7.8%) while the floor keeps falling: the
  limit is the kinematics-to-coefficient map, not the basis.

## Caveats

- This is interpolation inside a 3 × 3 × 3 grid of configs, on second-beat data that E0b shows is
  not yet settled. It says nothing about kinematics outside the grid or about transients.
- The chosen 8 harmonics is the largest value tried; with about 20 snapshots per beat a larger
  value cannot be tested on this corpus.
- The wing-fixed box stops at the wing tip, so the tip vortex outside it is not covered.
- The POD basis used during model selection had seen all 21 training configs. The holdout configs
  were not used for the basis, the model, or the selection.
- One deterministic fit, so there is no seed spread. E4 found this model family unreliable on fewer
  than the full 21 configs; that was not re-tested here.
- Velocity only. Pressure is not in the plotfiles (only its gradient).

## Next step

Render CFD, 64-mode reconstruction and prediction side by side for a holdout config, in the two 3D
views used in the overview deck, by rotating the wing-frame result back into the lab frame.
