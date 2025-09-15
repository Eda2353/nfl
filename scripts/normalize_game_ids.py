#!/usr/bin/env python3
"""Normalize synthetic game IDs in game_stats to official schedule IDs.

Usage:
  python3 scripts/normalize_game_ids.py --start 2020 --end 2024
  # Defaults to all seasons present if no range provided.
"""

import argparse
import os
import sys
from pathlib import Path
import logging
from sqlalchemy import create_engine

# Add src to import path for normalization module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from normalization import normalize_game_ids_engine


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def parse_args():
    p = argparse.ArgumentParser(description="Normalize game IDs in game_stats")
    p.add_argument('--start', type=int, default=None, help='Start season')
    p.add_argument('--end', type=int, default=None, help='End season')
    p.add_argument('--keep-stub-games', action='store_true', help='Do not delete synthetic stub games')
    return p.parse_args()


def main():
    setup_logging()
    log = logging.getLogger('normalize')

    # Build engine from environment without importing pandas/numpy via our DB wrapper
    os.environ.setdefault('DB_PATH', 'data/nfl_data.db')
    db_type = os.environ.get('DB_TYPE', 'sqlite').lower()
    if db_type == 'sqlite':
        url = f"sqlite:///{os.environ['DB_PATH']}"
    else:
        user = os.environ.get('DB_USER', '')
        pwd = os.environ.get('DB_PASSWORD', '')
        host = os.environ.get('DB_HOST', 'localhost')
        port = os.environ.get('DB_PORT', '5432')
        name = os.environ.get('DB_NAME', '')
        auth = f"{user}:{pwd}@" if user or pwd else ""
        url = f"postgresql://{auth}{host}:{port}/{name}"
    engine = create_engine(url)

    args = parse_args()
    seasons = None
    if args.start and args.end:
        seasons = list(range(args.start, args.end + 1))

    log.info("Normalizing game IDs in DB URL: %s", url)
    summary = normalize_game_ids_engine(engine, seasons=seasons, delete_stub_games=not args.keep_stub_games)
    log.info("Summary: %s", summary)


if __name__ == '__main__':
    main()
