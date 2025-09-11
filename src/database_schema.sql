-- NFL Fantasy Football Database Schema
-- Designed to store 20+ years of NFL player and game data

-- Teams table
CREATE TABLE teams (
    team_id VARCHAR(3) PRIMARY KEY,
    team_name VARCHAR(50) NOT NULL,
    city VARCHAR(50),
    division VARCHAR(10),
    conference VARCHAR(3)
);

-- Players table
CREATE TABLE players (
    player_id VARCHAR(20) PRIMARY KEY,
    player_name VARCHAR(100) NOT NULL,
    position VARCHAR(5),
    height INTEGER, -- inches
    weight INTEGER, -- pounds
    birth_date DATE,
    college VARCHAR(100),
    draft_year INTEGER,
    draft_round INTEGER,
    draft_pick INTEGER
);

-- Seasons table
CREATE TABLE seasons (
    season_id INTEGER PRIMARY KEY,
    season_type VARCHAR(10) -- REG, POST, PRE
);

-- Games table
CREATE TABLE games (
    game_id VARCHAR(20) PRIMARY KEY,
    season_id INTEGER,
    week INTEGER,
    game_date DATE,
    home_team_id VARCHAR(3),
    away_team_id VARCHAR(3),
    home_score INTEGER,
    away_score INTEGER,
    weather_conditions TEXT,
    temperature INTEGER,
    wind_speed INTEGER,
    is_dome BOOLEAN,
    game_time TIME,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);

-- Player roster/team history
CREATE TABLE player_teams (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20),
    team_id VARCHAR(3),
    season_id INTEGER,
    week_start INTEGER DEFAULT 1,
    week_end INTEGER DEFAULT 18,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

-- Game statistics - comprehensive stats table
CREATE TABLE game_stats (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20),
    game_id VARCHAR(20),
    team_id VARCHAR(3),
    
    -- Passing stats
    pass_attempts INTEGER DEFAULT 0,
    pass_completions INTEGER DEFAULT 0,
    pass_yards INTEGER DEFAULT 0,
    pass_touchdowns INTEGER DEFAULT 0,
    pass_interceptions INTEGER DEFAULT 0,
    pass_sacks INTEGER DEFAULT 0,
    pass_sack_yards INTEGER DEFAULT 0,
    
    -- Rushing stats
    rush_attempts INTEGER DEFAULT 0,
    rush_yards INTEGER DEFAULT 0,
    rush_touchdowns INTEGER DEFAULT 0,
    rush_fumbles INTEGER DEFAULT 0,
    
    -- Receiving stats
    receptions INTEGER DEFAULT 0,
    receiving_targets INTEGER DEFAULT 0,
    receiving_yards INTEGER DEFAULT 0,
    receiving_touchdowns INTEGER DEFAULT 0,
    receiving_fumbles INTEGER DEFAULT 0,
    
    -- Kicking stats
    field_goals_made INTEGER DEFAULT 0,
    field_goals_attempted INTEGER DEFAULT 0,
    extra_points_made INTEGER DEFAULT 0,
    extra_points_attempted INTEGER DEFAULT 0,
    
    -- Defense/ST stats
    tackles_solo INTEGER DEFAULT 0,
    tackles_assisted INTEGER DEFAULT 0,
    sacks_defense DECIMAL(3,1) DEFAULT 0,
    interceptions_defense INTEGER DEFAULT 0,
    fumbles_recovered INTEGER DEFAULT 0,
    fumbles_forced INTEGER DEFAULT 0,
    pass_defended INTEGER DEFAULT 0,
    defensive_touchdowns INTEGER DEFAULT 0,
    safety INTEGER DEFAULT 0,
    
    -- Special teams
    punt_returns INTEGER DEFAULT 0,
    punt_return_yards INTEGER DEFAULT 0,
    punt_return_touchdowns INTEGER DEFAULT 0,
    kick_returns INTEGER DEFAULT 0,
    kick_return_yards INTEGER DEFAULT 0,
    kick_return_touchdowns INTEGER DEFAULT 0,
    
    -- Punting
    punts INTEGER DEFAULT 0,
    punt_yards INTEGER DEFAULT 0,
    
    -- Advanced metrics (when available)
    snap_count INTEGER,
    snap_percentage DECIMAL(5,2),
    routes_run INTEGER,
    air_yards INTEGER,
    yards_after_catch INTEGER,
    target_share DECIMAL(5,4),
    
    -- Game context
    is_home BOOLEAN,
    game_script_differential INTEGER, -- point differential during game
    
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    
    UNIQUE(player_id, game_id)
);

-- Fantasy scoring configurations
CREATE TABLE scoring_systems (
    system_id SERIAL PRIMARY KEY,
    system_name VARCHAR(50) UNIQUE NOT NULL,
    
    -- Passing scoring
    pass_yard_points DECIMAL(4,3) DEFAULT 0.04,
    pass_td_points INTEGER DEFAULT 4,
    pass_int_points INTEGER DEFAULT -2,
    
    -- Rushing scoring  
    rush_yard_points DECIMAL(4,3) DEFAULT 0.1,
    rush_td_points INTEGER DEFAULT 6,
    
    -- Receiving scoring
    reception_points DECIMAL(3,1) DEFAULT 0, -- PPR setting
    receiving_yard_points DECIMAL(4,3) DEFAULT 0.1,
    receiving_td_points INTEGER DEFAULT 6,
    
    -- Fumble penalty
    fumble_points INTEGER DEFAULT -2,
    
    -- Kicking
    field_goal_points INTEGER DEFAULT 3,
    extra_point_points INTEGER DEFAULT 1,
    
    -- Defense/ST
    defensive_td_points INTEGER DEFAULT 6,
    sack_points DECIMAL(3,1) DEFAULT 1.0,
    int_points INTEGER DEFAULT 2,
    fumble_recovery_points INTEGER DEFAULT 2,
    safety_points INTEGER DEFAULT 2
);

-- Pre-calculated fantasy points for quick queries
CREATE TABLE fantasy_points (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20),
    game_id VARCHAR(20),
    system_id INTEGER,
    fantasy_points DECIMAL(6,2),
    
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (system_id) REFERENCES scoring_systems(system_id),
    
    UNIQUE(player_id, game_id, system_id)
);

-- Indexes for performance
CREATE INDEX idx_game_stats_player_season ON game_stats(player_id, game_id);
CREATE INDEX idx_game_stats_game_date ON games(game_date);
CREATE INDEX idx_game_stats_season_week ON games(season_id, week);
CREATE INDEX idx_fantasy_points_lookup ON fantasy_points(player_id, system_id);
CREATE INDEX idx_player_teams_season ON player_teams(player_id, season_id);