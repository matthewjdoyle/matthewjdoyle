#!/usr/bin/env python3
"""Fetch GitHub profile view counts and render a historical chart."""

from __future__ import annotations

import json
import logging
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import requests
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "store" / "profile-views.json"
CHART_PATH = ROOT / "assets" / "profile-views-chart.png"
FONT_PATH = ROOT / "assets" / "fonts" / "ComicNeue-Regular.ttf"
FONT_URL = (
    "https://raw.githubusercontent.com/crozynski/comicneue/master"
    "/Fonts/TTF/ComicNeue/ComicNeue-Regular.ttf"
)
KOMACCV_URL = "https://komarev.com/ghpvc/?username={username}"
INK = "#1a1a1a"
PAPER = "#fefefe"
MUTED = "#555555"
LINE = "#0066cc"

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


def ensure_comic_font() -> None:
    FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not FONT_PATH.exists():
        try:
            urllib.request.urlretrieve(FONT_URL, FONT_PATH)
        except OSError as exc:
            print(f"Warning: could not download comic font: {exc}", file=sys.stderr)
            return
    font_manager.fontManager.addfont(str(FONT_PATH))


def fetch_total_views(username: str) -> int:
    response = requests.get(KOMACCV_URL.format(username=username), timeout=30)
    response.raise_for_status()
    matches = re.findall(r'<text[^>]*y="14"[^>]*>(\d+)</text>', response.text)
    if not matches:
        raise RuntimeError("Could not parse profile view count from komarev response")
    return int(matches[-1])


def load_history() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {"username": "matthewjdoyle", "history": []}


def save_history(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def append_reading(data: dict, total: int, today: date) -> None:
    history = data.setdefault("history", [])
    today_str = today.isoformat()

    if history and history[-1]["date"] == today_str:
        history[-1]["total"] = total
        return

    history.append({"date": today_str, "total": total})


def _configure_date_axis(ax: plt.Axes, dates: list[date]) -> None:
    span_days = max((dates[-1] - dates[0]).days, 1)

    if len(dates) == 1:
        pad = timedelta(days=4)
        ax.set_xlim(dates[0] - pad, dates[0] + pad)
        locator = mdates.DayLocator(interval=1)
        formatter = mdates.DateFormatter("%d %b %Y")
    elif span_days <= 21:
        locator = mdates.DayLocator(interval=max(1, span_days // 5))
        formatter = mdates.DateFormatter("%d %b")
    elif span_days <= 120:
        locator = mdates.WeekdayLocator(byweekday=mdates.MO, interval=max(1, span_days // 28))
        formatter = mdates.DateFormatter("%d %b")
    elif span_days <= 730:
        locator = mdates.MonthLocator(interval=max(1, span_days // 180))
        formatter = mdates.DateFormatter("%b %Y")
    else:
        locator = mdates.YearLocator(base=max(1, span_days // 730))
        formatter = mdates.DateFormatter("%Y")

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")


def _configure_value_axis(ax: plt.Axes, totals: list[int]) -> None:
    minimum = min(totals)
    maximum = max(totals)
    spread = maximum - minimum

    if spread == 0:
        padding = max(maximum * 0.12, 25)
        lower = max(0, minimum - padding)
        upper = maximum + padding
    else:
        lower = max(0, minimum - spread * 0.08)
        upper = maximum + spread * 0.12

    ax.set_ylim(lower, upper)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5, min_n_ticks=4, integer=True))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: f"{int(value):,}"))


def render_chart(data: dict) -> None:
    history = data["history"]
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    ensure_comic_font()

    dates = [datetime.fromisoformat(entry["date"]).date() for entry in history]
    totals = [entry["total"] for entry in history]
    latest_total = totals[-1]
    date_nums = mdates.date2num(dates)

    with plt.xkcd(scale=1.05, length=80, randomness=2):
        fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=170, facecolor=PAPER)
        fig.subplots_adjust(left=0.11, right=0.94, top=0.78, bottom=0.18)

        ax.set_facecolor(PAPER)
        ax.plot(
            date_nums,
            totals,
            color=LINE,
            linewidth=2.4,
            marker="o",
            markersize=7 if len(dates) <= 20 else 4,
            markevery=max(1, len(dates) // 15) if len(dates) > 20 else 1,
            markerfacecolor=PAPER,
            markeredgewidth=1.8,
            markeredgecolor=LINE,
            zorder=3,
        )

        _configure_date_axis(ax, dates)
        _configure_value_axis(ax, totals)

        ax.set_xlabel("Date", fontsize=11, color=INK, labelpad=8)
        ax.set_ylabel("Total profile views", fontsize=11, color=INK, labelpad=8)
        ax.set_title(
            "GitHub profile views over time",
            fontsize=15,
            color=INK,
            pad=14,
            loc="left",
            fontweight="normal",
        )
        ax.grid(True, axis="y", color="#cccccc", alpha=0.65, linewidth=0.9, linestyle="-")
        ax.tick_params(axis="both", labelsize=9, colors=INK)

        annotation = f"{latest_total:,} views"
        if len(dates) > 1:
            delta = totals[-1] - totals[-2]
            if delta > 0:
                annotation = f"{latest_total:,} views\n(+{delta:,} since last update)"

        label_offset = (-90, 16) if len(dates) > 14 else (12, 14)
        ax.annotate(
            annotation,
            xy=(date_nums[-1], totals[-1]),
            xytext=label_offset,
            textcoords="offset points",
            fontsize=9,
            color=INK,
            ha="left" if label_offset[0] > 0 else "right",
            arrowprops={
                "arrowstyle": "->",
                "color": INK,
                "lw": 1.2,
                "connectionstyle": "arc3,rad=0.08",
            },
            bbox={"boxstyle": "round,pad=0.35", "facecolor": PAPER, "edgecolor": INK, "linewidth": 1.1},
        )

        updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fig.text(
            0.94,
            0.03,
            f"Updated {updated}",
            ha="right",
            va="bottom",
            fontsize=8,
            color=MUTED,
        )

        fig.savefig(
            CHART_PATH,
            facecolor=PAPER,
            edgecolor="none",
            bbox_inches="tight",
            pad_inches=0.12,
        )
        plt.close(fig)


def main() -> int:
    data = load_history()
    username = data.get("username", "matthewjdoyle")
    today = datetime.now(timezone.utc).date()

    try:
        total = fetch_total_views(username)
    except requests.RequestException as exc:
        print(f"Failed to fetch profile views: {exc}", file=sys.stderr)
        if not data.get("history"):
            return 1
        print("Using existing history only.", file=sys.stderr)
        total = data["history"][-1]["total"]

    append_reading(data, total, today)
    save_history(data)
    render_chart(data)
    print(f"Recorded {total:,} total views for {today.isoformat()}")
    print(f"Chart written to {CHART_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
