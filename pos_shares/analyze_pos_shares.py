"""Aggregate cached Sofascore scrapes into averaged pos_goals_share / pos_assists_share.

Loads every pickle in workshop/data/raw/ (produced by scrape_pos_data.py), computes
per-position goals/assists shares independently for each (league, season), then takes
an equal-weighted average across all of them so no single league or season - by virtue
of having more goals or more games - dominates the result.
"""

import json
import pickle
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from scrape_pos_data import LEAGUES, RAW_DIR, SEASONS, cache_path

OUTPUT_PATH = Path(__file__).parent / "data" / "pos_shares.json"

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
    path_to_combo = {cache_path(league, season): (league, season) for league in LEAGUES for season in SEASONS}

    scrapes = []
    for path in sorted(path_to_combo):
        if not path.exists():
            continue
        league, season = path_to_combo[path]
        with open(path, "rb") as f:
            player_stats = pickle.load(f)
        scrapes.append({"league": league, "season": season, "player_stats": player_stats})
    return scrapes


def _goals_assists_by_position(
    scrape: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float]]:
    """Return raw (not yet normalized) goals/assists totals per position for one scrape."""
    league = scrape["league"]
    season = scrape["season"]
    tournament_name = LEAGUE_TOURNAMENT_NAMES[league]

    df = pd.DataFrame([asdict(p) for p in scrape["player_stats"]])
    all_positions = [
        pos for pos in df["positions_detailed"].explode().unique().tolist() if pd.notna(pos)
    ]

    def get_goals_assists(career_stats: pd.DataFrame) -> pd.Series:
        matches = career_stats[
            (career_stats["uniqueTournament.name"] == tournament_name)
            & (career_stats["year"] == season)
        ]
        return pd.Series(
            {
                "goals": matches["statistics.goals"].sum(),
                "assists": matches["statistics.assists"].sum(),
            }
        )

    df[["goals", "assists"]] = df["career_stats"].apply(get_goals_assists)

    pos_goals = dict.fromkeys(all_positions, 0.0)
    pos_assists = dict.fromkeys(all_positions, 0.0)

    for _, row in df.iterrows():
        positions = row["positions_detailed"]
        if not isinstance(positions, list) or not positions:
            continue
        first_pos = positions[0]
        if pd.isna(first_pos):
            continue
        pos_goals[first_pos] += row["goals"]
        pos_assists[first_pos] += row["assists"]

    return pos_goals, pos_assists


def _to_shares(pos_totals: dict[str, float]) -> dict[str, float]:
    """Normalize raw per-position totals into fractions that sum to 1."""
    grand_total = sum(pos_totals.values())
    if grand_total == 0:
        return dict.fromkeys(pos_totals, 0.0)
    return {pos: total / grand_total for pos, total in pos_totals.items()}


def main() -> None:
    scrapes = _load_cached_scrapes()
    if not scrapes:
        raise SystemExit(f"No cached scrapes found in {RAW_DIR}. Run scrape_pos_data.py first.")

    goals_shares_per_combo: list[dict[str, float]] = []
    assists_shares_per_combo: list[dict[str, float]] = []

    for scrape in scrapes:
        pos_goals, pos_assists = _goals_assists_by_position(scrape)
        goals_shares_per_combo.append(_to_shares(pos_goals))
        assists_shares_per_combo.append(_to_shares(pos_assists))
        print(f"Processed {scrape['league']} {scrape['season']}")

    all_positions = sorted({pos for shares in goals_shares_per_combo for pos in shares})
    n_combos = len(goals_shares_per_combo)

    pos_goals_share = {
        pos: sum(shares.get(pos, 0.0) for shares in goals_shares_per_combo) / n_combos
        for pos in all_positions
    }
    pos_assists_share = {
        pos: sum(shares.get(pos, 0.0) for shares in assists_shares_per_combo) / n_combos
        for pos in all_positions
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(
            {"pos_goals_share": pos_goals_share, "pos_assists_share": pos_assists_share},
            f,
            indent=2,
        )

    print(f"Averaged across {n_combos} league-seasons. Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
