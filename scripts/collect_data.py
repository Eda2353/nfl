#!/usr/bin/env python3
"""Script to collect NFL data and populate the database."""

import sys
import os
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config
from database import DatabaseManager
from collectors import NFLDataCollector

def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('data_collection.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """Main data collection function."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting NFL data collection...")
    
    try:
        # Load configuration
        # Ensure a default DB_PATH if not provided externally
        os.environ.setdefault("DB_PATH", "data/nfl_data.db")
        config = Config.from_env()
        logger.info(f"Collecting data for seasons {config.data_collection.start_season}-{config.data_collection.end_season}")
        
        # Initialize database
        db_manager = DatabaseManager(config)
        logger.info("Database initialized successfully")
        
        # Initialize data collector
        collector = NFLDataCollector(config, db_manager)
        
        # Collect all data
        collector.collect_all_data()
        
        logger.info("Data collection completed successfully!")
        
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        raise

if __name__ == "__main__":
    main()
