"""Comprehensive opponent strength and matchup analysis for fantasy predictions."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sqlalchemy import text

try:
    from .database import DatabaseManager
    from .fantasy_calculator import FantasyCalculator
except ImportError:
    from database import DatabaseManager
    from fantasy_calculator import FantasyCalculator


@dataclass
class OffensiveStrength:
    """Offensive strength metrics for a team."""
    team_id: str
    season: int
    week: int
    
    # Overall offensive power
    points_per_game: float = 0.0
    yards_per_game: float = 0.0
    
    # Position-specific strengths
    passing_yards_per_game: float = 0.0
    rushing_yards_per_game: float = 0.0
    passing_tds_per_game: float = 0.0
    rushing_tds_per_game: float = 0.0
    
    # Turnover tendencies
    turnovers_per_game: float = 0.0
    sacks_allowed_per_game: float = 0.0
    
    # Advanced metrics
    red_zone_efficiency: float = 0.0
    third_down_conversion: float = 0.0
    
    # Overall strength score (0-100)
    offensive_score: float = 0.0


@dataclass
class DefensiveStrength:
    """Defensive strength metrics for a team."""
    team_id: str
    season: int
    week: int
    
    # Overall defensive power
    points_allowed_per_game: float = 0.0
    yards_allowed_per_game: float = 0.0
    
    # Position-specific defensive strength
    passing_yards_allowed_per_game: float = 0.0
    rushing_yards_allowed_per_game: float = 0.0
    
    # Turnover generation
    sacks_per_game: float = 0.0
    interceptions_per_game: float = 0.0
    fumbles_recovered_per_game: float = 0.0
    turnovers_forced_per_game: float = 0.0
    
    # Advanced metrics
    red_zone_defense: float = 0.0
    third_down_defense: float = 0.0
    
    # Overall strength score (0-100)
    defensive_score: float = 0.0


@dataclass
class MatchupStrength:
    """Complete matchup analysis between two teams."""
    offensive_team: str
    defensive_team: str
    season: int
    week: int
    
    # Team strength profiles
    offense_strength: OffensiveStrength
    defense_strength: DefensiveStrength
    
    # Matchup analysis
    matchup_type: str  # "Strong vs Strong", "Strong vs Weak", etc.
    offensive_advantage: float  # -100 to +100
    defensive_advantage: float  # -100 to +100
    
    # Predicted impact modifiers
    points_modifier: float = 1.0  # Multiplier for expected scoring
    turnover_modifier: float = 1.0  # Multiplier for turnover likelihood
    sack_modifier: float = 1.0  # Multiplier for sack likelihood


class MatchupAnalyzer:
    """Analyze team strengths and matchups for enhanced predictions."""
    
    def __init__(self, db_manager: DatabaseManager, calculator: FantasyCalculator):
        self.db = db_manager
        self.calculator = calculator
        
    def calculate_offensive_strength(self, team_id: str, season: int, week: int,
                                   weeks_to_analyze: int = 8) -> OffensiveStrength:
        """Calculate comprehensive offensive strength metrics for a team."""
        
        # Get recent offensive performance data
        with self.db.engine.connect() as conn:
            # Get team's offensive stats from recent games
            recent_games = pd.read_sql_query(text("""
                SELECT g.season_id, g.week, g.home_team_id, g.away_team_id,
                       g.home_score, g.away_score,
                       SUM(gs.pass_yards) as team_pass_yards,
                       SUM(gs.rush_yards) as team_rush_yards,
                       SUM(gs.pass_touchdowns) as team_pass_tds,
                       SUM(gs.rush_touchdowns) as team_rush_tds,
                       SUM(gs.receiving_touchdowns) as team_rec_tds,
                       SUM(gs.pass_interceptions + gs.rush_fumbles + gs.receiving_fumbles) as team_turnovers,
                       SUM(gs.pass_sacks) as team_sacks_allowed
                FROM games g
                JOIN game_stats gs ON g.game_id = gs.game_id
                WHERE ((g.home_team_id = :team_id AND gs.team_id = :team_id) OR 
                       (g.away_team_id = :team_id AND gs.team_id = :team_id))
                  AND g.season_id = :season
                  AND g.week < :week
                  AND g.week >= :week - :weeks_back
                GROUP BY g.game_id, g.season_id, g.week, g.home_team_id, g.away_team_id
                ORDER BY g.week DESC
            """), conn, params={
                'team_id': team_id, 'season': season, 'week': week,
                'weeks_back': weeks_to_analyze
            })
        
        if recent_games.empty:
            return OffensiveStrength(team_id, season, week)
        
        # Calculate offensive metrics
        offense = OffensiveStrength(team_id, season, week)
        
        # Determine team scores and stats for each game
        games_analyzed = 0
        total_points = 0
        total_pass_yards = 0
        total_rush_yards = 0
        total_pass_tds = 0
        total_rush_tds = 0
        total_rec_tds = 0
        total_turnovers = 0
        total_sacks_allowed = 0
        
        for _, game in recent_games.iterrows():
            # Determine if team was home or away and get their score
            is_home = game['home_team_id'] == team_id
            team_points = game['home_score'] if is_home else game['away_score']
            
            total_points += team_points
            total_pass_yards += game['team_pass_yards'] or 0
            total_rush_yards += game['team_rush_yards'] or 0
            total_pass_tds += game['team_pass_tds'] or 0
            total_rush_tds += game['team_rush_tds'] or 0
            total_rec_tds += game['team_rec_tds'] or 0
            total_turnovers += game['team_turnovers'] or 0
            total_sacks_allowed += game['team_sacks_allowed'] or 0
            games_analyzed += 1
        
        if games_analyzed > 0:
            offense.points_per_game = total_points / games_analyzed
            offense.passing_yards_per_game = total_pass_yards / games_analyzed
            offense.rushing_yards_per_game = total_rush_yards / games_analyzed
            offense.yards_per_game = offense.passing_yards_per_game + offense.rushing_yards_per_game
            offense.passing_tds_per_game = total_pass_tds / games_analyzed
            offense.rushing_tds_per_game = (total_rush_tds + total_rec_tds) / games_analyzed
            offense.turnovers_per_game = total_turnovers / games_analyzed
            offense.sacks_allowed_per_game = total_sacks_allowed / games_analyzed
            
            # Calculate overall offensive score (0-100 scale)
            # Based on league averages: ~22 ppg, ~350 ypg
            points_score = min(100, (offense.points_per_game / 30.0) * 100)
            yards_score = min(100, (offense.yards_per_game / 400.0) * 100)
            td_score = min(100, ((offense.passing_tds_per_game + offense.rushing_tds_per_game) / 3.0) * 100)
            turnover_score = max(0, 100 - (offense.turnovers_per_game * 25))  # Penalty for turnovers
            
            offense.offensive_score = (points_score * 0.4 + yards_score * 0.3 + 
                                     td_score * 0.2 + turnover_score * 0.1)
        
        return offense
    
    def calculate_defensive_strength(self, team_id: str, season: int, week: int,
                                   weeks_to_analyze: int = 8) -> DefensiveStrength:
        """Calculate comprehensive defensive strength metrics for a team."""
        
        # Get recent defensive performance data from team_defense_stats
        with self.db.engine.connect() as conn:
            recent_games = pd.read_sql_query(text("""
                SELECT tds.*
                FROM team_defense_stats tds
                WHERE tds.team_id = :team_id
                  AND tds.season_id = :season
                  AND tds.week < :week
                  AND tds.week >= :week - :weeks_back
                ORDER BY tds.week DESC
            """), conn, params={
                'team_id': team_id, 'season': season, 'week': week,
                'weeks_back': weeks_to_analyze
            })
        
        if recent_games.empty:
            return DefensiveStrength(team_id, season, week)
        
        # Calculate defensive metrics
        defense = DefensiveStrength(team_id, season, week)
        
        games_analyzed = len(recent_games)
        if games_analyzed > 0:
            # Convert all columns to numeric to handle potential bytes values from database
            recent_games['points_allowed'] = pd.to_numeric(recent_games['points_allowed'], errors='coerce').fillna(0)
            recent_games['yards_allowed'] = pd.to_numeric(recent_games['yards_allowed'], errors='coerce').fillna(0)
            recent_games['passing_yards_allowed'] = pd.to_numeric(recent_games['passing_yards_allowed'], errors='coerce').fillna(0)
            recent_games['rushing_yards_allowed'] = pd.to_numeric(recent_games['rushing_yards_allowed'], errors='coerce').fillna(0)
            recent_games['sacks'] = pd.to_numeric(recent_games['sacks'], errors='coerce').fillna(0)
            recent_games['interceptions'] = pd.to_numeric(recent_games['interceptions'], errors='coerce').fillna(0)
            recent_games['fumbles_recovered'] = pd.to_numeric(recent_games['fumbles_recovered'], errors='coerce').fillna(0)
            
            defense.points_allowed_per_game = recent_games['points_allowed'].mean()
            defense.yards_allowed_per_game = recent_games['yards_allowed'].mean()
            defense.passing_yards_allowed_per_game = recent_games['passing_yards_allowed'].mean()
            defense.rushing_yards_allowed_per_game = recent_games['rushing_yards_allowed'].mean()
            defense.sacks_per_game = recent_games['sacks'].mean()
            defense.interceptions_per_game = recent_games['interceptions'].mean()
            defense.fumbles_recovered_per_game = recent_games['fumbles_recovered'].mean()
            defense.turnovers_forced_per_game = (recent_games['interceptions'] + recent_games['fumbles_recovered']).mean()
            
            # Calculate overall defensive score (0-100 scale)
            # Lower points/yards allowed = better defense
            points_score = max(0, min(100, 100 - ((defense.points_allowed_per_game - 14) * 3)))
            yards_score = max(0, min(100, 100 - ((defense.yards_allowed_per_game - 250) * 0.2)))
            turnover_score = min(100, defense.turnovers_forced_per_game * 40)
            sack_score = min(100, defense.sacks_per_game * 25)
            
            defense.defensive_score = (points_score * 0.4 + yards_score * 0.3 + 
                                     turnover_score * 0.2 + sack_score * 0.1)
        
        return defense
    
    def analyze_matchup(self, offensive_team: str, defensive_team: str, 
                       season: int, week: int) -> MatchupStrength:
        """Analyze the complete matchup between an offensive team and defensive team."""
        
        # Get strength profiles for both teams
        offense = self.calculate_offensive_strength(offensive_team, season, week)
        defense = self.calculate_defensive_strength(defensive_team, season, week)
        
        # Determine matchup type
        offense_strong = offense.offensive_score >= 70
        defense_strong = defense.defensive_score >= 70
        
        if offense_strong and defense_strong:
            matchup_type = "Strong vs Strong"
        elif offense_strong and not defense_strong:
            matchup_type = "Strong vs Weak"
        elif not offense_strong and defense_strong:
            matchup_type = "Weak vs Strong"
        else:
            matchup_type = "Weak vs Weak"
        
        # Calculate advantage scores
        offensive_advantage = offense.offensive_score - defense.defensive_score
        defensive_advantage = defense.defensive_score - offense.offensive_score
        
        # Calculate impact modifiers based on matchup
        points_modifier = 1.0 + (offensive_advantage / 200.0)  # -0.5 to +0.5 range
        points_modifier = max(0.5, min(1.5, points_modifier))  # Clamp to reasonable range
        
        turnover_modifier = 1.0 + (defensive_advantage / 200.0)
        turnover_modifier = max(0.5, min(1.5, turnover_modifier))
        
        sack_modifier = 1.0 + (defense.sacks_per_game - offense.sacks_allowed_per_game) / 5.0
        sack_modifier = max(0.5, min(1.5, sack_modifier))
        
        return MatchupStrength(
            offensive_team=offensive_team,
            defensive_team=defensive_team,
            season=season,
            week=week,
            offense_strength=offense,
            defense_strength=defense,
            matchup_type=matchup_type,
            offensive_advantage=offensive_advantage,
            defensive_advantage=defensive_advantage,
            points_modifier=points_modifier,
            turnover_modifier=turnover_modifier,
            sack_modifier=sack_modifier
        )
    
    def get_opponent_for_team(self, team_id: str, season: int, week: int) -> Optional[str]:
        """Get the opponent team for a given team in a specific week."""
        
        with self.db.engine.connect() as conn:
            opponent = pd.read_sql_query(text("""
                SELECT 
                    CASE 
                        WHEN home_team_id = :team_id THEN away_team_id
                        WHEN away_team_id = :team_id THEN home_team_id
                    END as opponent_team
                FROM games
                WHERE (home_team_id = :team_id OR away_team_id = :team_id)
                  AND season_id = :season
                  AND week = :week
            """), conn, params={'team_id': team_id, 'season': season, 'week': week})
        
        return opponent.iloc[0]['opponent_team'] if not opponent.empty else None
    
    def get_matchup_for_player(self, player_team: str, season: int, week: int) -> Optional[MatchupStrength]:
        """Get matchup analysis from the perspective of a player's team (offense vs opponent defense)."""
        
        opponent_team = self.get_opponent_for_team(player_team, season, week)
        if not opponent_team:
            return None
            
        return self.analyze_matchup(player_team, opponent_team, season, week)
    
    def get_matchup_for_dst(self, dst_team: str, season: int, week: int) -> Optional[MatchupStrength]:
        """Get matchup analysis from the perspective of a DST (defense vs opponent offense)."""
        
        opponent_team = self.get_opponent_for_team(dst_team, season, week)
        if not opponent_team:
            return None
            
        return self.analyze_matchup(opponent_team, dst_team, season, week)


def main():
    """Test the matchup analyzer."""
    from config import Config
    
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    analyzer = MatchupAnalyzer(db_manager, calculator)
    
    # Test offense vs defense analysis
    print("Testing Matchup Analysis:")
    
    # Example: Chiefs offense vs 49ers defense
    matchup = analyzer.analyze_matchup('KC', 'SF', 2023, 10)
    print(f"\nKC Offense vs SF Defense:")
    print(f"Matchup Type: {matchup.matchup_type}")
    print(f"KC Offensive Score: {matchup.offense_strength.offensive_score:.1f}")
    print(f"SF Defensive Score: {matchup.defense_strength.defensive_score:.1f}")
    print(f"Points Modifier: {matchup.points_modifier:.2f}")
    print(f"Turnover Modifier: {matchup.turnover_modifier:.2f}")


if __name__ == "__main__":
    main()