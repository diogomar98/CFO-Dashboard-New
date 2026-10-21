"""Compact quarterly bar + trend charts using HTML/CSS only.

The command-centre shell renders via Streamlit st.html(), which may strip
inline SVG under DOMPurify. Using ordinary spans, HTML attributes and CSS
avoids SVG, external plotting dependencies and Javascript. The tiny plot is
descriptive only: the visual range is zoomed to actual observed values, never
a regulatory threshold or a forecast.
"""

import html
import math


SPARKLINE_CSS = """
<style>
/* Real Data only. The legacy Synthetic KPI markup remains unchanged. */
.home-left .kpi-reading-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
    min-width: 0;
}
.home-left .kpi-reading-row > .kpi-value {
    flex: 1 1 auto;
    min-width: 0;
    font-size: clamp(1.12rem, 1.65vw, 1.83rem);
    white-space: nowrap;
    letter-spacing: -0.06em;
}
.home-left .kpi-sparkline {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 0 0 110px;
    width: 110px;
    min-width: 0;
    gap: 2px;
    vertical-align: middle;
    position: relative;
}
.home-left .kpi-mini-plot {
    display: block;
    position: relative;
    width: 110px;
    height: 42px;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(27,64,40,0.05), rgba(27,64,40,0.14));
    border-bottom: 1px solid rgba(87,136,99,0.32);
}
.home-left .kpi-mini-bar {
    position: absolute;
    display: block;
    box-sizing: border-box;
    background: linear-gradient(180deg, rgba(93,183,119,0.55), rgba(37,108,66,0.22));
    border: 1px solid rgba(82,166,104,0.36);
    border-bottom: 0;
    border-radius: 2px 2px 0 0;
    z-index: 1;
}
.home-left .kpi-mini-bar.is-latest {
    background: linear-gradient(180deg, rgba(91,216,132,0.80), rgba(37,126,76,0.36));
    border-color: rgba(125,236,165,0.63);
}
.home-left .kpi-mini-segment {
    position: absolute;
    display: block;
    height: 2px;
    background: #C2F5D3;
    border-radius: 2px;
    box-shadow: 0 0 3px rgba(134,240,168,0.72);
    transform-origin: left center;
    z-index: 2;
}
.home-left .kpi-mini-dot {
    position: absolute;
    display: block;
    box-sizing: border-box;
    width: 5px;
    height: 5px;
    border: 1px solid #32744A;
    background: #C2F5D3;
    border-radius: 50%;
    z-index: 3;
}
.home-left .kpi-mini-dot.is-latest {
    width: 6px;
    height: 6px;
    background: #F2FFF6;
    border-color: #45BF73;
}
.home-left .kpi-sparkline-period {
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 0.50rem;
    color: #8ABA98;
    font-weight: 700;
    letter-spacing: 0.045em;
    white-space: nowrap;
}
@media (max-width: 1350px) {
    .home-left .kpi-sparkline {
        flex-basis: 96px;
        width: 96px;
    }
    .home-left .kpi-mini-plot {
        /* Shrink the complete plotted geometry without clipping it. */
        transform: scale(0.87);
        transform-origin: center center;
        margin: -2px -8px;
    }
    .home-left .kpi-reading-row > .kpi-value {
        font-size: clamp(1.03rem, 1.55vw, 1.63rem);
    }
}
@media (max-width: 1100px) {
    .home-left .kpi-sparkline { flex-basis: 110px; width: 110px; }
    .home-left .kpi-mini-plot { transform: none; margin: 0; }
}
</style>
"""


def sparkline_html(values, *, label="", period="quarters"):
    """Create historical bars and a line overlay without SVG, canvas or JS.

    Plots only non-null actuals supplied by the caller in chronological order.
    The same zoomed observed min–max scale drives both bars and line. As is
    conventional for a microtrend, heights are relative, *not* zero-based;
    accessible text and tooltip make the visual scaling explicit.
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
    observed = observed[-12:]
    if len(observed) < 2:
        return ""

    width, height = 110.0, 42.0
    left, right = 6.0, width - 6.0
    lo, hi = min(observed), max(observed)
    spread = hi - lo

    # Zoom is intentional and identical for both layers. It keeps close
    # regulatory ratios (e.g. 15.54 to 15.86%) visually legible.
    def normalized(value):
        return 0.55 if spread == 0 else (value - lo) / spread

    n = len(observed)
    bar_width = 5.4 if n >= 10 else 7.0
    plotted = []
    bars, lines, dots = [], [], []
    for i, value in enumerate(observed):
        x = left + (right - left) * i / (n - 1)
        y = 7.0 + normalized(value) * 28.0
        plotted.append((x, y))
        latest_class = " is-latest" if i == n - 1 else ""
        bars.append(
            f'<span class="kpi-mini-bar{latest_class}" '
            f'style="left:{x - bar_width / 2:.2f}px;bottom:2px;'
            f'width:{bar_width:.2f}px;height:{y:.2f}px"></span>'
        )
        dots.append(
            f'<span class="kpi-mini-dot{latest_class}" '
            f'style="left:{x - (3 if i == n - 1 else 2.5):.2f}px;'
            f'bottom:{y + 2 - (3 if i == n - 1 else 2.5):.2f}px"></span>'
        )

    # CSS line segments are positioned along the same y-axis as the bars:
    # rotation angle is negative when the value rises to the right.
    for (x1, y1), (x2, y2) in zip(plotted, plotted[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        angle = -math.degrees(math.atan2(dy, dx))
        lines.append(
            '<span class="kpi-mini-segment" '
            f'style="left:{x1:.2f}px;bottom:{y1 + 1:.2f}px;'
            f'width:{length:.2f}px;transform:rotate({angle:.3f}deg)"></span>'
        )

    title = html.escape(
        f"{label}: {n} reported {period}. "
        f"Range {lo:,.2f} to {hi:,.2f}; latest {observed[-1]:,.2f}. "
        "Visual scale zoomed to the observed range (not a zero baseline).",
        quote=True,
    )
    return (
        f'<span class="kpi-sparkline" role="img" aria-label="{title}" title="{title}">'
        '<span class="kpi-mini-plot" aria-hidden="true">'
        + "".join(bars)
        + "".join(lines)
        + "".join(dots)
        + '</span>'
        + f'<span class="kpi-sparkline-period">{n}Q TREND</span>'
        + '</span>'
    )
