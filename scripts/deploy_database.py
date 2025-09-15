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
from datetime import datetime
import json
import platform

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

def _current_year():
    return datetime.now().year


def _safe_scoring_name(name: str) -> str:
    return name.lower().replace(' ', '')


def _train_and_save_models(db_path: str, start_season: int, end_season: int) -> bool:
    """Train models for all scoring systems and save versioned artifacts with CURRENT.json.

    Uses 2020..current season inclusive (caller passes the range). Always includes the current season.
    """
    log = logging.getLogger("deploy.train")

    # Ensure src on sys.path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    try:
        from config import Config
        from database import DatabaseManager
        from fantasy_calculator import FantasyCalculator
        from prediction_model import PlayerPredictor
    except Exception as e:
        log.error("Failed to import training modules: %s", e)
        return False

    # Configure environment for DB
    os.environ.setdefault("DB_PATH", db_path)
    config = Config.from_env()
    db = DatabaseManager(config)

    # Discover scoring systems
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT system_name FROM scoring_systems ORDER BY system_name")
        systems = [row[0] for row in cur.fetchall()] or []
    finally:
        conn.close()
    if not systems:
        log.warning("No scoring systems found; skipping model training")
        return True

    # Determine latest completed game for metadata
    def _db_latest_tuple() -> tuple[int, int]:
        c = sqlite3.connect(db_path)
        try:
            cur = c.cursor()
            cur.execute(
                """
                SELECT season_id, week FROM games
                WHERE home_score IS NOT NULL AND away_score IS NOT NULL
                ORDER BY season_id DESC, week DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                return int(row[0]), int(row[1])
            return (end_season, 1)
        finally:
            c.close()

    last_season, last_week = _db_latest_tuple()

    # Seasons to train on
    seasons = list(range(start_season, end_season + 1))

    for scoring in systems:
        try:
            log.info("Training models for %s using seasons %s..%s", scoring, start_season, end_season)
            calc = FantasyCalculator(db)
            predictor = PlayerPredictor(db, calc)
            predictor.train_models(seasons, scoring)

            # Build paths
            models_dir = Path("data") / "models" / _safe_scoring_name(scoring)
            models_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{_safe_scoring_name(scoring)}_{last_season}_wk{last_week}.pkl"
            model_path = models_dir / filename
            predictor.save_models(str(model_path))

            # Metadata sidecar
            meta = {
                "scoring": scoring,
                "seasons_used": seasons,
                "last_data_season": last_season,
                "last_data_week": last_week,
                "trained_at_utc": datetime.utcnow().isoformat() + "Z",
                "python_version": platform.python_version(),
                "features": {
                    "feature_columns": getattr(predictor, "feature_columns", []),
                    "feature_columns_map": getattr(predictor, "feature_columns_map", {}),
                    "dst_feature_columns": getattr(predictor, "dst_feature_columns", []),
                    "supports_position_features": getattr(predictor, "supports_position_features", False),
                },
            }
            try:
                import sklearn, numpy  # type: ignore
                meta["sklearn_version"] = getattr(sklearn, "__version__", None)
                meta["numpy_version"] = getattr(numpy, "__version__", None)
            except Exception:
                pass

            (model_path.with_suffix('.json')).write_text(json.dumps(meta, indent=2))
            (models_dir / 'CURRENT.json').write_text(json.dumps({"file": filename, "metadata": meta}, indent=2))
            log.info("Saved models for %s -> %s", scoring, model_path)
        except Exception as e:
            log.error("Training failed for %s: %s", scoring, e)
            return False
    return True


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
    
    # Compute season range (2020..current)
    start_season = 2020
    end_season = _current_year()

    # Step 1: Core data collection (2020..current)
    success = run_command(
        f"START_SEASON={start_season} END_SEASON={end_season} python3 scripts/collect_data.py",
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

    # Step 3: Normalize synthetic game IDs to official schedule IDs
    success = run_command(
        f"python3 scripts/normalize_game_ids.py --start {start_season} --end {end_season}",
        "Normalizing synthetic game IDs to official IDs"
    )
    if not success:
        logger.warning("Game ID normalization failed; training joins may be affected")

    # Step 4: Collect detailed kicking data
    success = run_command(
        "python3 scripts/collect_kicking_for_deploy.py",
        "Collecting comprehensive kicking data with distances"
    )
    if not success:
        logger.warning("Kicker scoring may not work properly")

    # Step 5: Collect team defense (DST) stats for matchup/DST modeling
    success = run_command(
        f"python3 scripts/collect_team_defense_stats.py --start {start_season} --end {end_season}",
        "Collecting team defense (DST) stats"
    )
    if not success:
        logger.warning("DST stats may be missing; DST predictions/matchups limited")

    # Step 6: Import historical injury reports (2020+)
    success = run_command(
        f"python3 scripts/collect_historical_injuries.py --start {start_season} --end {end_season}",
        "Importing historical injury reports"
    )
    if not success:
        logger.warning("Historical injuries may be missing; historical injury views limited")

    # Step 7: Add duplicate constraints for data integrity
    success = run_command(
        "python3 scripts/add_duplicate_constraints.py",
        "Adding duplicate prevention constraints"
    )
    if not success:
        logger.warning("Duplicate prevention may not be optimal")
    
    # Step 8: Ensure scoring systems exist (schema-aware)
    success = run_command(
        "python3 scripts/add_scoring_systems.py",
        "Ensuring scoring systems are configured"
    )
    if not success:
        logger.warning("Scoring systems may not be configured optimally")
    
    # Step 9: Train models (2020..current, include current season)
    logger.info("\n🧠 Step 9/9: Training prediction models (includes current season)...")
    if not _train_and_save_models(production_db_path, start_season, end_season):
        logger.warning("Model training failed or incomplete; web app can still train on-demand.")

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
    print(f"  ✅ NFL teams, players, games (2020-{_current_year()})")
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
