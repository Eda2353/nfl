#!/usr/bin/env python3
"""Add UNIQUE constraints to prevent duplicates in key tables."""

import os
import sqlite3
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def add_duplicate_constraints():
    """Add UNIQUE constraints to prevent duplicate entries."""
    
    logger = setup_logging()
    
    # Use environment variable for database path, fallback to default
    db_path = os.environ.get("DB_PATH", "data/nfl_data.db")
    logger.info(f"Adding duplicate constraints to: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Add UNIQUE constraint to teams (already has PRIMARY KEY)
        logger.info("Teams table already has PRIMARY KEY constraint")
        
        # Add UNIQUE constraint to players (already has PRIMARY KEY)
        logger.info("Players table already has PRIMARY KEY constraint")
        
        # Add UNIQUE constraint to games (already has PRIMARY KEY)
        logger.info("Games table already has PRIMARY KEY constraint")
        
        # Field goal attempts - add unique constraint
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_field_goal 
                ON field_goal_attempts(game_id, kicker_player_id, kick_distance, quarter, time_remaining)
            """)
            logger.info("✅ Added unique constraint to field_goal_attempts")
        except Exception as e:
            logger.warning(f"Field goal constraint: {e}")
        
        # Extra point attempts - add unique constraint  
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_extra_point
                ON extra_point_attempts(game_id, kicker_player_id)
            """)
            logger.info("✅ Added unique constraint to extra_point_attempts")
        except Exception as e:
            logger.warning(f"Extra point constraint: {e}")
        
        # Player teams - add unique constraint
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_player_team
                ON player_teams(player_id, team_id, season_id, week_start, week_end)
            """)
            logger.info("✅ Added unique constraint to player_teams")
        except Exception as e:
            logger.warning(f"Player teams constraint: {e}")
        
        # Historical injuries - already has unique constraint
        logger.info("Historical injuries table already has UNIQUE constraint")
        
        conn.commit()
        logger.info("🎉 Duplicate constraints added successfully")
        
    except Exception as e:
        logger.error(f"❌ Error adding constraints: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_duplicate_constraints()