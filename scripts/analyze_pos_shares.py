"""Aggregate cached Sofascore scrapes into averaged pos_goals_p90 / pos_assists_p90.

Loads every pickle in workshop/data/raw/ (produced by scrape_pos_data.py), computes
per-position goals/assists per-90-minutes rates independently for each (league, season),
takes an equal-weighted average across all of them so no single league or season - by
virtue of having more goals, minutes, or games - dominates the result, then renormalizes
those averaged rates so they sum to 1 across positions.
"""

import json
import pickle
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.scrape_pos_data import LEAGUES, RAW_DIR, SEASONS, cache_path

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "pos_shares.json"

# Sofascore's uniqueTournament.name doesn't always match ScraperFC's league query
# string (e.g. "Spain La Liga" scrapes under the tournament name "LaLiga").
# Confirmed empirically against the England Premier League 24/25 cache.
LEAGUE_TOURNAMENT_NAMES = {
    "England Premier League": "Premier League",
    "France Ligue 1": "Ligue 1",
    "Germany Bundesliga": "Bundesliga",
    "Italy Serie A": "Serie A",
    "Spain La Liga": "LaLiga",
}


def _load_cached_scrapes() -> list[dict[str, Any]]:
    """Load every cached pickle, pairing each back up with its league/season via filename."""
    path_to_combo = {
        cache_path(league, season): (league, season)
        for league in LEAGUES
        for season in SEASONS
    }

    scrapes = []
    for path in sorted(path_to_combo):
        if not path.exists():
            continue
        league, season = path_to_combo[path]
        with open(path, "rb") as f:
            player_stats = pickle.load(f)
        scrapes.append(
            {"league": league, "season": season, "player_stats": player_stats}
        )
    return scrapes


def _goals_assists_minutes_by_position(
    scrape: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Return raw goals/assists/minutes-played totals per position for one scrape."""
    league = scrape["league"]
    season = scrape["season"]
    tournament_name = LEAGUE_TOURNAMENT_NAMES[league]

    df = pd.DataFrame([asdict(p) for p in scrape["player_stats"]])
    all_positions = [
        pos
        for pos in df["positions_detailed"].explode().unique().tolist()
        if pd.notna(pos)
    ]

    def get_goals_assists_minutes(career_stats: pd.DataFrame) -> pd.Series:
        if (
            "uniqueTournament.name" not in career_stats.columns
            or "year" not in career_stats.columns
        ):
            return pd.Series({"goals": 0, "assists": 0, "minutes": 0})
        matches = career_stats[
            (career_stats["uniqueTournament.name"] == tournament_name)
            & (career_stats["year"] == season)
        ]
        return pd.Series(
            {
                "goals": matches["statistics.goals"].sum(),
                "assists": matches["statistics.assists"].sum(),
                "minutes": matches["statistics.minutesPlayed"].sum(),
            }
        )

    df[["goals", "assists", "minutes"]] = df["career_stats"].apply(
        get_goals_assists_minutes
    )

    pos_goals = dict.fromkeys(all_positions, 0.0)
    pos_assists = dict.fromkeys(all_positions, 0.0)
    pos_minutes = dict.fromkeys(all_positions, 0.0)

    for _, row in df.iterrows():
        positions = row["positions_detailed"]
        if not isinstance(positions, list) or not positions:
            continue
        first_pos = positions[0]
        if pd.isna(first_pos):
            continue
        pos_goals[first_pos] += row["goals"]
        pos_assists[first_pos] += row["assists"]
        pos_minutes[first_pos] += row["minutes"]

    return pos_goals, pos_assists, pos_minutes


def _to_p90_rates(
    pos_totals: dict[str, float], pos_minutes: dict[str, float]
) -> dict[str, float]:
    """Convert raw per-position totals into a per-90-minutes rate.

    Positions with zero minutes played in this scrape are omitted rather than
    reported as a 0.0 rate, so they don't drag down the cross-combo average below.
    """
    return {
        pos: total / pos_minutes[pos] * 90
        for pos, total in pos_totals.items()
        if pos_minutes[pos] > 0
    }


def _normalize(rates: dict[str, float]) -> dict[str, float]:
    """Rescale per-position rates so they sum to 1."""
    total = sum(rates.values())
    if total == 0:
        return dict.fromkeys(rates, 0.0)
    return {pos: rate / total for pos, rate in rates.items()}


def main() -> None:
    scrapes = _load_cached_scrapes()
    if not scrapes:
        raise SystemExit(
            f"No cached scrapes found in {RAW_DIR}. Run scrape_pos_data.py first."
        )

    goals_p90_per_combo: list[dict[str, float]] = []
    assists_p90_per_combo: list[dict[str, float]] = []

    for scrape in scrapes:
        pos_goals, pos_assists, pos_minutes = _goals_assists_minutes_by_position(scrape)
        goals_p90_per_combo.append(_to_p90_rates(pos_goals, pos_minutes))
        assists_p90_per_combo.append(_to_p90_rates(pos_assists, pos_minutes))
        print(f"Processed {scrape['league']} {scrape['season']}")

    all_positions = sorted({pos for rates in goals_p90_per_combo for pos in rates})

    def average_rate(rates_per_combo: list[dict[str, float]], pos: str) -> float:
        values = [rates[pos] for rates in rates_per_combo if pos in rates]
        return sum(values) / len(values) if values else 0.0

    pos_goals_p90 = _normalize(
        {pos: average_rate(goals_p90_per_combo, pos) for pos in all_positions}
    )
    pos_assists_p90 = _normalize(
        {pos: average_rate(assists_p90_per_combo, pos) for pos in all_positions}
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(
            {"pos_goals_p90": pos_goals_p90, "pos_assists_p90": pos_assists_p90},
            f,
            indent=2,
        )

    print(f"Averaged across {len(scrapes)} league-seasons. Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
