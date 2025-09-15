#!/usr/bin/env python3
"""Fix historical NFL schedules by matching teams and weeks."""

import sys
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

def fix_historical_schedules():
    """Fix historical schedule data by matching teams and weeks."""
    logger = logging.getLogger(__name__)
    
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    
    # Define historical seasons to fix
    historical_seasons = [2020, 2021, 2022, 2023, 2024]
    
    for season in historical_seasons:
        try:
            logger.info(f"Fixing schedule data for {season} season...")
            
            # Get complete schedule data from NFL API
            schedules = nfl.import_schedules([season])
            schedules = schedules[schedules['game_type'] == 'REG']
            
            updated_count = 0
            
            # Match by teams and week instead of game ID
            with db_manager.engine.connect() as conn:
                for _, game in schedules.iterrows():
                    from sqlalchemy import text
                    
                    # Try to find matching game by season, week, and teams
                    result = conn.execute(text("""
                        UPDATE games 
                        SET home_team_id = :home_team_id,
                            away_team_id = :away_team_id,
                            game_date = :game_date,
                            home_score = :home_score,
                            away_score = :away_score,
                            game_time = :game_time
                        WHERE season_id = :season_id 
                          AND week = :week
                          AND (
                            (game_id LIKE '%' || :home_team || '%' AND game_id LIKE '%' || :away_team || '%')
                            OR (game_id LIKE '%' || :away_team || '%' AND game_id LIKE '%' || :home_team || '%')
                          )
                    """), {
                        'season_id': season,
                        'week': game['week'],
                        'home_team_id': game['home_team'],
                        'away_team_id': game['away_team'],
                        'home_team': game['home_team'],
                        'away_team': game['away_team'],
                        'game_date': game['gameday'],
                        'home_score': game.get('home_score'),
                        'away_score': game.get('away_score'),
                        'game_time': game.get('gametime')
                    })
                    
                    if result.rowcount > 0:
                        updated_count += result.rowcount
                
                conn.commit()
            
            logger.info(f"Updated {updated_count} games for {season} season")
            
        except Exception as e:
            logger.error(f"Error fixing schedule for season {season}: {e}")
            continue
    
    logger.info("Historical schedule fix completed")

def main():
    """Main function."""
    setup_logging()
    fix_historical_schedules()

if __name__ == "__main__":
    main()