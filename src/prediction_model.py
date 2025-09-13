"""Player performance prediction model using historical data and machine learning."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error
import pickle
from pathlib import Path

try:
    from .database import DatabaseManager
    from .fantasy_calculator import FantasyCalculator
    from .matchup_analyzer import MatchupAnalyzer
    from .position_matchup_analyzer import PositionMatchupAnalyzer
    from .config import Config
except ImportError:
    from database import DatabaseManager
    from fantasy_calculator import FantasyCalculator
    from matchup_analyzer import MatchupAnalyzer
    from position_matchup_analyzer import PositionMatchupAnalyzer
    from config import Config


@dataclass
class PredictionFeatures:
    """Features used for prediction."""
    player_id: str
    week: int
    season: int
    
    # Recent performance (last 3 games)
    avg_fantasy_points_l3: float = 0.0
    avg_targets_l3: float = 0.0
    avg_carries_l3: float = 0.0
    avg_passing_attempts_l3: float = 0.0
    
    # Season-to-date averages
    avg_fantasy_points_season: float = 0.0
    games_played_season: int = 0
    
    # Position and team context
    position_encoded: int = 0  # QB=0, RB=1, WR=2, TE=3
    
    # Target share and usage metrics
    target_share_l3: float = 0.0
    red_zone_looks_l3: float = 0.0
    
    # Advanced metrics
    consistency_score: float = 0.0  # Standard deviation of last 5 games
    trend_score: float = 0.0  # Linear trend of last 5 games
    
    # Enhanced position-specific matchup intelligence
    position_matchup_features: dict = field(default_factory=dict)  # Position-specific matchup features


@dataclass
class DSTFeatures:
    """Features used for DST prediction."""
    team_id: str
    week: int
    season: int
    
    # Recent defensive performance (last 3 games)
    avg_points_allowed_l3: float = 0.0
    avg_sacks_l3: float = 0.0
    avg_turnovers_l3: float = 0.0
    avg_fantasy_points_l3: float = 0.0
    
    # Season averages
    avg_points_allowed_season: float = 0.0
    avg_sacks_season: float = 0.0
    avg_turnovers_season: float = 0.0
    avg_fantasy_points_season: float = 0.0
    games_played_season: int = 0
    
    # Opponent strength (points scored by opponents recently)
    opponent_avg_points_l3: float = 0.0
    opponent_avg_points_season: float = 0.0
    
    # Home/away context
    is_home: int = 0  # 1 for home, 0 for away
    
    # Trend metrics
    consistency_score: float = 0.0
    trend_score: float = 0.0
    
    # Matchup intelligence
    opponent_offensive_score: float = 0.0  # Opponent's offensive strength (0-100)
    matchup_points_modifier: float = 1.0  # Expected points modifier based on matchup
    matchup_sack_modifier: float = 1.0  # Sack likelihood modifier


class PlayerPredictor:
    """Predict individual player performance for fantasy football."""
    
    def __init__(self, db_manager: DatabaseManager, calculator: FantasyCalculator):
        self.db = db_manager
        self.calculator = calculator
        self.matchup_analyzer = MatchupAnalyzer(db_manager, calculator)
        self.position_matchup_analyzer = PositionMatchupAnalyzer(db_manager, calculator)
        self.models = {}  # One model per position
        self.scalers = {}  # One scaler per position
        self.feature_columns = []
        self._feature_cache = {}
        
    def extract_features(self, player_id: str, target_week: int, target_season: int, 
                        scoring_system: str = 'FanDuel') -> Optional[PredictionFeatures]:
        """Extract prediction features for a player at a specific week."""
        
        # Get player info
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            player_info = pd.read_sql_query(text("""
                SELECT position FROM players WHERE player_id = :player_id
            """), conn, params={'player_id': player_id})
        
        if player_info.empty:
            return None
            
        position = player_info.iloc[0]['position']
        
        # Get historical games up to target week (exclusive)
        with self.db.engine.connect() as conn:
            historical_games = pd.read_sql_query(text("""
                SELECT gs.*, g.week, g.season_id
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                WHERE gs.player_id = :player_id 
                  AND (g.season_id < :season OR (g.season_id = :season AND g.week < :week))
                ORDER BY g.season_id DESC, g.week DESC
                LIMIT 50
            """), conn, params={
                'player_id': player_id, 
                'season': target_season, 
                'week': target_week
            })
        
        if len(historical_games) < 3:  # Need at least 3 games of history
            return None
        
        # Calculate fantasy points for each historical game
        fantasy_points = []
        for _, game in historical_games.iterrows():
            points = self.calculator.calculate_player_points(game, scoring_system)
            fantasy_points.append(points.total_points)
        
        historical_games['fantasy_points'] = fantasy_points
        
        # Extract features
        features = PredictionFeatures(
            player_id=player_id,
            week=target_week,
            season=target_season
        )
        
        # Recent performance (last 3 games)
        recent_3 = historical_games.head(3)
        features.avg_fantasy_points_l3 = recent_3['fantasy_points'].mean()
        features.avg_targets_l3 = recent_3['receiving_targets'].mean()
        features.avg_carries_l3 = recent_3['rush_attempts'].mean()
        features.avg_passing_attempts_l3 = recent_3['pass_attempts'].mean()
        features.target_share_l3 = recent_3['target_share'].mean() if not recent_3['target_share'].isna().all() else 0
        
        # Season-to-date averages (current season only)
        current_season_games = historical_games[historical_games['season_id'] == target_season]
        if not current_season_games.empty:
            features.avg_fantasy_points_season = current_season_games['fantasy_points'].mean()
            features.games_played_season = len(current_season_games)
        
        # Position encoding
        position_map = {'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3}
        features.position_encoded = position_map.get(position, 4)
        
        # Consistency and trend analysis
        recent_5 = historical_games.head(5)
        if len(recent_5) >= 3:
            features.consistency_score = recent_5['fantasy_points'].std()
            
            # Calculate trend (slope of last 5 games)
            if len(recent_5) >= 4:
                x = np.arange(len(recent_5))
                y = recent_5['fantasy_points'].values
                features.trend_score = np.polyfit(x, y, 1)[0]  # Linear slope
        
        # Get player's team for enhanced position-specific matchup analysis
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            team_info = pd.read_sql_query(text("""
                SELECT DISTINCT gs.team_id
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                WHERE gs.player_id = :player_id 
                  AND g.season_id = :season 
                  AND g.week < :week
                ORDER BY g.week DESC
                LIMIT 1
            """), conn, params={
                'player_id': player_id,
                'season': target_season,
                'week': target_week
            })
        
        if not team_info.empty:
            player_team = team_info.iloc[0]['team_id']
            
            # Get opponent team
            opponent_team = self.matchup_analyzer.get_opponent_for_team(player_team, target_season, target_week)
            
            if opponent_team:
                # Get position-specific matchup features
                position_features = self.position_matchup_analyzer.get_position_matchup_features(
                    position, player_team, opponent_team, target_season, target_week
                )
                
                # Store position-specific features (will be extracted differently per position)
                features.position_matchup_features = position_features
            else:
                features.position_matchup_features = {}
        
        return features
    
    def _get_position_feature_order(self, position: str) -> List[str]:
        """Get consistent ordering of position-specific features for model input."""
        
        position_feature_maps = {
            'QB': [
                'opponent_pass_defense_rank',
                'opponent_pass_rush_pressure', 
                'opponent_turnover_creation',
                'qb_efficiency_modifier',
                'qb_ceiling_modifier'
            ],
            'RB': [
                'opponent_rush_defense_rank',
                'opponent_rb_receiving_weakness',
                'rb_volume_modifier',
                'rb_efficiency_modifier',
                'rb_goal_line_advantage'
            ],
            'WR': [
                'opponent_pass_defense_rank',
                'opponent_wr_coverage_weakness',
                'wr_pressure_impact',
                'wr_efficiency_modifier',
                'wr_ceiling_modifier'
            ],
            'TE': [
                'opponent_te_coverage_weakness',
                'opponent_pass_defense_rank',
                'te_checkdown_opportunity',
                'te_efficiency_modifier',
                'te_red_zone_advantage'
            ]
        }
        
        return position_feature_maps.get(position, [])
    
    def prepare_training_data(self, seasons: List[int], scoring_system: str = 'FanDuel') -> Dict[str, pd.DataFrame]:
        """Prepare training data for all positions."""
        
        position_data = {'QB': [], 'RB': [], 'WR': [], 'TE': []}
        
        # Get all players and their games
        seasons_str = ','.join(map(str, seasons))
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            all_games = pd.read_sql_query(text(f"""
                SELECT gs.player_id, p.player_name, p.position, g.season_id, g.week,
                       gs.pass_yards, gs.pass_touchdowns, gs.pass_interceptions,
                       gs.rush_yards, gs.rush_touchdowns, gs.rush_fumbles,
                       gs.receptions, gs.receiving_yards, gs.receiving_touchdowns, 
                       gs.receiving_targets, gs.receiving_fumbles, gs.target_share
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                JOIN players p ON gs.player_id = p.player_id
                WHERE g.season_id IN ({seasons_str})
                  AND p.position IN ('QB', 'RB', 'WR', 'TE')
                ORDER BY gs.player_id, g.season_id, g.week
            """), conn)
        
        print(f"Processing {len(all_games)} games for training data...")
        
        # For each game, create a training example predicting that game's performance
        for _, game in all_games.iterrows():
            player_id = game['player_id']
            position = game['position']
            week = game['week']
            season = game['season_id']
            
            # Skip week 1 (no historical data)
            if week <= 2:
                continue
                
            # Extract features for predicting this game
            features = self.extract_features(player_id, week, season, scoring_system)
            if features is None:
                continue
            
            # Calculate actual fantasy points for this game
            actual_points = self.calculator.calculate_player_points(game, scoring_system)
            
            # Add to training data with position-specific features
            feature_dict = {
                'avg_fantasy_points_l3': features.avg_fantasy_points_l3,
                'avg_targets_l3': features.avg_targets_l3,
                'avg_carries_l3': features.avg_carries_l3,
                'avg_passing_attempts_l3': features.avg_passing_attempts_l3,
                'avg_fantasy_points_season': features.avg_fantasy_points_season,
                'games_played_season': features.games_played_season,
                'position_encoded': features.position_encoded,
                'target_share_l3': features.target_share_l3,
                'consistency_score': features.consistency_score,
                'trend_score': features.trend_score,
                'target': actual_points.total_points
            }
            
            # Add position-specific matchup features
            if features.position_matchup_features:
                feature_dict.update(features.position_matchup_features)
            
            if position in position_data:
                position_data[position].append(feature_dict)
        
        # Convert to DataFrames
        for position in position_data:
            if position_data[position]:
                position_data[position] = pd.DataFrame(position_data[position])
                print(f"{position}: {len(position_data[position])} training examples")
            else:
                position_data[position] = pd.DataFrame()
        
        return position_data

    # ------------------ Batched feature cache for prediction ------------------
    def prepare_prediction_cache(self, player_ids: List[str], target_week: int, target_season: int,
                                 scoring_system: str = 'FanDuel',
                                 meta_cb=None, tick_cb=None) -> None:
        """Prefetch historical games for many players at once and cache them per-player.

        This reduces per-player SQL round-trips during prediction.
        """
        if not player_ids:
            return
        uniq_ids = list({pid for pid in player_ids if pid})
        # Fetch historical games for all players in one pass
        placeholders = ','.join([f":p{i}" for i in range(len(uniq_ids))])
        params = {f"p{i}": pid for i, pid in enumerate(uniq_ids)}
        params.update({'season': target_season, 'week': target_week})
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            historical = pd.read_sql_query(text(f"""
                SELECT gs.*, g.week, g.season_id
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                WHERE gs.player_id IN ({placeholders})
                  AND (g.season_id < :season OR (g.season_id = :season AND g.week < :week))
                ORDER BY gs.player_id, g.season_id DESC, g.week DESC
            """), conn, params=params)

        # Compute fantasy points once for all rows
        if not historical.empty:
            total = len(historical)
            if meta_cb:
                try:
                    meta_cb(total)
                except Exception:
                    pass
            # Process in chunks to provide progress feedback
            def _fp(row):
                pts = self.calculator.calculate_player_points(row, scoring_system)
                return pts.total_points
            # Preallocate column
            historical['fantasy_points'] = 0.0
            chunk = max(200, total // 200)
            done = 0
            for start in range(0, total, chunk):
                end = min(start + chunk, total)
                chunk_df = historical.iloc[start:end]
                historical.loc[chunk_df.index, 'fantasy_points'] = chunk_df.apply(_fp, axis=1)
                done = end
                if tick_cb:
                    try:
                        tick_cb(done, total, f"Preparing features {done}/{total}")
                    except Exception:
                        pass
            # Group per player and cache
            grouped = historical.groupby('player_id')
            self._feature_cache = {pid: df for pid, df in grouped}
        else:
            if meta_cb:
                try:
                    meta_cb(0)
                except Exception:
                    pass
            self._feature_cache = {}
    
    def train_models(self, seasons: List[int], scoring_system: str = 'FanDuel'):
        """Train prediction models for each position."""
        
        print(f"Training models for seasons: {seasons}")
        
        # Prepare training data
        position_data = self.prepare_training_data(seasons, scoring_system)

        
        
        self.feature_columns = [
            'avg_fantasy_points_l3', 'avg_targets_l3', 'avg_carries_l3', 
            'avg_passing_attempts_l3', 'avg_fantasy_points_season', 'games_played_season',
            'position_encoded', 'target_share_l3', 'consistency_score', 'trend_score'
        ]
        
        for position in ['QB', 'RB', 'WR', 'TE']:
            data = position_data[position]
            
            if len(data) < 50:  # Need minimum data
                print(f"Insufficient data for {position}: {len(data)} examples")
                continue
            
            # Prepare features - use base features only for historical compatibility
            # Position-specific features will be added for future enhanced training
            X = data[self.feature_columns].fillna(0)
            y = data['target']
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train ensemble of models
            models = {
                # Use all CPU cores for RandomForest to speed up training
                'rf': RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
                'gb': GradientBoostingRegressor(n_estimators=100, random_state=42),
                'ridge': Ridge(alpha=1.0)
            }
            
            best_model = None
            best_score = float('inf')
            
            for model_name, model in models.items():
                if model_name == 'ridge':
                    model.fit(X_train_scaled, y_train)
                    y_pred = model.predict(X_test_scaled)
                else:
                    model.fit(X_train, y_train)
                    y_pred = model.predict(X_test)
                
                mae = mean_absolute_error(y_test, y_pred)
                rmse = np.sqrt(mean_squared_error(y_test, y_pred))
                
                print(f"{position} {model_name}: MAE={mae:.2f}, RMSE={rmse:.2f}")
                
                if mae < best_score:
                    best_score = mae
                    best_model = model
                    self.scalers[position] = scaler if model_name == 'ridge' else StandardScaler().fit(X_train)
            
            self.models[position] = best_model
            print(f"Best model for {position}: MAE={best_score:.2f}")
        
        # Mark that current models only support base features (historical compatibility)
        self.supports_position_features = False
        
        # Train DST model
        print("\n" + "="*50)
        print("Training DST model...")
        self.train_dst_model(seasons, scoring_system)
    
    def predict_player_points(self, player_id: str, week: int, season: int, 
                             scoring_system: str = 'FanDuel') -> Optional[float]:
        """Predict fantasy points for a specific player and week."""
        
        # Get player position
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            player_info = pd.read_sql_query(text("""
                SELECT position FROM players WHERE player_id = :player_id
            """), conn, params={'player_id': player_id})
        
        if player_info.empty:
            return None
            
        position = player_info.iloc[0]['position']
        
        if position not in self.models:
            return None
        
        # Extract features (use cache if available)
        cached_df = self._feature_cache.get(player_id)
        if cached_df is not None and len(cached_df) >= 3:
            # Build features from cached historical rows
            historical_games = cached_df
            recent_3 = historical_games.head(3)
            avg_fp_l3 = recent_3['fantasy_points'].mean()
            avg_targets_l3 = recent_3['receiving_targets'].mean()
            avg_carries_l3 = recent_3['rush_attempts'].mean()
            avg_pass_att_l3 = recent_3['pass_attempts'].mean()
            target_share_l3 = (recent_3['target_share'].mean()
                               if 'target_share' in recent_3 and not recent_3['target_share'].isna().all() else 0)
            current_season_games = historical_games[historical_games['season_id'] == season]
            avg_fp_season = current_season_games['fantasy_points'].mean() if not current_season_games.empty else 0
            games_played_season = len(current_season_games)
            # Position encoding
            with self.db.engine.connect() as conn:
                from sqlalchemy import text
                pos_df = pd.read_sql_query(text("SELECT position FROM players WHERE player_id = :pid"), conn, params={'pid': player_id})
            position = pos_df.iloc[0]['position'] if not pos_df.empty else 'UNK'
            position_map = {'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3}
            pos_enc = position_map.get(position, 4)
            # Consistency/trend
            recent_5 = historical_games.head(5)
            consistency = recent_5['fantasy_points'].std() if len(recent_5) >= 3 else 0
            trend = 0
            if len(recent_5) >= 4:
                x = np.arange(len(recent_5))
                y = recent_5['fantasy_points'].values
                trend = np.polyfit(x, y, 1)[0]
            base_features = [
                avg_fp_l3, avg_targets_l3, avg_carries_l3, avg_pass_att_l3,
                avg_fp_season, games_played_season, pos_enc, target_share_l3,
                consistency, trend
            ]
            feature_names = [
                'avg_fantasy_points_l3', 'avg_targets_l3', 'avg_carries_l3', 
                'avg_passing_attempts_l3', 'avg_fantasy_points_season', 'games_played_season',
                'position_encoded', 'target_share_l3', 'consistency_score', 'trend_score'
            ]
            X = pd.DataFrame([base_features], columns=feature_names)
            if isinstance(self.models[position], Ridge):
                X = self.scalers[position].transform(X)
            else:
                X = X.values
            pred = self.models[position].predict(X)[0]
            return float(max(0, pred))
        
        # Fallback to on-demand extraction
        features = self.extract_features(player_id, week, season, scoring_system)
        if features is None:
            return None
        
        # Prepare base feature vector
        base_features = [
            features.avg_fantasy_points_l3,
            features.avg_targets_l3,
            features.avg_carries_l3,
            features.avg_passing_attempts_l3,
            features.avg_fantasy_points_season,
            features.games_played_season,
            features.position_encoded,
            features.target_share_l3,
            features.consistency_score,
            features.trend_score
        ]
        
        # Add position-specific matchup features if available and models support them
        # For backward compatibility with models trained on historical data
        if hasattr(self, 'supports_position_features') and self.supports_position_features:
            position_specific_order = self._get_position_feature_order(position)
            for feature_name in position_specific_order:
                value = features.position_matchup_features.get(feature_name, 0.0) if features.position_matchup_features else 0.0
                base_features.append(value)
        
        feature_vector = base_features
        
        # Create feature array - use pandas DataFrame to preserve feature names for scaler
        feature_names = [
            'avg_fantasy_points_l3', 'avg_targets_l3', 'avg_carries_l3', 
            'avg_passing_attempts_l3', 'avg_fantasy_points_season', 'games_played_season',
            'position_encoded', 'target_share_l3', 'consistency_score', 'trend_score'
        ]
        
        if hasattr(self, 'supports_position_features') and self.supports_position_features:
            position_specific_order = self._get_position_feature_order(position)
            feature_names.extend(position_specific_order)
        
        X = pd.DataFrame([feature_vector], columns=feature_names[:len(feature_vector)])
        
        # Scale if using Ridge regression
        if isinstance(self.models[position], Ridge):
            X = self.scalers[position].transform(X)
        else:
            X = X.values
        
        # Make prediction
        prediction = self.models[position].predict(X)[0]
        
        # Ensure non-negative prediction
        return max(0, prediction)
    
    def save_models(self, filepath: str):
        """Save trained models to disk."""
        model_data = {
            'models': self.models,
            'scalers': self.scalers,
            'feature_columns': self.feature_columns
        }
        
        # Add DST feature columns if available
        if hasattr(self, 'dst_feature_columns'):
            model_data['dst_feature_columns'] = self.dst_feature_columns
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"Models saved to {filepath}")
    
    def load_models(self, filepath: str):
        """Load trained models from disk."""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        self.models = model_data['models']
        self.scalers = model_data['scalers']
        self.feature_columns = model_data['feature_columns']
        
        # Load DST feature columns if available
        if 'dst_feature_columns' in model_data:
            self.dst_feature_columns = model_data['dst_feature_columns']
        
        print(f"Models loaded from {filepath}")
        print(f"Loaded models: {list(self.models.keys())}")
    
    def get_top_predictions(self, week: int, season: int, position: str = None,
                          scoring_system: str = 'FanDuel', limit: int = 20) -> pd.DataFrame:
        """Get top predicted performers for a given week."""
        
        # Get all active players for that week
        conditions = ["p.position IN ('QB', 'RB', 'WR', 'TE')"]
        params = {'season': season}
        
        if position:
            conditions.append("p.position = :position")
            params['position'] = position
        
        where_clause = " AND ".join(conditions)
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            players = pd.read_sql_query(text(f"""
                SELECT DISTINCT p.player_id, p.player_name, p.position
                FROM players p
                JOIN game_stats gs ON p.player_id = gs.player_id
                JOIN games g ON gs.game_id = g.game_id
                WHERE {where_clause}
                  AND g.season_id = :season
                  AND g.week < :week
            """), conn, params={**params, 'week': week})
        
        predictions = []
        
        for _, player in players.iterrows():
            prediction = self.predict_player_points(
                player['player_id'], week, season, scoring_system
            )
            
            if prediction is not None:
                predictions.append({
                    'player_id': player['player_id'],
                    'player_name': player['player_name'],
                    'position': player['position'],
                    'predicted_points': prediction,
                    'week': week,
                    'season': season,
                    'scoring_system': scoring_system
                })
        
        results_df = pd.DataFrame(predictions)
        
        if not results_df.empty:
            results_df = results_df.sort_values('predicted_points', ascending=False)
            return results_df.head(limit)
        
        return pd.DataFrame()
    
    def extract_dst_features(self, team_id: str, target_week: int, target_season: int,
                            scoring_system: str = 'FanDuel') -> Optional[DSTFeatures]:
        """Extract prediction features for a DST at a specific week."""
        
        # Get historical DST performance up to target week (exclusive)
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            historical_dst = pd.read_sql_query(text("""
                SELECT *
                FROM team_defense_stats
                WHERE team_id = :team_id 
                  AND (season_id < :season OR (season_id = :season AND week < :week))
                ORDER BY season_id DESC, week DESC
                LIMIT 20
            """), conn, params={
                'team_id': team_id,
                'season': target_season,
                'week': target_week
            })
        
        if len(historical_dst) < 3:  # Need at least 3 games of history
            return None
        
        # Calculate fantasy points for each historical game
        fantasy_points = []
        for _, game in historical_dst.iterrows():
            points = self.calculator.calculate_dst_points(game, scoring_system)
            fantasy_points.append(points.total_points)
        
        historical_dst['fantasy_points'] = fantasy_points
        
        # Extract features
        features = DSTFeatures(
            team_id=team_id,
            week=target_week,
            season=target_season
        )
        
        # Recent performance (last 3 games)
        recent_3 = historical_dst.head(3)
        features.avg_points_allowed_l3 = recent_3['points_allowed'].mean()
        features.avg_sacks_l3 = recent_3['sacks'].mean()
        # Ensure numeric types for calculations
        interceptions_l3 = pd.to_numeric(recent_3['interceptions'], errors='coerce').fillna(0)
        fumbles_recovered_l3 = pd.to_numeric(recent_3['fumbles_recovered'], errors='coerce').fillna(0)
        features.avg_turnovers_l3 = (interceptions_l3 + fumbles_recovered_l3).mean()
        features.avg_fantasy_points_l3 = recent_3['fantasy_points'].mean()
        
        # Season-to-date averages (current season only)
        current_season_games = historical_dst[historical_dst['season_id'] == target_season]
        if not current_season_games.empty:
            features.avg_points_allowed_season = current_season_games['points_allowed'].mean()
            features.avg_sacks_season = current_season_games['sacks'].mean()
            # Ensure numeric types for calculations
            interceptions_season = pd.to_numeric(current_season_games['interceptions'], errors='coerce').fillna(0)
            fumbles_recovered_season = pd.to_numeric(current_season_games['fumbles_recovered'], errors='coerce').fillna(0)
            features.avg_turnovers_season = (interceptions_season + fumbles_recovered_season).mean()
            features.avg_fantasy_points_season = current_season_games['fantasy_points'].mean()
            features.games_played_season = len(current_season_games)
        
        # Get opponent strength (how many points do upcoming opponents typically score)
        # This would need opponent schedule information, for now use league average
        features.opponent_avg_points_l3 = 21.0  # NFL average points per game
        features.opponent_avg_points_season = 21.0
        
        # Home/away context (would need game schedule info, default to home)
        features.is_home = 1
        
        # Consistency and trend analysis
        recent_5 = historical_dst.head(5)
        if len(recent_5) >= 3:
            features.consistency_score = recent_5['fantasy_points'].std()
            
            # Calculate trend (slope of last 5 games)
            if len(recent_5) >= 4:
                x = np.arange(len(recent_5))
                y = recent_5['fantasy_points'].values
                features.trend_score = np.polyfit(x, y, 1)[0]  # Linear slope
        
        # Get matchup analysis (DST defense vs opponent offense)
        matchup = self.matchup_analyzer.get_matchup_for_dst(team_id, target_season, target_week)
        if matchup:
            features.opponent_offensive_score = matchup.offense_strength.offensive_score
            features.matchup_points_modifier = matchup.points_modifier
            features.matchup_sack_modifier = matchup.sack_modifier
        
        return features
    
    def train_dst_model(self, seasons: List[int], scoring_system: str = 'FanDuel'):
        """Train prediction model for DST."""
        
        print(f"Training DST model for seasons: {seasons}")
        
        # Prepare training data
        dst_data = []
        
        # Get all DST games (no need to join with games table as DST table has season_id/week)
        seasons_str = ','.join(map(str, seasons))
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            all_dst_games = pd.read_sql_query(text(f"""
                SELECT team_id, game_id, season_id, week,
                       points_allowed, sacks, interceptions, fumbles_recovered,
                       defensive_touchdowns, pick_six, fumble_touchdowns, 
                       return_touchdowns, safeties
                FROM team_defense_stats
                WHERE season_id IN ({seasons_str})
                ORDER BY team_id, season_id, week
            """), conn)
        
        print(f"Processing {len(all_dst_games)} DST games for training data...")
        
        # For each game, create a training example predicting that game's performance
        for _, game in all_dst_games.iterrows():
            team_id = game['team_id']
            week = game['week']
            season = game['season_id']
            
            # Skip early weeks (no historical data)
            if week <= 2:
                continue
            
            # Extract features for predicting this game
            features = self.extract_dst_features(team_id, week, season, scoring_system)
            if features is None:
                continue
            
            # Calculate actual fantasy points for this game
            actual_points = self.calculator.calculate_dst_points(game, scoring_system)
            
            # Add to training data
            feature_dict = {
                'avg_points_allowed_l3': features.avg_points_allowed_l3,
                'avg_sacks_l3': features.avg_sacks_l3,
                'avg_turnovers_l3': features.avg_turnovers_l3,
                'avg_fantasy_points_l3': features.avg_fantasy_points_l3,
                'avg_points_allowed_season': features.avg_points_allowed_season,
                'avg_sacks_season': features.avg_sacks_season,
                'avg_turnovers_season': features.avg_turnovers_season,
                'avg_fantasy_points_season': features.avg_fantasy_points_season,
                'games_played_season': features.games_played_season,
                'opponent_avg_points_l3': features.opponent_avg_points_l3,
                'opponent_avg_points_season': features.opponent_avg_points_season,
                'is_home': features.is_home,
                'consistency_score': features.consistency_score,
                'trend_score': features.trend_score,
                'opponent_offensive_score': features.opponent_offensive_score,
                'matchup_points_modifier': features.matchup_points_modifier,
                'matchup_sack_modifier': features.matchup_sack_modifier,
                'target': actual_points.total_points
            }
            
            dst_data.append(feature_dict)
        
        if len(dst_data) < 50:
            print(f"Insufficient DST data: {len(dst_data)} examples")
            return
        
        # Convert to DataFrame
        dst_df = pd.DataFrame(dst_data)
        print(f"DST: {len(dst_df)} training examples")
        
        # Define feature columns for DST
        dst_feature_columns = [
            'avg_points_allowed_l3', 'avg_sacks_l3', 'avg_turnovers_l3', 'avg_fantasy_points_l3',
            'avg_points_allowed_season', 'avg_sacks_season', 'avg_turnovers_season', 'avg_fantasy_points_season',
            'games_played_season', 'opponent_avg_points_l3', 'opponent_avg_points_season', 
            'is_home', 'consistency_score', 'trend_score',
            'opponent_offensive_score', 'matchup_points_modifier', 'matchup_sack_modifier'
        ]
        
        # Prepare features and target
        X = dst_df[dst_feature_columns].fillna(0)
        y = dst_df['target']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train models
        models = {
            # Use all CPU cores for RandomForest to speed up training
            'rf': RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
            'gb': GradientBoostingRegressor(n_estimators=100, random_state=42),
            'ridge': Ridge(alpha=1.0)
        }
        
        best_model = None
        best_score = float('inf')
        
        for model_name, model in models.items():
            if model_name == 'ridge':
                model.fit(X_train_scaled, y_train)
                y_pred = model.predict(X_test_scaled)
            else:
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)
            
            mae = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            
            print(f"DST {model_name}: MAE={mae:.2f}, RMSE={rmse:.2f}")
            
            if mae < best_score:
                best_score = mae
                best_model = model
                self.scalers['DST'] = scaler if model_name == 'ridge' else StandardScaler().fit(X_train)
        
        self.models['DST'] = best_model
        if not hasattr(self, 'dst_feature_columns'):
            self.dst_feature_columns = dst_feature_columns
        print(f"Best model for DST: MAE={best_score:.2f}")
    
    def predict_dst_points(self, team_id: str, week: int, season: int, 
                          scoring_system: str = 'FanDuel') -> Optional[float]:
        """Predict fantasy points for a specific DST and week."""
        
        if 'DST' not in self.models:
            return None
        
        # Extract features
        features = self.extract_dst_features(team_id, week, season, scoring_system)
        if features is None:
            return None
        
        # Prepare feature vector
        feature_vector = [
            features.avg_points_allowed_l3,
            features.avg_sacks_l3,
            features.avg_turnovers_l3,
            features.avg_fantasy_points_l3,
            features.avg_points_allowed_season,
            features.avg_sacks_season,
            features.avg_turnovers_season,
            features.avg_fantasy_points_season,
            features.games_played_season,
            features.opponent_avg_points_l3,
            features.opponent_avg_points_season,
            features.is_home,
            features.consistency_score,
            features.trend_score,
            features.opponent_offensive_score,
            features.matchup_points_modifier,
            features.matchup_sack_modifier
        ]
        
        X = np.array(feature_vector).reshape(1, -1)
        
        # Scale if using Ridge regression
        if isinstance(self.models['DST'], Ridge):
            X = self.scalers['DST'].transform(X)
        
        # Make prediction
        prediction = self.models['DST'].predict(X)[0]
        
        # Ensure reasonable prediction bounds
        return max(0, min(30, prediction))  # DST scores typically 0-30 points
