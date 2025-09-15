#!/usr/bin/env python3
"""Fix orphaned game stats that don't have matching games."""

import sqlite3
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def fix_orphaned_stats():
    """Remove game stats that don't have matching games."""
    
    logger = setup_logging()
    logger.info("🔧 Fixing orphaned game stats in data/nfl_data.db")
    
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    try:
        # Check initial situation
        cursor.execute("SELECT COUNT(*) FROM game_stats")
        initial_stats = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM game_stats gs 
            LEFT JOIN games g ON gs.game_id = g.game_id 
            WHERE g.game_id IS NULL
        """)
        orphaned_stats = cursor.fetchone()[0]
        
        logger.info(f"Before cleanup: {initial_stats} total stats, {orphaned_stats} orphaned")
        
        # Remove orphaned stats
        logger.info("🔄 Removing orphaned game stats...")
        cursor.execute("""
            DELETE FROM game_stats 
            WHERE game_id NOT IN (SELECT game_id FROM games)
        """)
        
        deleted_count = cursor.rowcount
        conn.commit()
        
        # Check final situation
        cursor.execute("SELECT COUNT(*) FROM game_stats")
        final_stats = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM game_stats gs 
            LEFT JOIN games g ON gs.game_id = g.game_id 
            WHERE g.game_id IS NULL
        """)
        remaining_orphaned = cursor.fetchone()[0]
        
        logger.info(f"\n📊 Cleanup Results:")
        logger.info(f"  Game Stats: {initial_stats} → {final_stats} (-{deleted_count})")
        logger.info(f"  Orphaned Stats: {orphaned_stats} → {remaining_orphaned}")
        
        if remaining_orphaned == 0:
            logger.info("✅ All game stats now have matching games!")
        else:
            logger.warning(f"⚠️ Still have {remaining_orphaned} orphaned stats")
        
        # Show stats by season
        cursor.execute("""
            SELECT g.season_id, COUNT(*) as stats_count
            FROM game_stats gs 
            JOIN games g ON gs.game_id = g.game_id 
            GROUP BY g.season_id 
            ORDER BY g.season_id
        """)
        
        stats_by_season = cursor.fetchall()
        logger.info(f"\n📅 Valid Stats by Season:")
        for season, count in stats_by_season:
            logger.info(f"  {season}: {count} stats")
        
        logger.info("🎯 Game stats now properly linked to games!")
        
    except Exception as e:
        logger.error(f"❌ Error fixing orphaned stats: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_orphaned_stats()