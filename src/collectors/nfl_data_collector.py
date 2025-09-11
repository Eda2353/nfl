"""NFL data collection using nfl_data_py library."""

import logging
import time
import ssl
import certifi
from typing import List, Dict, Optional
import pandas as pd
import nfl_data_py as nfl
from tqdm import tqdm

# Configure SSL context to use system certificates
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

try:
    from ..database import DatabaseManager
    from ..config import Config
except ImportError:
    from database import DatabaseManager
    from config import Config

logger = logging.getLogger(__name__)

class NFLDataCollector:
    """Collects NFL data using the nfl_data_py library."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        
    def collect_all_data(self):
        """Collect all NFL data for the configured season range."""
        logger.info(f"Starting data collection for seasons {self.config.data_collection.start_season}-{self.config.data_collection.end_season}")
        
        # Collect in order of dependencies
        self.collect_teams()
        self.collect_players() 
        self.collect_games_and_stats()
        self.setup_default_scoring_system()
        
        logger.info("Data collection completed")
    
    def collect_teams(self):
        """Collect team information."""
        logger.info("Collecting team data...")
        
        try:
            # Get team information - nfl_data_py provides team details
            teams_data = []
            
            # Standard NFL team abbreviations with details
            nfl_teams = {
                'ARI': {'name': 'Arizona Cardinals', 'city': 'Arizona', 'division': 'NFC West', 'conference': 'NFC'},
                'ATL': {'name': 'Atlanta Falcons', 'city': 'Atlanta', 'division': 'NFC South', 'conference': 'NFC'},
                'BAL': {'name': 'Baltimore Ravens', 'city': 'Baltimore', 'division': 'AFC North', 'conference': 'AFC'},
                'BUF': {'name': 'Buffalo Bills', 'city': 'Buffalo', 'division': 'AFC East', 'conference': 'AFC'},
                'CAR': {'name': 'Carolina Panthers', 'city': 'Carolina', 'division': 'NFC South', 'conference': 'NFC'},
                'CHI': {'name': 'Chicago Bears', 'city': 'Chicago', 'division': 'NFC North', 'conference': 'NFC'},
                'CIN': {'name': 'Cincinnati Bengals', 'city': 'Cincinnati', 'division': 'AFC North', 'conference': 'AFC'},
                'CLE': {'name': 'Cleveland Browns', 'city': 'Cleveland', 'division': 'AFC North', 'conference': 'AFC'},
                'DAL': {'name': 'Dallas Cowboys', 'city': 'Dallas', 'division': 'NFC East', 'conference': 'NFC'},
                'DEN': {'name': 'Denver Broncos', 'city': 'Denver', 'division': 'AFC West', 'conference': 'AFC'},
                'DET': {'name': 'Detroit Lions', 'city': 'Detroit', 'division': 'NFC North', 'conference': 'NFC'},
                'GB': {'name': 'Green Bay Packers', 'city': 'Green Bay', 'division': 'NFC North', 'conference': 'NFC'},
                'HOU': {'name': 'Houston Texans', 'city': 'Houston', 'division': 'AFC South', 'conference': 'AFC'},
                'IND': {'name': 'Indianapolis Colts', 'city': 'Indianapolis', 'division': 'AFC South', 'conference': 'AFC'},
                'JAX': {'name': 'Jacksonville Jaguars', 'city': 'Jacksonville', 'division': 'AFC South', 'conference': 'AFC'},
                'KC': {'name': 'Kansas City Chiefs', 'city': 'Kansas City', 'division': 'AFC West', 'conference': 'AFC'},
                'LV': {'name': 'Las Vegas Raiders', 'city': 'Las Vegas', 'division': 'AFC West', 'conference': 'AFC'},
                'LAC': {'name': 'Los Angeles Chargers', 'city': 'Los Angeles', 'division': 'AFC West', 'conference': 'AFC'},
                'LAR': {'name': 'Los Angeles Rams', 'city': 'Los Angeles', 'division': 'NFC West', 'conference': 'NFC'},
                'MIA': {'name': 'Miami Dolphins', 'city': 'Miami', 'division': 'AFC East', 'conference': 'AFC'},
                'MIN': {'name': 'Minnesota Vikings', 'city': 'Minnesota', 'division': 'NFC North', 'conference': 'NFC'},
                'NE': {'name': 'New England Patriots', 'city': 'New England', 'division': 'AFC East', 'conference': 'AFC'},
                'NO': {'name': 'New Orleans Saints', 'city': 'New Orleans', 'division': 'NFC South', 'conference': 'NFC'},
                'NYG': {'name': 'New York Giants', 'city': 'New York', 'division': 'NFC East', 'conference': 'NFC'},
                'NYJ': {'name': 'New York Jets', 'city': 'New York', 'division': 'AFC East', 'conference': 'AFC'},
                'PHI': {'name': 'Philadelphia Eagles', 'city': 'Philadelphia', 'division': 'NFC East', 'conference': 'NFC'},
                'PIT': {'name': 'Pittsburgh Steelers', 'city': 'Pittsburgh', 'division': 'AFC North', 'conference': 'AFC'},
                'SF': {'name': 'San Francisco 49ers', 'city': 'San Francisco', 'division': 'NFC West', 'conference': 'NFC'},
                'SEA': {'name': 'Seattle Seahawks', 'city': 'Seattle', 'division': 'NFC West', 'conference': 'NFC'},
                'TB': {'name': 'Tampa Bay Buccaneers', 'city': 'Tampa Bay', 'division': 'NFC South', 'conference': 'NFC'},
                'TEN': {'name': 'Tennessee Titans', 'city': 'Tennessee', 'division': 'AFC South', 'conference': 'AFC'},
                'WAS': {'name': 'Washington Commanders', 'city': 'Washington', 'division': 'NFC East', 'conference': 'NFC'},
            }
            
            for team_id, info in nfl_teams.items():
                teams_data.append({
                    'team_id': team_id,
                    'team_name': info['name'],
                    'city': info['city'],
                    'division': info['division'],
                    'conference': info['conference']
                })
            
            teams_df = pd.DataFrame(teams_data)
            self.db.bulk_insert_dataframe(teams_df, 'teams', if_exists='replace')
            logger.info(f"Inserted {len(teams_df)} teams")
            
        except Exception as e:
            logger.error(f"Error collecting team data: {e}")
            raise
    
    def collect_players(self):
        """Collect player roster information for all seasons."""
        logger.info("Collecting player roster data...")
        
        try:
            seasons = list(range(self.config.data_collection.start_season, 
                               self.config.data_collection.end_season + 1))
            
            all_players = []
            all_player_teams = []
            
            for season in tqdm(seasons, desc="Collecting player rosters"):
                try:
                    # Get roster data for the season
                    rosters = nfl.import_seasonal_rosters([season])
                    
                    if rosters.empty:
                        logger.warning(f"No roster data found for season {season}")
                        continue
                    
                    # Process players
                    for _, row in rosters.iterrows():
                        player_data = {
                            'player_id': row.get('player_id', ''),
                            'player_name': row.get('player_name', ''),
                            'position': row.get('position', ''),
                            'height': row.get('height'),
                            'weight': row.get('weight'),
                            'birth_date': row.get('birth_date'),
                            'college': row.get('college'),
                            'draft_year': row.get('draft_year'),
                            'draft_round': row.get('draft_round'),
                            'draft_pick': row.get('draft_pick')
                        }
                        all_players.append(player_data)
                        
                        # Player-team relationship
                        team_data = {
                            'player_id': row.get('player_id', ''),
                            'team_id': row.get('team', ''),
                            'season_id': season,
                            'week_start': 1,
                            'week_end': 18
                        }
                        all_player_teams.append(team_data)
                    
                    time.sleep(self.config.data_collection.rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"Error collecting roster for season {season}: {e}")
                    continue
            
            # Remove duplicates and insert players
            players_df = pd.DataFrame(all_players).drop_duplicates(subset=['player_id'])
            if not players_df.empty:
                self.db.bulk_insert_dataframe(players_df, 'players', if_exists='replace')
                logger.info(f"Inserted {len(players_df)} unique players")
            
            # Insert player-team relationships
            player_teams_df = pd.DataFrame(all_player_teams)
            if not player_teams_df.empty:
                self.db.bulk_insert_dataframe(player_teams_df, 'player_teams', if_exists='replace')
                logger.info(f"Inserted {len(player_teams_df)} player-team relationships")
            
        except Exception as e:
            logger.error(f"Error collecting player data: {e}")
            raise
    
    def collect_games_and_stats(self):
        """Collect game information and player statistics."""
        logger.info("Collecting games and player statistics...")
        
        seasons = list(range(self.config.data_collection.start_season,
                           self.config.data_collection.end_season + 1))
        
        # First collect seasons data
        seasons_data = [{'season_id': season, 'season_type': 'REG'} for season in seasons]
        seasons_df = pd.DataFrame(seasons_data)
        self.db.bulk_insert_dataframe(seasons_df, 'seasons', if_exists='replace')
        
        for season in tqdm(seasons, desc="Collecting game data and stats"):
            try:
                self._collect_season_games_and_stats(season)
                time.sleep(self.config.data_collection.rate_limit_delay)
                
            except Exception as e:
                logger.error(f"Error collecting data for season {season}: {e}")
                continue
    
    def _collect_season_games_and_stats(self, season: int):
        """Collect games and stats for a specific season."""
        
        # Get weekly player stats 
        weekly_stats = nfl.import_weekly_data([season])
        
        if weekly_stats.empty:
            logger.warning(f"No weekly stats found for season {season}")
            return
        
        # Create game IDs and collect unique games
        weekly_stats['game_id'] = (
            weekly_stats['season'].astype(str) + '_' +
            weekly_stats['week'].astype(str) + '_' +
            weekly_stats['recent_team'] + '_vs_' +
            weekly_stats['opponent_team']
        )
        
        # Process games first - get unique games
        games_info = weekly_stats[['season', 'week', 'recent_team', 'opponent_team', 'game_id']].drop_duplicates()
        
        games_data = []
        seen_games = set()
        
        for _, row in games_info.iterrows():
            game_id = row['game_id']
            if game_id not in seen_games:
                # We don't know which team is home/away from weekly data, so we'll set both to None
                game_data = {
                    'game_id': game_id,
                    'season_id': season,
                    'week': row['week'],
                    'game_date': None,  # Not available in weekly stats
                    'home_team_id': None,  # Can't determine from weekly stats
                    'away_team_id': None,  # Can't determine from weekly stats
                    'home_score': None,
                    'away_score': None,
                    'weather_conditions': None,
                    'temperature': None,
                    'wind_speed': None,
                    'is_dome': None,
                    'game_time': None
                }
                games_data.append(game_data)
                seen_games.add(game_id)
        
        if games_data:
            games_df = pd.DataFrame(games_data)
            self.db.bulk_insert_dataframe(games_df, 'games', if_exists='append')
        
        # Process player statistics
        if not weekly_stats.empty:
            # Clean up the data - the weekly data should already be one row per player per game
            weekly_stats = weekly_stats.dropna(subset=['player_id'])
            weekly_stats = weekly_stats[weekly_stats['player_id'] != '']
            
            # Convert to our database format
            stats_data = []
            for _, row in weekly_stats.iterrows():
                stat_data = {
                    'player_id': row['player_id'],
                    'game_id': row['game_id'],
                    'team_id': row['recent_team'],
                    
                    # Passing stats
                    'pass_attempts': row.get('attempts', 0) or 0,
                    'pass_completions': row.get('completions', 0) or 0,
                    'pass_yards': row.get('passing_yards', 0) or 0,
                    'pass_touchdowns': row.get('passing_tds', 0) or 0,
                    'pass_interceptions': row.get('interceptions', 0) or 0,
                    'pass_sacks': row.get('sacks', 0) or 0,
                    'pass_sack_yards': row.get('sack_yards', 0) or 0,
                    
                    # Rushing stats
                    'rush_attempts': row.get('carries', 0) or 0,
                    'rush_yards': row.get('rushing_yards', 0) or 0,
                    'rush_touchdowns': row.get('rushing_tds', 0) or 0,
                    'rush_fumbles': row.get('rushing_fumbles', 0) or 0,
                    
                    # Receiving stats
                    'receptions': row.get('receptions', 0) or 0,
                    'receiving_targets': row.get('targets', 0) or 0,
                    'receiving_yards': row.get('receiving_yards', 0) or 0,
                    'receiving_touchdowns': row.get('receiving_tds', 0) or 0,
                    'receiving_fumbles': row.get('receiving_fumbles', 0) or 0,
                    
                    # Advanced metrics
                    'target_share': row.get('target_share'),
                    'air_yards': row.get('receiving_air_yards', 0) or 0,
                    'yards_after_catch': row.get('receiving_yards_after_catch', 0) or 0,
                    
                    # Game context - we can't determine home/away from weekly stats
                    'is_home': None,
                }
                stats_data.append(stat_data)
            
            if stats_data:
                stats_df = pd.DataFrame(stats_data)
                self.db.bulk_insert_dataframe(stats_df, 'game_stats', if_exists='append')
                logger.info(f"Inserted {len(stats_df)} stat records for season {season}")
    
    def setup_default_scoring_system(self):
        """Set up default fantasy scoring systems."""
        logger.info("Setting up default scoring systems...")
        
        scoring_systems = [
            {
                'system_name': 'Standard',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 0,  # No PPR
                'receiving_yard_points': 0.1,
                'receiving_td_points': 6,
                'fumble_points': -2
            },
            {
                'system_name': 'PPR',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 1.0,  # Full PPR
                'receiving_yard_points': 0.1,
                'receiving_td_points': 6,
                'fumble_points': -2
            },
            {
                'system_name': 'Half PPR',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 0.5,  # Half PPR
                'receiving_yard_points': 0.1,
                'receiving_td_points': 6,
                'fumble_points': -2
            }
        ]
        
        scoring_df = pd.DataFrame(scoring_systems)
        self.db.bulk_insert_dataframe(scoring_df, 'scoring_systems', if_exists='replace')
        logger.info(f"Inserted {len(scoring_df)} scoring systems")