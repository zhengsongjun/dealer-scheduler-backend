"""Seed script: insert 200 mock dealers into the database."""
import random
import sys
from app.database import SessionLocal
from app.models.dealer import Dealer
from app.models.schedule import Schedule, ScheduleEntry
from app.models.availability import AvailabilityRequest
from app.models.time_off import TimeOffRequest
from app.models.ride_share import RideShareRequest
from app.models.scheduler_config import SchedulerConfig

FIRST_NAMES = [
    'James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer', 'Michael', 'Linda',
    'William', 'Elizabeth', 'David', 'Barbara', 'Richard', 'Susan', 'Joseph', 'Jessica',
    'Thomas', 'Sarah', 'Charles', 'Karen', 'Daniel', 'Lisa', 'Matthew', 'Nancy',
    'Anthony', 'Betty', 'Mark', 'Margaret', 'Donald', 'Sandra', 'Steven', 'Ashley',
    'Paul', 'Dorothy', 'Andrew', 'Kimberly', 'Joshua', 'Emily', 'Kenneth', 'Donna',
    'Kevin', 'Michelle', 'Brian', 'Carol', 'George', 'Amanda', 'Timothy', 'Melissa',
    'Ronald', 'Deborah', 'Edward', 'Stephanie', 'Jason', 'Rebecca', 'Jeffrey', 'Sharon',
    'Ryan', 'Laura', 'Jacob', 'Cynthia',
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
    'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
    'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson',
]

TYPES = ['tournament', 'cash', 'restart']
TYPE_WEIGHTS = [0.5, 0.35, 0.15]
SHIFTS = ['8AM', '4PM', '8PM', 'flexible']


def seed(force=False):
    db = SessionLocal()
    try:
        existing = db.query(Dealer).count()
        if existing > 0:
            if not force:
                print(f"Already {existing} dealers in DB, skipping seed. Use --force to reseed.")
                return
            print(f"Force reseed: clearing {existing} dealers and related data...")
            db.query(ScheduleEntry).delete()
            db.query(Schedule).delete()
            db.query(AvailabilityRequest).delete()
            db.query(TimeOffRequest).delete()
            db.query(RideShareRequest).delete()
            db.query(Dealer).delete()
            db.commit()

        for i in range(200):
            r = random.random()
            dtype = TYPES[0] if r < TYPE_WEIGHTS[0] else TYPES[1] if r < TYPE_WEIGHTS[0] + TYPE_WEIGHTS[1] else TYPES[2]
            emp = 'full_time' if random.random() < 0.7 else 'part_time'
            days_off = []
            if emp == 'full_time':
                d1 = random.randint(0, 6)
                d2 = random.randint(0, 6)
                while d2 == d1:
                    d2 = random.randint(0, 6)
                days_off = sorted([d1, d2])

            dealer = Dealer(
                id=f"{100001 + i}",
                first_name=random.choice(FIRST_NAMES),
                last_name=random.choice(LAST_NAMES),
                type=dtype,
                employment=emp,
                preferred_shift=random.choice(SHIFTS),
                days_off=days_off,
                phone=f"702-555-{random.randint(0,9999):04d}",
            )
            db.add(dealer)

        db.commit()
        print("Seeded 200 dealers.")

        # Seed scheduler config defaults
        existing_config = db.query(SchedulerConfig).count()
        if existing_config == 0:
            defaults = [
                SchedulerConfig(key='shortfall_penalty', value=-1000, label='Shortfall Penalty', description='S0: Penalty per unfilled demand slot'),
                SchedulerConfig(key='overstaff_reward', value=100, label='Overstaff Reward', description='S0: Reward per assignment on demanded slot'),
                SchedulerConfig(key='seniority_max_score', value=100, label='Seniority Max Score', description='S1: Max seniority score (normalization cap)'),
                SchedulerConfig(key='shift_pref_match', value=300, label='Shift Preference Match', description='S2: Reward for matching shift preference'),
                SchedulerConfig(key='shift_pref_mismatch', value=-300, label='Shift Preference Mismatch', description='S2: Penalty for mismatching shift preference'),
                SchedulerConfig(key='shift_flexible_bonus', value=10, label='Shift Flexible Bonus', description='S2: Small bonus for flexible/no preference'),
                SchedulerConfig(key='preferred_day_off_penalty', value=-200, label='Preferred Day Off Penalty', description='S3: Penalty for scheduling on preferred day off'),
                SchedulerConfig(key='ride_share_mismatch', value=-200, label='Ride Share Mismatch', description='S4: Penalty per ride-share pair mismatch'),
                SchedulerConfig(key='min_one_shift_reward', value=500, label='Min One Shift Reward', description='S5: Reward for giving dealer at least 1 shift'),
                SchedulerConfig(key='fairness_gap_penalty', value=-200, label='Fairness Gap Penalty', description='S6: Penalty multiplied by max-min shift gap'),
                SchedulerConfig(key='overtime_flex_pct', value=5, label='Overtime Flex %', description='S7: Allowed overtime percentage per day (default 5%)'),
                SchedulerConfig(key='shift_float_hours', value=2, label='Shift Float Hours', description='S7: Hours of shift float tolerance before penalizing satisfaction (default 2)'),
            ]
            db.add_all(defaults)
            db.commit()
            print("Seeded 10 scheduler config defaults.")
        else:
            print(f"Scheduler config already has {existing_config} rows, skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
