"""Generate force time series figure for heaving ellipsoid benchmark.

Creates publication-ready figure showing force convergence to quasi-steady state.
"""

import matplotlib.pyplot as plt
import numpy as np

# Force data from heaving ellipsoid 1000-step simulation
# Extracted from particle_real_comp3 (Fx) and comp4 (Fy)
time = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
fx_fluid = np.array([0.000, -0.214, -0.204, -0.197, -0.194, -0.192, -0.190, -0.190, -0.188, -0.189, -0.188])
fy_fluid = np.array([0.000, 0.109, 0.106, 0.105, 0.103, 0.103, 0.102, 0.101, 0.101, 0.100, 0.100])

# Force on body = -force on fluid
F_drag = -fx_fluid
F_lift = -fy_fluid

# Create figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

# Drag force
ax1.plot(time, F_drag, 'b-o', linewidth=2, markersize=6, label='Drag (Fx)')
ax1.axhline(y=F_drag[-1], color='b', linestyle='--', alpha=0.5, label=f'Steady: {F_drag[-1]:.3f}')
ax1.axvspan(7, 10, alpha=0.1, color='green', label='Quasi-steady region')
ax1.set_ylabel('Drag Force (F_x)', fontsize=12)
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.3)
ax1.set_ylim([0.15, 0.25])

# Lift force
ax2.plot(time, F_lift, 'r-s', linewidth=2, markersize=6, label='Lift (Fy)')
ax2.axhline(y=F_lift[-1], color='r', linestyle='--', alpha=0.5, label=f'Steady: {F_lift[-1]:.3f}')
ax2.axvspan(7, 10, alpha=0.1, color='green', label='Quasi-steady region')
ax2.set_xlabel('Time (dimensionless)', fontsize=12)
ax2.set_ylabel('Lift Force (F_y)', fontsize=12)
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.3)
ax2.set_ylim([-0.15, 0.0])

# Title
fig.suptitle('Heaving Ellipsoid Force Convergence (Re=100, 4.2M cells)', fontsize=14, fontweight='bold')

plt.tight_layout()

# Save figure
output_path = 'heaving_ellipsoid_forces.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"Saved: {output_path}")

# Also save as PDF for publication
plt.savefig('heaving_ellipsoid_forces.pdf', bbox_inches='tight')
print("Saved: heaving_ellipsoid_forces.pdf")

plt.close()