#!/usr/bin/env python3
"""Test script demonstrating improved predictions with comprehensive matchup analysis."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from src.fantasy_calculator import FantasyCalculator
from src.prediction_model import PlayerPredictor
from src.matchup_analyzer import MatchupAnalyzer

def demonstrate_matchup_intelligence():
    """Demonstrate the enhanced prediction system with matchup analysis."""
    
    print("🏈 NFL Fantasy Football Matchup-Enhanced Predictions")
    print("=" * 60)
    
    # Initialize system components
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    predictor = PlayerPredictor(db_manager, calculator)
    analyzer = MatchupAnalyzer(db_manager, calculator)
    
    print("✅ System initialized with enhanced matchup analysis")
    
    # Test matchup analysis system
    print("\n🔍 Testing Matchup Analysis System:")
    print("-" * 40)
    
    # Example: Strong offense vs weak defense
    print("1. Strong Offense vs Weak Defense Example:")
    matchup1 = analyzer.analyze_matchup('KC', 'CHI', 2023, 10)  # Chiefs vs Bears
    if matchup1:
        print(f"   KC Offense Score: {matchup1.offense_strength.offensive_score:.1f}")
        print(f"   CHI Defense Score: {matchup1.defense_strength.defensive_score:.1f}")
        print(f"   Matchup Type: {matchup1.matchup_type}")
        print(f"   Points Modifier: {matchup1.points_modifier:.2f}")
        print(f"   Expected Impact: {'Favorable' if matchup1.points_modifier > 1.0 else 'Challenging'}")
    
    # Example: Strong defense vs strong offense
    print("\n2. Strong Defense vs Strong Offense Example:")
    matchup2 = analyzer.analyze_matchup('BUF', 'SF', 2023, 10)  # Bills vs 49ers
    if matchup2:
        print(f"   BUF Offense Score: {matchup2.offense_strength.offensive_score:.1f}")
        print(f"   SF Defense Score: {matchup2.defense_strength.defensive_score:.1f}")
        print(f"   Matchup Type: {matchup2.matchup_type}")
        print(f"   Points Modifier: {matchup2.points_modifier:.2f}")
        print(f"   Expected Impact: {'Favorable' if matchup2.points_modifier > 1.0 else 'Challenging'}")
    
    # Test DST matchup analysis
    print("\n3. DST Matchup Analysis Example:")
    dst_matchup = analyzer.get_matchup_for_dst('SF', 2023, 10)  # 49ers DST
    if dst_matchup:
        print(f"   SF Defense Score: {dst_matchup.defense_strength.defensive_score:.1f}")
        print(f"   Opponent Offense Score: {dst_matchup.offense_strength.offensive_score:.1f}")
        print(f"   Matchup Type: {dst_matchup.matchup_type}")
        print(f"   Sack Modifier: {dst_matchup.sack_modifier:.2f}")
        print(f"   DST Outlook: {'Favorable' if dst_matchup.sack_modifier > 1.0 else 'Challenging'}")
    
    # Demonstrate all four matchup scenarios
    print("\n📊 Comprehensive Matchup Matrix:")
    print("-" * 40)
    
    matchup_examples = [
        ('KC', 'MIA', 'Strong vs Strong'),    # High-scoring teams
        ('KC', 'NYJ', 'Strong vs Weak'),      # Chiefs vs weak defense
        ('CHI', 'SF', 'Weak vs Strong'),      # Bears vs strong defense  
        ('CHI', 'NYJ', 'Weak vs Weak')        # Low-scoring matchup
    ]
    
    for offense, defense, expected_type in matchup_examples:
        matchup = analyzer.analyze_matchup(offense, defense, 2023, 10)
        if matchup:
            print(f"{offense} vs {defense}:")
            print(f"  Actual Type: {matchup.matchup_type}")
            print(f"  Points Modifier: {matchup.points_modifier:.2f}")
            print(f"  Advantage: {matchup.offensive_advantage:+.1f}")
            print()
    
    # Test enhanced prediction system
    print("🎯 Testing Enhanced Predictions:")
    print("-" * 40)
    
    # Load existing models to demonstrate enhanced features
    try:
        predictor.load_models('data/prediction_models.pkl')
        print("⚠️  Using existing models (without matchup features)")
        print("   Retrain models to include matchup intelligence")
    except:
        print("ℹ️  No existing models found")
        print("   Train models with enhanced matchup features:")
        print("   python3 src/train_models.py")
    
    print("\n🔄 Model Enhancement Summary:")
    print("-" * 40)
    print("Enhanced Player Features:")
    print("  ✓ opponent_defensive_score (0-100)")
    print("  ✓ matchup_points_modifier (0.5-1.5)")  
    print("  ✓ matchup_turnover_modifier (0.5-1.5)")
    
    print("\nEnhanced DST Features:")
    print("  ✓ opponent_offensive_score (0-100)")
    print("  ✓ matchup_points_modifier (0.5-1.5)")
    print("  ✓ matchup_sack_modifier (0.5-1.5)")
    
    print("\n🎯 Expected Improvements:")
    print("-" * 40)
    print("• Better QB predictions vs strong pass rush")
    print("• Improved RB/WR predictions vs weak run defense")  
    print("• Enhanced DST scoring vs turnover-prone offenses")
    print("• More accurate predictions in extreme matchups")
    
    print("\n📈 Next Steps:")
    print("-" * 40)
    print("1. Retrain models with matchup features:")
    print("   python3 src/train_models.py")
    print("\n2. Test predictions for upcoming week:")
    print("   python3 src/weekly_predictions.py")
    print("\n3. Generate optimal lineups:")
    print("   python3 src/optimize_lineup.py")
    

if __name__ == "__main__":
    demonstrate_matchup_intelligence()