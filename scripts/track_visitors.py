#!/usr/bin/env python3
"""Record the daily profile-view count and render it as a time series.

No service exposes a history of GitHub profile views, so we build one: read the
cumulative counter once a day, append it to resources/visitors.json, and redraw
the chart from the accumulated series.
"""

import json
import os
import re
import urllib.request
from datetime import date, datetime, timezone

USER = "misterepsilon"
COUNTER_URL = "https://komarev.com/ghpvc/?username=%s&style=flat-square&color=blue" % USER
DATA = "resources/visitors.json"

# dataviz categorical slot 1 (blue), stepped per mode. Both steps validated with
# the skill's validate_palette.js against the GitHub surfaces -- light #ffffff
# and dark #0d1117 -- all checks PASS.
THEMES = {
    "light": {
        "path": "resources/visitors-light.svg",
        "series": "#2a78d6",
        "text_primary": "#1f2328",
        "text_secondary": "#59636e",
        "grid": "#d1d9e0",
        "surface": "#ffffff",
    },
    "dark": {
        "path": "resources/visitors-dark.svg",
        "series": "#3987e5",
        "text_primary": "#f0f6fc",
        "text_secondary": "#9198a1",
        "grid": "#3d444d",
        "surface": "#0d1117",
    },
}

FONT = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"

W, H = 880, 280
PAD_L, PAD_R, PAD_T, PAD_B = 56, 24, 56, 40
PLOT_W = W - PAD_L - PAD_R
PLOT_H = H - PAD_T - PAD_B


def fetch_total():
    """Pull the cumulative view count out of the counter badge's SVG."""
    req = urllib.request.Request(COUNTER_URL, headers={"User-Agent": "profile-visitor-tracker"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        svg = resp.read().decode("utf-8", "replace")

    # The badge renders its label first, then its value; the value is the last <text>.
    values = re.findall(r">\s*([\d.,]+\s*[kKmM]?)\s*</text>", svg)
    if not values:
        raise RuntimeError("could not parse a count out of the counter badge")

    raw = values[-1].strip().replace(",", "")
    mult = 1
    if raw[-1] in "kK":
        mult, raw = 1000, raw[:-1]
    elif raw[-1] in "mM":
        mult, raw = 1000000, raw[:-1]
    return int(round(float(raw) * mult))


def load():
    if not os.path.exists(DATA):
        return {"user": USER, "history": []}
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


def record(store, today, total):
    """One row per day; a same-day rerun keeps the highest reading."""
    for row in store["history"]:
        if row["date"] == today:
            row["total"] = max(row["total"], total)
            break
    else:
        store["history"].append({"date": today, "total": total})
    store["history"].sort(key=lambda r: r["date"])
    store["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return store


def nice_ticks(vmax, count=4):
    """Round tick steps (1/2/5 x 10^n) so the axis reads in human numbers."""
    if vmax <= 0:
        return [0, 1]
    rough = vmax / float(count)
    mag = 1.0
    while rough / mag > 10:
        mag *= 10
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= rough:
            step = m * mag
            break
    step = max(1, int(round(step)))
    top = ((int(vmax) // step) + 1) * step
    return list(range(0, top + step, step))


def fmt_day(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def placeholder(theme, days):
    """Days 0-1 have no interval to plot yet; say so rather than draw a lie."""
    need = 2 - days
    plural = "s" if need != 1 else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d"'
        ' role="img" aria-label="Visitor history is still being collected">\n'
        '  <text x="%d" y="%d" text-anchor="middle" font-family="%s" font-size="15"'
        ' font-weight="600" fill="%s">Collecting visitor history&#8230;</text>\n'
        '  <text x="%d" y="%d" text-anchor="middle" font-family="%s" font-size="12"'
        ' fill="%s">The chart needs %d more daily reading%s before it can plot a trend.</text>\n'
        "</svg>\n"
        % (
            W, H, W, H,
            W // 2, H // 2 - 10, FONT, theme["text_primary"],
            W // 2, H // 2 + 14, FONT, theme["text_secondary"], need, plural,
        )
    )


def render(theme, history):
    if len(history) < 2:
        return placeholder(theme, len(history))

    # The counter is cumulative, so the series worth plotting is its
    # day-over-day difference. The first reading has no prior day to diff.
    points = []
    for prev, cur in zip(history, history[1:]):
        delta = max(0, cur["total"] - prev["total"])
        points.append((datetime.strptime(cur["date"], "%Y-%m-%d").date(), delta))

    total = history[-1]["total"]
    vmax = max(v for _, v in points)
    ticks = nice_ticks(vmax)
    top = ticks[-1]

    def px(i):
        if len(points) == 1:
            return PAD_L + PLOT_W / 2.0
        return PAD_L + PLOT_W * i / float(len(points) - 1)

    def py(v):
        return PAD_T + PLOT_H - (PLOT_H * v / float(top))

    out = []
    out.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d"'
        ' role="img" aria-label="Daily new profile visitors from %s to %s. Peak %d in a day,'
        ' %d views in total.">'
        % (W, H, W, H, history[1]["date"], history[-1]["date"], vmax, total)
    )
    out.append(
        "<title>Daily new profile visitors &#8212; peak %d/day, %d total</title>" % (vmax, total)
    )
    out.append(
        '<defs><linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="%s" stop-opacity="0.22"/>'
        '<stop offset="100%%" stop-color="%s" stop-opacity="0"/>'
        "</linearGradient></defs>" % (theme["series"], theme["series"])
    )
    # One series, so the title names it and no legend box is needed.
    out.append(
        '<text x="%d" y="26" font-family="%s" font-size="15" font-weight="600" fill="%s">'
        "New visitors per day</text>" % (PAD_L, FONT, theme["text_primary"])
    )
    out.append(
        '<text x="%d" y="45" font-family="%s" font-size="12" fill="%s">'
        "%d profile views in total &#183; since %s</text>"
        % (PAD_L, FONT, theme["text_secondary"], total, history[0]["date"])
    )

    # Recessive horizontal grid, with the y labels in muted ink.
    for t in ticks:
        y = py(t)
        out.append(
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"'
            ' stroke-opacity="0.55"/>' % (PAD_L, y, PAD_L + PLOT_W, y, theme["grid"])
        )
        out.append(
            '<text x="%d" y="%.1f" text-anchor="end" font-family="%s" font-size="11"'
            ' fill="%s">%d</text>' % (PAD_L - 10, y + 4, FONT, theme["text_secondary"], t)
        )

    coords = [(px(i), py(v)) for i, (_, v) in enumerate(points)]
    baseline = PAD_T + PLOT_H

    area = "M %.1f %d " % (coords[0][0], baseline)
    area += " ".join("L %.1f %.1f" % (x, y) for x, y in coords)
    area += " L %.1f %d Z" % (coords[-1][0], baseline)
    out.append('<path d="%s" fill="url(#fade)"/>' % area)

    line = "M " + " L ".join("%.1f %.1f" % (x, y) for x, y in coords)
    out.append(
        '<path d="%s" fill="none" stroke="%s" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"/>' % (line, theme["series"])
    )

    # Markers only while they stay legible: 8px across, ringed in the surface
    # colour so touching points stay separable.
    if len(coords) <= 24:
        for x, y in coords[:-1]:
            out.append(
                '<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="%s" stroke-width="2"/>'
                % (x, y, theme["series"], theme["surface"])
            )

    # Selective direct label: the latest point only, never a number on every point.
    lx, ly = coords[-1]
    out.append(
        '<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="%s" stroke-width="2"/>'
        % (lx, ly, theme["series"], theme["surface"])
    )
    out.append(
        '<text x="%.1f" y="%.1f" text-anchor="end" font-family="%s" font-size="12"'
        ' font-weight="600" fill="%s">%d</text>'
        % (lx, ly - 12, FONT, theme["text_primary"], points[-1][1])
    )

    out.append(
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1"/>'
        % (PAD_L, baseline, PAD_L + PLOT_W, baseline, theme["grid"])
    )

    # Roughly six evenly spaced date labels, ends anchored inward. The last day
    # is always labelled, so drop any strided label that would collide with it.
    last = len(points) - 1
    step = max(1, int(round(len(points) / 6.0)))
    marked = [i for i in range(0, last, step) if px(last) - px(i) >= 60] + [last]
    for i in marked:
        anchor = "start" if i == 0 else ("end" if i == last else "middle")
        out.append(
            '<text x="%.1f" y="%d" text-anchor="%s" font-family="%s" font-size="11"'
            ' fill="%s">%s</text>'
            % (px(i), H - PAD_B + 22, anchor, FONT, theme["text_secondary"], fmt_day(points[i][0]))
        )

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    total = fetch_total()
    today = date.today().isoformat()

    store = record(load(), today, total)
    os.makedirs("resources", exist_ok=True)
    with open(DATA, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(store, fh, indent=2)
        fh.write("\n")

    for theme in THEMES.values():
        with open(theme["path"], "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render(theme, store["history"]))

    print("%s: total=%d, days=%d" % (today, total, len(store["history"])))


if __name__ == "__main__":
    main()
