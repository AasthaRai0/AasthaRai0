#!/usr/bin/env python3
"""Generate a GitHub-style contribution calendar SVG from a public GitHub profile.

No paid API or third-party chart service is used. The workflow fetches the public
profile HTML and extracts the calendar's date + contribution-level attributes.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "AasthaRai0")
OUTPUT = Path(os.environ.get("OUTPUT_FILE", "assets/contribution-heatmap.svg"))
PROFILE_URL = f"https://github.com/{USERNAME}"
NAVY = "#0B1020"
PANEL = "#0D1117"
TEXT = "#D7D9E8"
MUTED = "#858BA3"
GRID = ["#171D32", "#29204B", "#49317A", "#7650B5", "#B69AF5"]
ACCENT = "#C084FC"
FONT = "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"


def fetch_profile() -> str:
    request = urllib.request.Request(
        PROFILE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ContributionHeatmap/1.0)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_cells(source: str) -> dict[dt.date, int]:
    """Read date and level from GitHub's contribution calendar markup."""
    cells: dict[dt.date, int] = {}

    # GitHub has used both <td data-date=...> and <rect data-date=...> over time.
    patterns = [
        r'<(?:rect|td)\b[^>]*\bdata-date="(\d{4}-\d{2}-\d{2})"[^>]*\bdata-level="([0-4])"',
        r'<(?:rect|td)\b[^>]*\bdata-level="([0-4])"[^>]*\bdata-date="(\d{4}-\d{2}-\d{2})"',
    ]
    for idx, pattern in enumerate(patterns):
        for match in re.finditer(pattern, source, flags=re.I):
            if idx == 0:
                date_text, level_text = match.group(1), match.group(2)
            else:
                level_text, date_text = match.group(1), match.group(2)
            try:
                cells[dt.date.fromisoformat(date_text)] = int(level_text)
            except ValueError:
                continue

    # Fallback for calendar cells whose attributes are separated by other markup.
    if not cells:
        tag_pattern = r'<(?:rect|td)\b[^>]*>'
        for tag in re.findall(tag_pattern, source, flags=re.I):
            date_match = re.search(r'\bdata-date="(\d{4}-\d{2}-\d{2})"', tag)
            level_match = re.search(r'\bdata-level="([0-4])"', tag)
            if date_match and level_match:
                try:
                    cells[dt.date.fromisoformat(date_match.group(1))] = int(level_match.group(1))
                except ValueError:
                    pass

    if len(cells) < 300:
        raise RuntimeError(
            f"Could not read enough contribution cells from {PROFILE_URL} "
            f"(found {len(cells)}). GitHub may have changed its HTML or blocked the request."
        )
    return cells


def month_label_positions(weeks: list[list[tuple[dt.date, int] | None]], cell: int, gap: int):
    positions = []
    last_month = None
    for wi, week in enumerate(weeks):
        first = next((entry[0] for entry in week if entry is not None), None)
        if first and first.month != last_month:
            positions.append((wi * (cell + gap), first.strftime("%b")))
            last_month = first.month
    return positions


def build_svg(cells: dict[dt.date, int]) -> str:
    today = max(cells)
    start = today - dt.timedelta(days=364)
    # Align the first column to Sunday, as in GitHub's contribution calendar.
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)
    end = today
    dates = []
    day = start
    while day <= end:
        dates.append(day)
        day += dt.timedelta(days=1)

    cell_size, gap = 11, 4
    step = cell_size + gap
    weeks_count = (len(dates) + 6) // 7
    weeks: list[list[tuple[dt.date, int] | None]] = []
    for wi in range(weeks_count):
        week = []
        for dow in range(7):
            index = wi * 7 + dow
            if index < len(dates):
                date = dates[index]
                week.append((date, cells.get(date, 0)))
            else:
                week.append(None)
        weeks.append(week)

    left, right, top, bottom = 48, 18, 62, 38
    grid_width = weeks_count * step - gap
    grid_height = 7 * step - gap
    width = left + grid_width + right
    height = top + grid_height + bottom

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub contribution calendar for ' + html.escape(USERNAME) + '</title>',
        '<desc id="desc">A purple-blue contribution heatmap for the last 365 days, with month and weekday labels.</desc>',
        f'<rect width="{width}" height="{height}" rx="16" fill="{NAVY}"/>',
        f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="15" fill="none" stroke="#25213D"/>',
        f'<text x="20" y="28" fill="{TEXT}" font-family="{FONT}" font-size="15" font-weight="700">Contribution activity</text>',
        f'<text x="20" y="46" fill="{MUTED}" font-family="{FONT}" font-size="10">{html.escape(USERNAME)} · last 365 days</text>',
    ]

    # Month labels
    for x, label in month_label_positions(weeks, cell_size, gap):
        out.append(
            f'<text x="{left+x}" y="59" fill="{MUTED}" font-family="{FONT}" font-size="10">{label}</text>'
        )

    # Weekday labels, with GitHub-like selective labels.
    for dow, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = top + dow * step + cell_size - 1
        out.append(
            f'<text x="12" y="{y}" fill="{MUTED}" font-family="{FONT}" font-size="9">{label}</text>'
        )

    for wi, week in enumerate(weeks):
        for dow, entry in enumerate(week):
            if entry is None:
                continue
            date, level = entry
            x = left + wi * step
            y = top + dow * step
            fill = GRID[max(0, min(4, level))]
            label = date.strftime("%b %-d, %Y") if os.name != "nt" else date.strftime("%b %#d, %Y")
            # Tooltip support in browsers; alt text remains useful in SVG-capable readers.
            out.append(
                f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" rx="3" '
                f'fill="{fill}" stroke="#FFFFFF" stroke-opacity="0.04">'
                f'<title>{html.escape(label)}: contribution level {level}</title></rect>'
            )

    # Legend
    legend_y = height - 19
    out.append(f'<text x="{left}" y="{legend_y}" fill="{MUTED}" font-family="{FONT}" font-size="9">Less</text>')
    legend_x = left + 28
    for i, color in enumerate(GRID):
        out.append(
            f'<rect x="{legend_x + i*15}" y="{legend_y-9}" width="10" height="10" rx="3" fill="{color}"/>'
        )
    out.append(f'<text x="{legend_x + 5*15 + 2}" y="{legend_y}" fill="{MUTED}" font-family="{FONT}" font-size="9">More</text>')
    out.append(f'<text x="{width-18}" y="{legend_y}" text-anchor="end" fill="{ACCENT}" font-family="{FONT}" font-size="9">Midnight Purple</text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    try:
        cells = extract_cells(fetch_profile())
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(build_svg(cells), encoding="utf-8")
        print(f"Wrote {OUTPUT} using {len(cells)} contribution dates.")
    except Exception as exc:
        print(f"Contribution graph generation failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
