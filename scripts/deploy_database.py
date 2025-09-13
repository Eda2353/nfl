#!/usr/bin/env python3
"""
Single script to recreate complete NFL fantasy database for web hosting.
Runs all necessary collection scripts in the correct order.
"""

import os
import sys
import logging
import subprocess
import time
from pathlib import Path

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def run_command(cmd, description):
    """Run a command and log progress."""
    logger = logging.getLogger(__name__)
    logger.info(f"🔄 {description}...")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        if result.returncode == 0:
            logger.info(f"✅ {description} completed")
            return True
        else:
            logger.error(f"❌ {description} failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ {description} error: {e}")
        return False

def deploy_database():
    """Deploy complete database by running all collection scripts."""
    
    logger = logging.getLogger(__name__)
    logger.info("🏈 NFL FANTASY DATABASE DEPLOYMENT")
    logger.info("=" * 50)
    
    start_time = time.time()
    
    # Change to project root directory
    os.chdir(Path(__file__).parent.parent)
    
    # Set environment variable to use production database name
    production_db_path = "data/nfl_data.db"
    os.environ["DB_PATH"] = production_db_path
    logger.info(f"📁 Creating production database: {production_db_path}")
    
    # Step 1: Core data collection (2020-2025)
    success = run_command(
        "START_SEASON=2020 END_SEASON=2025 python3 scripts/collect_data.py",
        "Collecting core NFL data (teams, players, games, stats)"
    )
    if not success:
        logger.error("Failed at core data collection")
        return False
    
    # Step 2: Fix historical schedules  
    success = run_command(
        "python3 scripts/rebuild_historical_schedules.py",
        "Rebuilding historical schedules with team matchups"
    )
    if not success:
        logger.warning("Historical schedules may not display properly")
    
    # Step 2.5: Add playoff games for better fantasy data
    success = run_command(
        "python3 scripts/add_playoff_games.py",
        "Adding playoff games (regular season quality data)"
    )
    if not success:
        logger.warning("Playoff games may not be included")
    
    # Step 3: Collect detailed kicking data
    success = run_command(
        "python3 scripts/collect_kicking_for_deploy.py",
        "Collecting comprehensive kicking data with distances"
    )
    if not success:
        logger.warning("Kicker scoring may not work properly")
    
    # Step 4: Collect team defense (DST) stats for matchup/DST modeling
    success = run_command(
        "python3 scripts/collect_team_defense_stats.py --start 2020 --end 2025",
        "Collecting team defense (DST) stats"
    )
    if not success:
        logger.warning("DST stats may be missing; DST predictions/matchups limited")

    # Step 5: Import historical injury reports (2020+)
    success = run_command(
        "python3 scripts/collect_historical_injuries.py --start 2020 --end 2025",
        "Importing historical injury reports"
    )
    if not success:
        logger.warning("Historical injuries may be missing; historical injury views limited")

    # Step 6: Add duplicate constraints for data integrity
    success = run_command(
        "python3 scripts/add_duplicate_constraints.py",
        "Adding duplicate prevention constraints"
    )
    if not success:
        logger.warning("Duplicate prevention may not be optimal")
    
    # Step 7: Ensure scoring systems exist (schema-aware)
    success = run_command(
        "python3 scripts/add_scoring_systems.py",
        "Ensuring scoring systems are configured"
    )
    if not success:
        logger.warning("Scoring systems may not be configured optimally")
    
    # Final verification
    logger.info("\n📊 Final Database Status:")
    
    import sqlite3
    production_db_name = os.environ.get("DB_PATH", "data/nfl_data.db")
    conn = sqlite3.connect(production_db_name)
    logger.info(f"📁 Verifying production database: {production_db_name}")
    cursor = conn.cursor()
    
    # Count records
    tables_to_check = [
        ('teams', 'Teams'),
        ('players', 'Players'),  
        ('games', 'Games'),
        ('game_stats', 'Player Statistics'),
        ('field_goal_attempts', 'Field Goal Attempts'),
        ('scoring_systems', 'Scoring Systems')
    ]
    
    total_records = 0
    for table, description in tables_to_check:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            logger.info(f"  {description}: {count:,} records")
            total_records += count
        except:
            logger.warning(f"  {description}: Table not found")
    
    conn.close()
    
    elapsed = time.time() - start_time
    logger.info(f"\n🎉 DEPLOYMENT COMPLETE!")
    logger.info(f"   Total records: {total_records:,}")
    logger.info(f"   Setup time: {elapsed/60:.1f} minutes")
    logger.info(f"   Database ready for web hosting!")

def main():
    """Main function with user confirmation."""
    print("🏈 NFL FANTASY DATABASE DEPLOYMENT SCRIPT")
    print("=" * 50)
    print()
    print("This will recreate your complete database including:")
    print("  ✅ NFL teams, players, games (2020-2025)")
    print("  ✅ Player statistics and game data")
    print("  ✅ Historical schedules with scores") 
    print("  ✅ Detailed kicking data (6,700+ field goals)")
    print("  ✅ All 5 scoring systems")
    print("  ✅ Injury reports")
    print()
    print("Estimated time: 15-30 minutes")
    print("Perfect for web hosting deployment!")
    print()
    
    response = input("Deploy complete database? (y/N): ")
    if response.lower() == 'y':
        setup_logging()
        deploy_database()
    else:
        print("Deployment cancelled.")

if __name__ == "__main__":
    main()
