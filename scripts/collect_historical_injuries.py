#!/usr/bin/env python3
"""Import historical NFL injury reports into the configured database.

Usage examples:
  # Use defaults (2020..current year) and DB_PATH env var if set
  python3 scripts/collect_historical_injuries.py

  # Explicit seasons and DB
  DB_PATH=data/nfl_data.db python3 scripts/collect_historical_injuries.py --start 2020 --end 2025
"""

import argparse
import sys
from pathlib import Path
import logging
import os

# Ensure src/ package is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from collectors.injury_collector import InjuryCollector


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Import historical NFL injuries into DB")
    parser.add_argument("--start", type=int, default=2020, help="Start season (inclusive)")
    parser.add_argument("--end", type=int, default=None, help="End season (inclusive); default=current year")
    return parser.parse_args()


def main():
    setup_logging()
    log = logging.getLogger("injury_import")
    args = parse_args()

    # Ensure a default DB_PATH if not provided externally
    os.environ.setdefault("DB_PATH", "data/nfl_data.db")

    # Load config and DB
    config = Config.from_env()
    db = DatabaseManager(config)

    end_season = args.end or __import__("datetime").datetime.now().year
    seasons = list(range(args.start, end_season + 1))

    log.info("Using database: %s", config.database.db_path)
    log.info("Importing historical injuries for seasons: %s", seasons)

    collector = InjuryCollector(db)
    try:
        count = collector.import_historical_injuries(seasons)
        log.info("Imported %d historical injury records", count)
    except Exception as e:
        log.error("Historical injury import failed: %s", e)
        raise

    # Rebuild indexes to optimize queries
    try:
        db.rebuild_indexes()
        log.info("Indexes rebuilt successfully")
    except Exception as e:
        log.warning("Index rebuild skipped/failed: %s", e)


if __name__ == "__main__":
    main()
