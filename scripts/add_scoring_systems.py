#!/usr/bin/env python3
"""Script to add FanDuel and DraftKings scoring systems to the database."""

import sys
import os
import logging
from pathlib import Path

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

def add_dfs_scoring_systems():
    """Add FanDuel and DraftKings scoring systems."""
    logger = logging.getLogger(__name__)
    
    # Load configuration (ensure default DB path if missing)
    os.environ.setdefault("DB_PATH", "data/nfl_data.db")
    config = Config.from_env()
    
    # Initialize database
    db_manager = DatabaseManager(config)
    
    # Define FanDuel scoring
    fanduel_scoring = {
        'system_name': 'FanDuel',
        'pass_yard_points': 0.04,
        'pass_td_points': 4,
        'pass_int_points': -1,  # FanDuel: -1 for interceptions
        'rush_yard_points': 0.1,
        'rush_td_points': 6,
        'reception_points': 0.5,  # FanDuel: Half PPR
        'receiving_yard_points': 0.1,
        'receiving_td_points': 6,
        'fumble_points': -2,  # FanDuel: -2 for fumbles
        'field_goal_points': 3,  # Base points (distance bonuses handled separately)
        'extra_point_points': 1,
        'defensive_td_points': 6,
        'sack_points': 1.0,
        'int_points': 2,
        'fumble_recovery_points': 2,
        'safety_points': 2
    }
    
    # Define DraftKings scoring
    draftkings_scoring = {
        'system_name': 'DraftKings',
        'pass_yard_points': 0.04,
        'pass_td_points': 4,
        'pass_int_points': -1,  # DraftKings: -1 for interceptions
        'rush_yard_points': 0.1,
        'rush_td_points': 6,
        'reception_points': 1.0,  # DraftKings: Full PPR
        'receiving_yard_points': 0.1,
        'receiving_td_points': 6,
        'fumble_points': -1,  # DraftKings: -1 for fumbles
        'field_goal_points': 3,  # Base points
        'extra_point_points': 1,
        'defensive_td_points': 6,
        'sack_points': 1.0,
        'int_points': 2,
        'fumble_recovery_points': 2,
        'safety_points': 2
    }
    
    # Insert both scoring systems
    scoring_systems = [fanduel_scoring, draftkings_scoring]
    
    for system in scoring_systems:
        try:
            # Check if system already exists
            existing = db_manager.execute_query(
                "SELECT system_id FROM scoring_systems WHERE system_name = ?",
                [system['system_name']]
            )
            
            if existing.empty:
                # Insert new system
                columns = ', '.join(system.keys())
                placeholders = ', '.join(['?' for _ in system.keys()])
                values = list(system.values())
                
                with db_manager.engine.connect() as conn:
                    from sqlalchemy import text
                    # Build parameter dict for named parameters
                    param_dict = dict(zip(system.keys(), values))
                    named_placeholders = ', '.join([f':{key}' for key in system.keys()])
                    conn.execute(text(f"INSERT INTO scoring_systems ({columns}) VALUES ({named_placeholders})"), param_dict)
                    conn.commit()
                logger.info(f"Added {system['system_name']} scoring system")
            else:
                logger.info(f"{system['system_name']} scoring system already exists")
                
        except Exception as e:
            logger.error(f"Error adding {system['system_name']} scoring system: {e}")
    
    logger.info("Scoring systems setup completed")

def main():
    """Main function."""
    setup_logging()
    add_dfs_scoring_systems()

if __name__ == "__main__":
    main()
