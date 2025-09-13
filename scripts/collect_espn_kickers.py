#!/usr/bin/env python3
"""Collect comprehensive kicker data from ESPN Fantasy API for 2020-2025."""

import requests
import json
import sqlite3
import logging
from datetime import datetime

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def collect_espn_kicker_data():
    """Collect kicker stats from ESPN Fantasy API for all seasons 2020-2025."""
    
    logger = setup_logging()
    
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    # Create table for ESPN kicker stats  
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS espn_kicker_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id VARCHAR(20),
            player_name VARCHAR(100),
            season INTEGER,
            team VARCHAR(10),
            games_played INTEGER,
            fg_made INTEGER,
            fg_attempted INTEGER,
            fg_pct REAL,
            fg_long INTEGER,
            fg_0_39_made INTEGER,
            fg_40_49_made INTEGER,
            fg_50_plus_made INTEGER,
            fg_0_39_att INTEGER,
            fg_40_49_att INTEGER,
            fg_50_plus_att INTEGER,
            extra_points_made INTEGER,
            extra_points_att INTEGER,
            total_points INTEGER,
            data_source VARCHAR(20) DEFAULT 'ESPN'
        )
    """)
    
    seasons = [2020, 2021, 2022, 2023, 2024, 2025]
    
    for season in seasons:
        logger.info(f"Collecting ESPN kicker data for {season}...")
        
        try:
            # ESPN Fantasy API endpoint
            url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            params = {
                'view': 'players_wl',
                'limit': 2000,
                'filter': '{"filterSlotIds":[17]}',  # Filter for kickers (slot ID 17)
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                players = data.get('players', [])
                
                kicker_count = 0
                
                for player in players:
                    if player.get('player', {}).get('defaultPositionId') == 5:  # Kicker position ID
                        
                        player_info = player.get('player', {})
                        stats = player.get('player', {}).get('stats', [])
                        
                        # Find season stats
                        season_stats = None
                        for stat_period in stats:
                            if stat_period.get('seasonId') == season:
                                season_stats = stat_period.get('stats', {})
                                break
                        
                        if season_stats:
                            player_name = player_info.get('fullName', 'Unknown')
                            player_id = str(player_info.get('id', ''))
                            team = player_info.get('proTeamId', '')
                            
                            # Extract kicking stats (ESPN stat IDs for kickers)
                            fg_made = season_stats.get('120', 0)  # Field goals made
                            fg_att = season_stats.get('121', 0)   # Field goals attempted  
                            fg_long = season_stats.get('122', 0)  # Longest field goal
                            fg_50_plus = season_stats.get('123', 0)  # 50+ yard FGs made
                            extra_points = season_stats.get('124', 0)  # Extra points made
                            total_points = season_stats.get('125', 0)  # Total kicking points
                            
                            # Insert into database
                            cursor.execute("""
                                INSERT OR REPLACE INTO espn_kicker_stats 
                                (player_id, player_name, season, team, fg_made, fg_attempted, 
                                 fg_long, fg_50_plus_made, extra_points_made, total_points)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                player_id, player_name, season, team, fg_made, fg_att,
                                fg_long, fg_50_plus, extra_points, total_points
                            ))
                            
                            kicker_count += 1
                
                conn.commit()
                logger.info(f"Collected {kicker_count} kickers for {season}")
                
            else:
                logger.warning(f"Failed to get {season} data: HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error collecting {season} data: {e}")
            continue
    
    # Show summary
    cursor.execute("SELECT COUNT(*) FROM espn_kicker_stats")
    total_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT season, COUNT(*) FROM espn_kicker_stats GROUP BY season ORDER BY season")
    by_season = cursor.fetchall()
    
    logger.info(f"Collection completed: {total_records} total kicker records")
    for season, count in by_season:
        logger.info(f"  {season}: {count} kickers")
    
    # Show sample long field goals
    cursor.execute("""
        SELECT player_name, season, fg_long, fg_50_plus_made 
        FROM espn_kicker_stats 
        WHERE fg_long > 50 
        ORDER BY fg_long DESC 
        LIMIT 10
    """)
    long_kickers = cursor.fetchall()
    
    logger.info("Top long field goal kickers:")
    for name, season, longest, made_50_plus in long_kickers:
        logger.info(f"  {name} ({season}): {longest} yard long, {made_50_plus} made 50+")
    
    conn.close()

if __name__ == "__main__":
    collect_espn_kicker_data()