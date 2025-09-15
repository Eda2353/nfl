#!/usr/bin/env python3
"""Rebuild historical schedules completely."""

import sys
import os
import logging
from pathlib import Path
import nfl_data_py as nfl
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager

def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def rebuild_historical_schedules():
    """Delete and rebuild historical games with proper schedule data."""
    logger = logging.getLogger(__name__)
    
    os.environ.setdefault("DB_PATH", "data/nfl_data.db")
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    
    historical_seasons = [2020, 2021, 2022, 2023, 2024]
    
    with db_manager.engine.connect() as conn:
        # Delete problematic historical games
        from sqlalchemy import text
        for season in historical_seasons:
            conn.execute(text("DELETE FROM games WHERE season_id = :season"), {'season': season})
            logger.info(f"Deleted existing games for {season}")
        conn.commit()
    
    # Rebuild with proper schedule data
    for season in historical_seasons:
        try:
            logger.info(f"Rebuilding schedule data for {season}...")
            
            schedules = nfl.import_schedules([season])
            schedules = schedules[schedules['game_type'] == 'REG']
            
            games_data = []
            for _, game in schedules.iterrows():
                game_data = {
                    'game_id': game['game_id'],
                    'season_id': season,
                    'week': game['week'],
                    'game_date': game['gameday'],
                    'home_team_id': game['home_team'],
                    'away_team_id': game['away_team'],
                    'home_score': game.get('home_score'),
                    'away_score': game.get('away_score'),
                    'weather_conditions': None,
                    'temperature': game.get('temp'),
                    'wind_speed': game.get('wind'),
                    'is_dome': None,
                    'game_time': game.get('gametime')
                }
                games_data.append(game_data)
            
            if games_data:
                games_df = pd.DataFrame(games_data)
                db_manager.bulk_insert_dataframe(games_df, 'games', if_exists='append')
                logger.info(f"Inserted {len(games_df)} games for {season}")
            
        except Exception as e:
            logger.error(f"Error rebuilding schedule for season {season}: {e}")
            continue
    
    logger.info("Historical schedule rebuild completed")

def main():
    """Main function."""
    setup_logging()
    rebuild_historical_schedules()

if __name__ == "__main__":
    main()
