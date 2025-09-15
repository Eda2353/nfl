#!/usr/bin/env python3
"""Clean duplicate entries from the current database."""

import sqlite3
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def clean_duplicates():
    """Remove duplicate entries from current database."""
    
    logger = setup_logging()
    logger.info("🧹 Cleaning duplicate entries from data/nfl_data.db")
    
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    try:
        # Check initial counts
        cursor.execute("SELECT COUNT(*) FROM field_goal_attempts")
        initial_fg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM extra_point_attempts")  
        initial_ep_count = cursor.fetchone()[0]
        
        logger.info(f"Before cleanup: {initial_fg_count} field goals, {initial_ep_count} extra points")
        
        # Clean duplicate field goals - keep the first occurrence
        logger.info("🔄 Removing duplicate field goals...")
        cursor.execute("""
            DELETE FROM field_goal_attempts 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM field_goal_attempts 
                GROUP BY game_id, kicker_player_id, kick_distance, COALESCE(quarter, 0), COALESCE(time_remaining, '')
            )
        """)
        
        fg_deleted = cursor.rowcount
        logger.info(f"✅ Removed {fg_deleted} duplicate field goals")
        
        # Clean duplicate extra points - keep the first occurrence  
        logger.info("🔄 Removing duplicate extra points...")
        cursor.execute("""
            DELETE FROM extra_point_attempts 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM extra_point_attempts 
                GROUP BY game_id, kicker_player_id
            )
        """)
        
        ep_deleted = cursor.rowcount
        logger.info(f"✅ Removed {ep_deleted} duplicate extra points")
        
        # Check for any other potential duplicates in game_stats
        logger.info("🔄 Checking game_stats for duplicates...")
        cursor.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT player_id || '|' || game_id) as duplicates 
            FROM game_stats
        """)
        stats_duplicates = cursor.fetchone()[0]
        
        if stats_duplicates > 0:
            logger.info(f"🔄 Removing {stats_duplicates} duplicate game stats...")
            cursor.execute("""
                DELETE FROM game_stats 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM game_stats 
                    GROUP BY player_id, game_id
                )
            """)
            stats_deleted = cursor.rowcount
            logger.info(f"✅ Removed {stats_deleted} duplicate game stats")
        else:
            logger.info("✅ No duplicate game stats found")
        
        conn.commit()
        
        # Final counts
        cursor.execute("SELECT COUNT(*) FROM field_goal_attempts")
        final_fg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM extra_point_attempts")
        final_ep_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM game_stats")
        final_stats_count = cursor.fetchone()[0]
        
        logger.info(f"\n📊 Cleanup Results:")
        logger.info(f"  Field Goals: {initial_fg_count} → {final_fg_count} (-{fg_deleted})")
        logger.info(f"  Extra Points: {initial_ep_count} → {final_ep_count} (-{ep_deleted})")
        logger.info(f"  Game Stats: {final_stats_count} (cleaned)")
        
        # Now add constraints to prevent future duplicates
        logger.info("\n🔒 Adding duplicate prevention constraints...")
        
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_field_goal 
                ON field_goal_attempts(game_id, kicker_player_id, kick_distance, COALESCE(quarter, 0), COALESCE(time_remaining, ''))
            """)
            logger.info("✅ Added field goal duplicate prevention")
        except Exception as e:
            logger.warning(f"Field goal constraint: {e}")
        
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_extra_point
                ON extra_point_attempts(game_id, kicker_player_id)
            """)
            logger.info("✅ Added extra point duplicate prevention")
        except Exception as e:
            logger.warning(f"Extra point constraint: {e}")
        
        conn.commit()
        logger.info("🎉 Database cleanup completed!")
        
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clean_duplicates()