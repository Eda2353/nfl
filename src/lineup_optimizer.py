"""Optimal lineup generation using simulation and optimization techniques."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from itertools import combinations
import random
from scipy.optimize import minimize
import math

try:
    from .database import DatabaseManager
    from .fantasy_calculator import FantasyCalculator
    from .prediction_model import PlayerPredictor
    from .config import Config
except ImportError:
    from database import DatabaseManager
    from fantasy_calculator import FantasyCalculator
    from prediction_model import PlayerPredictor
    from config import Config


@dataclass
class PlayerProjection:
    """Player projection for lineup optimization."""
    player_id: str
    player_name: str
    position: str
    team: str
    projected_points: float
    ceiling: float  # 90th percentile projection
    floor: float    # 10th percentile projection
    ownership: float = 5.0  # Expected ownership percentage
    salary: float = 5000.0  # Mock salary for optimization
    

@dataclass 
class LineupConstraints:
    """Constraints for lineup construction."""
    positions: Dict[str, int]  # e.g., {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1}
    salary_cap: float = 60000.0
    min_teams: int = 2  # Minimum number of different teams
    max_players_per_team: int = 4
    

@dataclass
class OptimalLineup:
    """Result of lineup optimization."""
    players: List[PlayerProjection]
    total_projected_points: float
    total_salary: float
    ceiling: float
    floor: float
    teams_used: List[str]
    score: float  # Optimization score


class LineupSimulator:
    """Simulate and optimize fantasy football lineups."""
    
    def __init__(self, db_manager: DatabaseManager, calculator: FantasyCalculator, 
                 predictor: PlayerPredictor):
        self.db = db_manager
        self.calculator = calculator
        self.predictor = predictor
        
        # DFS lineup constraints (DraftKings format)
        self.default_constraints = LineupConstraints(
            positions={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1, 'DST': 1},
            salary_cap=50000.0,
            min_teams=2,
            max_players_per_team=4
        )
    
    def generate_player_projections(self, week: int, season: int, 
                                  scoring_system: str = 'FanDuel') -> List[PlayerProjection]:
        """Generate projections for all available players."""
        
        projections = []
        
        # Get all active players for the week (players who played in recent weeks)
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            players = pd.read_sql_query(text("""
                SELECT p.player_id, p.player_name, p.position, 
                       gs.team_id, MAX(g.week) as last_week_played
                FROM players p
                JOIN game_stats gs ON p.player_id = gs.player_id
                JOIN games g ON gs.game_id = g.game_id
                WHERE p.position IN ('QB', 'RB', 'WR', 'TE')
                  AND g.season_id = :season
                  AND g.week < :week
                  AND gs.team_id IS NOT NULL
                GROUP BY p.player_id, p.player_name, p.position, gs.team_id
                HAVING last_week_played >= :week - 4
            """), conn, params={'season': season, 'week': week})
        
        for _, player in players.iterrows():
            # Get prediction
            projected_points = self.predictor.predict_player_points(
                player['player_id'], week, season, scoring_system
            )
            
            if projected_points is not None and projected_points > 3.0:  # Filter out very low projections
                # Calculate ceiling and floor using historical variance
                historical_points = self._get_player_historical_performance(
                    player['player_id'], season, scoring_system
                )
                
                if len(historical_points) > 0:
                    std_dev = np.std(historical_points)
                    ceiling = projected_points + (1.3 * std_dev)  # ~90th percentile
                    floor = max(0, projected_points - (1.3 * std_dev))  # ~10th percentile
                else:
                    ceiling = projected_points * 1.5
                    floor = projected_points * 0.3
                
                # Mock salary based on projected points and position
                salary = self._estimate_salary(projected_points, player['position'])
                
                projection = PlayerProjection(
                    player_id=player['player_id'],
                    player_name=player['player_name'],
                    position=player['position'],
                    team=player['team_id'],
                    projected_points=projected_points,
                    ceiling=ceiling,
                    floor=floor,
                    salary=salary
                )
                
                projections.append(projection)
        
        # Add DST projections
        dst_projections = self._get_dst_projections(week, season, scoring_system)
        projections.extend(dst_projections)
        
        return projections
    
    def _get_player_historical_performance(self, player_id: str, season: int, 
                                         scoring_system: str) -> List[float]:
        """Get recent historical performance for variance calculation."""
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            recent_games = pd.read_sql_query(text("""
                SELECT gs.*
                FROM game_stats gs
                JOIN games g ON gs.game_id = g.game_id
                WHERE gs.player_id = :player_id
                  AND g.season_id = :season
                ORDER BY g.week DESC
                LIMIT 8
            """), conn, params={'player_id': player_id, 'season': season})
        
        fantasy_points = []
        for _, game in recent_games.iterrows():
            points = self.calculator.calculate_player_points(game, scoring_system)
            fantasy_points.append(points.total_points)
        
        return fantasy_points
    
    def _estimate_salary(self, projected_points: float, position: str) -> float:
        """Estimate DFS salary based on projected points and position."""
        
        # Base salary multipliers by position
        multipliers = {'QB': 600, 'RB': 700, 'WR': 700, 'TE': 500}
        base_multiplier = multipliers.get(position, 600)
        
        # Add some variance and position adjustments
        salary = (projected_points * base_multiplier) + random.uniform(-500, 500)
        
        # Ensure reasonable salary ranges
        min_salary = {'QB': 4500, 'RB': 4000, 'WR': 4000, 'TE': 3500}.get(position, 4000)
        max_salary = {'QB': 9000, 'RB': 10000, 'WR': 9500, 'TE': 7500}.get(position, 8000)
        
        return max(min_salary, min(max_salary, salary))
    
    def _get_dst_projections(self, week: int, season: int, scoring_system: str) -> List[PlayerProjection]:
        """Get DST projections for all teams."""
        
        dst_projections = []
        
        # Get all teams that have played recently
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            teams = pd.read_sql_query(text("""
                SELECT DISTINCT t.team_id, t.team_name
                FROM teams t
                JOIN team_defense_stats tds ON t.team_id = tds.team_id
                WHERE tds.season_id = :season 
                  AND tds.week < :week
                  AND tds.week >= :week - 4
            """), conn, params={'season': season, 'week': week})
        
        for _, team in teams.iterrows():
            # Get DST prediction
            projected_points = self.predictor.predict_dst_points(
                team['team_id'], week, season, scoring_system
            )
            
            if projected_points is not None:
                # Calculate ceiling and floor for DST using historical variance
                historical_points = self._get_dst_historical_performance(
                    team['team_id'], season, scoring_system
                )
                
                if len(historical_points) > 0:
                    std_dev = np.std(historical_points)
                    ceiling = projected_points + (1.3 * std_dev)
                    floor = max(0, projected_points - (1.3 * std_dev))
                else:
                    ceiling = projected_points * 1.8  # DST has higher variance
                    floor = max(0, projected_points * 0.2)
                
                # Estimate DST salary (typically lower than skill positions)
                salary = self._estimate_dst_salary(projected_points)
                
                projection = PlayerProjection(
                    player_id=f"DST_{team['team_id']}",  # Special ID for DST
                    player_name=f"{team['team_name']} DST",
                    position='DST',
                    team=team['team_id'],
                    projected_points=projected_points,
                    ceiling=ceiling,
                    floor=floor,
                    salary=salary
                )
                
                dst_projections.append(projection)
        
        return dst_projections
    
    def _get_dst_historical_performance(self, team_id: str, season: int, 
                                      scoring_system: str) -> List[float]:
        """Get recent historical DST performance for variance calculation."""
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            recent_games = pd.read_sql_query(text("""
                SELECT *
                FROM team_defense_stats
                WHERE team_id = :team_id
                  AND season_id = :season
                ORDER BY week DESC
                LIMIT 8
            """), conn, params={'team_id': team_id, 'season': season})
        
        fantasy_points = []
        for _, game in recent_games.iterrows():
            points = self.calculator.calculate_dst_points(game, scoring_system)
            fantasy_points.append(points.total_points)
        
        return fantasy_points
    
    def _estimate_dst_salary(self, projected_points: float) -> float:
        """Estimate DFS salary for DST based on projected points."""
        
        # DST salary is typically 2000-6000 range
        base_salary = projected_points * 250  # Lower multiplier than skill positions
        
        # Add some variance
        salary = base_salary + random.uniform(-200, 200)
        
        # Ensure reasonable salary range for DST
        return max(2000, min(6000, salary))
    
    def optimize_lineup_greedy(self, projections: List[PlayerProjection], 
                              constraints: LineupConstraints = None) -> OptimalLineup:
        """Generate optimal lineup using greedy value-based approach."""
        
        if constraints is None:
            constraints = self.default_constraints
        
        # Calculate value (points per $1000 salary)
        for proj in projections:
            proj.value = proj.projected_points / (proj.salary / 1000)
        
        # Sort by value
        projections.sort(key=lambda x: x.value, reverse=True)
        
        selected_players = []
        remaining_salary = constraints.salary_cap
        position_needs = constraints.positions.copy()
        
        # Handle FLEX position
        if 'FLEX' in position_needs:
            flex_count = position_needs.pop('FLEX')
            # FLEX can be RB, WR, or TE (not DST)
            for pos in ['RB', 'WR', 'TE']:
                position_needs[pos] = position_needs.get(pos, 0) + flex_count
        
        # Greedy selection
        for proj in projections:
            # Check if we need this position
            if position_needs.get(proj.position, 0) <= 0:
                continue
                
            # Check if we can afford this player
            if proj.salary > remaining_salary:
                continue
            
            # Check team constraints
            team_count = sum(1 for p in selected_players if p.team == proj.team)
            if team_count >= constraints.max_players_per_team:
                continue
            
            # Add player to lineup
            selected_players.append(proj)
            remaining_salary -= proj.salary
            position_needs[proj.position] -= 1
            
            # Check if lineup is complete
            if all(count <= 0 for count in position_needs.values()):
                break
        
        return self._create_lineup_result(selected_players, constraints)
    
    def optimize_lineup_montecarlo(self, projections: List[PlayerProjection],
                                 constraints: LineupConstraints = None,
                                 iterations: int = 1000) -> List[OptimalLineup]:
        """Generate multiple optimal lineups using Monte Carlo simulation."""
        
        if constraints is None:
            constraints = self.default_constraints
        
        lineups = []
        
        for _ in range(iterations):
            # Simulate player performances using ceiling/floor ranges
            simulated_projections = []
            for proj in projections:
                # Sample from normal distribution between floor and ceiling
                simulated_points = np.random.normal(
                    proj.projected_points,
                    (proj.ceiling - proj.floor) / 4  # 4 standard deviations span range
                )
                simulated_points = max(0, simulated_points)  # No negative points
                
                sim_proj = PlayerProjection(
                    player_id=proj.player_id,
                    player_name=proj.player_name,
                    position=proj.position,
                    team=proj.team,
                    projected_points=simulated_points,
                    ceiling=proj.ceiling,
                    floor=proj.floor,
                    salary=proj.salary
                )
                simulated_projections.append(sim_proj)
            
            # Optimize lineup for this simulation
            lineup = self.optimize_lineup_greedy(simulated_projections, constraints)
            if lineup.players:  # Only add valid lineups
                lineups.append(lineup)
        
        # Return top unique lineups
        unique_lineups = self._get_unique_lineups(lineups)
        return sorted(unique_lineups, key=lambda x: x.total_projected_points, reverse=True)[:20]
    
    def _get_unique_lineups(self, lineups: List[OptimalLineup]) -> List[OptimalLineup]:
        """Filter out duplicate lineups."""
        
        unique_lineups = []
        seen_lineups = set()
        
        for lineup in lineups:
            # Create lineup signature
            player_ids = sorted([p.player_id for p in lineup.players])
            signature = tuple(player_ids)
            
            if signature not in seen_lineups:
                seen_lineups.add(signature)
                unique_lineups.append(lineup)
        
        return unique_lineups
    
    def _create_lineup_result(self, players: List[PlayerProjection], 
                            constraints: LineupConstraints) -> OptimalLineup:
        """Create OptimalLineup result from selected players."""
        
        if not players:
            return OptimalLineup([], 0, 0, 0, 0, [], 0)
        
        total_points = sum(p.projected_points for p in players)
        total_salary = sum(p.salary for p in players)
        ceiling = sum(p.ceiling for p in players)
        floor = sum(p.floor for p in players)
        teams_used = list(set(p.team for p in players))
        
        # Calculate score (optimization metric)
        score = total_points
        
        return OptimalLineup(
            players=players,
            total_projected_points=total_points,
            total_salary=total_salary,
            ceiling=ceiling,
            floor=floor,
            teams_used=teams_used,
            score=score
        )
    
    def generate_tournament_lineups(self, week: int, season: int, 
                                  scoring_system: str = 'FanDuel',
                                  num_lineups: int = 5) -> List[OptimalLineup]:
        """Generate multiple lineups optimized for tournament play."""
        
        print(f"Generating projections for Week {week}, {season}...")
        projections = self.generate_player_projections(week, season, scoring_system)
        print(f"Generated {len(projections)} player projections")
        
        if not projections:
            return []
        
        print("Running Monte Carlo optimization...")
        lineups = self.optimize_lineup_montecarlo(projections, iterations=500)
        
        # Select diverse lineups for tournament play
        tournament_lineups = []
        used_players = set()
        
        for lineup in lineups:
            if len(tournament_lineups) >= num_lineups:
                break
            
            # Check for player diversity
            lineup_players = set(p.player_id for p in lineup.players)
            overlap = len(lineup_players.intersection(used_players))
            
            # Allow some overlap but prefer diverse lineups
            if overlap <= len(lineup.players) * 0.6:  # Allow 60% overlap
                tournament_lineups.append(lineup)
                used_players.update(lineup_players)
        
        return tournament_lineups[:num_lineups]
    
    def analyze_lineup(self, lineup: OptimalLineup, week: int, season: int,
                      scoring_system: str = 'FanDuel') -> Dict:
        """Analyze lineup performance and provide insights."""
        
        analysis = {
            'lineup_summary': {
                'total_projected_points': lineup.total_projected_points,
                'total_salary': lineup.total_salary,
                'ceiling': lineup.ceiling,
                'floor': lineup.floor,
                'teams_used': len(lineup.teams_used),
                'salary_remaining': 50000 - lineup.total_salary
            },
            'players': [],
            'stack_analysis': {},
            'risk_analysis': {}
        }
        
        # Player analysis
        for player in lineup.players:
            player_analysis = {
                'name': player.player_name,
                'position': player.position,
                'team': player.team,
                'projected_points': player.projected_points,
                'salary': player.salary,
                'value': player.projected_points / (player.salary / 1000),
                'ceiling': player.ceiling,
                'floor': player.floor
            }
            analysis['players'].append(player_analysis)
        
        # Stack analysis (QB + receivers from same team)
        team_players = {}
        for player in lineup.players:
            if player.team not in team_players:
                team_players[player.team] = []
            team_players[player.team].append(player)
        
        for team, players in team_players.items():
            if len(players) >= 2:
                qb_count = sum(1 for p in players if p.position == 'QB')
                skill_count = sum(1 for p in players if p.position in ['RB', 'WR', 'TE'])
                
                if qb_count > 0 and skill_count > 0:
                    analysis['stack_analysis'][team] = {
                        'players': [p.player_name for p in players],
                        'stack_type': 'QB_Stack' if qb_count == 1 and skill_count >= 2 else 'Game_Stack'
                    }
        
        # Risk analysis
        variance = np.var([p.projected_points for p in lineup.players])
        analysis['risk_analysis'] = {
            'variance': variance,
            'risk_level': 'High' if variance > 50 else 'Medium' if variance > 25 else 'Low',
            'ceiling_upside': lineup.ceiling - lineup.total_projected_points,
            'floor_downside': lineup.total_projected_points - lineup.floor
        }
        
        return analysis