#!/usr/bin/env python3
"""Check what kicking data is available from NFL sources."""

import nfl_data_py as nfl
import pandas as pd

print("Checking available NFL data sources for kicking stats...")

# Check play-by-play data for field goal info
print("\n1. Play-by-Play Data (contains individual plays):")
try:
    pbp = nfl.import_pbp_data([2023])
    print(f"Found {len(pbp)} total plays")
    
    # Check available columns first
    pbp_columns = pbp.columns.tolist()
    kicking_cols = [col for col in pbp_columns if any(term in col.lower() for term in ['kick', 'field', 'goal', 'extra', 'distance'])]
    print(f"Kicking-related columns: {kicking_cols}")
    
    # Filter to field goal attempts
    if 'play_type' in pbp.columns:
        fg_plays = pbp[pbp['play_type'] == 'field_goal']
        print(f"Found {len(fg_plays)} field goal attempts")
        
        if not fg_plays.empty and 'kick_distance' in fg_plays.columns:
            print("\nSample field goal data:")
            sample_cols = ['kicker_player_name', 'kick_distance', 'field_goal_result'] 
            available_cols = [col for col in sample_cols if col in fg_plays.columns]
            if available_cols:
                print(fg_plays[available_cols].head())
    
except Exception as e:
    print(f"Error getting PBP data: {e}")

# Check weekly kicking stats
print("\n2. Weekly Stats Data:")
try:
    weekly = nfl.import_weekly_data([2023])
    print(f"Found {len(weekly)} total weekly records")
    
    # Check all available columns
    weekly_columns = weekly.columns.tolist()
    kicking_cols = [col for col in weekly_columns if any(term in col.lower() for term in ['kick', 'field', 'extra', 'pat', 'fg'])]
    print(f"Kicking-related columns: {kicking_cols}")
    
    kickers = weekly[weekly['position'] == 'K']
    print(f"Found {len(kickers)} kicker weekly records")
    
    if not kickers.empty and kicking_cols:
        print(f"\nSample kicker data:")
        display_cols = ['player_display_name'] + kicking_cols[:5]  # Limit columns
        available_cols = [col for col in display_cols if col in kickers.columns]
        if available_cols:
            print(kickers[available_cols].head())
    
except Exception as e:
    print(f"Error getting weekly data: {e}")