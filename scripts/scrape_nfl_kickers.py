#!/usr/bin/env python3
"""Scrape current kicker data from NFL.com for 2024-2025."""

import requests
import json
import sqlite3
import logging
from bs4 import BeautifulSoup
import re

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)

def scrape_nfl_kickers():
    """Scrape kicker stats from NFL.com for current seasons."""
    
    logger = setup_logging()
    conn = sqlite3.connect('data/nfl_data.db')
    cursor = conn.cursor()
    
    # Create table for current kicker stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nfl_kicker_stats_2024_2025 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name VARCHAR(100),
            team VARCHAR(10),
            season INTEGER,
            fg_made INTEGER,
            fg_attempted INTEGER,
            fg_pct REAL,
            fg_long INTEGER,
            fg_1_19 VARCHAR(10),
            fg_20_29 VARCHAR(10),
            fg_30_39 VARCHAR(10),
            fg_40_49 VARCHAR(10),
            fg_50_plus VARCHAR(10),
            extra_points VARCHAR(10),
            data_source VARCHAR(20) DEFAULT 'NFL.com'
        )
    """)
    
    # Try to get the page content for 2024
    seasons = [2024, 2025]
    
    for season in seasons:
        logger.info(f"Scraping NFL.com kicker data for {season}...")
        
        try:
            url = f"https://www.nfl.com/stats/player-stats/category/field-goals/{season}/reg/all/kickingfgmade/desc"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Check if there's JSON data in the page
                content = response.text
                
                # Look for JSON data in script tags
                json_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.*?});'
                json_match = re.search(json_pattern, content, re.DOTALL)
                
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        logger.info(f"Found JSON data for {season}")
                        
                        # Navigate through the data structure to find kicker stats
                        # This would need to be adjusted based on actual structure
                        logger.info("Need to parse NFL.com data structure...")
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse JSON for {season}")
                
                else:
                    logger.warning(f"No JSON data found for {season}")
                    
            else:
                logger.warning(f"Failed to get {season} data: HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error scraping {season} data: {e}")
            continue
    
    conn.close()

if __name__ == "__main__":
    scrape_nfl_kickers()