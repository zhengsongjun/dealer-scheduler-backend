"""
Mock 600 user submissions for week 2026-05-26 (Fri) ~ 2026-06-04 (Thu)
Based on 600_employer.json

1. dealers: 600 people, all tournament, all full_time
2. availability_requests: 600 records (75% day shift, 25% swing shift)
3. time_off_requests: 20 people, single day, 75% weekday / 25% weekend
4. carpool_groups + carpool_members: 2% = 12 people, 3-4 groups
"""
import json
import random
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import create_engine, text

random.seed(42)

DB_URL = "postgresql://postgres:123456@localhost:5432/dealer_manager"
engine = create_engine(DB_URL)

with open("600_employer.json", "r") as f:
    employees = json.load(f)

WEEK_START = date(2026, 5, 29)  # Friday
WEEK_END = date(2026, 6, 4)     # Thursday

# 5/26 - 6/4 all dates
ALL_DATES = [WEEK_START + timedelta(days=i) for i in range(10)]
# weekday = Mon-Fri (weekday() 0-4), weekend = Sat-Sun (weekday() 5-6)
WEEKDAYS = [d for d in ALL_DATES if d.weekday() < 5]  # 5/26(Fri=4), 5/29, 5/30, 5/31, 6/1, 6/2
WEEKENDS = [d for d in ALL_DATES if d.weekday() >= 5]  # 5/27(Sat), 5/28(Sun), 6/3(Sat), 6/4(Thu=3)

# Note: 5/26 is Friday (weekday()=4), 6/4 is Thursday (weekday()=3)
# So weekdays: 5/26(Fri), 5/29(Mon), 5/30(Tue), 5/31(Wed), 6/1(Thu), 6/2(Fri)
# weekends: 5/27(Sat), 5/28(Sun), 6/3(Sat)
# Wait - 6/4 is Thursday, so it's a weekday
# Let me recalculate properly in the code


def mock_dealers():
    """Import 600 employees into dealers table."""
    rows = []
    day_shift_count = int(len(employees) * 0.75)

    for i, emp in enumerate(employees):
        dealer_id = f"{100001 + i}"
        preferred_shift = "day" if i < day_shift_count else "swing"

        # random seniority_date (1-10 years ago)
        days_ago = random.randint(365, 3650)
        seniority = date.today() - timedelta(days=days_ago)

        # random days_off (2 days for full_time)
        d1 = random.randint(0, 6)
        d2 = random.randint(0, 6)
        while d2 == d1:
            d2 = random.randint(0, 6)
        days_off = sorted([d1, d2])

        rows.append({
            "id": dealer_id,
            "ee_number": emp["eenumber"],
            "first_name": emp["firstname"],
            "last_name": emp["lastname"],
            "type": "tournament",
            "employment": "full_time",
            "preferred_shift": preferred_shift,
            "days_off": days_off,
            "phone": f"702-555-{random.randint(0,9999):04d}",
            "seniority_date": seniority,
            "is_active": True,
        })
    return rows


def mock_availability(dealer_ids):
    """600 people submit availability for this week."""
    rows = []
    day_shift_count = int(len(dealer_ids) * 0.75)

    for i, did in enumerate(dealer_ids):
        shift = "day" if i < day_shift_count else "swing"

        # random preferred_days_off (1-2 days)
        days_off = sorted(random.sample(range(7), random.randint(1, 2)))

        submitted = datetime.now(timezone.utc) - timedelta(
            hours=random.randint(1, 72),
            minutes=random.randint(0, 59),
        )
        rows.append({
            "dealer_id": did,
            "week_start": WEEK_START,
            "shift": shift,
            "preferred_days_off": days_off,
            "submitted_at": submitted,
        })
    return rows


def mock_time_off(dealer_ids):
    """20 people request single-day time off. 75% weekday, 25% weekend."""
    chosen = random.sample(dealer_ids, 20)
    rows = []
    reasons = ["personal", "family", "medical", "appointment", "travel"]

    # Separate weekdays and weekends from the date range
    weekdays = [d for d in ALL_DATES if d.weekday() < 5]
    weekends = [d for d in ALL_DATES if d.weekday() >= 5]

    for i, did in enumerate(chosen):
        if i < 15:
            # 75% weekday
            leave_date = random.choice(weekdays)
        else:
            # 25% weekend
            leave_date = random.choice(weekends)

        rows.append({
            "id": f"TO{i+1:04d}",
            "dealer_id": did,
            "start_date": leave_date,
            "end_date": leave_date,
            "reason": random.choice(reasons),
            "status": "pending",
            "submitted_at": datetime.now(timezone.utc) - timedelta(
                hours=random.randint(1, 48),
                minutes=random.randint(0, 59),
            ),
        })
    return rows


def mock_carpool(dealer_ids):
    """2% of 600 = 12 people, split into 3-4 groups of 3-4 members each."""
    chosen = random.sample(dealer_ids, 12)
    num_groups = random.choice([3, 4])

    # Distribute 12 people into groups
    groups_data = []
    idx = 0
    for g in range(num_groups):
        if g == num_groups - 1:
            members = chosen[idx:]
        else:
            size = random.randint(3, min(4, 12 - idx - (num_groups - g - 1) * 3))
            members = chosen[idx:idx + size]
            idx += size
        groups_data.append(members)

    carpool_groups = []
    carpool_members = []
    for i, members in enumerate(groups_data):
        group_id = f"CP{i+1:03d}"
        carpool_groups.append({
            "id": group_id,
            "name": f"Carpool Group {i+1}",
        })
        for j, did in enumerate(members):
            carpool_members.append({
                "group_id": group_id,
                "dealer_id": did,
                "is_driver": j == 0,
            })

    return carpool_groups, carpool_members


def main():
    dealers = mock_dealers()
    dealer_ids = [d["id"] for d in dealers]

    avails = mock_availability(dealer_ids)
    time_offs = mock_time_off(dealer_ids)
    cp_groups, cp_members = mock_carpool(dealer_ids)

    with engine.begin() as conn:
        # Clear all data
        print("Clearing database...")
        conn.execute(text("DELETE FROM carpool_members"))
        conn.execute(text("DELETE FROM carpool_groups"))
        conn.execute(text("DELETE FROM schedule_entries"))
        conn.execute(text("DELETE FROM schedules"))
        conn.execute(text("DELETE FROM availability_requests"))
        conn.execute(text("DELETE FROM time_off_requests"))
        conn.execute(text("DELETE FROM ride_share_requests"))
        conn.execute(text("DELETE FROM dealers"))

        # Insert dealers
        for d in dealers:
            conn.execute(text("""
                INSERT INTO dealers (id, ee_number, first_name, last_name, type, employment, preferred_shift, days_off, phone, seniority_date, is_active)
                VALUES (:id, :ee_number, :first_name, :last_name, :type, :employment, :preferred_shift, :days_off, :phone, :seniority_date, :is_active)
            """), d)

        # Insert availability
        for r in avails:
            conn.execute(text("""
                INSERT INTO availability_requests (dealer_id, week_start, shift, preferred_days_off, submitted_at)
                VALUES (:dealer_id, :week_start, :shift, :preferred_days_off, :submitted_at)
            """), r)

        # Insert time off
        for r in time_offs:
            conn.execute(text("""
                INSERT INTO time_off_requests (id, dealer_id, start_date, end_date, reason, status, submitted_at)
                VALUES (:id, :dealer_id, :start_date, :end_date, :reason, :status, :submitted_at)
            """), r)

        # Insert carpool groups
        for g in cp_groups:
            conn.execute(text("""
                INSERT INTO carpool_groups (id, name)
                VALUES (:id, :name)
            """), g)

        # Insert carpool members
        for m in cp_members:
            conn.execute(text("""
                INSERT INTO carpool_members (group_id, dealer_id, is_driver)
                VALUES (:group_id, :dealer_id, :is_driver)
            """), m)

    print(f"Done! Inserted:")
    print(f"  dealers:               {len(dealers)}")
    print(f"  availability_requests: {len(avails)}")
    print(f"  time_off_requests:     {len(time_offs)}")
    print(f"  carpool_groups:        {len(cp_groups)}")
    print(f"  carpool_members:       {len(cp_members)}")


if __name__ == "__main__":
    main()
