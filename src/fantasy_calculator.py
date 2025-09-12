"""Fantasy point calculation engine for different scoring systems."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    from .database import DatabaseManager
    from .config import Config
except ImportError:
    from database import DatabaseManager
    from config import Config


@dataclass
class FantasyPoints:
    """Container for calculated fantasy points with breakdown."""
    total_points: float
    passing_points: float = 0.0
    rushing_points: float = 0.0
    receiving_points: float = 0.0
    bonus_points: float = 0.0
    penalty_points: float = 0.0


@dataclass  
class DSTFantasyPoints:
    """Container for calculated DST fantasy points with breakdown."""
    total_points: float
    points_allowed_score: float = 0.0
    turnovers_score: float = 0.0
    sacks_score: float = 0.0
    touchdowns_score: float = 0.0
    safety_score: float = 0.0
    bonus_score: float = 0.0


class FantasyCalculator:
    """Calculate fantasy points for different scoring systems."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._load_scoring_systems()
    
    def _load_scoring_systems(self):
        """Load scoring systems from database."""
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            systems_df = pd.read_sql_query(text("SELECT * FROM scoring_systems"), conn)
        
        self.scoring_systems = {}
        
        if systems_df is not None and not systems_df.empty:
            for _, row in systems_df.iterrows():
                self.scoring_systems[row['system_name']] = row.to_dict()
        else:
            # Fallback in-memory defaults to prevent runtime failures if DB is empty
            self.scoring_systems = {
                'FanDuel': {
                    'system_name': 'FanDuel',
                    'pass_yard_points': 0.04,
                    'pass_td_points': 4,
                    'pass_int_points': -1,
                    'rush_yard_points': 0.1,
                    'rush_td_points': 6,
                    'reception_points': 0.5,
                    'receiving_yard_points': 0.1,
                    'receiving_td_points': 6,
                    'fumble_points': -2,
                    'field_goal_points': 3,
                    'extra_point_points': 1,
                    'defensive_td_points': 6,
                    'sack_points': 1.0,
                    'int_points': 2,
                    'fumble_recovery_points': 2,
                    'safety_points': 2,
                    'dst_shutout_points': 10,
                    'dst_1to6_points': 7,
                    'dst_7to13_points': 4,
                    'dst_14to20_points': 1,
                    'dst_21to27_points': 0,
                    'dst_28to34_points': -1,
                    'dst_35plus_points': -4,
                    'dst_under300_bonus': 0,
                    'dst_under100_bonus': 0
                }
            }
    
    def calculate_player_points(self, game_stats: pd.Series, scoring_system: str) -> FantasyPoints:
        """Calculate fantasy points for a single player's game stats."""
        
        if scoring_system not in self.scoring_systems:
            raise ValueError(f"Unknown scoring system: {scoring_system}")
        
        # Helper function to safely convert values to numeric
        def safe_numeric(value, default=0):
            """Convert any value to a numeric type safely."""
            if value is None:
                return default
            if isinstance(value, bytes):
                try:
                    value = value.decode('utf-8')
                except:
                    return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        system = self.scoring_systems[scoring_system]
        points = FantasyPoints(total_points=0.0)
        
        # Passing points
        points.passing_points += safe_numeric(game_stats.get('pass_yards', 0)) * system['pass_yard_points']
        points.passing_points += safe_numeric(game_stats.get('pass_touchdowns', 0)) * system['pass_td_points']
        
        # Rushing points
        points.rushing_points += safe_numeric(game_stats.get('rush_yards', 0)) * system['rush_yard_points']
        points.rushing_points += safe_numeric(game_stats.get('rush_touchdowns', 0)) * system['rush_td_points']
        
        # Receiving points
        points.receiving_points += safe_numeric(game_stats.get('receptions', 0)) * system['reception_points']
        points.receiving_points += safe_numeric(game_stats.get('receiving_yards', 0)) * system['receiving_yard_points']
        points.receiving_points += safe_numeric(game_stats.get('receiving_touchdowns', 0)) * system['receiving_td_points']
        
        # Penalties (negative points)
        points.penalty_points += safe_numeric(game_stats.get('pass_interceptions', 0)) * system['pass_int_points']
        fumbles_lost = safe_numeric(game_stats.get('rush_fumbles', 0)) + safe_numeric(game_stats.get('receiving_fumbles', 0))
        points.penalty_points += fumbles_lost * system['fumble_points']
        
        # Bonuses (FanDuel/DraftKings specific)
        if scoring_system in ['FanDuel', 'DraftKings']:
            # 100+ rushing/receiving yards bonus
            rush_yards = safe_numeric(game_stats.get('rush_yards', 0))
            receiving_yards = safe_numeric(game_stats.get('receiving_yards', 0))
            
            if rush_yards >= 100:
                points.bonus_points += 3
            if receiving_yards >= 100:
                points.bonus_points += 3
                
            # 300+ passing yards bonus
            pass_yards = safe_numeric(game_stats.get('pass_yards', 0))
            if pass_yards >= 300:
                points.bonus_points += 3
        
        # Calculate total
        points.total_points = (
            points.passing_points + 
            points.rushing_points + 
            points.receiving_points + 
            points.bonus_points + 
            points.penalty_points
        )
        
        return points
    
    def calculate_dst_points(self, defense_stats: pd.Series, scoring_system: str) -> DSTFantasyPoints:
        """Calculate fantasy points for a team's defense/special teams performance."""
        
        if scoring_system not in self.scoring_systems:
            raise ValueError(f"Unknown scoring system: {scoring_system}")
        
        # Helper function to safely convert values to numeric
        def safe_numeric(value, default=0):
            """Convert any value to a numeric type safely."""
            if value is None:
                return default
            if isinstance(value, bytes):
                try:
                    value = value.decode('utf-8')
                except:
                    return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        system = self.scoring_systems[scoring_system]
        points = DSTFantasyPoints(total_points=0.0)
        
        # Points allowed scoring (tiered system)
        points_allowed = safe_numeric(defense_stats.get('points_allowed', 0))
        
        # Helper for compatibility between schema keys and older DST key names
        def sysval(new_key, old_key, default):
            return system.get(new_key, system.get(old_key, default))

        if points_allowed == 0:
            points.points_allowed_score = sysval('dst_shutout_points', 'dst_points_allowed_0_points', 10)
        elif points_allowed <= 6:
            points.points_allowed_score = sysval('dst_1to6_points', 'dst_points_allowed_1_6_points', 7)
        elif points_allowed <= 13:
            points.points_allowed_score = sysval('dst_7to13_points', 'dst_points_allowed_7_13_points', 4)
        elif points_allowed <= 20:
            points.points_allowed_score = sysval('dst_14to20_points', 'dst_points_allowed_14_20_points', 1)
        elif points_allowed <= 27:
            points.points_allowed_score = sysval('dst_21to27_points', 'dst_points_allowed_21_27_points', 0)
        elif points_allowed <= 34:
            points.points_allowed_score = sysval('dst_28to34_points', 'dst_points_allowed_28_34_points', -1)
        else:
            points.points_allowed_score = sysval('dst_35plus_points', 'dst_points_allowed_35_points', -4)
        
        # Defensive turnovers and sacks
        interceptions = safe_numeric(defense_stats.get('interceptions', 0))
        fumbles_recovered = safe_numeric(defense_stats.get('fumbles_recovered', 0))
        sacks = safe_numeric(defense_stats.get('sacks', 0))
        
        points.turnovers_score += interceptions * sysval('int_points', 'dst_interception_points', 2)
        points.turnovers_score += fumbles_recovered * sysval('fumble_recovery_points', 'dst_fumble_recovery_points', 2)
        points.sacks_score += sacks * sysval('sack_points', 'dst_sack_points', 1.0)
        
        # Defensive/special teams touchdowns
        defensive_tds = safe_numeric(defense_stats.get('defensive_touchdowns', 0))
        pick_six = safe_numeric(defense_stats.get('pick_six', 0))
        fumble_tds = safe_numeric(defense_stats.get('fumble_touchdowns', 0))
        return_tds = safe_numeric(defense_stats.get('return_touchdowns', 0))
        
        total_tds = defensive_tds + pick_six + fumble_tds + return_tds
        points.touchdowns_score += total_tds * sysval('defensive_td_points', 'dst_touchdown_points', 6)
        
        # Safeties
        safeties = safe_numeric(defense_stats.get('safeties', 0))
        points.safety_score += safeties * sysval('safety_points', 'dst_safety_points', 2)
        
        # Yardage bonuses (if implemented)
        yards_allowed = safe_numeric(defense_stats.get('yards_allowed', 0))
        
        try:
            if yards_allowed < 100:
                points.bonus_score += system.get('dst_under100_bonus', 0)
            elif yards_allowed < 300:
                points.bonus_score += system.get('dst_under300_bonus', 0)
        except (ValueError, TypeError):
            # Skip bonus if yards_allowed is not convertible
            pass
        
        # Calculate total
        points.total_points = (
            points.points_allowed_score + 
            points.turnovers_score + 
            points.sacks_score + 
            points.touchdowns_score + 
            points.safety_score + 
            points.bonus_score
        )
        
        return points
    
    def calculate_season_points(self, player_id: str, season: int, scoring_system: str) -> pd.DataFrame:
        """Calculate fantasy points for a player's entire season."""
        
        # Get player's game stats for the season
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            stats_df = pd.read_sql_query(text("""
                SELECT gs.*, g.season_id, g.week, p.player_name, p.position
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                JOIN players p ON gs.player_id = p.player_id
                WHERE gs.player_id = :player_id AND g.season_id = :season
                ORDER BY g.week
            """), conn, params={'player_id': player_id, 'season': season})
        
        if stats_df.empty:
            return pd.DataFrame()
        
        # Calculate points for each game
        fantasy_points = []
        for _, game_stats in stats_df.iterrows():
            points = self.calculate_player_points(game_stats, scoring_system)
            
            fantasy_points.append({
                'player_id': player_id,
                'player_name': game_stats['player_name'],
                'position': game_stats['position'],
                'season': season,
                'week': game_stats['week'],
                'game_id': game_stats['game_id'],
                'fantasy_points': points.total_points,
                'passing_points': points.passing_points,
                'rushing_points': points.rushing_points,
                'receiving_points': points.receiving_points,
                'bonus_points': points.bonus_points,
                'penalty_points': points.penalty_points,
                'scoring_system': scoring_system
            })
        
        return pd.DataFrame(fantasy_points)
    
    def calculate_top_performers(self, scoring_system: str, season: int = None, 
                                position: str = None, min_games: int = 8) -> pd.DataFrame:
        """Find top fantasy performers for a scoring system."""
        
        # Build query conditions
        conditions = ["p.position IN ('QB', 'RB', 'WR', 'TE')"]
        params = []
        
        if season:
            conditions.append("g.season_id = ?")
            params.append(season)
        
        if position:
            conditions.append("p.position = ?")
            params.append(position)
        
        where_clause = " AND ".join(conditions)
        
        # Get all game stats
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            param_dict = {f'param_{i}': param for i, param in enumerate(params)}
            # Replace ? placeholders with named parameters
            query = f"""
                SELECT 
                    gs.player_id, p.player_name, p.position, g.season_id,
                    gs.pass_yards, gs.pass_touchdowns, gs.pass_interceptions,
                    gs.rush_yards, gs.rush_touchdowns, gs.rush_fumbles,
                    gs.receptions, gs.receiving_yards, gs.receiving_touchdowns, gs.receiving_fumbles
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                JOIN players p ON gs.player_id = p.player_id
                WHERE {where_clause}
            """
            # Replace ? with named parameters
            for i in range(len(params)):
                query = query.replace('?', f':param_{i}', 1)
            stats_df = pd.read_sql_query(text(query), conn, params=param_dict)
        
        if stats_df.empty:
            return pd.DataFrame()
        
        # Calculate fantasy points for each game
        player_totals = []
        
        for player_id in stats_df['player_id'].unique():
            player_data = stats_df[stats_df['player_id'] == player_id]
            
            if len(player_data) < min_games:
                continue
            
            total_points = 0.0
            total_games = 0
            
            for _, game_stats in player_data.iterrows():
                points = self.calculate_player_points(game_stats, scoring_system)
                total_points += points.total_points
                total_games += 1
            
            if total_games > 0:
                player_info = player_data.iloc[0]
                player_totals.append({
                    'player_id': player_id,
                    'player_name': player_info['player_name'],
                    'position': player_info['position'],
                    'games_played': total_games,
                    'total_fantasy_points': round(total_points, 2),
                    'avg_fantasy_points': round(total_points / total_games, 2),
                    'scoring_system': scoring_system
                })
        
        result_df = pd.DataFrame(player_totals)
        return result_df.sort_values('total_fantasy_points', ascending=False)
    
    def compare_scoring_systems(self, player_id: str, season: int) -> pd.DataFrame:
        """Compare a player's performance across different scoring systems."""
        
        comparisons = []
        
        for system_name in ['FanDuel', 'DraftKings']:
            season_points = self.calculate_season_points(player_id, season, system_name)
            
            if not season_points.empty:
                total_points = season_points['fantasy_points'].sum()
                avg_points = season_points['fantasy_points'].mean()
                games = len(season_points)
                
                comparisons.append({
                    'player_id': player_id,
                    'player_name': season_points.iloc[0]['player_name'],
                    'position': season_points.iloc[0]['position'],
                    'season': season,
                    'scoring_system': system_name,
                    'total_points': round(total_points, 2),
                    'avg_points_per_game': round(avg_points, 2),
                    'games_played': games
                })
        
        return pd.DataFrame(comparisons)
    
    def get_weekly_rankings(self, week: int, season: int, scoring_system: str, 
                          position: str = None, limit: int = 50) -> pd.DataFrame:
        """Get top performers for a specific week."""
        
        conditions = ["p.position IN ('QB', 'RB', 'WR', 'TE')", "g.week = ?", "g.season_id = ?"]
        params = [week, season]
        
        if position:
            conditions.append("p.position = ?")
            params.append(position)
        
        where_clause = " AND ".join(conditions)
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            param_dict = {f'param_{i}': param for i, param in enumerate(params)}
            query = f"""
                SELECT 
                    gs.player_id, p.player_name, p.position, gs.team_id,
                    gs.pass_yards, gs.pass_touchdowns, gs.pass_interceptions,
                    gs.rush_yards, gs.rush_touchdowns, gs.rush_fumbles,
                    gs.receptions, gs.receiving_yards, gs.receiving_touchdowns, gs.receiving_fumbles
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                JOIN players p ON gs.player_id = p.player_id
                WHERE {where_clause}
                ORDER BY p.player_name
            """
            # Replace ? with named parameters
            for i in range(len(params)):
                query = query.replace('?', f':param_{i}', 1)
            stats_df = pd.read_sql_query(text(query), conn, params=param_dict)
        
        if stats_df.empty:
            return pd.DataFrame()
        
        # Calculate fantasy points for each player
        weekly_rankings = []
        
        for _, player_stats in stats_df.iterrows():
            points = self.calculate_player_points(player_stats, scoring_system)
            
            weekly_rankings.append({
                'player_id': player_stats['player_id'],
                'player_name': player_stats['player_name'],
                'position': player_stats['position'],
                'team': player_stats['team_id'],
                'fantasy_points': round(points.total_points, 2),
                'week': week,
                'season': season,
                'scoring_system': scoring_system
            })
        
        result_df = pd.DataFrame(weekly_rankings)
        result_df = result_df.sort_values('fantasy_points', ascending=False)
        
        return result_df.head(limit) if limit else result_df
    
    def get_dst_weekly_rankings(self, week: int, season: int, scoring_system: str, 
                               limit: int = 32) -> pd.DataFrame:
        """Get DST rankings for a specific week."""
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            dst_df = pd.read_sql_query(text("""
                SELECT tds.*, t.team_name
                FROM team_defense_stats tds
                JOIN teams t ON tds.team_id = t.team_id
                WHERE tds.week = :week AND tds.season_id = :season
                ORDER BY tds.team_id
            """), conn, params={'week': week, 'season': season})
        
        if dst_df.empty:
            return pd.DataFrame()
        
        # Calculate fantasy points for each DST
        dst_rankings = []
        
        for _, dst_stats in dst_df.iterrows():
            points = self.calculate_dst_points(dst_stats, scoring_system)
            
            dst_rankings.append({
                'team_id': dst_stats['team_id'],
                'team_name': dst_stats['team_name'],
                'position': 'DST',
                'fantasy_points': round(points.total_points, 2),
                'points_allowed': dst_stats['points_allowed'],
                'sacks': dst_stats['sacks'],
                'interceptions': dst_stats['interceptions'],
                'fumbles_recovered': dst_stats['fumbles_recovered'],
                'defensive_touchdowns': (dst_stats.get('defensive_touchdowns', 0) + 
                                       dst_stats.get('pick_six', 0) + 
                                       dst_stats.get('fumble_touchdowns', 0) + 
                                       dst_stats.get('return_touchdowns', 0)),
                'safeties': dst_stats['safeties'],
                'week': week,
                'season': season,
                'scoring_system': scoring_system,
                # Breakdown for analysis
                'points_allowed_score': round(points.points_allowed_score, 2),
                'turnovers_score': round(points.turnovers_score, 2),
                'sacks_score': round(points.sacks_score, 2),
                'touchdowns_score': round(points.touchdowns_score, 2),
                'safety_score': round(points.safety_score, 2)
            })
        
        result_df = pd.DataFrame(dst_rankings)
        result_df = result_df.sort_values('fantasy_points', ascending=False)
        
        return result_df.head(limit) if limit else result_df
    
    def calculate_dst_season_points(self, team_id: str, season: int, scoring_system: str) -> pd.DataFrame:
        """Calculate DST fantasy points for an entire season."""
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            dst_df = pd.read_sql_query(text("""
                SELECT tds.*, t.team_name
                FROM team_defense_stats tds
                JOIN teams t ON tds.team_id = t.team_id
                WHERE tds.team_id = :team_id AND tds.season_id = :season
                ORDER BY tds.week
            """), conn, params={'team_id': team_id, 'season': season})
        
        if dst_df.empty:
            return pd.DataFrame()
        
        # Calculate points for each game
        season_points = []
        
        for _, dst_stats in dst_df.iterrows():
            points = self.calculate_dst_points(dst_stats, scoring_system)
            
            season_points.append({
                'team_id': team_id,
                'team_name': dst_stats['team_name'],
                'position': 'DST',
                'season': season,
                'week': dst_stats['week'],
                'game_id': dst_stats['game_id'],
                'fantasy_points': round(points.total_points, 2),
                'points_allowed_score': round(points.points_allowed_score, 2),
                'turnovers_score': round(points.turnovers_score, 2),
                'sacks_score': round(points.sacks_score, 2),
                'touchdowns_score': round(points.touchdowns_score, 2),
                'safety_score': round(points.safety_score, 2),
                'scoring_system': scoring_system
            })
        
        return pd.DataFrame(season_points)
