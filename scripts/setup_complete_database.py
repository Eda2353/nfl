#!/usr/bin/env python3
"""
Complete database setup script for web hosting deployment.
Recreates the entire NFL fantasy database from scratch with all data.
"""

import sys
import os
import logging
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from collectors.dst_collector import DSTCollector

def setup_logging():
    """Set up comprehensive logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def setup_complete_database():
    """Complete database setup - recreates everything we have built."""
    
    logger = logging.getLogger(__name__)
    logger.info("🏈 Starting COMPLETE NFL Fantasy Database Setup...")
    logger.info("This will recreate the entire database with all historical data")
    
    start_time = time.time()
    
    try:
        # 1. Initialize database and core structure
        logger.info("\n📊 Step 1/7: Database initialization...")
        # Ensure a default DB_PATH if not provided externally
        os.environ.setdefault("DB_PATH", "data/nfl_data.db")
        config = Config.from_env()
        db_manager = DatabaseManager(config)
        logger.info("✅ Database structure created")
        
        # 2. Collect core NFL data (teams, players, games, stats)
        logger.info("\n🏈 Step 2/7: Collecting core NFL data (2020-2025)...")
        from collectors.nfl_data_collector import NFLDataCollector
        
        # Set collection range to our full dataset
        original_start = config.data_collection.start_season
        original_end = config.data_collection.end_season
        
        config.data_collection.start_season = 2020
        config.data_collection.end_season = 2025
        
        data_collector = NFLDataCollector(config, db_manager)
        data_collector.collect_all_data()
        
        # Restore original config
        config.data_collection.start_season = original_start
        config.data_collection.end_season = original_end
        
        logger.info("✅ Core NFL data collected")
        
        # 3. Fix historical schedules (critical for schedule display)
        logger.info("\n📅 Step 3/7: Fixing historical schedules...")
        exec(open('scripts/rebuild_historical_schedules.py').read())
        logger.info("✅ Historical schedules fixed")
        
        # 4. Collect comprehensive kicking data with distances
        logger.info("\n⚽ Step 4/7: Collecting detailed kicking data (2020-2025)...")
        
        # Create kicker tables
        with db_manager.engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS field_goal_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id VARCHAR(20),
                    season_id INTEGER,
                    week INTEGER,
                    kicker_player_id VARCHAR(20),
                    kicker_player_name VARCHAR(100),
                    team_id VARCHAR(3),
                    kick_distance INTEGER,
                    result VARCHAR(10),
                    game_date DATE,
                    quarter INTEGER,
                    time_remaining VARCHAR(10)
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS extra_point_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id VARCHAR(20),
                    season_id INTEGER,
                    week INTEGER,
                    kicker_player_id VARCHAR(20),
                    kicker_player_name VARCHAR(100),
                    team_id VARCHAR(3),
                    result VARCHAR(10),
                    game_date DATE
                );
            """))
            conn.commit()
        
        # Collect kicking data
        exec(open('collect_historical_kicks.py').read())
        logger.info("✅ Kicking data collected")
        
        # 5. Collect team defense/special teams stats (for DST & matchup analysis)
        logger.info("\n🛡️  Step 5/7: Collecting team defense stats (2020-2025)...")
        try:
            dst_collector = DSTCollector(db_manager)
            dst_collector.collect_team_defense_stats([2020, 2021, 2022, 2023, 2024, 2025])
            logger.info("✅ Team defense stats collected")
        except Exception as e:
            logger.warning(f"⚠️ Team defense stat collection skipped/failed: {e}")

        # 6. Collect historical injury data (comprehensive, 2020+)
        logger.info("\n🏥 Step 6/7: Importing historical injury reports (2020-2025)...")
        from collectors.injury_collector import InjuryCollector
        try:
            injury_collector = InjuryCollector(db_manager)
            imported = injury_collector.import_historical_injuries([2020, 2021, 2022, 2023, 2024, 2025])
            logger.info(f"✅ Imported {imported} historical injury records")
        except Exception as e:
            logger.warning(f"⚠️ Historical injury import skipped/failed: {e}")

        # Rebuild indexes after bulk loads
        try:
            logger.info("\n🧩 Rebuilding indexes after bulk imports...")
            db_manager.rebuild_indexes()
            logger.info("✅ Indexes rebuilt")
        except Exception as e:
            logger.warning(f"⚠️ Index rebuild skipped/failed: {e}")

        # 7. Ensure scoring systems are properly set up
        logger.info("\n🎯 Step 7/7: Finalizing scoring systems...")
        from init_scoring_systems import init_scoring_systems
        init_scoring_systems(db_manager)
        logger.info("✅ Scoring systems configured")
        
        # Final verification
        logger.info("\n📋 Database Setup Verification:")
        with db_manager.engine.connect() as conn:
            from sqlalchemy import text
            
            # Count key data
            teams_count = conn.execute(text("SELECT COUNT(*) FROM teams")).fetchone()[0]
            players_count = conn.execute(text("SELECT COUNT(*) FROM players")).fetchone()[0] 
            games_count = conn.execute(text("SELECT COUNT(*) FROM games")).fetchone()[0]
            stats_count = conn.execute(text("SELECT COUNT(*) FROM game_stats")).fetchone()[0]
            fg_count = conn.execute(text("SELECT COUNT(*) FROM field_goal_attempts")).fetchone()[0]
            scoring_count = conn.execute(text("SELECT COUNT(*) FROM scoring_systems")).fetchone()[0]
            
            logger.info(f"  Teams: {teams_count}")
            logger.info(f"  Players: {players_count}")
            logger.info(f"  Games: {games_count}")
            logger.info(f"  Player Stats: {stats_count}")
            logger.info(f"  Field Goal Attempts: {fg_count}")
            logger.info(f"  Scoring Systems: {scoring_count}")
            
            # Check data coverage by season
            season_games = conn.execute(text("""
                SELECT season_id, COUNT(*) as games, COUNT(home_team_id) as complete_games
                FROM games 
                GROUP BY season_id 
                ORDER BY season_id
            """)).fetchall()
            
            logger.info(f"  Season Coverage:")
            for season, total, complete in season_games:
                logger.info(f"    {season}: {complete}/{total} games with teams")
        
        elapsed = time.time() - start_time
        logger.info(f"\n🎉 COMPLETE DATABASE SETUP FINISHED!")
        logger.info(f"   Total time: {elapsed/60:.1f} minutes")
        logger.info(f"   Ready for web hosting deployment!")
        
    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        raise

def main():
    """Main setup function."""
    print("=" * 60)
    print("🏈 NFL FANTASY DATABASE - COMPLETE SETUP")
    print("=" * 60)
    print()
    print("This script will recreate the entire database from scratch.")
    print("It includes:")
    print("  • Teams, players, games, and statistics (2020-2025)")
    print("  • Historical schedules with team matchups")  
    print("  • Detailed kicking data with field goal distances")
    print("  • Injury reports and historical data")
    print("  • All 5 scoring systems (Standard, PPR, Half PPR, FanDuel, DraftKings)")
    print()
    print("Estimated time: 15-30 minutes")
    print("=" * 60)
    print()
    
    # Confirm before starting
    response = input("Continue with complete database setup? (y/N): ")
    if response.lower() != 'y':
        print("Setup cancelled.")
        return
    
    setup_logging()
    setup_complete_database()

if __name__ == "__main__":
    main()
