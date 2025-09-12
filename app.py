#!/usr/bin/env python3
"""
Flask web application for NFL Fantasy Prediction System
Modern web interface for gameday predictions with injury intelligence
"""

from flask import Flask, render_template, jsonify, request
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.database import DatabaseManager
from src.gameday_predictor import GamedayPredictor
from src.collectors.injury_collector import InjuryCollector
from src.collectors.nfl_data_collector import NFLDataCollector
from datetime import datetime, timedelta
from sqlalchemy import text
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nfl-fantasy-predictions-2025'

# Global instances
config = Config.from_env()
db_manager = DatabaseManager(config)
gameday_predictor = GamedayPredictor(config, db_manager)
injury_collector = InjuryCollector(db_manager)
data_collector = NFLDataCollector(config, db_manager)

# Global state
prediction_cache = {}
injury_cache = {}
schedule_cache = {}

@app.route('/api/health')
def health():
    """Simple health check endpoint."""
    try:
        # Try a lightweight DB check
        with db_manager.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/initialization-status')
def initialization_status():
    """Report whether the database appears initialized for the web app."""
    try:
        status = {
            'initialized': False,
            'scoring_systems': 0,
            'teams': 0,
            'players': 0,
            'games': 0
        }
        with db_manager.engine.connect() as conn:
            status['scoring_systems'] = conn.execute(text("SELECT COUNT(*) FROM scoring_systems")).fetchone()[0]
            status['teams'] = conn.execute(text("SELECT COUNT(*) FROM teams")).fetchone()[0]
            status['players'] = conn.execute(text("SELECT COUNT(*) FROM players")).fetchone()[0]
            status['games'] = conn.execute(text("SELECT COUNT(*) FROM games")).fetchone()[0]
        # Consider initialized if scoring systems exist and there is at least some game data
        status['initialized'] = status['scoring_systems'] > 0 and status['games'] > 0
        return jsonify(status)
    except Exception as e:
        app.logger.error(f"Initialization status error: {e}")
        return jsonify({'initialized': False, 'error': str(e)}), 200

@app.route('/api/initialize-database', methods=['POST'])
def initialize_database():
    """Initialize database with baseline data and scoring systems in background."""
    try:
        payload = request.get_json(silent=True) or {}
        start_season = int(payload.get('start_season', 2022))
        end_season = int(payload.get('end_season', datetime.now().year))

        def init_in_background():
            try:
                app.logger.info("Initializing database: creating default scoring systems and core data...")

                # Ensure scoring systems exist
                try:
                    from src.init_scoring_systems import init_scoring_systems
                except Exception:
                    # Fallback import path if running with src on path
                    from init_scoring_systems import init_scoring_systems
                init_scoring_systems(db_manager)
                app.logger.info("Default scoring systems initialized")

                # Collect minimal data set (teams/players/games/stats)
                # Use configured collector; limit range to avoid huge imports
                original_start = config.data_collection.start_season
                original_end = config.data_collection.end_season
                try:
                    config.data_collection.start_season = start_season
                    config.data_collection.end_season = end_season
                    data_collector.collect_all_data()
                finally:
                    config.data_collection.start_season = original_start
                    config.data_collection.end_season = original_end

                # Clear caches so UI sees fresh data
                prediction_cache.clear()
                schedule_cache.clear()
                injury_cache.clear()
                app.logger.info("Database initialization completed")
            except Exception as e:
                app.logger.error(f"Database initialization failed: {e}")

        thread = threading.Thread(target=init_in_background)
        thread.daemon = True
        thread.start()

        return jsonify({'status': 'success', 'message': 'Initialization started'}), 202
    except Exception as e:
        app.logger.error(f"Error starting initialization: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')

@app.route('/api/scoring-systems')
def get_scoring_systems():
    """Get available scoring systems."""
    with db_manager.engine.connect() as conn:
        systems = conn.execute(text("SELECT system_name FROM scoring_systems")).fetchall()
        return jsonify([system[0] for system in systems])

@app.route('/api/current-week')
def get_current_week():
    """Get current NFL week and season based on actual game data."""
    current_date = datetime.now()
    
    # Determine current season
    if current_date.month >= 9:
        season = current_date.year
    else:
        season = current_date.year - 1
    
    # Find the current week based on completed games and upcoming games
    try:
        with db_manager.engine.connect() as conn:
            # Find the latest completed week
            latest_completed = conn.execute(text("""
                SELECT MAX(week) as latest_week
                FROM games 
                WHERE season_id = :season 
                AND home_score IS NOT NULL 
                AND away_score IS NOT NULL
            """), {'season': season}).fetchone()
            
            # Find the earliest upcoming week with games
            next_week = conn.execute(text("""
                SELECT MIN(week) as next_week
                FROM games 
                WHERE season_id = :season 
                AND home_score IS NULL 
                AND away_score IS NULL
            """), {'season': season}).fetchone()
            
            completed_week = latest_completed[0] if latest_completed[0] else 0
            upcoming_week = next_week[0] if next_week[0] else 18
            
            # Current week is the next week to be played
            if upcoming_week <= 18:
                week = upcoming_week
            elif completed_week > 0:
                week = completed_week  # Season is over, show latest week
            else:
                week = 1  # Default to week 1
                
            app.logger.info(f"Current week calculation: completed={completed_week}, upcoming={upcoming_week}, selected={week}")
            
    except Exception as e:
        app.logger.error(f"Error determining current week from database: {e}")
        # Fallback to date-based calculation
        if current_date.month >= 9:
            week_start = datetime(season, 9, 5)  # Approximate season start
            weeks_elapsed = (current_date - week_start).days // 7 + 1
            week = min(max(weeks_elapsed, 1), 18)
        else:
            week = 18  # Assume post-season
    
    return jsonify({
        'season': season,
        'week': week,
        'current_date': current_date.strftime('%Y-%m-%d')
    })

@app.route('/api/schedule/<int:season>/<int:week>')
def get_schedule(season, week):
    """Get NFL schedule for specific week."""
    cache_key = f"{season}_{week}"
    
    if cache_key in schedule_cache:
        return jsonify(schedule_cache[cache_key])
    
    try:
        with db_manager.engine.connect() as conn:
            games = conn.execute(text("""
                SELECT g.game_id, g.game_date, g.game_time,
                       ht.team_name as home_team, ht.team_id as home_team_id,
                       at.team_name as away_team, at.team_id as away_team_id,
                       g.home_score, g.away_score
                FROM games g
                JOIN teams ht ON g.home_team_id = ht.team_id
                JOIN teams at ON g.away_team_id = at.team_id
                WHERE g.season_id = :season AND g.week = :week
                ORDER BY g.game_date, g.game_time
            """), {'season': season, 'week': week}).fetchall()
            
            schedule_data = []
            for game in games:
                # Handle date formatting - could be string or datetime
                game_date = game[1]
                if hasattr(game_date, 'strftime'):
                    formatted_date = game_date.strftime('%Y-%m-%d')
                elif game_date:
                    formatted_date = str(game_date)
                else:
                    formatted_date = None
                
                # Handle time formatting - could be string or time
                game_time = game[2]
                if hasattr(game_time, 'strftime'):
                    formatted_time = game_time.strftime('%H:%M')
                elif game_time:
                    formatted_time = str(game_time)
                else:
                    formatted_time = 'TBD'
                
                schedule_data.append({
                    'game_id': game[0],
                    'date': formatted_date,
                    'time': formatted_time,
                    'home_team': game[3],
                    'home_team_id': game[4],
                    'away_team': game[5],
                    'away_team_id': game[6],
                    'home_score': game[7],
                    'away_score': game[8],
                    'completed': game[7] is not None and game[8] is not None
                })
            
            schedule_cache[cache_key] = schedule_data
            return jsonify(schedule_data)
    
    except Exception as e:
        app.logger.error(f"Error getting schedule: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/injury-report')
def get_injury_report():
    """Get current injury report."""
    cache_key = 'current_injuries'
    
    # Use cache if less than 15 minutes old
    if cache_key in injury_cache:
        cached_time, cached_data = injury_cache[cache_key]
        if datetime.now() - cached_time < timedelta(minutes=15):
            return jsonify(cached_data)
    
    try:
        injuries = injury_collector.get_current_injuries()
        
        injury_data = {
            'timestamp': datetime.now().isoformat(),
            'total_injuries': len(injuries),
            'by_status': {},
            'by_position': {},
            'by_team': {},
            'details': []
        }
        
        for injury in injuries:
            # Group by status
            status = injury.status
            if status not in injury_data['by_status']:
                injury_data['by_status'][status] = 0
            injury_data['by_status'][status] += 1
            
            # Group by position
            position = injury.position
            if position not in injury_data['by_position']:
                injury_data['by_position'][position] = 0
            injury_data['by_position'][position] += 1
            
            # Group by team
            team = injury.team
            if team not in injury_data['by_team']:
                injury_data['by_team'][team] = 0
            injury_data['by_team'][team] += 1
            
            # Add to details
            injury_data['details'].append({
                'player_name': injury.player_name,
                'position': injury.position,
                'team': injury.team,
                'status': injury.status,
                'fantasy_status': injury.fantasy_status,
                'injury_type': injury.injury_type,
                'injury_location': injury.injury_location,
                'return_date': injury.return_date,
                'impact_severity': injury.impact_severity,
                'is_out': injury.is_out,
                'is_questionable': injury.is_questionable
            })
        
        # Cache the result
        injury_cache[cache_key] = (datetime.now(), injury_data)
        return jsonify(injury_data)
    
    except Exception as e:
        app.logger.error(f"Error getting injury report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/injury-report/<int:season>/<int:week>')
def get_historical_injury_report(season, week):
    """Get historical injury report for specific season and week."""
    cache_key = f'historical_{season}_{week}'
    
    # Use cache if less than 24 hours old (historical data changes less frequently)
    if cache_key in injury_cache:
        cached_time, cached_data = injury_cache[cache_key]
        if datetime.now() - cached_time < timedelta(hours=24):
            return jsonify(cached_data)
    
    try:
        injuries = injury_collector.get_historical_injuries(season, week)
        
        injury_data = {
            'timestamp': datetime.now().isoformat(),
            'season': season,
            'week': week,
            'total_injuries': len(injuries),
            'by_status': {},
            'by_position': {},
            'by_team': {},
            'details': []
        }
        
        for injury in injuries:
            # Group by status
            status = injury.status
            if status not in injury_data['by_status']:
                injury_data['by_status'][status] = 0
            injury_data['by_status'][status] += 1
            
            # Group by position
            position = injury.position
            if position not in injury_data['by_position']:
                injury_data['by_position'][position] = 0
            injury_data['by_position'][position] += 1
            
            # Group by team
            team = injury.team
            if team not in injury_data['by_team']:
                injury_data['by_team'][team] = 0
            injury_data['by_team'][team] += 1
            
            # Add to details
            injury_data['details'].append({
                'player_name': injury.player_name,
                'position': injury.position,
                'team': injury.team,
                'status': injury.status,
                'fantasy_status': injury.fantasy_status,
                'injury_type': injury.injury_type,
                'injury_location': injury.injury_location,
                'return_date': injury.return_date,
                'impact_severity': injury.impact_severity,
                'is_out': injury.is_out,
                'is_questionable': injury.is_questionable
            })
        
        # Cache the result
        injury_cache[cache_key] = (datetime.now(), injury_data)
        return jsonify(injury_data)
    
    except Exception as e:
        app.logger.error(f"Error getting historical injury report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/predictions/<int:season>/<int:week>/<scoring_system>')
def get_predictions(season, week, scoring_system):
    """Get gameday predictions for specific week and scoring system."""
    cache_key = f"{season}_{week}_{scoring_system}"
    
    # Use cache if less than 30 minutes old
    if cache_key in prediction_cache:
        cached_time, cached_data = prediction_cache[cache_key]
        if datetime.now() - cached_time < timedelta(minutes=30):
            return jsonify(cached_data)
    
    try:
        # Train models if needed
        app.logger.info(f"Generating predictions for Week {week}, {season} - {scoring_system}")
        
        # Get gameday predictions
        gameday_data = gameday_predictor.get_gameday_predictions(
            week=week, season=season, scoring_system=scoring_system
        )
        
        # Format for frontend
        prediction_data = {
            'timestamp': gameday_data['timestamp'].isoformat(),
            'week': gameday_data['week'],
            'season': gameday_data['season'],
            'scoring_system': gameday_data['scoring_system'],
            'summary': gameday_data.get('summary', {}),
            'injury_report': {},
            'top_players': {},
            'optimal_lineup': {},
            'dst_recommendations': gameday_data.get('dst_predictions', [])[:10]
        }
        
        # Process injury report
        if gameday_data.get('injury_report'):
            injury_report = gameday_data['injury_report']
            prediction_data['injury_report'] = {
                'total_out': injury_report['total_out'],
                'total_questionable': injury_report['total_questionable'],
                'high_impact_teams': injury_report.get('high_impact_teams', [])
            }
        
        # Process player predictions
        if gameday_data.get('player_predictions'):
            predictions = gameday_data['player_predictions']
            
            # Group by position and get top players
            by_position = {}
            for pred in predictions:
                pos = pred['position']
                if pos not in by_position:
                    by_position[pos] = []
                by_position[pos].append(pred)
            
            for position in ['QB', 'RB', 'WR', 'TE']:
                if position in by_position:
                    players = by_position[position]
                    players.sort(key=lambda x: x['predicted_points'], reverse=True)
                    prediction_data['top_players'][position] = players[:10]
        
        # Process optimal lineup
        if gameday_data.get('optimal_lineups', {}).get('optimal'):
            optimal = gameday_data['optimal_lineups']['optimal']
            prediction_data['optimal_lineup'] = {
                'total_projected': optimal['total_projected'],
                'players': optimal['players']
            }
        
        # Cache the result
        prediction_cache[cache_key] = (datetime.now(), prediction_data)
        return jsonify(prediction_data)
    
    except Exception as e:
        import traceback
        app.logger.error(f"Error generating predictions: {e}")
        app.logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update-data', methods=['POST'])
def update_data():
    """Update database with latest NFL data, injury reports, and schedules."""
    try:
        data = request.get_json()
        seasons = data.get('seasons', [2024, 2025])
        update_injuries = data.get('update_injuries', True)
        update_schedules = data.get('update_schedules', True)
        
        def update_in_background():
            try:
                app.logger.info(f"Starting comprehensive data update for seasons: {seasons}")
                
                # Update NFL game data and statistics
                if update_schedules:
                    app.logger.info("Updating NFL schedules and game data...")
                    for season in seasons:
                        try:
                            if season >= 2025:
                                # Use current season method for 2025+
                                app.logger.info(f"Updating current season {season} data...")
                                # Check if we already have data for this season
                                with db_manager.engine.connect() as conn:
                                    result = conn.execute(text("SELECT COUNT(*) FROM games WHERE season_id = :season"), 
                                                        {"season": season}).fetchone()
                                    game_count = result[0] if result else 0
                                
                                if game_count > 0:
                                    app.logger.info(f"Current season {season} already has {game_count} games")
                                    app.logger.info(f"Skipping game collection to avoid duplicates")
                                    # Could add logic here to update only new/changed games if needed
                                else:
                                    app.logger.info(f"No existing data for current season {season}, collecting all data...")
                                    data_collector._collect_current_season_data(season)
                            else:
                                # For historical seasons, just update stats (games likely already exist)
                                app.logger.info(f"Updating historical season {season} stats...")
                                # Check if we have recent data for this season first
                                with db_manager.engine.connect() as conn:
                                    result = conn.execute(text("SELECT COUNT(*) FROM games WHERE season_id = :season"), 
                                                        {"season": season}).fetchone()
                                    game_count = result[0] if result else 0
                                
                                if game_count > 0:
                                    app.logger.info(f"Season {season} already has {game_count} games, skipping game collection")
                                    # Still update player stats for this season
                                    app.logger.info(f"Refreshing player stats for season {season}...")
                                else:
                                    app.logger.info(f"No existing data for season {season}, collecting all data...")
                                    data_collector._collect_season_games_and_stats(season)
                        except Exception as season_error:
                            app.logger.warning(f"Failed to update season {season}: {season_error}")
                            continue
                
                # Update injury reports
                if update_injuries:
                    app.logger.info("Updating injury reports...")
                    try:
                        # Import/update historical injury data for recent seasons
                        historical_seasons = [s for s in seasons if s >= 2020]  # nfl-data-py has injury data from 2020+
                        if historical_seasons:
                            injury_count = injury_collector.import_historical_injuries(historical_seasons)
                            app.logger.info(f"Updated {injury_count} historical injury records")
                        
                        # Update current week injury data (this will be fetched fresh via ESPN API on next request)
                        app.logger.info("Current injuries will be refreshed on next API call")
                        
                    except Exception as injury_error:
                        app.logger.warning(f"Injury update partially failed: {injury_error}")
                
                app.logger.info("Comprehensive data update completed successfully")
                
                # Clear all relevant caches to force fresh data
                prediction_cache.clear()
                schedule_cache.clear()
                injury_cache.clear()  # Clear injury cache to force fresh data
                
            except Exception as e:
                app.logger.error(f"Data update failed: {e}")
        
        # Start update in background thread
        thread = threading.Thread(target=update_in_background)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started', 
            'message': 'Comprehensive data update started in background',
            'includes': {
                'schedules': update_schedules,
                'injuries': update_injuries,
                'seasons': seasons
            }
        })
    
    except Exception as e:
        app.logger.error(f"Error starting data update: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/train-models', methods=['POST'])
def train_models():
    """Train prediction models."""
    try:
        data = request.get_json()
        scoring_system = data.get('scoring_system', 'FanDuel')
        seasons = data.get('seasons', [2022, 2023, 2024])
        
        def train_in_background():
            try:
                app.logger.info(f"Training models for {scoring_system} using seasons: {seasons}")
                gameday_predictor.predictor.train_models(seasons, scoring_system)
                app.logger.info("Model training completed successfully")
                
                # Clear prediction cache
                prediction_cache.clear()
                
            except Exception as e:
                app.logger.error(f"Model training failed: {e}")
        
        # Start training in background
        thread = threading.Thread(target=train_in_background)
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'started', 'message': 'Model training started in background'})
    
    except Exception as e:
        app.logger.error(f"Error starting model training: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize models on startup
    try:
        app.logger.info("Initializing NFL Fantasy Prediction System...")
        # Could pre-train models here if needed
        app.logger.info("System initialized successfully")
    except Exception as e:
        app.logger.error(f"System initialization failed: {e}")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
