#!/usr/bin/env python3
"""
Simple startup script for NFL Fantasy Predictor Web App
Ensures models are trained before starting the web server
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from app import app
from src.config import Config
from src.database import DatabaseManager
from src.gameday_predictor import GamedayPredictor

def initialize_system():
    """Initialize and train models before starting web server."""
    print("🏈 Initializing NFL Fantasy Prediction System...")
    
    try:
        # Initialize components
        config = Config.from_env()
        db_manager = DatabaseManager(config)
        gameday_predictor = GamedayPredictor(config, db_manager)
        
        print("✅ System components initialized")
        
        # Check if models exist, otherwise train them
        import os
        model_file = './data/prediction_models.pkl'
        
        if os.path.exists(model_file):
            print("🧠 Loading existing models...")
            try:
                gameday_predictor.predictor.load_models(model_file)
                print("   ✅ Models loaded from cache")
            except Exception as e:
                print(f"   ⚠️ Failed to load models: {e}")
                print("   🔄 Training new models...")
                # Fall back to training
                scoring_systems = ['FanDuel', 'DraftKings']
                training_seasons = [2022, 2023, 2024]
                
                for scoring_system in scoring_systems:
                    try:
                        print(f"   Training {scoring_system} models...")
                        gameday_predictor.predictor.train_models(training_seasons, scoring_system)
                        print(f"   ✅ {scoring_system} models trained")
                    except Exception as e:
                        print(f"   ⚠️ {scoring_system} training failed: {e}")
        else:
            print("🧠 Pre-training models...")
            scoring_systems = ['FanDuel', 'DraftKings']
            training_seasons = [2022, 2023, 2024]
            
            for scoring_system in scoring_systems:
                try:
                    print(f"   Training {scoring_system} models...")
                    gameday_predictor.predictor.train_models(training_seasons, scoring_system)
                    print(f"   ✅ {scoring_system} models trained")
                except Exception as e:
                    print(f"   ⚠️ {scoring_system} training failed: {e}")
            
            # Save models for next time
            try:
                gameday_predictor.predictor.save_models(model_file)
            except Exception as e:
                print(f"   ⚠️ Failed to save models: {e}")
        
        print("🚀 System ready!")
        return True
        
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("NFL FANTASY PREDICTOR - WEB APPLICATION")
    print("=" * 60)
    
    # Initialize system
    if initialize_system():
        print("\n🌐 Starting web server...")
        print("📱 Access the app at: http://localhost:5001")
        print("🛑 Press Ctrl+C to stop")
        print("-" * 60)
        
        # Start Flask app
        try:
            app.run(debug=False, host='0.0.0.0', port=5001, threaded=True)
        except KeyboardInterrupt:
            print("\n👋 Shutting down gracefully...")
    else:
        print("❌ Cannot start web server due to initialization failure")
        sys.exit(1)