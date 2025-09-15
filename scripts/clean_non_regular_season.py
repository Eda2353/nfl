#!/usr/bin/env python3
"""Remove preseason and playoff games from current database to focus on regular season."""

import sqlite3
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def clean_non_regular_season():
    """Remove non-regular season games to focus on fantasy-relevant data."""
    
    logger = setup_logging()
    logger.info("🧹 Removing preseason and playoff games from data/nfl_data.db")
    
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    try:
        # Check initial counts
        cursor.execute("SELECT COUNT(*) FROM games")
        initial_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT season_id, COUNT(*) FROM games GROUP BY season_id ORDER BY season_id")
        initial_by_season = cursor.fetchall()
        
        logger.info(f"Before cleanup: {initial_count} total games")
        for season, count in initial_by_season:
            logger.info(f"  {season}: {count} games")
        
        # Regular season is typically weeks 1-18 (sometimes 1-17)
        # Remove games outside regular season weeks
        logger.info("\n🔄 Removing non-regular season games (week > 18)...")
        
        cursor.execute("DELETE FROM games WHERE week > 18")
        playoff_deleted = cursor.rowcount
        logger.info(f"✅ Removed {playoff_deleted} playoff games")
        
        # For older seasons, week 17 was the max, so let's also clean up any week 0 or negative weeks
        cursor.execute("DELETE FROM games WHERE week <= 0")
        preseason_deleted = cursor.rowcount
        logger.info(f"✅ Removed {preseason_deleted} preseason/invalid games")
        
        # Also remove any games that clearly look like preseason based on game_id patterns
        cursor.execute("DELETE FROM games WHERE game_id LIKE '%_PRE_%' OR game_id LIKE '%_0_%'")
        pattern_deleted = cursor.rowcount
        logger.info(f"✅ Removed {pattern_deleted} preseason games by pattern")
        
        conn.commit()
        
        # Final counts
        cursor.execute("SELECT COUNT(*) FROM games")
        final_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT season_id, COUNT(*) FROM games GROUP BY season_id ORDER BY season_id")
        final_by_season = cursor.fetchall()
        
        total_deleted = initial_count - final_count
        
        logger.info(f"\n📊 Cleanup Results:")
        logger.info(f"  Total games: {initial_count} → {final_count} (-{total_deleted})")
        logger.info(f"  Breakdown: {playoff_deleted} playoffs, {preseason_deleted} preseason, {pattern_deleted} by pattern")
        
        logger.info(f"\n📅 Regular Season Games by Year:")
        for season, count in final_by_season:
            logger.info(f"  {season}: {count} games")
        
        logger.info("🎯 Database now focused on regular season fantasy-relevant games!")
        
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clean_non_regular_season()