# Gaffer's Clipboard - Calibration

Scrapes and analyzes real-world football data to produce calibration inputs
(weights, distributions, shares, etc.) for the analytics algorithms designed
and implemented in the main [Gaffer's Clipboard](https://github.com/kaziksobo/Gaffers-Clipboard)
repo. This repo only scrapes and analyzes - it doesn't implement or ship any
of the algorithms themselves.

## Convention

One subfolder per analysis. Each subfolder is self-contained and follows the
same two-script pattern:

- `scrape_*.py` - pulls raw data and caches it to that subfolder's `data/raw/`
  as pickles, one file per combination (e.g. per league/season). Skips any
  combination whose cache file already exists, so it's safe to stop and
  resume.
- `analyze_*.py` - loads everything cached in `data/raw/`, does the actual
  aggregation, and writes a small final JSON output (e.g. `data/pos_shares.json`)
  to be copied into the main repo's `config/`.

Raw pickle caches are currently committed to git rather than gitignored, since
they're being kept around for now. They're considered disposable - they're
only scrape output, never hand-edited, and can be regenerated at any time by
rerunning the scraper.

## Setup

```bash
uv sync
```

## Analyses

### `pos_shares/`

Scrapes Sofascore player stats (via [ScraperFC](https://github.com/oseymour/ScraperFC))
for the top 5 European leagues (Premier League, Ligue 1, Bundesliga, Serie A,
La Liga) across the 23/24, 24/25, and 25/26 seasons, then computes each
outfield position's share of total goals and total assists, averaged equally
across all 15 league-seasons.

```bash
uv run python pos_shares/scrape_pos_data.py   # slow - ~40 min per league-season
uv run python pos_shares/analyze_pos_shares.py
```

Output: `pos_shares/data/pos_shares.json`
