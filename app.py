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
from src.collectors.dst_collector import DSTCollector
from src.normalization import normalize_game_ids
from datetime import datetime, timedelta
from sqlalchemy import text
import threading
import logging
from pathlib import Path
import json
import platform
import warnings

# Configure logging
logging.basicConfig(level=logging.INFO)
# Suppress verbose INFO logs from the injury collector module
logging.getLogger('src.collectors.injury_collector').setLevel(logging.WARNING)
logging.getLogger('collectors.injury_collector').setLevel(logging.WARNING)

# Suppress scikit-learn feature-name UserWarning during predictions
warnings.filterwarnings(
    "ignore",
    message=r"X does not have valid feature names, but .* was fitted with feature names",
    category=UserWarning,
    module=r"sklearn\..*"
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nfl-fantasy-predictions-2025'

# Default DB target: prefer data/nfl_data.db unless overridden by environment
os.environ.setdefault('DB_PATH', 'data/nfl_data.db')

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

## (Removed background progress job machinery)

############################
# Model persistence helpers
############################

def _models_base_dir() -> Path:
    """Base directory for all trained models."""
    return Path(os.getenv('MODEL_DIR', 'data/models'))

def _safe_scoring(scoring_system: str) -> str:
    return scoring_system.lower().replace(' ', '')

def _scoring_dir(scoring_system: str) -> Path:
    return _models_base_dir() / _safe_scoring(scoring_system)

def _legacy_model_path_for_scoring(scoring_system: str) -> Path:
    """Legacy flat file location used previously (for backward compatibility)."""
    sanitized = scoring_system.replace(' ', '_')
    base = os.getenv('MODEL_BASENAME', f'models_{sanitized}.pkl')
    return Path(os.getenv('LEGACY_MODEL_DIR', 'data')) / base

def _latest_completed_game(seasons: list[int] | None = None) -> tuple[int, int] | None:
    """Return (season, week) of the latest fully completed game in DB, optionally limited to seasons list."""
    try:
        with db_manager.engine.connect() as conn:
            if seasons:
                placeholders = ','.join(str(s) for s in seasons)
                q = text(f"""
                    SELECT season_id, MAX(week) AS w
                    FROM games
                    WHERE season_id IN ({placeholders}) AND home_score IS NOT NULL AND away_score IS NOT NULL
                    GROUP BY season_id
                    ORDER BY season_id DESC
                """)
                rows = conn.execute(q).fetchall()
                if rows:
                    # Take the most recent season's max week
                    season, week = rows[0]
                    return int(season), int(week)
            # Fallback: any season
            row = conn.execute(text("""
                SELECT season_id, week
                FROM games
                WHERE home_score IS NOT NULL AND away_score IS NOT NULL
                ORDER BY season_id DESC, week DESC
                LIMIT 1
            """)).fetchone()
            if row:
                return int(row[0]), int(row[1])
    except Exception as e:
        app.logger.warning(f"Latest completed game lookup failed: {e}")
    return None

def _week_ready(season: int, week: int) -> dict:
    """Check if a given (season, week) is fully ingested and ready for training.
    Criteria: all games have scores, team_defense_stats has two rows per game,
    and no synthetic game_ids remain for that week.
    """
    out = {'season': season, 'week': week, 'ready': False, 'games': 0, 'scored_games': 0,
           'dst_rows': 0, 'synthetic_ids': 0}
    try:
        with db_manager.engine.connect() as conn:
            total = conn.execute(text("""
                SELECT COUNT(*) FROM games WHERE season_id=:s AND week=:w
            """), {'s': season, 'w': week}).fetchone()[0]
            scored = conn.execute(text("""
                SELECT COUNT(*) FROM games WHERE season_id=:s AND week=:w AND home_score IS NOT NULL AND away_score IS NOT NULL
            """), {'s': season, 'w': week}).fetchone()[0]
            dst = conn.execute(text("""
                SELECT COUNT(*) FROM team_defense_stats WHERE season_id=:s AND week=:w
            """), {'s': season, 'w': week}).fetchone()[0]
            synth = conn.execute(text("""
                SELECT COUNT(*)
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                WHERE g.season_id=:s AND g.week=:w AND (gs.game_id LIKE '%/_vs_%' ESCAPE '/' OR gs.game_id LIKE '%_vs_%')
            """), {'s': season, 'w': week}).fetchone()[0]
            out.update({'games': total, 'scored_games': scored, 'dst_rows': dst, 'synthetic_ids': synth})
            if total > 0 and scored == total and dst == total * 2 and synth == 0:
                out['ready'] = True
    except Exception as e:
        app.logger.warning(f"Week readiness check failed for {season} W{week}: {e}")
    return out

def _latest_ready_before(season: int, week: int) -> tuple[int, int] | None:
    for w in range(week - 1, 0, -1):
        st = _week_ready(season, w)
        if st.get('ready'):
            return (season, w)
    # look back prior seasons if needed
    for s in range(season - 1, season - 5, -1):
        if s < 2000:
            break
        for w in range(18, 0, -1):
            st = _week_ready(s, w)
            if st.get('ready'):
                return (s, w)
    return None

def _cutoff_model_path(scoring: str, season: int, week: int) -> Path:
    sdir = _scoring_dir(scoring)
    return sdir / f"{_safe_scoring(scoring)}_{season}_wk{week}.pkl"

def _save_cutoff_model(scoring: str, season: int, week: int, trained_through: tuple[int, int] | None, seasons_used: list[int]):
    try:
        sdir = _scoring_dir(scoring)
        sdir.mkdir(parents=True, exist_ok=True)
        path = _cutoff_model_path(scoring, season, week)
        gameday_predictor.predictor.save_models(str(path))
        meta = {
            'scoring': scoring,
            'target_season': season,
            'target_week': week,
            'trained_through': {'season': trained_through[0], 'week': trained_through[1]} if trained_through else None,
            'seasons_used': seasons_used,
            'trained_at_utc': datetime.utcnow().isoformat() + 'Z'
        }
        side = path.with_suffix('.json')
        _write_atomic(side, json.dumps(meta, indent=2).encode('utf-8'))
        app.logger.info(f"Saved cutoff model for {scoring} at {path}")
    except Exception as e:
        app.logger.warning(f"Failed to save cutoff model for {scoring}: {e}")

def _ensure_cutoff_model_for_request(scoring: str, season: int, week: int):
    path = _cutoff_model_path(scoring, season, week)
    if path.exists():
        app.logger.info(f"Loading cutoff model: {path}")
        gameday_predictor.predictor.load_models(str(path))
        return
    # Train cutoff model now
    seasons = gameday_predictor._get_training_seasons(season)
    trained_through = _latest_ready_before(season, week)
    app.logger.info(f"Training cutoff model for {scoring} up to before {season} W{week} (trained_through={trained_through})")
    gameday_predictor.predictor.train_models(seasons, scoring, cutoff=(season, week))
    _save_cutoff_model(scoring, season, week, trained_through, seasons)

def _write_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'wb') as f:
        f.write(data)
    tmp.replace(path)

def _save_current_model(scoring_system: str, seasons: list[int]):
    """Persist trained models with versioned name and update CURRENT pointer."""
    try:
        latest = _latest_completed_game(seasons) or _latest_completed_game(None) or (seasons[-1], 1)
        last_season, last_week = latest
        tag = f"{last_season}_wk{last_week}"
        sdir = _scoring_dir(scoring_system)
        sdir.mkdir(parents=True, exist_ok=True)
        fname = f"{_safe_scoring(scoring_system)}_{tag}.pkl"
        model_path = sdir / fname
        # Save pickle
        gameday_predictor.predictor.save_models(str(model_path))
        # Metadata
        meta = {
            'scoring': scoring_system,
            'seasons_used': seasons,
            'last_data_season': last_season,
            'last_data_week': last_week,
            'trained_at_utc': datetime.utcnow().isoformat() + 'Z',
            'app_secret': app.config.get('SECRET_KEY', ''),  # simple app build marker
            'python_version': platform.python_version(),
        }
        try:
            import sklearn, numpy
            meta['sklearn_version'] = getattr(sklearn, '__version__', None)
            meta['numpy_version'] = getattr(numpy, '__version__', None)
        except Exception:
            pass
        # Try to capture feature metadata if available
        pred = gameday_predictor.predictor
        meta['features'] = {
            'feature_columns': getattr(pred, 'feature_columns', []),
            'dst_feature_columns': getattr(pred, 'dst_feature_columns', []),
            'supports_position_features': getattr(pred, 'supports_position_features', False)
        }
        # Write sidecar and CURRENT pointer
        sidecar = model_path.with_suffix('.json')
        _write_atomic(sidecar, json.dumps(meta, indent=2).encode('utf-8'))
        current = sdir / 'CURRENT.json'
        current_obj = {'file': fname, 'metadata': meta}
        _write_atomic(current, json.dumps(current_obj, indent=2).encode('utf-8'))
        app.logger.info(f"Saved models for {scoring_system} to {model_path}")
    except Exception as e:
        app.logger.warning(f"Could not save models for {scoring_system}: {e}")

def _try_load_models(scoring_system: str) -> bool:
    """Load models for a scoring system from new layout or legacy fallback."""
    try:
        sdir = _scoring_dir(scoring_system)
        current = sdir / 'CURRENT.json'
        if current.exists():
            try:
                data = json.loads(current.read_text())
                fname = data.get('file')
                if fname:
                    path = sdir / fname
                    if path.exists():
                        app.logger.info(f"Loading saved models for {scoring_system} from {path}")
                        gameday_predictor.predictor.load_models(str(path))
                        return True
            except Exception as e:
                app.logger.warning(f"CURRENT.json read error for {scoring_system}: {e}")
        # Fallback: pick latest pkl in sdir
        if sdir.exists():
            pkls = sorted(sdir.glob('*.pkl'))
            if pkls:
                path = pkls[-1]
                app.logger.info(f"Loading saved models for {scoring_system} from {path}")
                gameday_predictor.predictor.load_models(str(path))
                return True
        # Legacy fallback
        legacy = _legacy_model_path_for_scoring(scoring_system)
        if legacy.exists():
            app.logger.info(f"Loading legacy models for {scoring_system} from {legacy}")
            gameday_predictor.predictor.load_models(str(legacy))
            return True
        app.logger.info(f"No saved model found for {scoring_system}")
        return False
    except Exception as e:
        app.logger.warning(f"Failed to load saved models for {scoring_system}: {e}")
        return False

def _current_model_info(scoring_system: str) -> dict | None:
    """Read CURRENT.json for a scoring system if present."""
    try:
        sdir = _scoring_dir(scoring_system)
        current = sdir / 'CURRENT.json'
        if current.exists():
            return json.loads(current.read_text())
    except Exception as e:
        app.logger.warning(f"Model info read failed for {scoring_system}: {e}")
    return None

def _db_latest_completed_tuple() -> tuple[int, int] | None:
    latest = _latest_completed_game(None)
    return latest

def _all_scoring_systems() -> list[str]:
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("SELECT system_name FROM scoring_systems ORDER BY system_name"))
            return [r[0] for r in rows]
    except Exception:
        return []

def _model_status_for_scoring(scoring: str) -> dict:
    """Return status dict including staleness vs DB latest."""
    info = _current_model_info(scoring)
    db_latest = _db_latest_completed_tuple()
    status = {
        'scoring': scoring,
        'model': None,
        'db_latest': {'season': db_latest[0], 'week': db_latest[1]} if db_latest else None,
        'stale': True,  # default stale when unknown
    }
    if info and isinstance(info, dict):
        meta = info.get('metadata') or {}
        status['model'] = {
            'file': info.get('file'),
            'last_data_season': meta.get('last_data_season'),
            'last_data_week': meta.get('last_data_week'),
            'trained_at_utc': meta.get('trained_at_utc'),
            'seasons_used': meta.get('seasons_used')
        }
        if db_latest and meta.get('last_data_season') is not None:
            m_tuple = (int(meta.get('last_data_season')), int(meta.get('last_data_week') or 0))
            status['stale'] = m_tuple < db_latest
        else:
            status['stale'] = True
    else:
        status['model'] = None
        status['stale'] = True  # No model → stale
    return status

def _current_season_by_date() -> int:
    now = datetime.now()
    return now.year if now.month >= 9 else now.year - 1

def _train_models_for_scoring_in_background(scoring: str, seasons: list[int]):
    def _run():
        try:
            app.logger.info(f"Training models for {scoring} using seasons: {seasons}")
            gameday_predictor.predictor.train_models(seasons, scoring)
            _save_current_model(scoring, seasons)
            prediction_cache.clear()
            app.logger.info(f"Models for {scoring} trained and saved")
        except Exception as e:
            app.logger.error(f"Training failed for {scoring}: {e}")
    th = threading.Thread(target=_run)
    th.daemon = True
    th.start()
    return th

@app.route('/api/model-status')
def model_status():
    scoring = request.args.get('scoring')
    if scoring:
        return jsonify(_model_status_for_scoring(scoring))
    systems = _all_scoring_systems()
    statuses = [_model_status_for_scoring(s) for s in systems]
    return jsonify({'models': statuses})

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
                       COALESCE(ht.team_name, g.home_team_id) as home_team, 
                       g.home_team_id as home_team_id,
                       COALESCE(at.team_name, g.away_team_id) as away_team, 
                       g.away_team_id as away_team_id,
                       g.home_score, g.away_score
                FROM games g
                LEFT JOIN teams ht ON g.home_team_id = ht.team_id
                LEFT JOIN teams at ON g.away_team_id = at.team_id
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
        # Train/load cutoff model for this selection if needed
        app.logger.info(f"Generating predictions for Week {week}, {season} - {scoring_system}")

        _ensure_cutoff_model_for_request(scoring_system, season, week)
        
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

## (Removed async prediction start/progress/result endpoints)

@app.route('/api/update-data', methods=['POST'])
def update_data():
    """Update database with latest NFL data, injury reports, and schedules."""
    try:
        data = request.get_json()
        seasons = data.get('seasons', [2024, 2025])
        update_injuries = data.get('update_injuries', True)
        update_schedules = data.get('update_schedules', True)
        update_dst = data.get('update_dst', True)
        
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

                # Update team defense/special teams stats (DST)
                if update_dst:
                    app.logger.info("Collecting team defense (DST) statistics...")
                    try:
                        dst_collector = DSTCollector(db_manager)
                        dst_collector.collect_team_defense_stats(seasons)
                        app.logger.info("DST statistics collection complete")
                    except Exception as dst_error:
                        app.logger.warning(f"DST stats update failed: {dst_error}")
                
                # Normalize synthetic game IDs to official IDs (post-collection)
                try:
                    app.logger.info("Normalizing game IDs to official schedule IDs...")
                    summary = normalize_game_ids(db_manager, seasons=seasons, delete_stub_games=True)
                    app.logger.info(f"Game ID normalization summary: {summary}")
                except Exception as norm_err:
                    app.logger.warning(f"Game ID normalization skipped/failed: {norm_err}")

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
                
                # Rebuild indexes after bulk data operations
                try:
                    app.logger.info("Rebuilding database indexes for performance...")
                    db_manager.rebuild_indexes()
                    app.logger.info("Index rebuild complete")
                except Exception as e:
                    app.logger.warning(f"Index rebuild skipped/failed: {e}")

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
                'dst_stats': update_dst,
                'seasons': seasons
            },
            'model_status': {
                'models': [_model_status_for_scoring(s) for s in _all_scoring_systems()],
                'db_latest': {'season': (_db_latest_completed_tuple() or (None, None))[0],
                              'week':   (_db_latest_completed_tuple() or (None, None))[1]}
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
                # Persist trained models (versioned + CURRENT)
                _save_current_model(scoring_system, seasons)
                
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

@app.route('/api/train-stale-models', methods=['POST'])
def train_stale_models():
    """Train models for all scoring systems that are stale relative to DB latest data.

    Uses GamedayPredictor's season selection to decide training window.
    Runs in background and returns which trainings were started.
    """
    try:
        systems = _all_scoring_systems()
        db_latest = _db_latest_completed_tuple()
        started = []
        skipped = []
        current_season = _current_season_by_date()
        for scoring in systems:
            status = _model_status_for_scoring(scoring)
            if status.get('stale', True):
                seasons = gameday_predictor._get_training_seasons(current_season)
                _train_models_for_scoring_in_background(scoring, seasons)
                started.append({'scoring': scoring, 'seasons': seasons})
            else:
                skipped.append({'scoring': scoring})
        return jsonify({'status': 'started', 'started': started, 'skipped': skipped, 'db_latest': db_latest}), 202
    except Exception as e:
        app.logger.error(f"Error starting stale model training: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize models on startup
    try:
        app.logger.info("Initializing NFL Fantasy Prediction System...")
        # Attempt to load saved models for default scoring system (FanDuel)
        try:
            _try_load_models('FanDuel')
        except Exception:
            pass
        # Could pre-train models here if needed
        app.logger.info("System initialized successfully")
    except Exception as e:
        app.logger.error(f"System initialization failed: {e}")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
