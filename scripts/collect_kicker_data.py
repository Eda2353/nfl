#!/usr/bin/env python3
"""Collect comprehensive kicker data with field goal distances from 2020-2025."""

import sys
import logging
from pathlib import Path
import nfl_data_py as nfl
import pandas as pd
import requests
import json
from datetime import datetime

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

def collect_kicker_data():
    """Collect comprehensive kicker data from 2020-2025."""
    logger = logging.getLogger(__name__)
    
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    
    # Create kicker-specific tables if they don't exist
    create_kicker_tables(db_manager, logger)
    
    # Collect data from multiple sources
    seasons = [2020, 2021, 2022, 2023, 2024, 2025]
    
    for season in seasons:
        logger.info(f"Collecting kicker data for {season} season...")
        
        try:
            # Method 1: NFL play-by-play data (most detailed)
            if season <= 2023:  # NFL data available
                collect_pbp_kicking_data(season, db_manager, logger)
            
            # Method 2: ESPN/NFL.com current data for 2024-2025
            if season >= 2024:
                collect_current_kicking_data(season, db_manager, logger)
                
        except Exception as e:
            logger.error(f"Error collecting kicker data for {season}: {e}")
            continue
    
    logger.info("Kicker data collection completed")

def create_kicker_tables(db_manager, logger):
    """Create tables for detailed kicker statistics."""
    
    # Table for individual field goal attempts with distance
    field_goal_table = """
    CREATE TABLE IF NOT EXISTS field_goal_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id VARCHAR(20),
        season_id INTEGER,
        week INTEGER,
        kicker_player_id VARCHAR(20),
        kicker_player_name VARCHAR(100),
        team_id VARCHAR(3),
        kick_distance INTEGER,
        result VARCHAR(10),  -- 'made', 'missed', 'blocked'
        game_date DATE,
        quarter INTEGER,
        time_remaining VARCHAR(10),
        
        FOREIGN KEY (game_id) REFERENCES games(game_id),
        FOREIGN KEY (kicker_player_id) REFERENCES players(player_id),
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );
    """
    
    # Table for extra point attempts
    extra_point_table = """
    CREATE TABLE IF NOT EXISTS extra_point_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id VARCHAR(20),
        season_id INTEGER,
        week INTEGER,
        kicker_player_id VARCHAR(20),
        kicker_player_name VARCHAR(100),
        team_id VARCHAR(3),
        result VARCHAR(10),  -- 'made', 'missed', 'blocked'
        game_date DATE,
        
        FOREIGN KEY (game_id) REFERENCES games(game_id),
        FOREIGN KEY (kicker_player_id) REFERENCES players(player_id),
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );
    """
    
    # Execute table creation
    with db_manager.engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text(field_goal_table))
        conn.execute(text(extra_point_table))
        conn.commit()
        logger.info("Created kicker tables")

def collect_pbp_kicking_data(season, db_manager, logger):
    """Collect detailed kicking data from play-by-play for historical seasons."""
    
    try:
        # Get play-by-play data with kicking columns
        pbp = nfl.import_pbp_data([season])
        logger.info(f"Loaded {len(pbp)} plays for {season}")
        
        # Field goal attempts
        fg_attempts = pbp[pbp['play_type'] == 'field_goal'].copy()
        logger.info(f"Found {len(fg_attempts)} field goal attempts")
        
        if not fg_attempts.empty:
            fg_data = []
            for _, play in fg_attempts.iterrows():
                fg_data.append({
                    'game_id': play.get('game_id'),
                    'season_id': season,
                    'week': play.get('week'),
                    'kicker_player_id': play.get('kicker_player_id'),
                    'kicker_player_name': play.get('kicker_player_name'),
                    'team_id': play.get('posteam'),
                    'kick_distance': play.get('kick_distance'),
                    'result': play.get('field_goal_result', 'unknown'),
                    'game_date': play.get('game_date'),
                    'quarter': play.get('qtr'),
                    'time_remaining': play.get('time')
                })
            
            if fg_data:
                fg_df = pd.DataFrame(fg_data)
                db_manager.bulk_insert_dataframe(fg_df, 'field_goal_attempts', if_exists='append')
                logger.info(f"Inserted {len(fg_df)} field goal attempts for {season}")
        
        # Extra point attempts
        ep_attempts = pbp[pbp['extra_point_attempt'] == 1].copy()
        logger.info(f"Found {len(ep_attempts)} extra point attempts")
        
        if not ep_attempts.empty:
            ep_data = []
            for _, play in ep_attempts.iterrows():
                ep_data.append({
                    'game_id': play.get('game_id'),
                    'season_id': season,
                    'week': play.get('week'),
                    'kicker_player_id': play.get('kicker_player_id'),
                    'kicker_player_name': play.get('kicker_player_name'),
                    'team_id': play.get('posteam'),
                    'result': play.get('extra_point_result', 'unknown'),
                    'game_date': play.get('game_date')
                })
            
            if ep_data:
                ep_df = pd.DataFrame(ep_data)
                db_manager.bulk_insert_dataframe(ep_df, 'extra_point_attempts', if_exists='append')
                logger.info(f"Inserted {len(ep_df)} extra point attempts for {season}")
        
    except Exception as e:
        logger.error(f"Error collecting PBP kicking data for {season}: {e}")

def collect_current_kicking_data(season, db_manager, logger):
    """Collect current season kicking data from ESPN/NFL APIs for 2024-2025."""
    
    logger.info(f"Attempting to collect current kicking data for {season}...")
    
    # Try ESPN API endpoints mentioned in search results
    espn_endpoints = [
        f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/athletes",
        f"http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}",
    ]
    
    # For now, log that we need manual implementation
    logger.warning(f"Current season {season} kicking data collection needs manual implementation")
    logger.info("ESPN API endpoints available but require authentication/parsing setup")
    
    # TODO: Implement ESPN API parsing for current seasons
    # This would involve:
    # 1. Parsing ESPN's kicker stats API
    # 2. Extracting individual field goal attempts with distances
    # 3. Mapping to our database structure

def main():
    """Main function."""
    setup_logging()
    collect_kicker_data()

if __name__ == "__main__":
    main()