"""Compact quarterly bar + trend charts using HTML/CSS only.

The command-centre shell renders via Streamlit st.html(), which may strip
inline SVG under DOMPurify. Using ordinary spans, HTML attributes and CSS
avoids SVG, external plotting dependencies and Javascript. The tiny plot is descriptive only. Its y-axis includes zero so small
percentage-point changes are not visually overstated.
"""

import html
import math


SPARKLINE_CSS = """
<style>
/* Real Data only. The legacy Synthetic KPI markup remains unchanged.
   Allow four KPI cards to grow, avoiding clipping when the header is tall. */
.home-stage {
    height: auto !important;
    min-height: max(740px, calc(100vh - 14rem));
}
.home-left {
    grid-template-rows: repeat(4, minmax(168px, 1fr)) !important;
}
.home-left .kpi-card {
    min-height: 168px;
    box-sizing: border-box;
    padding: 0.82rem 0.88rem 0.76rem;
    justify-content: center;
}
.home-left .executive-context {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}
@media (max-width: 1100px) {
    .home-stage { min-height: 0; }
}

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
    flex: 0 0 116px;
    width: 116px;
    min-width: 0;
    gap: 2px;
    vertical-align: middle;
    position: relative;
}
.home-left .kpi-mini-plot {
    display: block;
    position: relative;
    width: 116px;
    height: 42px;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(27,64,40,0.02), rgba(27,64,40,0.045));
    border-bottom: 1px solid rgba(87,136,99,0.19);
}
.home-left .kpi-mini-bar {
    position: absolute;
    display: block;
    box-sizing: border-box;
    background: linear-gradient(180deg, rgba(93,183,119,0.27), rgba(37,108,66,0.095));
    border: 1px solid rgba(82,166,104,0.15);
    border-bottom: 0;
    border-radius: 2px 2px 0 0;
    z-index: 1;
}
.home-left .kpi-mini-bar.is-latest {
    background: linear-gradient(180deg, rgba(91,216,132,0.46), rgba(37,126,76,0.16));
    border-color: rgba(125,236,165,0.36);
}
.home-left .kpi-mini-segment {
    position: absolute;
    display: block;
    height: 2px;
    background: rgba(188,243,204,0.75);
    border-radius: 2px;
    box-shadow: 0 0 2px rgba(134,240,168,0.25);
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
    background: rgba(188,243,204,0.75);
    border-radius: 50%;
    z-index: 3;
}
.home-left .kpi-mini-dot.is-latest {
    width: 6px;
    height: 6px;
    background: #C3F2D1;
    border-color: #45BF73;
}
.home-left .kpi-sparkline-period {
    font-family: "Cascadia Mono", Consolas, monospace;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.15rem;
    font-size: 0.50rem;
    color: #7DA78B;
    font-weight: 600;
    letter-spacing: 0;
    white-space: nowrap;
}
@media (max-width: 1350px) {
    .home-left .kpi-sparkline {
        flex-basis: 100px;
        width: 100px;
    }
    .home-left .kpi-mini-plot {
        /* Shrink the complete plotted geometry without clipping it. */
        transform: scale(0.86);
        transform-origin: center center;
        margin: -2px -8px;
    }
    .home-left .kpi-reading-row > .kpi-value {
        font-size: clamp(1.03rem, 1.55vw, 1.63rem);
    }
}
@media (max-width: 1100px) {
    .home-left .kpi-sparkline { flex-basis: 116px; width: 116px; }
    .home-left .kpi-mini-plot { transform: none; margin: 0; }
}
</style>
"""


def sparkline_html(values, *, label="", period="quarters", dates=None):
    """Draw reported quarterly bars and a line using a shared zero-based axis.

    Unlike a min–max zoom, a 0.3pp CET1 movement does not fill the plot.
    The first and last reported quarters appear beneath the plot.
    """
    if values is None:
        return ""

    values = list(values)
    if dates is not None:
        dates = list(dates)
        if len(dates) != len(values):
            raise ValueError("A chart date is required for each quarterly value.")
    else:
        dates = [""] * len(values)

    observations = []
    for date, value in zip(dates, values):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            observations.append((str(date), number))

    observations = observations[-12:]
    if len(observations) < 2:
        return ""

    width = 116.0
    left, right = 7.0, width - 7.0
    values_only = [v for _, v in observations]
    lower = min(0.0, min(values_only))
    upper = max(0.0, max(values_only))
    extra = (upper - lower) * 0.07
    if extra <= 0:
        extra = 1.0
    if upper > 0:
        upper += extra
    if lower < 0:
        lower -= extra
    span = upper - lower

    def position(value):
        # CSS bottom position in px; 32px usable height.
        return 4.0 + (value - lower) / span * 32.0

    zero_pos = position(0.0)
    n = len(observations)
    bar_width = 5.0 if n >= 10 else 7.0
    plotted, bars, lines, dots = [], [], [], []

    for i, (date, value) in enumerate(observations):
        x = left + (right - left) * i / (n - 1)
        y = position(value)
        plotted.append((x, y))
        bar_bottom = min(y, zero_pos)
        bar_height = abs(y - zero_pos)
        latest_class = " is-latest" if i == n - 1 else ""
        bar_title = html.escape(
            f"{date or ('Observation ' + str(i + 1))}: {value:,.5f}", quote=True
        )
        bars.append(
            f'<span class="kpi-mini-bar{latest_class}" title="{bar_title}" '
            f'style="left:{x - bar_width / 2:.2f}px;bottom:{bar_bottom:.2f}px;'
            f'width:{bar_width:.2f}px;height:{max(0.8,bar_height):.2f}px"></span>'
        )
        dot_size = 6.0 if i == n - 1 else 5.0
        dots.append(
            f'<span class="kpi-mini-dot{latest_class}" '
            f'style="left:{x - dot_size/2:.2f}px;'
            f'bottom:{y-dot_size/2:.2f}px"></span>'
        )

    for (x1, y1), (x2, y2) in zip(plotted, plotted[1:]):
        dx, dy = x2 - x1, y2 - y1
        distance = math.hypot(dx, dy)
        angle = -math.degrees(math.atan2(dy, dx))
        lines.append(
            '<span class="kpi-mini-segment" '
            f'style="left:{x1:.2f}px;bottom:{y1 + 1:.2f}px;'
            f'width:{distance:.2f}px;transform:rotate({angle:.3f}deg)"></span>'
        )

    first_date = html.escape(observations[0][0] or "First")
    last_date = html.escape(observations[-1][0] or "Latest")
    whole_range = html.escape(
        f"{label}: {n} reported {period}; {observations[0][0]} to {observations[-1][0]}. "
        f"Latest {values_only[-1]:,.5f}; zero-based vertical axis. "
        "The plot is descriptive, not a risk/return assessment.",
        quote=True,
    )
    return (
        f'<span class="kpi-sparkline" role="img" aria-label="{whole_range}" '
        f'title="{whole_range}">'
        '<span class="kpi-mini-plot" aria-hidden="true">'
        + "".join(bars)
        + "".join(lines)
        + "".join(dots)
        + '</span>'
        + f'<span class="kpi-sparkline-period"><span>{first_date}</span><span>{last_date}</span></span>'
        + '</span>'
    )
