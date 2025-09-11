#!/usr/bin/env python3
"""Test script for the fantasy calculator."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from fantasy_calculator import FantasyCalculator

def main():
    """Test the fantasy calculator with real data."""
    
    # Initialize
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    
    print("=== FANTASY CALCULATOR TEST ===")
    print(f"Available scoring systems: {list(calculator.scoring_systems.keys())}")
    
    # Test 1: Compare FanDuel vs DraftKings for 2023 top performers
    print("\n=== TOP 10 QUARTERBACKS 2023 (FanDuel vs DraftKings) ===")
    
    for system in ['FanDuel', 'DraftKings']:
        print(f"\n{system} Scoring:")
        top_qbs = calculator.calculate_top_performers(
            scoring_system=system, 
            season=2023, 
            position='QB', 
            min_games=10
        )
        
        if not top_qbs.empty:
            print(top_qbs[['player_name', 'games_played', 'total_fantasy_points', 'avg_fantasy_points']].head(5))
    
    # Test 2: Weekly rankings for a specific week
    print("\n=== WEEK 1, 2023 TOP PERFORMERS (All Positions, FanDuel) ===")
    week1_2023 = calculator.get_weekly_rankings(
        week=1, 
        season=2023, 
        scoring_system='FanDuel', 
        limit=10
    )
    
    if not week1_2023.empty:
        print(week1_2023[['player_name', 'position', 'team', 'fantasy_points']])
    
    # Test 3: Season comparison for a specific player
    print("\n=== PLAYER COMPARISON: FanDuel vs DraftKings (2023) ===")
    
    # Find a high-scoring player from 2023
    top_players = calculator.calculate_top_performers('FanDuel', 2023, min_games=10)
    if not top_players.empty:
        top_player_id = top_players.iloc[0]['player_id']
        comparison = calculator.compare_scoring_systems(top_player_id, 2023)
        
        if not comparison.empty:
            print(comparison[['player_name', 'position', 'scoring_system', 'total_points', 'avg_points_per_game']])
    
    # Test 4: Show scoring system differences
    print("\n=== SCORING SYSTEM DIFFERENCES ===")
    print("FanDuel: Half PPR (0.5 per catch), -2 for fumbles")
    print("DraftKings: Full PPR (1.0 per catch), -1 for fumbles")
    print("Both: +3 bonus for 100+ rush/rec yards, +3 bonus for 300+ pass yards")

if __name__ == "__main__":
    main()