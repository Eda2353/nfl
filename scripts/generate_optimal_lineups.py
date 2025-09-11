#!/usr/bin/env python3
"""Generate optimal fantasy football lineups using the complete system."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from fantasy_calculator import FantasyCalculator
from prediction_model import PlayerPredictor
from lineup_optimizer import LineupSimulator

def format_lineup_display(lineup, lineup_num):
    """Format lineup for display."""
    print(f"\n{'='*60}")
    print(f"OPTIMAL LINEUP #{lineup_num}")
    print(f"{'='*60}")
    print(f"Projected Points: {lineup.total_projected_points:.2f}")
    print(f"Salary: ${lineup.total_salary:,.0f}")
    print(f"Ceiling: {lineup.ceiling:.1f} | Floor: {lineup.floor:.1f}")
    print(f"Teams: {', '.join(lineup.teams_used)} ({len(lineup.teams_used)} teams)")
    print(f"\n{'Position':<3} {'Player':<20} {'Team':<4} {'Proj':<6} {'Salary':<7} {'Value':<5}")
    print('-' * 60)
    
    # Sort by position for display
    position_order = {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 4, 'DST': 5}
    sorted_players = sorted(lineup.players, key=lambda x: (position_order.get(x.position, 99), -x.projected_points))
    
    for player in sorted_players:
        value = player.projected_points / (player.salary / 1000)
        print(f"{player.position:<3} {player.player_name[:19]:<20} {player.team:<4} "
              f"{player.projected_points:>5.1f} ${player.salary:>6.0f} {value:>4.1f}x")

def main():
    """Generate and display optimal lineups."""
    
    # Initialize all components
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    predictor = PlayerPredictor(db_manager, calculator)
    simulator = LineupSimulator(db_manager, calculator, predictor)
    
    print("=== NFL FANTASY FOOTBALL LINEUP OPTIMIZER ===")
    print("Loading prediction models...")
    
    # Load trained models
    try:
        predictor.load_models("data/prediction_models.pkl")
        print("✅ Prediction models loaded successfully")
    except FileNotFoundError:
        print("❌ Prediction models not found. Please run train_prediction_models.py first.")
        return
    
    # Generate lineups for Week 11, 2023 
    week = 11
    season = 2023
    scoring_system = 'FanDuel'
    
    print(f"\nGenerating optimal lineups for Week {week}, {season} ({scoring_system})...")
    print("This may take a minute as we simulate thousands of scenarios...")
    
    # Generate tournament-style lineups
    lineups = simulator.generate_tournament_lineups(
        week=week,
        season=season,
        scoring_system=scoring_system,
        num_lineups=3
    )
    
    if not lineups:
        print("❌ No valid lineups could be generated. Check data availability.")
        return
    
    print(f"\n🎯 Generated {len(lineups)} optimal lineups!")
    
    # Display lineups
    for i, lineup in enumerate(lineups, 1):
        format_lineup_display(lineup, i)
        
        # Show detailed analysis for first lineup
        if i == 1:
            print(f"\n{'='*40}")
            print("DETAILED ANALYSIS - LINEUP #1")
            print(f"{'='*40}")
            
            analysis = simulator.analyze_lineup(lineup, week, season, scoring_system)
            
            print(f"Salary Remaining: ${analysis['lineup_summary']['salary_remaining']:,.0f}")
            print(f"Risk Level: {analysis['risk_analysis']['risk_level']}")
            print(f"Upside Potential: +{analysis['risk_analysis']['ceiling_upside']:.1f} points")
            print(f"Downside Risk: -{analysis['risk_analysis']['floor_downside']:.1f} points")
            
            if analysis['stack_analysis']:
                print("\nStacks Identified:")
                for team, stack in analysis['stack_analysis'].items():
                    print(f"  {team}: {stack['stack_type']} ({', '.join(stack['players'])})")
            else:
                print("\nNo stacks identified (diversified lineup)")
    
    # Show summary comparison
    print(f"\n{'='*60}")
    print("LINEUP COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'#':<2} {'Projected':<10} {'Ceiling':<8} {'Floor':<6} {'Teams':<6} {'Risk':<8}")
    print('-' * 50)
    
    for i, lineup in enumerate(lineups, 1):
        analysis = simulator.analyze_lineup(lineup, week, season, scoring_system)
        print(f"{i:<2} {lineup.total_projected_points:>8.1f} "
              f"{lineup.ceiling:>7.1f} {lineup.floor:>5.1f} "
              f"{len(lineup.teams_used):>5} "
              f"{analysis['risk_analysis']['risk_level']:>8}")
    
    print(f"\n{'='*60}")
    print("LINEUP STRATEGY RECOMMENDATIONS")
    print(f"{'='*60}")
    print("🏆 CASH GAMES: Use Lineup #1 (highest floor, lowest risk)")
    print("🎰 TOURNAMENTS: Consider Lineup #2-3 (higher ceiling, more risk)")
    print("📊 DIVERSIFICATION: Run multiple lineups to maximize coverage")
    print("\n💡 Remember: These are projections based on historical data.")
    print("   Always consider injury reports, weather, and matchups!")
    
    print(f"\n🚀 Lineup optimization complete!")
    print("   Ready for your fantasy football domination! 💪")

if __name__ == "__main__":
    main()