import numpy as np

from experiments.common.stats import position_class, reversal_share


def test_reversal_share_uniform_and_concentrated():
    ph = np.arange(1000) / 1000
    assert abs(reversal_share(np.ones(1000), ph) - 0.2) < 0.01
    e = np.zeros(1000)
    e[250] = 1.0
    assert reversal_share(e, ph) == 1.0
    e = np.zeros(1000)
    e[500] = 1.0
    assert reversal_share(e, ph) == 0.0


def test_reversal_phases_match_repo_kinematics():
    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles

    for ph in (0.25, 0.75):  # stroke angle is extremal (stroke rate zero) at the reversals
        a, b, c = (euler_angles(ph + d, frequency=1.0, stroke_amp_rad=1.0, pitch_amp_rad=0.5)[0] for d in (-1e-4, 0.0, 1e-4))
        assert abs(b) > abs(a) and abs(b) > abs(c)


def test_position_class_counts():
    levels = [(s, f, p) for s in (35, 45, 55) for f in (0.85, 1.0, 1.15) for p in (30, 45, 60)]
    classes = [position_class(*x) for x in levels]
    assert {c: classes.count(c) for c in set(classes)} == {"corner": 8, "edge": 12, "face": 6, "centre": 1}
