"""Plotting configuration for flapping wing visualization.

Provides colorblind-safe colors and consistent styling for publication figures.
Uses IBM colorblind-safe palette.
"""

import matplotlib.pyplot as plt
import matplotlib as mpl

# IBM colorblind-safe palette
# https://www.ibm.com/design/language/color#colorblind-accessibility
IBM_COLORS = {
    "blue": "#648FFF",
    "purple": "#785EF0",
    "magenta": "#DC267F",
    "orange": "#FE6100",
    "yellow": "#FFB000",
    "gray": "#7F7F7F",
    "black": "#000000",
}

# Semantic color mapping for wing aerodynamics
COLORS = {
    "stroke": IBM_COLORS["blue"],       # Stroke angle phi
    "pitch": IBM_COLORS["magenta"],     # Pitch angle alpha
    "deviation": IBM_COLORS["purple"],  # Deviation angle theta
    "lift": IBM_COLORS["orange"],       # Lift force
    "drag": IBM_COLORS["blue"],         # Drag force
    "thrust": IBM_COLORS["yellow"],     # Thrust (negative drag)
    "power": IBM_COLORS["magenta"],     # Power
    "vortex_pos": IBM_COLORS["orange"], # Positive vorticity (CCW)
    "vortex_neg": IBM_COLORS["blue"],   # Negative vorticity (CW)
}

# Line styles for different data series
LINESTYLES = {
    "simulation": "-",      # Solid for simulation data
    "experiment": "--",     # Dashed for experimental data
    "theory": ":",          # Dotted for analytical/theory
    "reference": "-.",      # Dash-dot for reference data
}

# Marker styles
MARKERS = {
    "simulation": "o",
    "experiment": "s",
    "theory": None,
    "reference": "^",
}


def setup_publication_style():
    """Configure matplotlib for publication-quality figures."""
    plt.style.use('seaborn-v0_8-whitegrid')

    mpl.rcParams.update({
        # Font sizes
        'font.size': 10,
        'axes.titlesize': 11,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,

        # Font family
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],

        # Line widths
        'lines.linewidth': 1.5,
        'axes.linewidth': 0.8,
        'grid.linewidth': 0.5,

        # Figure size (single column width for journal)
        'figure.figsize': (3.5, 2.8),
        'figure.dpi': 150,

        # Save settings
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,

        # Grid
        'grid.alpha': 0.3,
        'axes.grid': True,

        # Legend
        'legend.framealpha': 0.9,
        'legend.edgecolor': 'gray',

        # Markers
        'lines.markersize': 4,
    })


def get_cycle_colors(n: int = 6) -> list[str]:
    """Get n colors from the IBM palette for cycling."""
    palette = [
        IBM_COLORS["blue"],
        IBM_COLORS["orange"],
        IBM_COLORS["magenta"],
        IBM_COLORS["purple"],
        IBM_COLORS["yellow"],
        IBM_COLORS["gray"],
    ]
    return palette[:n]


def velocity_colormap():
    """Colormap for velocity fields (diverging, centered at 0)."""
    return 'RdBu_r'


def vorticity_colormap():
    """Colormap for vorticity fields (diverging, centered at 0)."""
    return 'RdBu_r'


def pressure_colormap():
    """Colormap for pressure fields."""
    return 'viridis'


# Apply publication style on import
setup_publication_style()
