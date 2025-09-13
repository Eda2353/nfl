#!/usr/bin/env python3
"""
Weekly Enhanced Position-Specific Simulation
Draft optimal teams each week and track enhanced model performance
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from src.fantasy_calculator import FantasyCalculator
from src.prediction_model import PlayerPredictor
from src.position_matchup_analyzer import PositionMatchupAnalyzer
from sqlalchemy import text

def get_optimal_lineup_for_week(db, predictor, calculator, week, season, scoring_system):
    """Get optimal lineup for a specific week using enhanced predictions."""
    
    with db.engine.connect() as conn:
        # Get all available players for this week
        available_players = pd.read_sql_query(text("""
            SELECT DISTINCT p.player_id, p.player_name, p.position
            FROM players p
            JOIN game_stats gs ON p.player_id = gs.player_id
            JOIN games g ON gs.game_id = g.game_id
            WHERE g.season_id = :season AND g.week = :week
              AND p.position IN ('QB', 'RB', 'WR', 'TE')
        """), conn, params={'season': season, 'week': week})
    
    # Get enhanced predictions for all available players
    predictions = []
    
    for _, player in available_players.iterrows():
        try:
            predicted_points = predictor.predict_player_points(
                player['player_id'], week, season, scoring_system
            )
            
            if predicted_points is not None and predicted_points > 0:
                predictions.append({
                    'player_id': player['player_id'],
                    'player_name': player['player_name'],
                    'position': player['position'],
                    'predicted_points': predicted_points
                })
        except Exception:
            continue
    
    if not predictions:
        return None
    
    predictions_df = pd.DataFrame(predictions)
    
    # Draft optimal lineup (top performers by position)
    optimal_lineup = {}
    
    for position in ['QB', 'RB', 'WR', 'TE']:
        pos_players = predictions_df[predictions_df['position'] == position]
        if len(pos_players) > 0:
            if position == 'RB':
                # Draft top 2 RBs
                top_players = pos_players.nlargest(2, 'predicted_points')
            elif position == 'WR':
                # Draft top 3 WRs  
                top_players = pos_players.nlargest(3, 'predicted_points')
            else:
                # Draft top 1 QB, TE
                top_players = pos_players.nlargest(1, 'predicted_points')
            
            optimal_lineup[position] = top_players.to_dict('records')
    
    # Add DST prediction (simplified)
    with db.engine.connect() as conn:
        dst_teams = pd.read_sql_query(text("""
            SELECT DISTINCT team_id
            FROM team_defense_stats tds
            JOIN games g ON tds.game_id = g.game_id
            WHERE g.season_id = :season AND g.week = :week
        """), conn, params={'season': season, 'week': week})
    
    if len(dst_teams) > 0:
        # Pick a representative DST (simplified for this demo)
        dst_team = dst_teams.iloc[0]['team_id']
        try:
            dst_prediction = predictor.predict_dst_points(dst_team, week, season, scoring_system)
            if dst_prediction is not None:
                optimal_lineup['DST'] = [{'team_id': dst_team, 'predicted_points': dst_prediction}]
        except Exception:
            pass
    
    return optimal_lineup

def get_actual_performance(db, lineup, week, season, scoring_system):
    """Get actual performance for the drafted lineup."""
    
    actual_results = {}
    
    with db.engine.connect() as conn:
        for position, players in lineup.items():
            actual_results[position] = []
            
            if position == 'DST':
                for dst in players:
                    try:
                        actual_points = conn.execute(text("""
                            SELECT SUM(
                                CASE 
                                    WHEN tds.points_allowed = 0 THEN 10
                                    WHEN tds.points_allowed BETWEEN 1 AND 6 THEN 7
                                    WHEN tds.points_allowed BETWEEN 7 AND 13 THEN 4
                                    WHEN tds.points_allowed BETWEEN 14 AND 20 THEN 1
                                    WHEN tds.points_allowed BETWEEN 21 AND 27 THEN 0
                                    WHEN tds.points_allowed BETWEEN 28 AND 34 THEN -1
                                    ELSE -4
                                END +
                                tds.interceptions * 2 +
                                tds.fumbles_recovered * 2 +
                                tds.sacks * 1 +
                                tds.defensive_touchdowns * 6 +
                                tds.safeties * 2
                            ) as fantasy_points
                            FROM team_defense_stats tds
                            JOIN games g ON tds.game_id = g.game_id
                            WHERE tds.team_id = :team_id 
                              AND g.season_id = :season 
                              AND g.week = :week
                        """), {'team_id': dst['team_id'], 'season': season, 'week': week}).fetchone()
                        
                        if actual_points and actual_points[0]:
                            actual_results[position].append({
                                'team_id': dst['team_id'],
                                'predicted_points': dst['predicted_points'],
                                'actual_points': float(actual_points[0])
                            })
                    except Exception:
                        continue
            else:
                for player in players:
                    try:
                        actual_points = conn.execute(text("""
                            SELECT fantasy_points
                            FROM fantasy_points fp
                            JOIN games g ON fp.game_id = g.game_id
                            WHERE fp.player_id = :player_id 
                              AND g.season_id = :season 
                              AND g.week = :week
                              AND fp.system_id = 1
                        """), {'player_id': player['player_id'], 'season': season, 'week': week}).fetchone()
                        
                        if actual_points:
                            actual_results[position].append({
                                'player_id': player['player_id'],
                                'player_name': player['player_name'],
                                'predicted_points': player['predicted_points'],
                                'actual_points': float(actual_points[0])
                            })
                    except Exception:
                        continue
    
    return actual_results

def run_weekly_enhanced_simulation():
    """Run week-by-week enhanced simulation with detailed results table."""
    
    print("📅 WEEKLY ENHANCED POSITION-SPECIFIC SIMULATION")
    print("=" * 80)
    print("Drafting optimal lineups each week using enhanced models")
    
    # Initialize enhanced system
    config = Config.from_env()
    db = DatabaseManager(config)
    calculator = FantasyCalculator(db)
    predictor = PlayerPredictor(db, calculator)
    
    # Train enhanced models
    print("\n🧠 Training Enhanced Models...")
    training_seasons = [2018, 2019]
    predictor.train_models(training_seasons, 'FanDuel')
    print("✅ Enhanced models trained")
    
    # Simulate weeks 1-17 of 2020 season
    weeks_to_simulate = range(1, 18)
    season = 2020
    weekly_results = []
    
    print(f"\n📊 2020 Season Week-by-Week Results:")
    print("=" * 120)
    
    # Header
    print(f"{'Week':<4} {'Position':<8} {'Player/Team':<25} {'Predicted':<10} {'Actual':<8} {'Diff':<8} {'Diff%':<8}")
    print("-" * 120)
    
    for week in weeks_to_simulate:
        print(f"\n📅 WEEK {week}")
        print("-" * 40)
        
        # Draft optimal lineup
        optimal_lineup = get_optimal_lineup_for_week(db, predictor, calculator, week, season, 'FanDuel')
        
        if not optimal_lineup:
            print(f"Week {week:2d}: No data available")
            continue
        
        # Get actual performance
        actual_results = get_actual_performance(db, optimal_lineup, week, season, 'FanDuel')
        
        # Calculate week totals
        week_predicted_total = 0
        week_actual_total = 0
        week_details = []
        
        for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
            if position in actual_results and actual_results[position]:
                for player_result in actual_results[position]:
                    predicted = player_result['predicted_points']
                    actual = player_result['actual_points']
                    diff = actual - predicted
                    diff_pct = (diff / predicted * 100) if predicted > 0 else 0
                    
                    week_predicted_total += predicted
                    week_actual_total += actual
                    
                    # Player name
                    if position == 'DST':
                        name = f"{player_result['team_id']} DST"
                    else:
                        name = player_result['player_name']
                    
                    week_details.append({
                        'week': week,
                        'position': position,
                        'name': name,
                        'predicted': predicted,
                        'actual': actual,
                        'diff': diff,
                        'diff_pct': diff_pct
                    })
                    
                    print(f"{week:2d}   {position:<8} {name:<25} {predicted:8.1f}  {actual:6.1f}  {diff:+6.1f}  {diff_pct:+6.1f}%")
        
        # Week summary
        if week_details:
            week_diff = week_actual_total - week_predicted_total
            week_diff_pct = (week_diff / week_predicted_total * 100) if week_predicted_total > 0 else 0
            
            weekly_results.append({
                'week': week,
                'predicted_total': week_predicted_total,
                'actual_total': week_actual_total,
                'diff': week_diff,
                'diff_pct': week_diff_pct,
                'players': len(week_details)
            })
            
            print(f"{'':<4} {'TOTAL':<8} {'Week ' + str(week) + ' Team':<25} {week_predicted_total:8.1f}  {week_actual_total:6.1f}  {week_diff:+6.1f}  {week_diff_pct:+6.1f}%")
        else:
            print(f"Week {week:2d}: No complete lineup data available")
    
    # Season summary
    print("\n" + "=" * 120)
    print("📊 SEASON SUMMARY - ENHANCED POSITION-SPECIFIC MODELS")
    print("=" * 120)
    
    if weekly_results:
        total_predicted = sum([w['predicted_total'] for w in weekly_results])
        total_actual = sum([w['actual_total'] for w in weekly_results])
        total_diff = total_actual - total_predicted
        total_diff_pct = (total_diff / total_predicted * 100) if total_predicted > 0 else 0
        
        print(f"\n🏆 ENHANCED SYSTEM PERFORMANCE:")
        print(f"  📅 Weeks Simulated: {len(weekly_results)}")
        print(f"  📈 Total Predicted: {total_predicted:.1f} points")
        print(f"  📊 Total Actual: {total_actual:.1f} points")
        print(f"  📉 Total Difference: {total_diff:+.1f} points")
        print(f"  📊 Accuracy: {100 - abs(total_diff_pct):.1f}%")
        print(f"  📈 Average Weekly Predicted: {total_predicted/len(weekly_results):.1f} points")
        print(f"  📊 Average Weekly Actual: {total_actual/len(weekly_results):.1f} points")
        
        # Best and worst weeks
        best_week = max(weekly_results, key=lambda x: x['actual_total'] if x['actual_total'] > 0 else 0)
        worst_week = min(weekly_results, key=lambda x: x['actual_total'] if x['actual_total'] > 0 else float('inf'))
        
        print(f"\n🏆 Best Week: Week {best_week['week']} ({best_week['actual_total']:.1f} points)")
        print(f"⚠️  Challenging Week: Week {worst_week['week']} ({worst_week['actual_total']:.1f} points)")
        
        print(f"\n📈 Enhanced Model Features Successfully Applied:")
        print(f"  • Position-specific matchup intelligence")  
        print(f"  • QB vs pass defense targeting")
        print(f"  • RB vs rush defense + receiving opportunities")
        print(f"  • WR vs coverage weakness analysis") 
        print(f"  • TE vs middle coverage + red zone targeting")
        
    else:
        print("⚠️ No complete weekly results available for analysis")
    
    print(f"\n🎯 Enhanced position-specific system simulation complete!")


if __name__ == "__main__":
    run_weekly_enhanced_simulation()