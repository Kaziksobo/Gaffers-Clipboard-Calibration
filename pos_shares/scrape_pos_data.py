"""Scrape Sofascore player details for the top-5 leagues across three seasons.

Each (league, season) combination is scraped independently and pickled to
workshop/data/raw/ as soon as it finishes, so a crash or rate limit partway
through only costs the in-progress combination. Reruns skip anything already
cached, so this can be safely stopped and resumed.
"""

import pickle
from pathlib import Path

import ScraperFC as sfc

LEAGUES = [
    "England Premier League",
    "France Ligue 1",
    "Germany Bundesliga",
    "Italy Serie A",
    "Spain La Liga",
]
SEASONS = ["23/24", "24/25", "25/26"]

RAW_DIR = Path(__file__).parent / "data" / "raw"


def cache_path(league: str, season: str) -> Path:
    """Return the deterministic cache path for a given league/season combo."""
    slug = f"{league}_{season}".replace(" ", "_").replace("/", "-").lower()
    return RAW_DIR / f"{slug}.pkl"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ss = sfc.Sofascore()

    for league in LEAGUES:
        for season in SEASONS:
            path = cache_path(league, season)
            if path.exists():
                print(f"Skipping {league} {season} (already cached at {path})")
                continue

            print(f"Scraping {league} {season}...")
            try:
                player_stats = ss.scrape_player_details(season, league)
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED {league} {season}: {exc}")
                continue

            # career_stats holds every year/competition a player has ever appeared in.
            # Only this scrape's season is ever used downstream, and the rest bloats
            # the cache ~7x for no benefit, so drop it before pickling.
            for player in player_stats:
                if "year" in player.career_stats.columns:
                    player.career_stats = player.career_stats[
                        player.career_stats["year"] == season
                    ].reset_index(drop=True)

            with open(path, "wb") as f:
                pickle.dump(player_stats, f)
            print(f"Saved {len(player_stats)} players to {path}")


if __name__ == "__main__":
    main()
