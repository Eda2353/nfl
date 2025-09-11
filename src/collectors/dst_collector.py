"""Team Defense/Special Teams data collection from nfl-data-py."""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import nfl_data_py as nfl
from sqlalchemy import text

try:
    from ..database import DatabaseManager
    from ..config import Config
except ImportError:
    from database import DatabaseManager
    from config import Config


class DSTCollector:
    """Collect and store team defense statistics."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
    def collect_team_defense_stats(self, seasons: List[int]) -> None:
        """Collect team defense statistics from game data and schedules."""
        
        print(f"Collecting team defense data for seasons: {seasons}")
        
        # Get schedule data for all seasons
        schedules = nfl.import_schedules(seasons)
        schedules = schedules[schedules['game_type'] == 'REG']  # Regular season only
        
        print(f"Processing {len(schedules)} regular season games...")
        
        defense_stats = []
        
        for _, game in schedules.iterrows():
            game_id = game['game_id']
            season = game['season']
            week = game['week']
            home_team = game['home_team']
            away_team = game['away_team']
            home_score = game['home_score'] if not pd.isna(game['home_score']) else 0
            away_score = game['away_score'] if not pd.isna(game['away_score']) else 0
            
            # Create defense stats for both teams
            # Home team defense (defending against away team)
            home_defense = {
                'team_id': home_team,
                'game_id': game_id,
                'season_id': season,
                'week': week,
                'points_allowed': int(away_score),
                'opponent_team_id': away_team,
                'is_home': True,
                # Initialize other stats to 0 - will be populated from play-by-play if available
                'yards_allowed': 0,
                'passing_yards_allowed': 0,
                'rushing_yards_allowed': 0,
                'interceptions': 0,
                'fumbles_recovered': 0,
                'sacks': 0.0,
                'sack_yards': 0,
                'defensive_touchdowns': 0,
                'pick_six': 0,
                'fumble_touchdowns': 0,
                'safeties': 0,
                'blocked_kicks': 0,
                'return_touchdowns': 0
            }
            
            # Away team defense (defending against home team)
            away_defense = {
                'team_id': away_team,
                'game_id': game_id,
                'season_id': season,
                'week': week,
                'points_allowed': int(home_score),
                'opponent_team_id': home_team,
                'is_home': False,
                # Initialize other stats to 0
                'yards_allowed': 0,
                'passing_yards_allowed': 0,
                'rushing_yards_allowed': 0,
                'interceptions': 0,
                'fumbles_recovered': 0,
                'sacks': 0.0,
                'sack_yards': 0,
                'defensive_touchdowns': 0,
                'pick_six': 0,
                'fumble_touchdowns': 0,
                'safeties': 0,
                'blocked_kicks': 0,
                'return_touchdowns': 0
            }
            
            defense_stats.extend([home_defense, away_defense])
        
        # Try to enhance with play-by-play data for more detailed stats
        self._enhance_with_pbp_data(defense_stats, seasons)
        
        # Store in database
        self._store_defense_stats(defense_stats)
        
        print(f"Collected {len(defense_stats)} team defense records")
    
    def _enhance_with_pbp_data(self, defense_stats: List[Dict], seasons: List[int]) -> None:
        """Enhance defense stats with play-by-play data where available."""
        
        print("Attempting to enhance with play-by-play data...")
        
        try:
            # Get play-by-play data for sample of games to extract defensive stats
            # This is computationally expensive, so we'll do it selectively
            for season in seasons[-2:]:  # Only process last 2 seasons for PBP data
                print(f"Processing PBP data for {season}...")
                try:
                    pbp_data = nfl.import_pbp_data([season])
                    
                    if pbp_data.empty:
                        continue
                        
                    # Process defensive stats from play-by-play
                    self._extract_defense_stats_from_pbp(pbp_data, defense_stats, season)
                    
                except Exception as e:
                    print(f"Warning: Could not process PBP data for {season}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Warning: Could not enhance with PBP data: {e}")
            print("Proceeding with basic points allowed data only")
    
    def _extract_defense_stats_from_pbp(self, pbp_data: pd.DataFrame, 
                                      defense_stats: List[Dict], season: int) -> None:
        """Extract defensive statistics from play-by-play data."""
        
        # Group by game and defensive team to aggregate stats
        game_groups = pbp_data.groupby(['game_id', 'defteam'])
        
        for (game_id, def_team), plays in game_groups:
            if pd.isna(def_team):
                continue
                
            # Find corresponding defense stat record
            defense_record = None
            for stat in defense_stats:
                if stat['game_id'] == game_id and stat['team_id'] == def_team and stat['season_id'] == season:
                    defense_record = stat
                    break
            
            if not defense_record:
                continue
            
            # Calculate defensive stats from plays
            # Sacks
            sacks = plays[plays['sack'] == 1]
            defense_record['sacks'] = len(sacks)
            defense_record['sack_yards'] = sacks['yards_gained'].abs().sum() if not sacks.empty else 0
            
            # Interceptions
            ints = plays[plays['interception'] == 1]
            defense_record['interceptions'] = len(ints)
            
            # Pick-six (interception returned for TD)
            pick_six = ints[ints['return_touchdown'] == 1]
            defense_record['pick_six'] = len(pick_six)
            
            # Fumble recoveries
            fumble_recoveries = plays[(plays['fumble_lost'] == 1) & (plays['fumble_recovery_1_team'] == def_team)]
            defense_record['fumbles_recovered'] = len(fumble_recoveries)
            
            # Safeties
            safeties = plays[(plays['safety'] == 1) & (plays['defteam'] == def_team)]
            defense_record['safeties'] = len(safeties)
            
            # Total yards allowed (approximate from offensive plays against this defense)
            offensive_plays = plays[plays['play_type'].isin(['pass', 'run'])]
            if not offensive_plays.empty:
                defense_record['yards_allowed'] = offensive_plays['yards_gained'].sum()
                
                # Passing yards allowed
                pass_plays = offensive_plays[offensive_plays['play_type'] == 'pass']
                defense_record['passing_yards_allowed'] = pass_plays['yards_gained'].sum()
                
                # Rushing yards allowed  
                run_plays = offensive_plays[offensive_plays['play_type'] == 'run']
                defense_record['rushing_yards_allowed'] = run_plays['yards_gained'].sum()
    
    def _store_defense_stats(self, defense_stats: List[Dict]) -> None:
        """Store team defense statistics in the database."""
        
        print("Storing team defense statistics in database...")
        
        with self.db.engine.connect() as conn:
            # Clear existing data for these seasons
            seasons = list(set(stat['season_id'] for stat in defense_stats))
            seasons_str = ','.join(map(str, seasons))
            
            conn.execute(text(f"DELETE FROM team_defense_stats WHERE season_id IN ({seasons_str})"))
            
            # Insert new data in batches
            batch_size = 100  # Smaller batch size to avoid parameter limits
            for i in range(0, len(defense_stats), batch_size):
                batch = defense_stats[i:i + batch_size]
                
                # Prepare insert query
                placeholders = []
                params = {}
                
                for j, stat in enumerate(batch):
                    placeholder = f"(:team_id_{j}, :game_id_{j}, :season_id_{j}, :week_{j}, " \
                                f":points_allowed_{j}, :yards_allowed_{j}, :passing_yards_allowed_{j}, " \
                                f":rushing_yards_allowed_{j}, :interceptions_{j}, :fumbles_recovered_{j}, " \
                                f":sacks_{j}, :sack_yards_{j}, :defensive_touchdowns_{j}, " \
                                f":pick_six_{j}, :fumble_touchdowns_{j}, :safeties_{j}, " \
                                f":blocked_kicks_{j}, :return_touchdowns_{j}, :is_home_{j}, :opponent_team_id_{j})"
                    placeholders.append(placeholder)
                    
                    # Add parameters to dict
                    for key, value in stat.items():
                        params[f"{key}_{j}"] = value
                
                query = f"""
                    INSERT INTO team_defense_stats (
                        team_id, game_id, season_id, week, points_allowed, yards_allowed,
                        passing_yards_allowed, rushing_yards_allowed, interceptions, 
                        fumbles_recovered, sacks, sack_yards, defensive_touchdowns,
                        pick_six, fumble_touchdowns, safeties, blocked_kicks, 
                        return_touchdowns, is_home, opponent_team_id
                    ) VALUES {', '.join(placeholders)}
                """
                
                conn.execute(text(query), params)
            
            conn.commit()
        
        print(f"Successfully stored {len(defense_stats)} team defense records")
    
    def get_team_defense_stats(self, team_id: str, season: int, 
                             week: Optional[int] = None) -> pd.DataFrame:
        """Get team defense statistics for a specific team and timeframe."""
        
        with self.db.engine.connect() as conn:
            conditions = ["team_id = :team_id", "season_id = :season"]
            params = {'team_id': team_id, 'season': season}
            
            if week is not None:
                conditions.append("week <= :week")
                params['week'] = week
            
            where_clause = " AND ".join(conditions)
            
            return pd.read_sql_query(text(f"""
                SELECT * FROM team_defense_stats
                WHERE {where_clause}
                ORDER BY week
            """), conn, params=params)


def main():
    """Test the DST collector."""
    config = Config.from_env()
    db_manager = DatabaseManager(config)
    collector = DSTCollector(db_manager)
    
    # Collect data for recent seasons
    collector.collect_team_defense_stats([2022, 2023])


if __name__ == "__main__":
    main()