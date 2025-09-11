#!/usr/bin/env python3
"""
Position-Specific Matchup Analyzer
Enhanced matchup intelligence that matches player skills vs specific defensive weaknesses
"""

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
class PositionDefensiveProfile:
    """Position-specific defensive profile for a team."""
    team_id: str
    season: int
    week: int
    
    # Pass Defense (vs QB/WR/TE)
    pass_yards_allowed_per_game: float = 0.0
    pass_tds_allowed_per_game: float = 0.0
    sack_rate: float = 0.0  # Sacks per pass attempt
    int_rate: float = 0.0   # INTs per pass attempt
    qb_rating_allowed: float = 100.0
    
    # Rush Defense (vs RB)
    rush_yards_allowed_per_game: float = 0.0
    rush_tds_allowed_per_game: float = 0.0
    yards_per_carry_allowed: float = 4.0
    
    # Position-specific allowed stats
    rb_receiving_yards_allowed: float = 0.0
    wr_yards_allowed_per_game: float = 0.0
    te_yards_allowed_per_game: float = 0.0
    
    # Red zone defense
    red_zone_pass_tds_allowed: float = 0.0
    red_zone_rush_tds_allowed: float = 0.0
    
    # Rankings (1=best defense, 32=worst defense)
    pass_defense_rank: int = 16
    rush_defense_rank: int = 16
    sack_pressure_rank: int = 16
    turnover_creation_rank: int = 16


@dataclass 
class PositionMatchupAdvantage:
    """Position-specific matchup advantage calculation."""
    player_position: str
    offensive_team: str
    defensive_team: str
    season: int
    week: int
    
    # Position-specific matchup scores
    primary_matchup_score: float = 0.0    # Main skill vs main defense
    secondary_matchup_score: float = 0.0  # Secondary skill vs defense
    pressure_impact_score: float = 0.0    # Pass rush impact (QB/WR/TE)
    turnover_risk_score: float = 0.0      # Turnover likelihood
    red_zone_advantage: float = 0.0       # Red zone scoring advantage
    
    # Modifiers
    efficiency_modifier: float = 1.0      # Overall efficiency boost/penalty
    volume_modifier: float = 1.0          # Expected volume change
    ceiling_modifier: float = 1.0         # Big play/TD potential
    floor_modifier: float = 1.0           # Consistency/safety net


class PositionMatchupAnalyzer:
    """Enhanced matchup analyzer with position-specific intelligence."""
    
    def __init__(self, db_manager: DatabaseManager, calculator: FantasyCalculator):
        self.db = db_manager
        self.calculator = calculator
        
    def calculate_position_defensive_profile(self, team_id: str, season: int, week: int,
                                          weeks_to_analyze: int = 8) -> PositionDefensiveProfile:
        """Calculate position-specific defensive profile for a team."""
        
        profile = PositionDefensiveProfile(team_id, season, week)
        
        # Get recent defensive performance vs different position types
        with self.db.engine.connect() as conn:
            # Get team's defensive stats from recent games
            recent_defense = pd.read_sql_query(text("""
                SELECT tds.*, g.week
                FROM team_defense_stats tds
                JOIN games g ON tds.game_id = g.game_id
                WHERE tds.team_id = :team_id
                  AND tds.season_id = :season
                  AND tds.week < :week
                  AND tds.week >= :week - :weeks_back
                ORDER BY tds.week DESC
            """), conn, params={
                'team_id': team_id, 'season': season, 'week': week,
                'weeks_back': weeks_to_analyze
            })
            
            # Get opponent offensive stats against this defense
            opponent_offense = pd.read_sql_query(text("""
                SELECT g.week, 
                       SUM(CASE WHEN p.position = 'QB' THEN gs.pass_yards ELSE 0 END) as qb_pass_yards,
                       SUM(CASE WHEN p.position = 'QB' THEN gs.pass_touchdowns ELSE 0 END) as qb_pass_tds,
                       SUM(CASE WHEN p.position = 'QB' THEN gs.pass_attempts ELSE 0 END) as qb_pass_attempts,
                       SUM(CASE WHEN p.position = 'RB' THEN gs.rush_yards ELSE 0 END) as rb_rush_yards,
                       SUM(CASE WHEN p.position = 'RB' THEN gs.rush_touchdowns ELSE 0 END) as rb_rush_tds,
                       SUM(CASE WHEN p.position = 'RB' THEN gs.rush_attempts ELSE 0 END) as rb_rush_attempts,
                       SUM(CASE WHEN p.position = 'RB' THEN gs.receiving_yards ELSE 0 END) as rb_rec_yards,
                       SUM(CASE WHEN p.position = 'WR' THEN gs.receiving_yards ELSE 0 END) as wr_rec_yards,
                       SUM(CASE WHEN p.position = 'TE' THEN gs.receiving_yards ELSE 0 END) as te_rec_yards
                FROM games g
                JOIN game_stats gs ON g.game_id = gs.game_id
                JOIN players p ON gs.player_id = p.player_id
                WHERE ((g.home_team_id = :team_id AND gs.team_id != :team_id) OR
                       (g.away_team_id = :team_id AND gs.team_id != :team_id))
                  AND g.season_id = :season
                  AND g.week < :week
                  AND g.week >= :week - :weeks_back
                  AND p.position IN ('QB', 'RB', 'WR', 'TE')
                GROUP BY g.game_id, g.week
                ORDER BY g.week DESC
            """), conn, params={
                'team_id': team_id, 'season': season, 'week': week,
                'weeks_back': weeks_to_analyze
            })
        
        if recent_defense.empty or opponent_offense.empty:
            return profile
            
        games_analyzed = len(recent_defense)
        
        if games_analyzed > 0:
            # Calculate basic defensive stats
            profile.pass_yards_allowed_per_game = opponent_offense['qb_pass_yards'].mean()
            profile.rush_yards_allowed_per_game = opponent_offense['rb_rush_yards'].mean()
            
            # Calculate rates
            total_pass_attempts = opponent_offense['qb_pass_attempts'].sum()
            total_rush_attempts = opponent_offense['rb_rush_attempts'].sum()
            
            if total_pass_attempts > 0:
                profile.pass_tds_allowed_per_game = opponent_offense['qb_pass_tds'].mean()
                profile.sack_rate = recent_defense['sacks'].sum() / total_pass_attempts
                profile.int_rate = recent_defense['interceptions'].sum() / total_pass_attempts
            
            if total_rush_attempts > 0:
                profile.rush_tds_allowed_per_game = opponent_offense['rb_rush_tds'].mean()
                profile.yards_per_carry_allowed = profile.rush_yards_allowed_per_game / (total_rush_attempts / games_analyzed) if total_rush_attempts > 0 else 4.0
            
            # Position-specific receiving yards allowed
            profile.rb_receiving_yards_allowed = opponent_offense['rb_rec_yards'].mean()
            profile.wr_yards_allowed_per_game = opponent_offense['wr_rec_yards'].mean()
            profile.te_yards_allowed_per_game = opponent_offense['te_rec_yards'].mean()
        
        # Calculate rankings relative to league
        profile = self._calculate_defensive_rankings(profile, season, week)
        
        return profile
    
    def _calculate_defensive_rankings(self, profile: PositionDefensiveProfile, 
                                    season: int, week: int) -> PositionDefensiveProfile:
        """Calculate defensive rankings relative to league average."""
        
        # Get league averages for ranking
        with self.db.engine.connect() as conn:
            league_defense = pd.read_sql_query(text("""
                SELECT team_id,
                       AVG(points_allowed) as avg_points_allowed,
                       AVG(sacks) as avg_sacks,
                       AVG(interceptions + fumbles_recovered) as avg_turnovers
                FROM team_defense_stats
                WHERE season_id = :season
                  AND week < :week
                  AND week >= :week - 8
                GROUP BY team_id
                HAVING COUNT(*) >= 3
                ORDER BY avg_points_allowed
            """), conn, params={'season': season, 'week': week})
        
        if not league_defense.empty:
            # Rank by points allowed (lower is better)
            league_defense['points_rank'] = league_defense['avg_points_allowed'].rank(method='min')
            league_defense['sack_rank'] = league_defense['avg_sacks'].rank(method='min', ascending=False)
            league_defense['turnover_rank'] = league_defense['avg_turnovers'].rank(method='min', ascending=False)
            
            team_data = league_defense[league_defense['team_id'] == profile.team_id]
            if not team_data.empty:
                profile.pass_defense_rank = int(team_data.iloc[0]['points_rank'])
                profile.sack_pressure_rank = int(team_data.iloc[0]['sack_rank'])
                profile.turnover_creation_rank = int(team_data.iloc[0]['turnover_rank'])
                
                # Estimate rush defense rank based on points allowed (simplified)
                profile.rush_defense_rank = profile.pass_defense_rank
        
        return profile
    
    def analyze_position_matchup(self, player_position: str, offensive_team: str, 
                               defensive_team: str, season: int, week: int) -> PositionMatchupAdvantage:
        """Analyze position-specific matchup advantage."""
        
        matchup = PositionMatchupAdvantage(
            player_position, offensive_team, defensive_team, season, week
        )
        
        # Get defensive profile
        defense_profile = self.calculate_position_defensive_profile(
            defensive_team, season, week
        )
        
        # Position-specific matchup calculation
        if player_position == 'QB':
            matchup = self._analyze_qb_matchup(matchup, defense_profile)
        elif player_position == 'RB':
            matchup = self._analyze_rb_matchup(matchup, defense_profile)
        elif player_position == 'WR':
            matchup = self._analyze_wr_matchup(matchup, defense_profile)
        elif player_position == 'TE':
            matchup = self._analyze_te_matchup(matchup, defense_profile)
        
        return matchup
    
    def _analyze_qb_matchup(self, matchup: PositionMatchupAdvantage, 
                          defense: PositionDefensiveProfile) -> PositionMatchupAdvantage:
        """Analyze QB vs pass defense matchup."""
        
        # Primary: Pass defense weakness = QB advantage
        matchup.primary_matchup_score = 33 - defense.pass_defense_rank  # Convert rank to advantage score
        
        # Pressure impact: Strong pass rush = QB disadvantage
        matchup.pressure_impact_score = defense.sack_pressure_rank - 16  # Negative if strong pass rush
        
        # Turnover risk: High INT rate = QB risk
        matchup.turnover_risk_score = 16 - defense.turnover_creation_rank  # Positive = more risk
        
        # Calculate efficiency modifier
        base_modifier = 1.0
        
        # Weak pass defense = boost, strong pass defense = penalty
        if defense.pass_defense_rank > 24:  # Bottom 8 pass defenses
            base_modifier += 0.15
        elif defense.pass_defense_rank < 9:  # Top 8 pass defenses  
            base_modifier -= 0.15
            
        # Pass rush impact
        if defense.sack_pressure_rank < 9:  # Elite pass rush
            base_modifier -= 0.10
        elif defense.sack_pressure_rank > 24:  # Weak pass rush
            base_modifier += 0.10
            
        matchup.efficiency_modifier = max(0.7, min(1.4, base_modifier))
        
        # Volume tends to be stable for QBs
        matchup.volume_modifier = 1.0
        
        # Ceiling modifier based on big play potential
        if defense.pass_defense_rank > 20:  # Vulnerable to big plays
            matchup.ceiling_modifier = 1.15
        elif defense.pass_defense_rank < 12:  # Good at limiting big plays
            matchup.ceiling_modifier = 0.90
        else:
            matchup.ceiling_modifier = 1.0
            
        return matchup
    
    def _analyze_rb_matchup(self, matchup: PositionMatchupAdvantage,
                          defense: PositionDefensiveProfile) -> PositionMatchupAdvantage:
        """Analyze RB vs run defense matchup."""
        
        # Primary: Run defense weakness = RB rushing advantage
        matchup.primary_matchup_score = 33 - defense.rush_defense_rank
        
        # Secondary: Pass defense vs RB receiving
        matchup.secondary_matchup_score = max(0, defense.rb_receiving_yards_allowed - 20) / 5
        
        # Calculate efficiency modifier
        base_modifier = 1.0
        
        # Weak run defense = major boost
        if defense.rush_defense_rank > 24:
            base_modifier += 0.20
        elif defense.rush_defense_rank < 9:
            base_modifier -= 0.20
            
        # RB receiving opportunity
        if defense.rb_receiving_yards_allowed > 30:  # Weak vs receiving RBs
            base_modifier += 0.05
            
        matchup.efficiency_modifier = max(0.6, min(1.5, base_modifier))
        
        # Volume modifier - weak run defense = more carries
        if defense.rush_defense_rank > 20:
            matchup.volume_modifier = 1.10
        elif defense.rush_defense_rank < 12:
            matchup.volume_modifier = 0.95
        else:
            matchup.volume_modifier = 1.0
            
        return matchup
    
    def _analyze_wr_matchup(self, matchup: PositionMatchupAdvantage,
                          defense: PositionDefensiveProfile) -> PositionMatchupAdvantage:
        """Analyze WR vs pass defense matchup."""
        
        # Primary: Pass defense weakness = WR advantage
        matchup.primary_matchup_score = 33 - defense.pass_defense_rank
        
        # Secondary: Specific WR coverage weakness
        matchup.secondary_matchup_score = max(0, defense.wr_yards_allowed_per_game - 200) / 20
        
        # Pressure impact: Pass rush affects QB, indirectly affects WR
        matchup.pressure_impact_score = defense.sack_pressure_rank - 16
        
        base_modifier = 1.0
        
        # Weak pass defense = WR boost
        if defense.pass_defense_rank > 20:
            base_modifier += 0.18
        elif defense.pass_defense_rank < 12:
            base_modifier -= 0.18
            
        # Strong pass rush = fewer opportunities
        if defense.sack_pressure_rank < 12:
            base_modifier -= 0.08
            
        matchup.efficiency_modifier = max(0.7, min(1.4, base_modifier))
        
        # High ceiling potential vs weak secondaries
        if defense.pass_defense_rank > 24:
            matchup.ceiling_modifier = 1.25
        else:
            matchup.ceiling_modifier = 1.0
            
        return matchup
    
    def _analyze_te_matchup(self, matchup: PositionMatchupAdvantage,
                          defense: PositionDefensiveProfile) -> PositionMatchupAdvantage:
        """Analyze TE vs defense matchup."""
        
        # Primary: TE coverage weakness
        matchup.primary_matchup_score = max(0, defense.te_yards_allowed_per_game - 40) / 5
        
        # Secondary: Overall pass defense
        matchup.secondary_matchup_score = 33 - defense.pass_defense_rank
        
        # Pass rush can help TEs (checkdown options)
        matchup.pressure_impact_score = 16 - defense.sack_pressure_rank  # Strong rush = TE opportunity
        
        base_modifier = 1.0
        
        # Weak vs TEs = significant boost
        if defense.te_yards_allowed_per_game > 60:
            base_modifier += 0.20
        elif defense.te_yards_allowed_per_game < 30:
            base_modifier -= 0.15
            
        # Strong pass rush = more checkdowns to TE
        if defense.sack_pressure_rank < 12:
            base_modifier += 0.08
            
        matchup.efficiency_modifier = max(0.7, min(1.3, base_modifier))
        
        return matchup
    
    def get_position_matchup_features(self, player_position: str, offensive_team: str,
                                    defensive_team: str, season: int, week: int) -> Dict[str, float]:
        """Get position-specific matchup features for model input."""
        
        matchup = self.analyze_position_matchup(
            player_position, offensive_team, defensive_team, season, week
        )
        
        # Return position-specific features
        if player_position == 'QB':
            return {
                'opponent_pass_defense_rank': 33 - matchup.primary_matchup_score,
                'opponent_pass_rush_pressure': -matchup.pressure_impact_score,
                'opponent_turnover_creation': matchup.turnover_risk_score,
                'qb_efficiency_modifier': matchup.efficiency_modifier,
                'qb_ceiling_modifier': matchup.ceiling_modifier
            }
        elif player_position == 'RB':
            return {
                'opponent_rush_defense_rank': 33 - matchup.primary_matchup_score,
                'opponent_rb_receiving_weakness': matchup.secondary_matchup_score,
                'rb_volume_modifier': matchup.volume_modifier,
                'rb_efficiency_modifier': matchup.efficiency_modifier,
                'rb_goal_line_advantage': matchup.red_zone_advantage
            }
        elif player_position == 'WR':
            return {
                'opponent_pass_defense_rank': 33 - matchup.primary_matchup_score,
                'opponent_wr_coverage_weakness': matchup.secondary_matchup_score,
                'wr_pressure_impact': matchup.pressure_impact_score,
                'wr_efficiency_modifier': matchup.efficiency_modifier,
                'wr_ceiling_modifier': matchup.ceiling_modifier
            }
        elif player_position == 'TE':
            return {
                'opponent_te_coverage_weakness': matchup.primary_matchup_score,
                'opponent_pass_defense_rank': matchup.secondary_matchup_score,
                'te_checkdown_opportunity': matchup.pressure_impact_score,
                'te_efficiency_modifier': matchup.efficiency_modifier,
                'te_red_zone_advantage': matchup.red_zone_advantage
            }
        
        return {}


def main():
    """Test the position-specific matchup analyzer."""
    from config import Config
    
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    calculator = FantasyCalculator(db_manager)
    analyzer = PositionMatchupAnalyzer(db_manager, calculator)
    
    print("🎯 Testing Position-Specific Matchup Analysis")
    print("=" * 50)
    
    # Test different position matchups
    test_matchups = [
        ('QB', 'KC', 'NYJ', 2023, 10),  # Mahomes vs weak pass defense
        ('RB', 'TEN', 'SF', 2023, 10),  # Henry vs strong run defense  
        ('WR', 'MIA', 'NE', 2023, 10),  # Hill vs division rival
        ('TE', 'KC', 'LV', 2023, 10)   # Kelce vs weak TE coverage
    ]
    
    for position, offense, defense, season, week in test_matchups:
        print(f"\n{position} Matchup: {offense} vs {defense} (Week {week}, {season})")
        print("-" * 40)
        
        matchup = analyzer.analyze_position_matchup(position, offense, defense, season, week)
        features = analyzer.get_position_matchup_features(position, offense, defense, season, week)
        
        print(f"Primary Matchup Score: {matchup.primary_matchup_score:.1f}")
        print(f"Efficiency Modifier: {matchup.efficiency_modifier:.2f}")
        
        print("Position-Specific Features:")
        for feature, value in features.items():
            print(f"  {feature}: {value:.2f}")


if __name__ == "__main__":
    main()