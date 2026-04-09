from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.scheduler_config import SchedulerConfig
from ..schemas.scheduler_config import SchedulerConfigOut, SchedulerConfigBatchUpdate
from ..auth.jwt import get_current_admin

router = APIRouter()

DEFAULT_CONFIGS = [
    {'key': 'shortfall_penalty', 'value': -1000, 'label': 'Shortfall Penalty', 'description': 'S0: Penalty per unfilled demand slot'},
    {'key': 'overstaff_reward', 'value': 100, 'label': 'Overstaff Reward', 'description': 'S0: Reward per assignment on demanded slot'},
    {'key': 'seniority_max_score', 'value': 100, 'label': 'Seniority Max Score', 'description': 'S1: Max seniority score (normalization cap)'},
    {'key': 'shift_pref_match', 'value': 300, 'label': 'Shift Preference Match', 'description': 'S2: Reward for matching shift preference'},
    {'key': 'shift_pref_mismatch', 'value': -300, 'label': 'Shift Preference Mismatch', 'description': 'S2: Penalty for mismatching shift preference'},
    {'key': 'shift_flexible_bonus', 'value': 10, 'label': 'Shift Flexible Bonus', 'description': 'S2: Small bonus for flexible/no preference'},
    {'key': 'preferred_day_off_penalty', 'value': -200, 'label': 'Preferred Day Off Penalty', 'description': 'S3: Penalty for scheduling on preferred day off'},
    {'key': 'ride_share_mismatch', 'value': -200, 'label': 'Ride Share Mismatch', 'description': 'S4: Penalty per ride-share pair mismatch'},
    {'key': 'min_one_shift_reward', 'value': 500, 'label': 'Min One Shift Reward', 'description': 'S5: Reward for giving dealer at least 1 shift'},
    {'key': 'fairness_gap_penalty', 'value': -200, 'label': 'Fairness Gap Penalty', 'description': 'S6: Penalty multiplied by max-min shift gap'},
    {'key': 'overtime_flex_pct', 'value': 5, 'label': 'Overtime Flex %', 'description': 'S7: Allowed overtime percentage per day (default 5%)'},
    {'key': 'shift_float_hours', 'value': 2, 'label': 'Shift Float Hours', 'description': 'S7: Hours of shift float tolerance before penalizing satisfaction (default 2)'},
]


@router.get("")
def list_configs(db: Session = Depends(get_db)):
    # Auto-insert any missing config keys
    existing_keys = {r.key for r in db.query(SchedulerConfig.key).all()}
    missing = [c for c in DEFAULT_CONFIGS if c['key'] not in existing_keys]
    if missing:
        for c in missing:
            db.add(SchedulerConfig(**c))
        db.commit()
    rows = db.query(SchedulerConfig).order_by(SchedulerConfig.id).all()
    return [SchedulerConfigOut(key=r.key, value=r.value, label=r.label, description=r.description) for r in rows]


@router.put("")
def batch_update(req: SchedulerConfigBatchUpdate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    key_map = {item.key: item.value for item in req.configs}
    rows = db.query(SchedulerConfig).filter(SchedulerConfig.key.in_(key_map.keys())).all()
    for row in rows:
        row.value = key_map[row.key]
    db.commit()
    return {"updated": len(rows)}


@router.post("/reset")
def reset_defaults(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    default_map = {c['key']: c['value'] for c in DEFAULT_CONFIGS}
    rows = db.query(SchedulerConfig).all()
    for row in rows:
        if row.key in default_map:
            row.value = default_map[row.key]
    db.commit()
    return {"reset": len(rows)}
