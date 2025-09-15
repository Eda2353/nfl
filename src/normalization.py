"""Utilities to normalize/migrate game identifiers to official schedule IDs.

Maps synthetic weekly-data IDs like "2023_12_MIN_vs_GB" to the official
games.game_id by matching season, week, and teams (home/away order agnostic).

Implementation note: this module avoids pandas/numpy imports to prevent
loading heavy BLAS libraries that can crash on some macOS Python setups.
It uses raw SQL via SQLAlchemy instead.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text, create_engine
from sqlalchemy.engine import Engine

try:
    from .database import DatabaseManager
except ImportError:  # when imported as top-level module via sys.path hack in scripts
    DatabaseManager = None  # Optional; script path can pass an Engine directly

logger = logging.getLogger(__name__)

SYNTHETIC_RE = re.compile(r"^(?P<season>\d{4})_(?P<week>\d{1,2})_(?P<t1>[A-Z]{2,3})_vs_(?P<t2>[A-Z]{2,3})$")

TEAM_ALIASES: Dict[str, str] = {
    # Common aliases
    "JAC": "JAX",
    "WSH": "WAS",
}


def _norm_team(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def normalize_game_ids_engine(engine: Engine, seasons: Optional[List[int]] = None,
                              delete_stub_games: bool = True) -> Dict[str, int]:
    """Normalize game_stats.game_id to official IDs from games.

    Args:
        db: DatabaseManager bound to the target DB.
        seasons: Optional list of seasons to limit processing.
        delete_stub_games: If True, remove stub rows in games whose IDs are synthetic after mapping.

    Returns:
        Summary counts dict.
    """
    summary = {"candidates": 0, "mapped": 0, "unmatched": 0, "ambiguous": 0, "deleted_stub_games": 0}

    season_filter_sql = ""
    season_params = {}
    if seasons:
        # Filter by synthetic id prefix season_*
        season_placeholders = ",".join([f":s{i}" for i in range(len(seasons))])
        season_filter_sql = f" AND (substr(gs.game_id,1,4) IN ({season_placeholders}))"
        season_params = {f"s{i}": str(seasons[i]) for i in range(len(seasons))}

    with engine.connect() as conn:
        # Find synthetic IDs present in game_stats
        query = f"""
            SELECT DISTINCT gs.game_id AS synthetic_id
            FROM game_stats gs
            LEFT JOIN games g ON gs.game_id = g.game_id
            WHERE ((gs.game_id LIKE '%/_vs_%' ESCAPE '/' OR gs.game_id LIKE '%_vs_%')
                   OR g.game_id IS NULL)
            {season_filter_sql}
            ORDER BY 1
        """
        rows = conn.execute(text(query), season_params).fetchall()
        candidates = [r[0] for r in rows if r and r[0]]

        summary["candidates"] = len(candidates)
        if not candidates:
            logger.info("No synthetic game IDs detected for normalization")
            return summary

        updates: List[Tuple[str, str]] = []
        for sid in candidates:
            m = SYNTHETIC_RE.match(sid or "")
            if not m:
                summary["unmatched"] += 1
                continue
            season = int(m.group("season"))
            week = int(m.group("week"))
            t1 = _norm_team(m.group("t1"))
            t2 = _norm_team(m.group("t2"))

            # Find official game
            rows = conn.execute(text(
                """
                SELECT game_id
                FROM games
                WHERE season_id = :season AND week = :week
                  AND (
                        (home_team_id = :t1 AND away_team_id = :t2)
                     OR (home_team_id = :t2 AND away_team_id = :t1)
                  )
                """
            ), {"season": season, "week": week, "t1": t1, "t2": t2}).fetchall()

            if not rows:
                summary["unmatched"] += 1
                continue
            if len(rows) > 1:
                summary["ambiguous"] += 1
                continue
            official = rows[0][0]
            updates.append((official, sid))

        # Apply updates in batches
        batch_size = 500
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            # Build a parameterized CASE update for speed, or loop small batches
            for official, synthetic in batch:
                conn.execute(text(
                    "UPDATE game_stats SET game_id = :official WHERE game_id = :synthetic"
                ), {"official": official, "synthetic": synthetic})
            conn.commit()

        summary["mapped"] = len(updates)

        if delete_stub_games and updates:
            # Remove synthetic games that were placeholders
            res = conn.execute(text(
                "DELETE FROM games WHERE (game_id LIKE '%/_vs_%' ESCAPE '/' OR game_id LIKE '%_vs_%')"
            ))
            try:
                conn.commit()
            except Exception:
                pass
            summary["deleted_stub_games"] = getattr(res, "rowcount", 0) or 0

    return summary


def normalize_game_ids(db: "DatabaseManager", seasons: Optional[List[int]] = None,
                       delete_stub_games: bool = True) -> Dict[str, int]:
    """Compatibility wrapper to accept DatabaseManager if available."""
    if hasattr(db, 'engine'):
        return normalize_game_ids_engine(db.engine, seasons=seasons, delete_stub_games=delete_stub_games)
    raise RuntimeError("normalize_game_ids expected DatabaseManager with 'engine' attribute or use normalize_game_ids_engine")
