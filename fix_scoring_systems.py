#!/usr/bin/env python3
"""Fix FanDuel and DraftKings scoring systems with proper DST columns."""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_scoring_systems():
    """Add FanDuel and DraftKings with all required columns."""
    
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    try:
        # First, delete existing FanDuel and DraftKings entries if they exist
        cursor.execute("DELETE FROM scoring_systems WHERE system_name IN ('FanDuel', 'DraftKings')")
        logger.info("Cleared existing FanDuel and DraftKings entries")
        
        # Insert FanDuel with all columns including DST
        cursor.execute("""
            INSERT INTO scoring_systems (
                system_name, pass_yard_points, pass_td_points, pass_int_points,
                rush_yard_points, rush_td_points, reception_points, receiving_yard_points,
                receiving_td_points, fumble_points, two_point_points,
                dst_sack_points, dst_interception_points, dst_fumble_recovery_points,
                dst_touchdown_points, dst_safety_points, dst_block_kick_points, dst_return_yard_points,
                dst_points_allowed_0_points, dst_points_allowed_1_6_points, dst_points_allowed_7_13_points,
                dst_points_allowed_14_20_points, dst_points_allowed_21_27_points, 
                dst_points_allowed_28_34_points, dst_points_allowed_35_points, dst_yards_allowed_points
            ) VALUES (
                'FanDuel', 0.04, 4, -1,
                0.1, 6, 0.5, 0.1,
                6, -2, 2,
                1.0, 2, 2,
                6, 2, 2, 0,
                10, 7, 4,
                1, 0,
                -1, -4, 0
            )
        """)
        logger.info("Added FanDuel scoring system")
        
        # Insert DraftKings with all columns including DST
        cursor.execute("""
            INSERT INTO scoring_systems (
                system_name, pass_yard_points, pass_td_points, pass_int_points,
                rush_yard_points, rush_td_points, reception_points, receiving_yard_points,
                receiving_td_points, fumble_points, two_point_points,
                dst_sack_points, dst_interception_points, dst_fumble_recovery_points,
                dst_touchdown_points, dst_safety_points, dst_block_kick_points, dst_return_yard_points,
                dst_points_allowed_0_points, dst_points_allowed_1_6_points, dst_points_allowed_7_13_points,
                dst_points_allowed_14_20_points, dst_points_allowed_21_27_points, 
                dst_points_allowed_28_34_points, dst_points_allowed_35_points, dst_yards_allowed_points
            ) VALUES (
                'DraftKings', 0.04, 4, -1,
                0.1, 6, 1.0, 0.1,
                6, -1, 2,
                1.0, 2, 2,
                6, 2, 2, 0,
                10, 7, 4,
                1, 0,
                -1, -4, 0
            )
        """)
        logger.info("Added DraftKings scoring system")
        
        conn.commit()
        
        # Verify the systems were added
        cursor.execute("SELECT system_name FROM scoring_systems")
        systems = [row[0] for row in cursor.fetchall()]
        logger.info(f"Available scoring systems: {systems}")
        
        # Check column count
        cursor.execute("PRAGMA table_info(scoring_systems)")
        columns = cursor.fetchall()
        logger.info(f"Table has {len(columns)} columns")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_scoring_systems()