"""Built-in strand presets.

A strand preset only describes *shape* (profile, taper, twist). Absolute width
and detail settings stay on the region so the same preset works at any scale.
Preset index 0 is reserved for "use the region settings"; built-ins are 1..N
and are baked into the node tree through Index Switch nodes.
"""

# Region inputs that a per-strand preset can override (order matters for the tree).
SHAPE_PARAMS = (
    "Thickness Ratio",
    "Root Width",
    "Peak Position",
    "Tip Width",
    "Taper Power",
    "Root Sharpness",
    "Root Teardrop",
    "Root Asymmetry",
    "Root Flatten",
    "Tip Sharpness",
    "Tip Teardrop",
    "Tip Asymmetry",
    "Tip Flatten",
    "Twist",
)


def _shape(thick, root_w, peak, tip_w, taper, root, tip, twist=0.0):
    return dict(zip(SHAPE_PARAMS, (thick, root_w, peak, tip_w, taper, *root, *tip, twist)))


# profile tuples: (sharpness, teardrop, asymmetry, flatten)
STRAND_PRESETS = {
    "SOFT_CLUMP": ("Soft Clump", "Rounded, soft lock",
                   _shape(0.55, 0.60, 0.35, 0.00, 1.4, (2.0, 0.10, 0.00, 0.30), (2.0, 0.20, 0.00, 0.20))),
    "SHARP_ANIME": ("Sharp Anime", "Pointed, clearly stylized",
                    _shape(0.35, 0.70, 0.20, 0.00, 0.8, (2.2, 0.30, 0.00, 0.50), (1.2, 0.50, 0.00, 0.60))),
    "FLAT_RIBBON": ("Flat Ribbon", "Wide and flattened",
                    _shape(0.18, 0.80, 0.40, 0.05, 2.0, (3.0, 0.00, 0.00, 0.60), (2.5, 0.00, 0.00, 0.60))),
    "NATURAL_LOCK": ("Natural Lock", "Asymmetric, more natural",
                     _shape(0.50, 0.50, 0.30, 0.00, 1.2, (2.0, 0.20, 0.25, 0.30), (1.8, 0.30, 0.35, 0.30), 0.10)),
    "TWISTED": ("Twisted Ribbon", "Ribbon that twists along its length",
                _shape(0.30, 0.70, 0.35, 0.00, 1.6, (2.5, 0.10, 0.00, 0.40), (2.0, 0.20, 0.00, 0.40), 1.0)),
    "FLYAWAY": ("Flyaway", "Very thin, irregular strand",
                _shape(0.80, 0.30, 0.10, 0.00, 1.0, (2.0, 0.00, 0.00, 0.00), (2.0, 0.00, 0.00, 0.00))),
}

# Index used in the per-curve `sf_preset` attribute (0 = region settings).
PRESET_ORDER = tuple(STRAND_PRESETS.keys())


def preset_index(key):
    return PRESET_ORDER.index(key) + 1


# Width-along-length shortcuts (spec 5.2): Root Width, Peak Position, Tip Width, Taper Power
WIDTH_PROFILES = {
    "NATURAL": ("Natural", (0.60, 0.30, 0.00, 1.4)),
    "FULL": ("Full", (0.85, 0.50, 0.10, 2.5)),
    "SHARP": ("Sharp", (0.70, 0.15, 0.00, 0.7)),
}

# Secondary distribution modes (spec 6.1): Flow Variation, Width Min, Width Max, Length Min
DISTRIBUTION_MODES = {
    "PARALLEL": ("Parallel", "Follow the main strand almost perfectly", (0.05, 0.20, 0.30, 0.60)),
    "FLOW": ("Flow", "Follow the strand with slight deviation", (0.35, 0.15, 0.35, 0.40)),
    "ORGANIC": ("Organic", "Stronger variation in direction and grouping", (0.90, 0.10, 0.45, 0.25)),
}
