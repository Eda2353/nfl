"""Initialize scoring systems in the database."""

import logging
from sqlalchemy import text
import pandas as pd

logger = logging.getLogger(__name__)

def init_scoring_systems(db_manager):
    """Initialize scoring systems if they don't exist.

    This function is schema-aware: it inspects the current
    scoring_systems columns and only inserts fields that exist.
    It also maps between legacy column names and the current schema.
    """
    
    with db_manager.engine.connect() as conn:
        # Check existing systems
        existing = pd.read_sql_query(text("SELECT system_name FROM scoring_systems"), conn)
        existing_names = set(existing['system_name'].tolist())

        # Get existing columns for schema-aware inserts
        columns_df = pd.read_sql_query(text("PRAGMA table_info(scoring_systems)"), conn)
        existing_cols = set(columns_df['name'].tolist())

        def map_values_to_existing_columns(values: dict) -> dict:
            """Map canonical scoring values onto whatever columns exist in the table."""
            out = {}
            # Always include system_name if available
            if 'system_name' in existing_cols:
                out['system_name'] = values['system_name']
            
            # Core scoring
            core_keys = [
                'pass_yard_points', 'pass_td_points', 'pass_int_points',
                'rush_yard_points', 'rush_td_points',
                'reception_points', 'receiving_yard_points', 'receiving_td_points',
                'fumble_points'
            ]
            for k in core_keys:
                if k in existing_cols and k in values:
                    out[k] = values[k]

            # Kicking (optional in older schemas)
            for k in ['field_goal_points', 'extra_point_points']:
                if k in existing_cols and k in values:
                    out[k] = values[k]

            # DST stats mapping (support legacy names if present)
            # sacks
            if 'sack_points' in existing_cols and 'sack_points' in values:
                out['sack_points'] = values['sack_points']
            elif 'dst_sack_points' in existing_cols and 'sack_points' in values:
                out['dst_sack_points'] = values['sack_points']
            # interceptions
            if 'int_points' in existing_cols and 'int_points' in values:
                out['int_points'] = values['int_points']
            elif 'dst_interception_points' in existing_cols and 'int_points' in values:
                out['dst_interception_points'] = values['int_points']
            # fumble recoveries
            if 'fumble_recovery_points' in existing_cols and 'fumble_recovery_points' in values:
                out['fumble_recovery_points'] = values['fumble_recovery_points']
            elif 'dst_fumble_recovery_points' in existing_cols and 'fumble_recovery_points' in values:
                out['dst_fumble_recovery_points'] = values['fumble_recovery_points']
            # defensive TDs
            if 'defensive_td_points' in existing_cols and 'defensive_td_points' in values:
                out['defensive_td_points'] = values['defensive_td_points']
            elif 'dst_touchdown_points' in existing_cols and 'defensive_td_points' in values:
                out['dst_touchdown_points'] = values['defensive_td_points']
            # safeties
            if 'safety_points' in existing_cols and 'safety_points' in values:
                out['safety_points'] = values['safety_points']
            elif 'dst_safety_points' in existing_cols and 'safety_points' in values:
                out['dst_safety_points'] = values['safety_points']

            # Points allowed tiers (new vs legacy names)
            mapping_tiers = [
                ('dst_shutout_points', 'dst_points_allowed_0_points'),
                ('dst_1to6_points', 'dst_points_allowed_1_6_points'),
                ('dst_7to13_points', 'dst_points_allowed_7_13_points'),
                ('dst_14to20_points', 'dst_points_allowed_14_20_points'),
                ('dst_21to27_points', 'dst_points_allowed_21_27_points'),
                ('dst_28to34_points', 'dst_points_allowed_28_34_points'),
                ('dst_35plus_points', 'dst_points_allowed_35_points'),
            ]
            for new_key, old_key in mapping_tiers:
                val = values.get(new_key)
                if val is None:
                    continue
                if new_key in existing_cols:
                    out[new_key] = val
                elif old_key in existing_cols:
                    out[old_key] = val

            # Yardage bonuses (optional)
            for k in ['dst_under300_bonus', 'dst_under100_bonus']:
                if k in existing_cols and k in values:
                    out[k] = values[k]

            return out
        
        # Define default systems
        default_systems = []
        
        if 'Standard' not in existing_names:
            default_systems.append({
                'system_name': 'Standard',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 0,
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
            })
            
        if 'PPR' not in existing_names:
            default_systems.append({
                'system_name': 'PPR',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 1.0,
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
            })
            
        if 'Half PPR' not in existing_names:
            default_systems.append({
                'system_name': 'Half PPR',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -2,
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
            })
            
        if 'FanDuel' not in existing_names:
            default_systems.append({
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
            })
            
        if 'DraftKings' not in existing_names:
            default_systems.append({
                'system_name': 'DraftKings',
                'pass_yard_points': 0.04,
                'pass_td_points': 4,
                'pass_int_points': -1,
                'rush_yard_points': 0.1,
                'rush_td_points': 6,
                'reception_points': 1.0,
                'receiving_yard_points': 0.1,
                'receiving_td_points': 6,
                'fumble_points': -1,
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
            })
        
        # Insert new systems (schema-aware)
        for base in default_systems:
            system = map_values_to_existing_columns(base)
            if not system:
                continue
            columns = ', '.join(system.keys())
            placeholders = ', '.join([f':{key}' for key in system.keys()])
            query = text(f"INSERT INTO scoring_systems ({columns}) VALUES ({placeholders})")
            conn.execute(query, system)
            conn.commit()
            logger.info(f"Added {base['system_name']} scoring system with {len(system)} columns matched to schema")
        
        if default_systems:
            logger.info(f"Initialized {len(default_systems)} scoring systems")
        else:
            logger.info("All scoring systems already exist")
