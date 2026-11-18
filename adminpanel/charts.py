def line_points(values, width=640, height=120, pad=8):
    """SVG polyline points for a small line chart (no JavaScript, no chart library)."""
    if not values:
        return ""
    top = max(values) or 1
    step = (width - 2 * pad) / max(len(values) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{height - pad - (v / top) * (height - 2 * pad):.1f}" for i, v in enumerate(values))
