"""Configuration settings for NFL Fantasy Football Optimizer."""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    db_type: str = "sqlite"  # sqlite or postgresql
    db_path: str = "data/nfl_fantasy.db"  # for sqlite
    db_host: Optional[str] = None  # for postgresql
    db_port: Optional[int] = None
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None

@dataclass
class DataCollectionConfig:
    """Data collection settings."""
    start_season: int = 2004
    end_season: int = 2024
    include_preseason: bool = False
    include_postseason: bool = True
    batch_size: int = 100
    rate_limit_delay: float = 0.5  # seconds between API calls

@dataclass
class Config:
    """Main configuration class."""
    database: DatabaseConfig = None
    data_collection: DataCollectionConfig = None
    
    def __post_init__(self):
        if self.database is None:
            self.database = DatabaseConfig()
        if self.data_collection is None:
            self.data_collection = DataCollectionConfig()
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        config = cls()
        
        # Database config from env
        config.database.db_type = os.getenv("DB_TYPE", "sqlite")
        config.database.db_path = os.getenv("DB_PATH", "data/nfl_fantasy.db")
        config.database.db_host = os.getenv("DB_HOST")
        config.database.db_port = int(os.getenv("DB_PORT", 5432)) if os.getenv("DB_PORT") else None
        config.database.db_name = os.getenv("DB_NAME")
        config.database.db_user = os.getenv("DB_USER")
        config.database.db_password = os.getenv("DB_PASSWORD")
        
        # Data collection config from env
        config.data_collection.start_season = int(os.getenv("START_SEASON", 2004))
        config.data_collection.end_season = int(os.getenv("END_SEASON", 2024))
        
        return config