"""Small dependency-free SVG KPI sparklines drawn from observed historical data.

A sparkline is descriptive, *not* a forecast, and its colour is deliberately
neutral so rising RWA or income isn't mistaken for a risk judgement.
"""
import html
import math


def sparkline_html(values, *, label="", period="quarters"):
    """Return a compact accessible SVG from genuine ordered observations.

    Values must already be in chronological order. Non-finite observations are
    dropped, not interpolated. A one-point history has no drawable trend.
    """
    if values is None:
        return ""
    observed = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            observed.append(number)
    if len(observed) < 2:
        return ""
    observed = observed[-12:]  # all reported quarters so far (max 12 points)
    width, height = 104.0, 33.0
    left, right, top, bottom = 4.0, 100.0, 5.0, 28.0
    lo, hi = min(observed), max(observed)
    span = hi - lo

    points = []
    for i, val in enumerate(observed):
        x = left + (right - left) * i / (len(observed) - 1)
        y = (top + bottom) / 2 if span == 0 else bottom - (val - lo) / span * (bottom - top)
        points.append((x, y))
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    last_x, last_y = points[-1]
    accessible_label = html.escape(
        f"{label}: {len(observed)} reported {period}; "
        f"earliest {observed[0]:,.2f}, latest {observed[-1]:,.2f}.",
        quote=True,
    )
    return (
        '<span class="kpi-sparkline" title="' + accessible_label + '">'
        '<svg viewBox="0 0 104 33" width="104" height="33" '
        'role="img" aria-label="' + accessible_label + '">'
        '<line x1="4" y1="28" x2="100" y2="28" stroke="#345340" '
        'stroke-width="0.8" stroke-dasharray="2 4"/>'
        '<polyline points="' + coords + '" fill="none" stroke="#7DCB9B" '
        'stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.9" '
        'fill="#C9F2D5" stroke="#30563D" stroke-width="1"/>'
        '</svg>'
        f'<span class="kpi-sparkline-period">{len(observed)}Q TREND</span>'
        '</span>'
    )
