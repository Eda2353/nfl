#!/usr/bin/env python3
"""Collect kicking data for deployment - uses DB_PATH environment variable."""

import os
import sqlite3
import nfl_data_py as nfl

# Use environment variable for database path
db_path = os.environ.get("DB_PATH", "data/nfl_data.db")
print(f"Using database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute("""
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
""")

cursor.execute("""
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
""")

conn.commit()

# Collect kicking data for all seasons
seasons = [2020, 2021, 2022, 2023, 2024, 2025]
total_fg = 0
total_ep = 0

for season in seasons:
    print(f"Collecting kicking data for {season}...")
    
    try:
        pbp = nfl.import_pbp_data([season])
        
        # Field goal attempts
        fg_attempts = pbp[pbp['play_type'] == 'field_goal'].copy()
        season_fg = len(fg_attempts)
        
        for _, play in fg_attempts.iterrows():
            cursor.execute("""
                INSERT OR IGNORE INTO field_goal_attempts 
                (game_id, season_id, week, kicker_player_id, kicker_player_name, team_id, kick_distance, result, game_date, quarter, time_remaining)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                play.get('game_id'),
                season,
                play.get('week'),
                play.get('kicker_player_id'),
                play.get('kicker_player_name'),
                play.get('posteam'),
                play.get('kick_distance'),
                play.get('field_goal_result'),
                play.get('game_date'),
                play.get('qtr'),
                play.get('time')
            ))
        
        # Extra point attempts  
        ep_attempts = pbp[pbp['extra_point_attempt'] == 1].copy()
        season_ep = len(ep_attempts)
        
        for _, play in ep_attempts.iterrows():
            cursor.execute("""
                INSERT OR IGNORE INTO extra_point_attempts 
                (game_id, season_id, week, kicker_player_id, kicker_player_name, team_id, result, game_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                play.get('game_id'),
                season,
                play.get('week'),
                play.get('kicker_player_id'),
                play.get('kicker_player_name'),
                play.get('posteam'),
                play.get('extra_point_result'),
                play.get('game_date')
            ))
        
        conn.commit()
        print(f"  Completed {season}: {season_fg} FGs, {season_ep} EPs")
        total_fg += season_fg
        total_ep += season_ep
        
    except Exception as e:
        print(f"  Error with {season}: {e}")

print(f"\nTotal collected: {total_fg} field goals, {total_ep} extra points")
conn.close()