#!/usr/bin/env python3
"""Add playoff games to the database - they're fantasy-relevant unlike preseason."""

import os
import sqlite3
import nfl_data_py as nfl
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def add_playoff_games():
    """Add playoff games to database for more complete fantasy data."""
    
    logger = setup_logging()
    
    # Use environment variable for database path
    db_path = os.environ.get("DB_PATH", "data/nfl_data.db")
    logger.info(f"Adding playoff games to: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check initial counts
        cursor.execute("SELECT COUNT(*) FROM games")
        initial_count = cursor.fetchone()[0]
        logger.info(f"Before adding playoffs: {initial_count} games")
        
        seasons = [2020, 2021, 2022, 2023, 2024, 2025]
        total_added = 0
        
        for season in seasons:
            logger.info(f"🏆 Collecting playoff games for {season}...")
            
            try:
                # Get all schedules including playoffs
                schedules = nfl.import_schedules([season])
                playoff_games = schedules[schedules['game_type'].isin(['WC', 'DIV', 'CON', 'SB'])]  # All playoff types
                
                logger.info(f"Found {len(playoff_games)} playoff games for {season}")
                
                season_added = 0
                for _, game in playoff_games.iterrows():
                    # Check if game already exists
                    cursor.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (game['game_id'],))
                    exists = cursor.fetchone()[0] > 0
                    
                    if not exists:
                        cursor.execute("""
                            INSERT INTO games 
                            (game_id, season_id, week, game_date, home_team_id, away_team_id, 
                             home_score, away_score, weather_conditions, temperature, wind_speed, is_dome, game_time)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            game['game_id'],
                            season,
                            game['week'],
                            game['gameday'],
                            game['home_team'],
                            game['away_team'],
                            game.get('home_score'),
                            game.get('away_score'),
                            None,  # weather_conditions
                            game.get('temp'),
                            game.get('wind'),
                            None,  # is_dome
                            game.get('gametime')
                        ))
                        season_added += 1
                
                conn.commit()
                total_added += season_added
                logger.info(f"✅ Added {season_added} playoff games for {season}")
                
            except Exception as e:
                logger.warning(f"Could not collect playoffs for {season}: {e}")
                continue
        
        # Final count
        cursor.execute("SELECT COUNT(*) FROM games")
        final_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT season_id, COUNT(*) FROM games GROUP BY season_id ORDER BY season_id")
        final_by_season = cursor.fetchall()
        
        logger.info(f"\n📊 Playoff Addition Results:")
        logger.info(f"  Total games: {initial_count} → {final_count} (+{total_added})")
        
        logger.info(f"\n📅 Games by Season (Regular + Playoffs):")
        for season, count in final_by_season:
            logger.info(f"  {season}: {count} games")
        
        logger.info("🏆 Database now includes playoff games for better fantasy data!")
        
    except Exception as e:
        logger.error(f"❌ Error adding playoffs: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_playoff_games()