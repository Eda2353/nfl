"""Database connection and management utilities."""

import sqlite3
import logging
from pathlib import Path
from typing import Optional
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from .config import Config
except ImportError:
    from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, config: Config):
        self.config = config
        self.engine: Optional[Engine] = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection and create tables if needed."""
        if self.config.database.db_type == "sqlite":
            # Ensure data directory exists
            db_path = Path(self.config.database.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            connection_string = f"sqlite:///{self.config.database.db_path}"
        else:
            # PostgreSQL connection
            connection_string = (
                f"postgresql://{self.config.database.db_user}:"
                f"{self.config.database.db_password}@"
                f"{self.config.database.db_host}:"
                f"{self.config.database.db_port}/"
                f"{self.config.database.db_name}"
            )
        
        self.engine = create_engine(connection_string)
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables from schema file."""
        schema_path = Path(__file__).parent / "database_schema.sql"
        
        try:
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Split by semicolon and execute each statement
            statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
            
            with self.engine.connect() as conn:
                for statement in statements:
                    if statement:
                        try:
                            conn.execute(text(statement))
                            conn.commit()
                        except Exception as e:
                            logger.warning(f"Statement execution warning: {e}")
                            # Continue with other statements
                            pass
                            
        except FileNotFoundError:
            logger.error(f"Schema file not found: {schema_path}")
            raise
    
    def execute_query(self, query: str, params=None) -> pd.DataFrame:
        """Execute a SELECT query and return results as DataFrame."""
        return pd.read_sql_query(query, self.engine, params=params)
    
    def execute_statement(self, statement: str, params=None):
        """Execute an INSERT/UPDATE/DELETE statement."""
        with self.engine.connect() as conn:
            conn.execute(text(statement), params or {})
            conn.commit()
    
    def bulk_insert_dataframe(self, df: pd.DataFrame, table_name: str, if_exists='append'):
        """Insert DataFrame into database table."""
        df.to_sql(table_name, self.engine, if_exists=if_exists, index=False)
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        with self.engine.connect() as conn:
            if self.config.database.db_type == "sqlite":
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
                ), {"table_name": table_name})
            else:
                result = conn.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:table_name"
                ), {"table_name": table_name})
            
            return result.fetchone() is not None
    
    def get_existing_seasons(self) -> list:
        """Get list of seasons already in database."""
        try:
            df = self.execute_query("SELECT DISTINCT season_id FROM seasons ORDER BY season_id")
            return df['season_id'].tolist()
        except:
            return []
    
    def get_existing_games(self, season: int) -> list:
        """Get list of game IDs already in database for a season."""
        try:
            df = self.execute_query(
                "SELECT game_id FROM games WHERE season_id = ?", 
                params=[season]
            )
            return df['game_id'].tolist()
        except:
            return []