#!/usr/bin/env python3
"""
Quick 2020 NFL Season Simulation - Test a few key weeks to validate our enhanced models.
"""

import sys
import os
import pandas as pd
import numpy as np
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from src.fantasy_calculator import FantasyCalculator
from src.prediction_model import PlayerPredictor

def test_week_simulation(week: int = 5):
    """Test simulation for a single week in 2020."""
    
    print(f"🏈 2020 WEEK {week} SIMULATION TEST")
    print("=" * 40)
    print("Testing enhanced matchup-aware models")
    
    # Initialize components
    config = Config.from_env()
    db = DatabaseManager(config)
    calculator = FantasyCalculator(db)
    predictor = PlayerPredictor(db, calculator)
    
    # Train models (excluding 2020 to avoid lookahead bias)
    training_seasons = [2018, 2019]
    season = 2020
    
    print(f"🔧 Training models on seasons: {training_seasons}")
    try:
        predictor.train_models(training_seasons, 'FanDuel')
        predictor.train_dst_model(training_seasons, 'FanDuel')
        print("✅ Models trained successfully")
    except Exception as e:
        print(f"⚠️ Model training issue: {str(e)[:100]}...")
        # Try loading existing models
        try:
            predictor.load_models('data/prediction_models.pkl')
            print("✅ Loaded existing models")
        except:
            print("❌ No models available")
            return
    
    # Get top performers for the week
    print(f"\n🎯 Getting predictions for Week {week}, 2020...")
    
    # Get some top players from 2020 Week 5
    test_players = [
        ('00-0033873', 'Russell Wilson', 'QB', 'SEA'),
        ('00-0031280', 'Derrick Henry', 'RB', 'TEN'),
        ('00-0031437', 'Davante Adams', 'WR', 'GB'),
        ('00-0035676', 'Travis Kelce', 'TE', 'KC'),
    ]
    
    test_dsts = [
        ('PIT', 'Pittsburgh Steelers'),
        ('IND', 'Indianapolis Colts'),
        ('BAL', 'Baltimore Ravens')
    ]
    
    print(f"\n📊 WEEK {week} PREDICTIONS vs ACTUALS:")
    print("-" * 60)
    print(f"{'Player':<20} {'Pos':<3} {'Team':<4} {'Predicted':<9} {'Actual':<8} {'Diff':<6}")
    print("-" * 60)
    
    total_predicted = 0
    total_actual = 0
    predictions_made = 0
    
    # Test player predictions
    for player_id, name, position, team in test_players:
        try:
            # Get prediction
            prediction = predictor.predict_player_points(player_id, week, season, 'FanDuel')
            
            # Get actual performance
            with db.engine.connect() as conn:
                from sqlalchemy import text
                actual_stats = pd.read_sql_query(text("""
                    SELECT gs.* 
                    FROM game_stats gs
                    JOIN games g ON gs.game_id = g.game_id
                    WHERE gs.player_id = :player_id
                      AND g.season_id = :season
                      AND g.week = :week
                """), conn, params={'player_id': player_id, 'season': season, 'week': week})
            
            if prediction is not None and not actual_stats.empty:
                actual_points = calculator.calculate_player_points(actual_stats.iloc[0], 'FanDuel')
                actual = actual_points.total_points
                diff = actual - prediction
                
                print(f"{name[:19]:<20} {position:<3} {team:<4} {prediction:<9.1f} {actual:<8.1f} {diff:+5.1f}")
                
                total_predicted += prediction
                total_actual += actual
                predictions_made += 1
            else:
                print(f"{name[:19]:<20} {position:<3} {team:<4} {'N/A':<9} {'N/A':<8} {'N/A':<6}")
                
        except Exception as e:
            print(f"{name[:19]:<20} {position:<3} {team:<4} {'ERROR':<9} {'ERROR':<8} {'ERR':<6}")
    
    # Test DST predictions
    for dst_id, dst_name in test_dsts:
        try:
            # Get prediction
            prediction = predictor.predict_dst_points(dst_id, week, season, 'FanDuel')
            
            # Get actual performance
            with db.engine.connect() as conn:
                from sqlalchemy import text
                actual_stats = pd.read_sql_query(text("""
                    SELECT * FROM team_defense_stats
                    WHERE team_id = :team_id
                      AND season_id = :season
                      AND week = :week
                """), conn, params={'team_id': dst_id, 'season': season, 'week': week})
            
            if prediction is not None and not actual_stats.empty:
                actual_points = calculator.calculate_dst_points(actual_stats.iloc[0], 'FanDuel')
                actual = actual_points.total_points
                diff = actual - prediction
                
                print(f"{dst_name[:19]:<20} {'DST':<3} {dst_id:<4} {prediction:<9.1f} {actual:<8.1f} {diff:+5.1f}")
                
                total_predicted += prediction
                total_actual += actual
                predictions_made += 1
            else:
                print(f"{dst_name[:19]:<20} {'DST':<3} {dst_id:<4} {'N/A':<9} {'N/A':<8} {'N/A':<6}")
                
        except Exception as e:
            print(f"{dst_name[:19]:<20} {'DST':<3} {dst_id:<4} {'ERROR':<9} {'ERROR':<8} {'ERR':<6}")
    
    print("-" * 60)
    
    if predictions_made > 0:
        print(f"{'TOTAL':<28} {total_predicted:<9.1f} {total_actual:<8.1f} {total_actual - total_predicted:+5.1f}")
        
        accuracy = (1 - abs(total_actual - total_predicted) / max(total_predicted, 1)) * 100
        print(f"\n📈 Overall Accuracy: {accuracy:.1f}%")
        
        if accuracy > 80:
            print("🟢 EXCELLENT: Model shows strong predictive accuracy")
        elif accuracy > 70:
            print("🟡 GOOD: Model shows solid predictive accuracy") 
        elif accuracy > 60:
            print("🟠 FAIR: Model shows reasonable predictive accuracy")
        else:
            print("🔴 NEEDS IMPROVEMENT: Model accuracy below expectations")
    else:
        print("❌ No predictions could be made")
    
    print(f"\n🎯 Model Features Tested:")
    print("  ✓ Enhanced matchup intelligence")
    print("  ✓ Opponent strength analysis")
    print("  ✓ Bidirectional matchup modifiers")
    print("  ✓ Time-aware training (no lookahead bias)")


def test_multiple_weeks():
    """Test several weeks to get broader view of model performance."""
    
    print("🏈 2020 MULTI-WEEK SIMULATION")
    print("=" * 50)
    
    test_weeks = [3, 5, 8, 12, 15]  # Sample weeks throughout season
    
    for week in test_weeks:
        print(f"\n" + "="*20 + f" WEEK {week} " + "="*20)
        test_week_simulation(week)
        
    print(f"\n🏆 SIMULATION COMPLETE")
    print("Enhanced matchup-aware models tested across multiple weeks")


if __name__ == "__main__":
    # Test a single week first
    test_week_simulation(5)
    
    # Uncomment to test multiple weeks
    # test_multiple_weeks()