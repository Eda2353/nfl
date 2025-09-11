#!/usr/bin/env python3
"""Train and test the player performance prediction models."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from fantasy_calculator import FantasyCalculator
from prediction_model import PlayerPredictor

def main():
    """Train prediction models using historical data."""
    
    # Initialize
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    predictor = PlayerPredictor(db_manager, calculator)
    
    print("=== NFL PLAYER PREDICTION MODEL TRAINING ===")
    
    # Train on 2018-2022 data (5 seasons of training data)
    training_seasons = [2018, 2019, 2020, 2021, 2022]
    
    print("Training models on seasons:", training_seasons)
    predictor.train_models(training_seasons, scoring_system='FanDuel')
    
    # Save the trained models
    model_path = "data/prediction_models.pkl"
    predictor.save_models(model_path)
    
    print("\n=== TESTING ON 2023 DATA ===")
    
    # Test predictions for week 10, 2023
    test_week = 10
    test_season = 2023
    
    print(f"\nTop predicted performers for Week {test_week}, {test_season}:")
    
    for position in ['QB', 'RB', 'WR', 'TE']:
        predictions = predictor.get_top_predictions(
            week=test_week, 
            season=test_season, 
            position=position,
            scoring_system='FanDuel',
            limit=5
        )
        
        if not predictions.empty:
            print(f"\nTop 5 {position}s:")
            print(predictions[['player_name', 'predicted_points']].to_string(index=False))
    
    # Compare predictions to actual results
    print(f"\n=== VALIDATION: Comparing Predictions to Actual Week {test_week} Results ===")
    
    actual_results = calculator.get_weekly_rankings(
        week=test_week,
        season=test_season,
        scoring_system='FanDuel',
        limit=20
    )
    
    if not actual_results.empty:
        print("\nActual Week 10 Top Performers:")
        print(actual_results[['player_name', 'position', 'fantasy_points']].head(10))
        
        # Calculate prediction accuracy for top players
        top_actual = actual_results.head(10)
        correct_predictions = 0
        
        for position in ['QB', 'RB', 'WR', 'TE']:
            pos_actual = top_actual[top_actual['position'] == position]
            pos_predicted = predictor.get_top_predictions(
                week=test_week, season=test_season, position=position, limit=5
            )
            
            if not pos_actual.empty and not pos_predicted.empty:
                # Check if top predicted player is in top actual performers
                top_predicted_id = pos_predicted.iloc[0]['player_id'] if 'player_id' in pos_predicted.columns else None
                top_actual_ids = pos_actual['player_id'].tolist() if 'player_id' in pos_actual.columns else []
                
                # For display purposes, check name matching since we might not have player_id in actual results
                top_predicted_name = pos_predicted.iloc[0]['player_name']
                actual_names = pos_actual['player_name'].tolist()
                
                if top_predicted_name in actual_names:
                    correct_predictions += 1
                    print(f"✅ {position}: Correctly predicted {top_predicted_name} in top performers")
                else:
                    print(f"❌ {position}: Predicted {top_predicted_name}, but top actual was {actual_names[0] if actual_names else 'N/A'}")
        
        print(f"\nPrediction Accuracy: {correct_predictions}/4 positions correctly predicted")
    
    print("\n=== MODEL TRAINING COMPLETE ===")
    print(f"Models saved to: {model_path}")
    print("Ready for lineup optimization!")

if __name__ == "__main__":
    main()