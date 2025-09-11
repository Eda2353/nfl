#!/usr/bin/env python3
"""
Check 2020 season data availability
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from sqlalchemy import text

def check_2020_data():
    config = Config.from_env()
    db = DatabaseManager(config)

    with db.engine.connect() as conn:
        # Check 2020 data availability
        result = conn.execute(text('''
            SELECT g.week, COUNT(*) as games, COUNT(DISTINCT p.player_id) as players,
                   AVG(fp.fantasy_points) as avg_points, MAX(fp.fantasy_points) as max_points
            FROM games g
            JOIN game_stats gs ON g.game_id = gs.game_id
            JOIN players p ON gs.player_id = p.player_id
            JOIN fantasy_points fp ON gs.player_id = fp.player_id AND gs.game_id = fp.game_id
            WHERE g.season_id = 2020 AND g.week IN (1, 5, 10, 15)
              AND p.position IN ('QB', 'RB', 'WR', 'TE')
              AND fp.fantasy_points >= 10
              AND fp.system_id = 1
            GROUP BY g.week ORDER BY g.week
        '''))
        
        print('2020 Season Data Check:')
        for row in result:
            print(f'Week {row.week}: {row.games} games, {row.players} players with 10+ points, avg: {row.avg_points:.1f}, max: {row.max_points:.1f}')

        # Also check top performers
        top_performers = conn.execute(text('''
            SELECT p.player_name, p.position, fp.fantasy_points, g.week
            FROM games g
            JOIN game_stats gs ON g.game_id = gs.game_id
            JOIN players p ON gs.player_id = p.player_id
            JOIN fantasy_points fp ON gs.player_id = fp.player_id AND gs.game_id = fp.game_id
            WHERE g.season_id = 2020 AND g.week = 1
              AND p.position IN ('QB', 'RB', 'WR', 'TE')
              AND fp.system_id = 1
            ORDER BY fp.fantasy_points DESC
            LIMIT 10
        '''))
        
        print('\nTop Week 1 2020 Performers:')
        for row in top_performers:
            print(f'{row.player_name} ({row.position}): {row.fantasy_points:.1f} points')

if __name__ == "__main__":
    check_2020_data()