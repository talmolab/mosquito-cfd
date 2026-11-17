# Surrogate-data exploration (lab meeting 2026-11-24)

Exploratory experiments; nothing here is production code. Design:
`docs/superpowers/specs/2026-11-16-surrogate-exploration-design.md`.

| | Experiment | Status | Report |
|---|---|---|---|
| 0 | Environment gate and sizing | done: seed 1234 reproduced exactly; 30 s per fit | [report](step0_environment/report.md) |
| E0 | Beat 1 versus beat 2 | done: the beats differ by 5–17% of peak (fine grid, median); `CF_z` mean drops 14% | [report](e0_periodicity/report.html) |
| E1 | Hover gate | done: Track B error is 1–2% of peak and inside all three yardsticks for every held-out config and component (worst seed) | [report](e1_hover_gate/report.html) |
