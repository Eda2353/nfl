#!/usr/bin/env python3
"""Collect historical NFL schedules to fix incomplete game data."""

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

def collect_historical_schedules():
    """Collect complete historical schedule data for 2020-2024."""
    logger = logging.getLogger(__name__)
    
    # Load configuration (ensure default DB path if missing)
    os.environ.setdefault("DB_PATH", "data/nfl_data.db")
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    
    # Define historical seasons to fix
    historical_seasons = [2020, 2021, 2022, 2023, 2024]
    
    for season in historical_seasons:
        try:
            logger.info(f"Collecting schedule data for {season} season...")
            
            # Get complete schedule data
            schedules = nfl.import_schedules([season])
            schedules = schedules[schedules['game_type'] == 'REG']  # Regular season only
            
            logger.info(f"Found {len(schedules)} regular season games for {season}")
            
            # Process each game
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
                    'temperature': None,
                    'wind_speed': None,
                    'is_dome': None,
                    'game_time': game.get('gametime')
                }
                games_data.append(game_data)
            
            if games_data:
                games_df = pd.DataFrame(games_data)
                
                # Update existing games with complete data
                with db_manager.engine.connect() as conn:
                    for _, game in games_df.iterrows():
                        from sqlalchemy import text
                        conn.execute(text("""
                            UPDATE games 
                            SET home_team_id = :home_team_id,
                                away_team_id = :away_team_id,
                                game_date = :game_date,
                                home_score = :home_score,
                                away_score = :away_score,
                                game_time = :game_time
                            WHERE game_id = :game_id
                        """), {
                            'game_id': game['game_id'],
                            'home_team_id': game['home_team_id'],
                            'away_team_id': game['away_team_id'],
                            'game_date': game['game_date'],
                            'home_score': game['home_score'],
                            'away_score': game['away_score'],
                            'game_time': game['game_time']
                        })
                    conn.commit()
                
                logger.info(f"Updated {len(games_df)} games for {season} season")
            
        except Exception as e:
            logger.error(f"Error collecting schedule for season {season}: {e}")
            continue
    
    logger.info("Historical schedule collection completed")

def main():
    """Main function."""
    setup_logging()
    collect_historical_schedules()

if __name__ == "__main__":
    main()
