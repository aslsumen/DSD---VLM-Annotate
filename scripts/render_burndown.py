r"""Render the Sprint 2 burndown chart as a dependency-free SVG.

Data lives here (single source) and is mirrored in docs/SPRINT_BURNDOWN.md.
Run from the repository root:  .\.venv\Scripts\python.exe scripts\render_burndown.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

TOTAL = 82
START = date(2026, 11, 2)
END = date(2026, 11, 15)

# date -> remaining story points (None = no data / no work assumed)
ACTUAL: dict[date, float | None] = {
    date(2026, 11, 2): 82,
    date(2026, 11, 3): 82,
    date(2026, 11, 4): 82,
    date(2026, 11, 5): 8,
    date(2026, 11, 6): None,
    date(2026, 11, 7): None,
    date(2026, 11, 8): None,
    date(2026, 11, 9): None,
    date(2026, 11, 10): None,
    date(2026, 11, 11): None,
    date(2026, 11, 12): None,
    date(2026, 11, 13): None,
    date(2026, 11, 14): None,
    date(2026, 11, 15): 5,
}

WIDTH, HEIGHT = 960, 560
LEFT, RIGHT, TOP, BOTTOM = 80, 40, 60, 80
PLOT_W = WIDTH - LEFT - RIGHT
PLOT_H = HEIGHT - TOP - BOTTOM


def x_for(day: date) -> float:
    span = (END - START).days
    return LEFT + PLOT_W * ((day - START).days / span)


def y_for(points: float) -> float:
    return TOP + PLOT_H * (1 - points / TOTAL)


def build_svg() -> str:
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Segoe UI, Arial, sans-serif">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
        f'<text x="{LEFT}" y="32" font-size="20" font-weight="700" fill="#111827">'
        "Sprint 2 burndown — VLM Annotate (provisional, 85 SP)</text>",
        f'<text x="{LEFT}" y="50" font-size="12" fill="#6b7280">'
        "2026-11-02 → 2026-11-15 · actual reflects the 2026-11-05 harness session, not team velocity</text>",
    ]

    # grid + y labels
    for step in range(0, TOTAL + 1, 10):
        y = y_for(step)
        parts.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + PLOT_W}" y2="{y:.1f}" '
            'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{LEFT - 10}" y="{y + 4:.1f}" font-size="11" fill="#6b7280" '
            f'text-anchor="end">{step}</text>'
        )
    parts.append(
        f'<text x="24" y="{TOP + PLOT_H / 2}" font-size="12" fill="#374151" '
        f'transform="rotate(-90 24 {TOP + PLOT_H / 2})" text-anchor="middle">'
        "remaining story points</text>"
    )

    # x labels every two days
    day = START
    while day <= END:
        x = x_for(day)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP + PLOT_H}" x2="{x:.1f}" y2="{TOP + PLOT_H + 6}" '
            'stroke="#9ca3af"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{TOP + PLOT_H + 22}" font-size="10" fill="#374151" '
            f'text-anchor="middle">{day.strftime("%d %b")}</text>'
        )
        day += timedelta(days=2)

    # weekend shading
    day = START
    while day <= END:
        if day.weekday() >= 5:
            x0 = x_for(day) - PLOT_W / (END - START).days / 2
            parts.append(
                f'<rect x="{x0:.1f}" y="{TOP}" width="{PLOT_W / (END - START).days:.1f}" '
                f'height="{PLOT_H}" fill="#f3f4f6"/>'
            )
        day += timedelta(days=1)

    # ideal line
    ideal = " ".join(
        f"{x_for(START + timedelta(days=i)):.1f},{y_for(TOTAL * (1 - i / (END - START).days)):.1f}"
        for i in range((END - START).days + 1)
    )
    parts.append(
        f'<polyline points="{ideal}" fill="none" stroke="#9ca3af" stroke-width="2" '
        'stroke-dasharray="6 5"/>'
    )

    # actual line (only defined points)
    actual_points = [
        (day, value) for day, value in sorted(ACTUAL.items()) if value is not None
    ]
    poly = " ".join(f"{x_for(day):.1f},{y_for(value):.1f}" for day, value in actual_points)
    parts.append(f'<polyline points="{poly}" fill="none" stroke="#1d4ed8" stroke-width="3"/>')
    for day, value in actual_points:
        parts.append(
            f'<circle cx="{x_for(day):.1f}" cy="{y_for(value):.1f}" r="5" fill="#1d4ed8"/>'
        )
    last_day, last_value = actual_points[-1]
    parts.append(
        f'<text x="{x_for(last_day) + 10:.1f}" y="{y_for(last_value) + 4:.1f}" '
        f'font-size="12" font-weight="700" fill="#1d4ed8">{last_value:.0f} SP</text>'
    )

    # legend
    legend_y = HEIGHT - 28
    parts.append(
        f'<line x1="{LEFT}" y1="{legend_y}" x2="{LEFT + 28}" y2="{legend_y}" '
        'stroke="#9ca3af" stroke-width="2" stroke-dasharray="6 5"/>'
        f'<text x="{LEFT + 36}" y="{legend_y + 4}" font-size="12" fill="#374151">ideal</text>'
    )
    parts.append(
        f'<line x1="{LEFT + 110}" y1="{legend_y}" x2="{LEFT + 138}" y2="{legend_y}" '
        'stroke="#1d4ed8" stroke-width="3"/>'
        f'<text x="{LEFT + 146}" y="{legend_y + 4}" font-size="12" fill="#374151">actual</text>'
    )
    parts.append(
        f'<rect x="{LEFT + 220}" y="{legend_y - 8}" width="16" height="16" fill="#f3f4f6"/>'
        f'<text x="{LEFT + 244}" y="{legend_y + 4}" font-size="12" fill="#374151">'
        "weekend / no work assumed</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "docs" / "burndown" / "sprint-02.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_svg(), encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
