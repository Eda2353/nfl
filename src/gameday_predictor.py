"""
Gameday Predictor with Real-Time Injury Integration
Combines enhanced position-specific predictions with current injury reports
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .config import Config
from .database import DatabaseManager
from .fantasy_calculator import FantasyCalculator
from .prediction_model import PlayerPredictor
from .collectors.injury_collector import InjuryCollector, GamedayInjuryFilter

class GamedayPredictor:
    """Enhanced predictor that integrates real-time injury data for gameday decisions."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.calculator = FantasyCalculator(db_manager)
        self.predictor = PlayerPredictor(db_manager, self.calculator)
        self.injury_collector = InjuryCollector()
        self.injury_filter = GamedayInjuryFilter(self.injury_collector)
        self.logger = logging.getLogger(__name__)
    
    def get_gameday_predictions(self, week: int, season: int, scoring_system: str,
                              include_injury_adjustments: bool = True) -> Dict:
        """Get comprehensive gameday predictions with injury integration."""
        
        self.logger.info(f"Generating gameday predictions for Week {week}, {season}")
        
        # Step 1: Get injury report
        injury_report = None
        if include_injury_adjustments:
            self.logger.info("Fetching current injury report...")
            injury_report = self.injury_filter.get_gameday_report()
            self.logger.info(f"Injury Report: {injury_report['total_out']} OUT, "
                           f"{injury_report['total_questionable']} Questionable")
        
        # Step 2: Get all available players for the week
        available_players = self._get_available_players(week, season)
        self.logger.info(f"Found {len(available_players)} available players")
        
        # Step 3: Generate base predictions
        player_predictions = self._generate_base_predictions(
            available_players, week, season, scoring_system
        )
        self.logger.info(f"Generated {len(player_predictions)} base predictions")
        
        # Step 4: Apply injury adjustments
        if include_injury_adjustments and player_predictions:
            self.logger.info("Applying injury adjustments...")
            
            # Filter out players listed as OUT
            player_predictions = self.injury_filter.filter_out_players(player_predictions)
            
            # Apply injury impact adjustments
            player_predictions = self.injury_filter.apply_injury_adjustments(player_predictions)
        
        # Step 5: Generate optimal lineups
        optimal_lineups = self._generate_optimal_lineups(player_predictions, scoring_system)
        
        # Step 6: Get DST predictions with injury considerations
        dst_predictions = self._get_dst_predictions_with_injuries(week, season, scoring_system)
        
        return {
            'timestamp': datetime.now(),
            'week': week,
            'season': season,
            'scoring_system': scoring_system,
            'injury_report': injury_report,
            'player_predictions': player_predictions,
            'optimal_lineups': optimal_lineups,
            'dst_predictions': dst_predictions,
            'summary': self._generate_prediction_summary(player_predictions, optimal_lineups)
        }
    
    def get_player_gameday_status(self, player_name: str, team: str = None) -> Dict:
        """Get comprehensive gameday status for a specific player."""
        
        # Check injury status
        is_out = self.injury_collector.is_player_out(player_name, team)
        
        # Get injury details if any
        injuries = self.injury_collector.get_current_injuries()
        player_injury = None
        
        for injury in injuries:
            name_match = injury.player_name.lower() == player_name.lower()
            team_match = team is None or injury.team.lower() == team.lower()
            
            if name_match and team_match:
                player_injury = injury
                break
        
        return {
            'player_name': player_name,
            'team': team,
            'is_out': is_out,
            'injury_details': player_injury,
            'recommendation': 'AVOID' if is_out else 'MONITOR' if player_injury else 'CLEAR'
        }
    
    def get_lineup_recommendations(self, week: int, season: int, scoring_system: str,
                                 budget_constraints: Optional[Dict] = None) -> Dict:
        """Get detailed lineup recommendations with injury considerations."""
        
        gameday_data = self.get_gameday_predictions(week, season, scoring_system)
        
        recommendations = {
            'top_plays': self._get_top_plays_by_position(gameday_data['player_predictions']),
            'value_plays': self._get_value_plays(gameday_data['player_predictions']),
            'injury_pivots': self._get_injury_pivot_recommendations(gameday_data),
            'stack_recommendations': self._get_stack_recommendations(gameday_data),
            'avoid_list': self._get_avoid_list(gameday_data)
        }
        
        return {
            'timestamp': gameday_data['timestamp'],
            'week': week,
            'season': season,
            'recommendations': recommendations,
            'injury_impact_summary': self._summarize_injury_impact(gameday_data)
        }
    
    def _get_available_players(self, week: int, season: int) -> List[Dict]:
        """Get all players available for the specified week."""
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            
            # Get players who have games this week
            query = text("""
                SELECT DISTINCT p.player_id, p.player_name, p.position,
                       pt.team_id
                FROM players p
                JOIN player_teams pt ON p.player_id = pt.player_id
                JOIN games g ON (pt.team_id = g.home_team_id OR pt.team_id = g.away_team_id)
                WHERE g.season_id = :season AND g.week = :week
                  AND p.position IN ('QB', 'RB', 'WR', 'TE')
                  AND pt.season_id = :season
            """)
            
            result = conn.execute(query, {'season': season, 'week': week}).fetchall()
            
            return [
                {
                    'player_id': row[0],
                    'player_name': row[1],
                    'position': row[2],
                    'team_id': row[3]
                }
                for row in result
            ]
    
    def _get_training_seasons(self, current_season: int) -> List[int]:
        """
        Get the list of seasons to use for model training.
        Includes the last 3 complete seasons plus any available data from the current season.
        """
        # Always include the last 3 complete seasons
        base_seasons = [current_season - 3, current_season - 2, current_season - 1]
        
        # Check if we have usable data from the current season
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            
            # Check for completed games in the current season
            completed_games = conn.execute(text("""
                SELECT COUNT(*) as completed_count
                FROM games 
                WHERE season_id = :season 
                AND home_score IS NOT NULL 
                AND away_score IS NOT NULL
            """), {'season': current_season}).fetchone()
            
            games_completed = completed_games[0] if completed_games else 0
            
            # Include current season if we have at least 8 completed games (roughly half of Week 1)
            if games_completed >= 8:
                training_seasons = base_seasons + [current_season]
                self.logger.info(f"Including current season {current_season} in training ({games_completed} completed games)")
            else:
                training_seasons = base_seasons
                if games_completed > 0:
                    self.logger.info(f"Excluding current season {current_season} from training (only {games_completed} completed games)")
                    
        # Filter out any seasons that might be too old or invalid
        valid_seasons = [s for s in training_seasons if s >= 2020]
        
        self.logger.info(f"Training seasons selected: {valid_seasons}")
        return valid_seasons
    
    def _generate_base_predictions(self, players: List[Dict], week: int, 
                                 season: int, scoring_system: str) -> List[Dict]:
        """Generate base predictions for all players."""
        
        predictions = []
        
        # Ensure models are trained for this scoring system
        if not hasattr(self.predictor, 'models') or not self.predictor.models:
            training_seasons = self._get_training_seasons(season)
            self.logger.info(f"Training models for {scoring_system} using seasons: {training_seasons}")
            self.predictor.train_models(training_seasons, scoring_system)
        
        failed_predictions = 0
        for player in players:
            try:
                predicted_points = self.predictor.predict_player_points(
                    player['player_id'], week, season, scoring_system
                )
                
                if predicted_points is not None and predicted_points > 0:
                    predictions.append({
                        'player_id': player['player_id'],
                        'player_name': player['player_name'],
                        'position': player['position'],
                        'team_id': player['team_id'],
                        'predicted_points': predicted_points,
                        'confidence_score': self._calculate_confidence_score(
                            player['player_id'], week, season
                        )
                    })
                else:
                    failed_predictions += 1
            except Exception as e:
                failed_predictions += 1
                self.logger.warning(f"Failed to predict for {player['player_name']}: {e}")
                continue
        
        if failed_predictions > 0:
            self.logger.warning(f"{failed_predictions} predictions failed or returned None/zero")
        
        return predictions
    
    def _generate_optimal_lineups(self, predictions: List[Dict], scoring_system: str) -> Dict:
        """Generate optimal lineups from predictions."""
        
        lineups = {}
        
        # Group by position
        by_position = {}
        for pred in predictions:
            pos = pred['position']
            if pos not in by_position:
                by_position[pos] = []
            by_position[pos].append(pred)
        
        # Sort each position by predicted points
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x['predicted_points'], reverse=True)
        
        # Create optimal lineup
        optimal_lineup = {}
        total_projected = 0
        
        for position in ['QB', 'RB', 'WR', 'TE']:
            if position in by_position and by_position[position]:
                if position == 'RB':
                    # Take top 2 RBs
                    optimal_lineup[position] = by_position[position][:2]
                elif position == 'WR':
                    # Take top 3 WRs
                    optimal_lineup[position] = by_position[position][:3]
                else:
                    # Take top 1 QB, TE
                    optimal_lineup[position] = by_position[position][:1]
                
                # Add to total projection
                for player in optimal_lineup[position]:
                    total_projected += player['predicted_points']
        
        lineups['optimal'] = {
            'players': optimal_lineup,
            'total_projected': total_projected
        }
        
        return lineups
    
    def _get_dst_predictions_with_injuries(self, week: int, season: int, 
                                         scoring_system: str) -> List[Dict]:
        """Get DST predictions considering opponent injuries."""
        
        # Get available DST teams
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            
            query = text("""
                SELECT DISTINCT g.home_team_id as team_id, g.away_team_id as opponent
                FROM games g 
                WHERE g.season_id = :season AND g.week = :week
                UNION
                SELECT DISTINCT g.away_team_id as team_id, g.home_team_id as opponent
                FROM games g 
                WHERE g.season_id = :season AND g.week = :week
            """)
            
            matchups = conn.execute(query, {'season': season, 'week': week}).fetchall()
        
        dst_predictions = []
        
        for team_id, opponent in matchups:
            try:
                base_prediction = self.predictor.predict_dst_points(
                    team_id, week, season, scoring_system
                )
                
                if base_prediction is not None:
                    # Check for opponent injuries that boost DST value
                    opponent_injuries = self.injury_collector.get_injury_impact_for_team(opponent)
                    injury_boost = self._calculate_dst_injury_boost(opponent_injuries)
                    
                    adjusted_prediction = base_prediction * (1.0 + injury_boost)
                    
                    dst_predictions.append({
                        'team_id': team_id,
                        'opponent': opponent,
                        'base_prediction': base_prediction,
                        'injury_boost': injury_boost,
                        'adjusted_prediction': adjusted_prediction,
                        'opponent_key_injuries': len([
                            p for injuries in opponent_injuries.values() 
                            for p in injuries if p.position in ['QB', 'RB', 'WR']
                        ])
                    })
                    
            except Exception as e:
                self.logger.warning(f"Failed DST prediction for {team_id}: {e}")
        
        # Sort by adjusted prediction
        dst_predictions.sort(key=lambda x: x['adjusted_prediction'], reverse=True)
        return dst_predictions
    
    def _calculate_confidence_score(self, player_id: str, week: int, season: int) -> float:
        """Calculate prediction confidence score (0-1)."""
        # Simplified confidence based on historical data availability
        return 0.75  # Placeholder - could be enhanced with more sophisticated logic
    
    def _calculate_dst_injury_boost(self, opponent_injuries: Dict) -> float:
        """Calculate DST boost from opponent injuries."""
        boost = 0.0
        
        # QB injuries have highest impact
        if 'QB' in opponent_injuries:
            for injury in opponent_injuries['QB']:
                if injury.is_out:
                    boost += 0.15  # 15% boost for backup QB
                elif injury.is_questionable:
                    boost += 0.05  # 5% boost for questionable QB
        
        # Offensive line injuries boost sack potential
        for position in ['C', 'G', 'T']:  # Center, Guard, Tackle
            if position in opponent_injuries:
                for injury in opponent_injuries[position]:
                    if injury.is_out:
                        boost += 0.03  # 3% boost per OL injury
        
        return min(boost, 0.25)  # Cap at 25% boost
    
    def _get_top_plays_by_position(self, predictions: List[Dict]) -> Dict:
        """Get top plays by position."""
        by_position = {}
        for pred in predictions:
            pos = pred['position']
            if pos not in by_position:
                by_position[pos] = []
            by_position[pos].append(pred)
        
        top_plays = {}
        for pos, players in by_position.items():
            players.sort(key=lambda x: x['predicted_points'], reverse=True)
            top_plays[pos] = players[:5]  # Top 5 per position
        
        return top_plays
    
    def _get_value_plays(self, predictions: List[Dict]) -> List[Dict]:
        """Identify value plays (high projected points, potentially lower owned)."""
        # Simplified - could integrate salary data for true value calculation
        return sorted(predictions, key=lambda x: x['predicted_points'], reverse=True)[10:20]
    
    def _get_injury_pivot_recommendations(self, gameday_data: Dict) -> List[Dict]:
        """Get pivot recommendations based on injuries."""
        pivots = []
        
        if gameday_data['injury_report']:
            out_players = gameday_data['injury_report']['out_by_position']
            
            for position, injured_players in out_players.items():
                for injured in injured_players:
                    # Find backup/replacement players on same team
                    team_players = [
                        p for p in gameday_data['player_predictions']
                        if p.get('team_id') == injured.team and p['position'] == position
                    ]
                    
                    if team_players:
                        best_replacement = max(team_players, key=lambda x: x['predicted_points'])
                        pivots.append({
                            'injured_player': injured.player_name,
                            'recommended_pivot': best_replacement['player_name'],
                            'pivot_projection': best_replacement['predicted_points'],
                            'reason': f"{injured.player_name} ruled OUT"
                        })
        
        return pivots
    
    def _get_stack_recommendations(self, gameday_data: Dict) -> List[Dict]:
        """Get QB-WR stack recommendations considering injuries."""
        # Simplified stacking logic
        return []  # Could be expanded
    
    def _get_avoid_list(self, gameday_data: Dict) -> List[Dict]:
        """Get players to avoid due to injuries or other factors."""
        avoid_list = []
        
        if gameday_data['injury_report']:
            # Add all OUT players
            out_players = gameday_data['injury_report']['out_by_position']
            for position, players in out_players.items():
                for player in players:
                    avoid_list.append({
                        'player_name': player.player_name,
                        'position': player.position,
                        'team': player.team,
                        'reason': f"OUT - {player.injury_type}"
                    })
        
        return avoid_list
    
    def _generate_prediction_summary(self, predictions: List[Dict], lineups: Dict) -> Dict:
        """Generate summary of predictions."""
        if not predictions:
            return {}
        
        total_players = len(predictions)
        avg_projection = sum(p['predicted_points'] for p in predictions) / total_players
        
        return {
            'total_players_analyzed': total_players,
            'average_projection': avg_projection,
            'top_projection': max(p['predicted_points'] for p in predictions),
            'optimal_lineup_projection': lineups.get('optimal', {}).get('total_projected', 0)
        }
    
    def _summarize_injury_impact(self, gameday_data: Dict) -> Dict:
        """Summarize the impact of injuries on predictions."""
        if not gameday_data.get('injury_report'):
            return {'total_impact': 'No injury data available'}
        
        injury_report = gameday_data['injury_report']
        
        return {
            'players_out': injury_report['total_out'],
            'players_questionable': injury_report['total_questionable'],
            'high_impact_teams': injury_report.get('high_impact_teams', []),
            'positions_most_affected': list(injury_report.get('out_by_position', {}).keys())
        }