#!/usr/bin/env python3
"""
2020 NFL Season Simulation - Draft optimal teams each week and track performance.
Tests our enhanced matchup-aware prediction models against actual results.
"""

import sys
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from src.fantasy_calculator import FantasyCalculator
from src.prediction_model import PlayerPredictor
class Season2020Simulator:
    """Simulate the entire 2020 NFL season with weekly optimal team drafts."""
    
    def __init__(self):
        self.config = Config.from_env()
        self.db = DatabaseManager(self.config)
        self.calculator = FantasyCalculator(self.db)
        self.predictor = PlayerPredictor(self.db, self.calculator)
        
        # Load or train models (excluding 2020 data to avoid lookahead bias)
        self.training_seasons = [2018, 2019]  # Only use data before 2020
        self.simulation_season = 2020
        self.weeks_to_simulate = list(range(1, 18))  # NFL regular season weeks
        
        # Results storage
        self.weekly_results = []
        
    def prepare_models_for_simulation(self):
        """Train models using only data before 2020 to avoid lookahead bias."""
        print("🔧 Preparing models for 2020 simulation...")
        print(f"Training on seasons: {self.training_seasons}")
        
        # Train player models
        self.predictor.train_models(self.training_seasons, 'FanDuel')
        
        # Train DST model
        self.predictor.train_dst_model(self.training_seasons, 'FanDuel')
        
        print("✅ Models trained and ready for simulation")
    
    def get_available_players(self, week: int) -> pd.DataFrame:
        """Get all players who played in the given week of 2020."""
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            players = pd.read_sql_query(text("""
                SELECT DISTINCT p.player_id, p.player_name, p.position,
                       gs.team_id
                FROM players p
                JOIN game_stats gs ON p.player_id = gs.player_id
                JOIN games g ON gs.game_id = g.game_id
                WHERE g.season_id = :season
                  AND g.week = :week
                  AND p.position IN ('QB', 'RB', 'WR', 'TE')
                ORDER BY p.position, p.player_name
            """), conn, params={'season': self.simulation_season, 'week': week})
        return players
    
    def get_available_dsts(self, week: int) -> pd.DataFrame:
        """Get all DSTs that played in the given week of 2020."""
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            dsts = pd.read_sql_query(text("""
                SELECT DISTINCT tds.team_id, t.team_name
                FROM team_defense_stats tds
                JOIN teams t ON tds.team_id = t.team_id
                WHERE tds.season_id = :season
                  AND tds.week = :week
                ORDER BY tds.team_id
            """), conn, params={'season': self.simulation_season, 'week': week})
        return dsts
    
    def get_player_projections(self, week: int) -> List[Dict]:
        """Get model projections for all available players in given week."""
        print(f"  📊 Generating player projections for Week {week}...")
        
        available_players = self.get_available_players(week)
        projections = []
        
        for _, player in available_players.iterrows():
            prediction = self.predictor.predict_player_points(
                player['player_id'], week, self.simulation_season, 'FanDuel'
            )
            
            if prediction is not None and prediction > 0:
                projections.append({
                    'player_id': player['player_id'],
                    'name': player['player_name'],
                    'position': player['position'],
                    'team': player['team_id'],
                    'projected_points': prediction,
                    'salary': self.estimate_salary(player['position'], prediction)
                })
        
        print(f"    ✓ Generated {len(projections)} player projections")
        return projections
    
    def get_dst_projections(self, week: int) -> List[Dict]:
        """Get model projections for all available DSTs in given week."""
        print(f"  🛡️ Generating DST projections for Week {week}...")
        
        available_dsts = self.get_available_dsts(week)
        projections = []
        
        for _, dst in available_dsts.iterrows():
            prediction = self.predictor.predict_dst_points(
                dst['team_id'], week, self.simulation_season, 'FanDuel'
            )
            
            if prediction is not None:
                projections.append({
                    'player_id': f"DST_{dst['team_id']}",
                    'name': f"{dst['team_name']} DST",
                    'position': 'DST',
                    'team': dst['team_id'],
                    'projected_points': prediction,
                    'salary': self.estimate_dst_salary(prediction)
                })
        
        print(f"    ✓ Generated {len(projections)} DST projections")
        return projections
    
    def estimate_salary(self, position: str, projected_points: float) -> int:
        """Estimate realistic DraftKings salary based on position and projection."""
        # Rough salary estimates based on typical DraftKings pricing
        base_salaries = {'QB': 5500, 'RB': 5000, 'WR': 4500, 'TE': 3500}
        base = base_salaries.get(position, 4000)
        
        # Adjust based on projection (higher projection = higher salary)
        if projected_points > 20:
            multiplier = 1.4
        elif projected_points > 15:
            multiplier = 1.2
        elif projected_points > 10:
            multiplier = 1.0
        elif projected_points > 5:
            multiplier = 0.8
        else:
            multiplier = 0.6
            
        return int(base * multiplier / 100) * 100  # Round to nearest 100
    
    def estimate_dst_salary(self, projected_points: float) -> int:
        """Estimate DST salary based on projection."""
        base = 2500
        if projected_points > 10:
            multiplier = 1.3
        elif projected_points > 7:
            multiplier = 1.1
        elif projected_points > 4:
            multiplier = 1.0
        else:
            multiplier = 0.8
        return int(base * multiplier / 100) * 100
    
    def draft_optimal_lineup(self, week: int) -> Optional[Dict]:
        """Draft the optimal lineup for given week using our model projections."""
        print(f"🏈 Drafting optimal lineup for Week {week}...")
        
        # Get projections
        player_projections = self.get_player_projections(week)
        dst_projections = self.get_dst_projections(week)
        all_projections = player_projections + dst_projections
        
        if len(all_projections) < 8:  # Need minimum players for lineup
            print(f"  ⚠️ Insufficient projections for Week {week}")
            return None
        
        # Use simplified greedy optimizer for this simulation
        lineup = self.select_optimal_lineup_greedy(all_projections)
        
        if lineup:
            total_projected = sum(p['projected_points'] for p in lineup)
            total_salary = sum(p['salary'] for p in lineup)
            print(f"  ✅ Optimal lineup drafted: {total_projected:.1f} projected points, ${total_salary:,} salary")
        
        return lineup
    
    def select_optimal_lineup_greedy(self, projections: List[Dict]) -> List[Dict]:
        """Simple greedy lineup selection for simulation."""
        # Sort by value (points per $1000 salary)
        for p in projections:
            p['value'] = p['projected_points'] / (p['salary'] / 1000) if p['salary'] > 0 else 0
        
        projections.sort(key=lambda x: x['value'], reverse=True)
        
        # Required positions for lineup
        position_requirements = {
            'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'DST': 1
        }
        
        lineup = []
        position_filled = {pos: 0 for pos in position_requirements}
        
        # Fill required positions with best value players
        for projection in projections:
            pos = projection['position']
            if pos in position_requirements and position_filled[pos] < position_requirements[pos]:
                lineup.append(projection)
                position_filled[pos] += 1
                
                if len(lineup) == 8:  # Complete lineup
                    break
        
        return lineup if len(lineup) == 8 else []
    
    def get_actual_results(self, lineup: List[Dict], week: int) -> List[Dict]:
        """Get actual fantasy points for the drafted lineup."""
        actual_results = []
        
        for player in lineup:
            if player['position'] == 'DST':
                # DST actual points
                team_id = player['team']
                with self.db.engine.connect() as conn:
                    from sqlalchemy import text
                    dst_stats = pd.read_sql_query(text("""
                        SELECT * FROM team_defense_stats
                        WHERE team_id = :team_id
                          AND season_id = :season
                          AND week = :week
                    """), conn, params={'team_id': team_id, 'season': self.simulation_season, 'week': week})
                
                if not dst_stats.empty:
                    actual_points = self.calculator.calculate_dst_points(dst_stats.iloc[0], 'FanDuel')
                    actual_results.append({
                        **player,
                        'actual_points': actual_points.total_points
                    })
            else:
                # Player actual points
                player_id = player['player_id']
                with self.db.engine.connect() as conn:
                    from sqlalchemy import text
                    player_stats = pd.read_sql_query(text("""
                        SELECT gs.* 
                        FROM game_stats gs
                        JOIN games g ON gs.game_id = g.game_id
                        WHERE gs.player_id = :player_id
                          AND g.season_id = :season
                          AND g.week = :week
                    """), conn, params={'player_id': player_id, 'season': self.simulation_season, 'week': week})
                
                if not player_stats.empty:
                    actual_points = self.calculator.calculate_player_points(player_stats.iloc[0], 'FanDuel')
                    actual_results.append({
                        **player,
                        'actual_points': actual_points.total_points
                    })
        
        return actual_results
    
    def simulate_week(self, week: int) -> Dict:
        """Simulate a complete week: draft lineup and get actual results."""
        print(f"\n🗓️ WEEK {week} SIMULATION")
        print("=" * 40)
        
        # Draft optimal lineup
        lineup = self.draft_optimal_lineup(week)
        if not lineup:
            return {'week': week, 'success': False, 'reason': 'Could not draft lineup'}
        
        # Get actual results
        actual_results = self.get_actual_results(lineup, week)
        
        # Calculate performance
        total_projected = sum(p['projected_points'] for p in lineup)
        total_actual = sum(p['actual_points'] for p in actual_results if 'actual_points' in p)
        
        # Display results
        print(f"\n📋 WEEK {week} LINEUP & RESULTS:")
        print("-" * 60)
        print(f"{'Position':<8} {'Player':<20} {'Team':<4} {'Proj':<6} {'Actual':<6} {'Diff':<6}")
        print("-" * 60)
        
        for result in actual_results:
            if 'actual_points' in result:
                proj = result['projected_points']
                actual = result['actual_points']
                diff = actual - proj
                print(f"{result['position']:<8} {result['name'][:19]:<20} {result['team']:<4} "
                      f"{proj:<6.1f} {actual:<6.1f} {diff:+5.1f}")
        
        print("-" * 60)
        print(f"{'TOTAL':<33} {total_projected:<6.1f} {total_actual:<6.1f} {total_actual - total_projected:+5.1f}")
        
        accuracy = (1 - abs(total_actual - total_projected) / max(total_projected, 1)) * 100
        print(f"\n📈 Week {week} Accuracy: {accuracy:.1f}%")
        
        return {
            'week': week,
            'success': True,
            'lineup': actual_results,
            'projected_total': total_projected,
            'actual_total': total_actual,
            'accuracy': accuracy,
            'players_found': len(actual_results)
        }
    
    def run_full_simulation(self):
        """Run the complete 2020 season simulation."""
        print("🏈 2020 NFL SEASON SIMULATION")
        print("=" * 50)
        print("Testing enhanced matchup-aware prediction models")
        print("Training Period: 2018-2019 seasons")
        print("Testing Period: 2020 regular season (Weeks 1-17)")
        print()
        
        # Prepare models
        self.prepare_models_for_simulation()
        
        # Simulate each week
        successful_weeks = []
        for week in self.weeks_to_simulate:
            result = self.simulate_week(week)
            if result['success']:
                self.weekly_results.append(result)
                successful_weeks.append(week)
        
        # Overall season analysis
        self.analyze_season_performance(successful_weeks)
    
    def analyze_season_performance(self, successful_weeks: List[int]):
        """Analyze overall performance across the season."""
        if not self.weekly_results:
            print("❌ No successful weeks to analyze")
            return
        
        print(f"\n🏆 2020 SEASON SUMMARY")
        print("=" * 50)
        
        total_projected = sum(r['projected_total'] for r in self.weekly_results)
        total_actual = sum(r['actual_total'] for r in self.weekly_results)
        avg_accuracy = sum(r['accuracy'] for r in self.weekly_results) / len(self.weekly_results)
        
        print(f"Weeks Simulated: {len(successful_weeks)} of {len(self.weeks_to_simulate)}")
        print(f"Total Projected Points: {total_projected:.1f}")
        print(f"Total Actual Points: {total_actual:.1f}")
        print(f"Overall Difference: {total_actual - total_projected:+.1f}")
        print(f"Average Weekly Accuracy: {avg_accuracy:.1f}%")
        
        # Weekly accuracy breakdown
        print(f"\n📊 WEEKLY ACCURACY BREAKDOWN:")
        print("-" * 30)
        for result in self.weekly_results:
            status = "✅" if result['accuracy'] > 80 else "⚠️" if result['accuracy'] > 60 else "❌"
            print(f"Week {result['week']:2d}: {result['accuracy']:5.1f}% {status}")
        
        # Best and worst weeks
        best_week = max(self.weekly_results, key=lambda x: x['accuracy'])
        worst_week = min(self.weekly_results, key=lambda x: x['accuracy'])
        
        print(f"\n🌟 Best Week: {best_week['week']} ({best_week['accuracy']:.1f}% accuracy)")
        print(f"💔 Worst Week: {worst_week['week']} ({worst_week['accuracy']:.1f}% accuracy)")
        
        print(f"\n🎯 Model Performance Assessment:")
        if avg_accuracy > 80:
            print("🟢 EXCELLENT: Model shows strong predictive accuracy")
        elif avg_accuracy > 70:
            print("🟡 GOOD: Model shows solid predictive accuracy")
        elif avg_accuracy > 60:
            print("🟠 FAIR: Model shows reasonable predictive accuracy")
        else:
            print("🔴 POOR: Model needs improvement")


def main():
    """Run the 2020 season simulation."""
    simulator = Season2020Simulator()
    simulator.run_full_simulation()


if __name__ == "__main__":
    main()