#!/usr/bin/env python3
"""Collect historical kicking data from NFL play-by-play 2020-2023."""

import sys
from pathlib import Path
import nfl_data_py as nfl
import pandas as pd
import sqlite3

def collect_historical_kicks():
    """Collect field goal and extra point data with distances."""
    
    conn = sqlite3.connect('data/nfl_data.db')
    
    seasons = [2024, 2025]  # Just collect the missing current seasons
    
    for season in seasons:
        print(f"Collecting kicking data for {season}...")
        
        try:
            # Get play-by-play data
            pbp = nfl.import_pbp_data([season])
            print(f"Loaded {len(pbp)} plays")
            
            # Field goal attempts
            fg_attempts = pbp[pbp['play_type'] == 'field_goal'].copy()
            print(f"Found {len(fg_attempts)} field goal attempts")
            
            for _, play in fg_attempts.iterrows():
                conn.execute("""
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
            print(f"Found {len(ep_attempts)} extra point attempts")
            
            for _, play in ep_attempts.iterrows():
                conn.execute("""
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
            print(f"Completed {season}")
            
        except Exception as e:
            print(f"Error with {season}: {e}")
            continue
    
    # Show summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM field_goal_attempts")
    fg_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM extra_point_attempts") 
    ep_count = cursor.fetchone()[0]
    
    print(f"\nSummary:")
    print(f"Total field goals: {fg_count}")
    print(f"Total extra points: {ep_count}")
    
    # Sample data
    cursor.execute("SELECT kicker_player_name, kick_distance, result FROM field_goal_attempts WHERE kick_distance > 50 ORDER BY kick_distance DESC LIMIT 5")
    long_fgs = cursor.fetchall()
    print(f"\nLongest field goals:")
    for fg in long_fgs:
        print(f"  {fg[0]}: {fg[1]} yards - {fg[2]}")
    
    conn.close()

if __name__ == "__main__":
    collect_historical_kicks()