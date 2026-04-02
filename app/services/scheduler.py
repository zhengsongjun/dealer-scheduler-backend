"""Scheduler for dealer shift assignment — local OR-Tools + Google Cloud MathOpt API."""
from datetime import date, timedelta
from dataclasses import dataclass, field
from math import ceil
from ortools.sat.python import cp_model
import requests
import time
import logging

from ..config import GOOGLE_OR_API_KEY, GOOGLE_OR_API_ENDPOINT, USE_CLOUD_SOLVER

logger = logging.getLogger(__name__)


@dataclass
class DealerInfo:
    id: str
    employment: str  # full_time | part_time
    days_off: list[int] = field(default_factory=list)  # 0=Sun..6=Sat
    preferred_shift: str = "flexible"  # 9AM | 4PM | flexible
    availability_shift: str | None = None  # day | swing | mixed
    preferred_days_off: list[int] = field(default_factory=list)
    approved_time_off: list[date] = field(default_factory=list)
    ride_share_group: str | None = None
    ee_number: str | None = None  # employee number, smaller = more senior


@dataclass
class SlotDemand:
    date: date
    shift: str  # 9AM | 4PM
    dealers_needed: int


@dataclass
class RideShareGroup:
    group_key: str
    member_ids: list[str]


@dataclass
class SchedulerWeights:
    shortfall_penalty: int = -1000
    overstaff_reward: int = 100
    seniority_max_score: int = 100
    shift_pref_match: int = 300
    shift_pref_mismatch: int = -300
    shift_flexible_bonus: int = 10
    preferred_day_off_penalty: int = -200
    ride_share_mismatch: int = -200
    min_one_shift_reward: int = 500
    fairness_gap_penalty: int = -200


@dataclass
class ScheduleResult:
    assignments: list[tuple[str, date, str]]  # (dealer_id, date, shift)
    total_assignments: int
    unfilled_slots: int
    solver_status: str
    solve_time_ms: int


def _convert_days_off(days: list[int]) -> set[int]:
    """Convert 0=Sun..6=Sat to Python weekday (0=Mon..6=Sun)."""
    mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    return {mapping[d] for d in days if d in mapping}


BIG = 1e7


def _build_cloud_model(
    dealers: list[DealerInfo],
    demands: list[SlotDemand],
    ride_share_groups: list[RideShareGroup],
    week_start: date,
    weights: SchedulerWeights,
):
    """Build MathOpt model JSON (binary IP) for CP-SAT cloud solving.

    Returns (model_json, var_map) where var_map maps var_id -> (dealer_id, date, shift).
    """
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    shifts = ["9AM", "4PM"]
    demand_map: dict[tuple[date, str], int] = {}
    for d in demands:
        demand_map[(d.date, d.shift)] = d.dealers_needed
    dealer_map = {d.id: d for d in dealers}

    # ── Variables ──
    var_ids: list[str] = []
    var_names: list[str] = []
    obj_coeffs: dict[str, float] = {}  # var_id -> objective coefficient
    var_map: dict[str, tuple[str, date, str]] = {}  # var_id -> (dealer_id, date, shift)
    vid = 0

    # x[dealer, day, shift] = 0/1
    x: dict[tuple[str, date, str], str] = {}
    for d in dealers:
        for day in week_dates:
            for s in shifts:
                sid = str(vid)
                x[d.id, day, s] = sid
                var_ids.append(sid)
                var_names.append(f"x_{d.id}_{day}_{s}")
                var_map[sid] = (d.id, day, s)
                obj_coeffs[sid] = 0.0
                vid += 1

    # unfilled[day, shift] = int var (0..needed)
    unfilled: dict[tuple[date, str], str] = {}
    unfilled_ub: dict[str, int] = {}
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed > 0:
                sid = str(vid)
                unfilled[day, s] = sid
                unfilled_ub[sid] = needed
                var_ids.append(sid)
                var_names.append(f"uf_{day}_{s}")
                obj_coeffs[sid] = 0.0
                vid += 1

    # total_shifts[dealer] = int var (0..5)  -- H2: max 5 days
    total_vars: dict[str, str] = {}
    for d in dealers:
        sid = str(vid)
        total_vars[d.id] = sid
        var_ids.append(sid)
        var_names.append(f"tot_{d.id}")
        obj_coeffs[sid] = 0.0
        vid += 1

    # has_shift[dealer] = 0/1 (for S5: everyone gets at least 1 shift)
    has_vars: dict[str, str] = {}
    for d in dealers:
        sid = str(vid)
        has_vars[d.id] = sid
        var_ids.append(sid)
        var_names.append(f"has_{d.id}")
        obj_coeffs[sid] = 0.0
        vid += 1

    # works_9am[dealer], works_4pm[dealer] for H4 (hard shift consistency)
    w9_vars: dict[str, str] = {}
    w4_vars: dict[str, str] = {}
    for d in dealers:
        sid9 = str(vid); vid += 1
        sid4 = str(vid); vid += 1
        w9_vars[d.id] = sid9
        w4_vars[d.id] = sid4
        var_ids.extend([sid9, sid4])
        var_names.extend([f"w9_{d.id}", f"w4_{d.id}"])
        obj_coeffs[sid9] = 0.0
        obj_coeffs[sid4] = 0.0

    # shortfall[day, shift] = int var (0..needed) for S0-demand penalty
    shortfall: dict[tuple[date, str], str] = {}
    shortfall_ub: dict[str, int] = {}
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed > 0:
                sid = str(vid)
                shortfall[day, s] = sid
                shortfall_ub[sid] = needed
                var_ids.append(sid)
                var_names.append(f"sf_{day}_{s}")
                obj_coeffs[sid] = 0.0
                vid += 1

    # rs_match[dealer, day, shift] for ride-share soft constraint
    rs_member_set = set()
    rs_groups_map: dict[str, list[str]] = {}
    for group in ride_share_groups:
        members = [m for m in group.member_ids if m in dealer_map]
        if len(members) >= 2:
            rs_groups_map[group.group_key] = members
            rs_member_set.update(members)
    rs_diff_vars: dict[tuple[str, str, date, str], str] = {}
    for gk, members in rs_groups_map.items():
        anchor = members[0]
        for m in members[1:]:
            for day in week_dates:
                for s in shifts:
                    sid = str(vid)
                    rs_diff_vars[anchor, m, day, s] = sid
                    var_ids.append(sid)
                    var_names.append(f"rsd_{anchor}_{m}_{day}_{s}")
                    obj_coeffs[sid] = 0.0
                    vid += 1

    # max_shifts, min_shifts, fairness_gap
    max_sid = str(vid); var_ids.append(max_sid); var_names.append("max_shifts"); obj_coeffs[max_sid] = 0.0; vid += 1
    min_sid = str(vid); var_ids.append(min_sid); var_names.append("min_shifts"); obj_coeffs[min_sid] = 0.0; vid += 1
    gap_sid = str(vid); var_ids.append(gap_sid); var_names.append("gap"); obj_coeffs[gap_sid] = 0.0; vid += 1

    # Build variable arrays
    all_total = set(total_vars.values())
    all_has = set(has_vars.values())
    all_w9 = set(w9_vars.values())
    all_w4 = set(w4_vars.values())
    all_shortfall = set(shortfall.values())
    all_rs_diff = set(rs_diff_vars.values())
    n = len(var_ids)
    lower_bounds = [0.0] * n
    upper_bounds = []
    integers = [True] * n
    for i, sid in enumerate(var_ids):
        if sid in unfilled_ub:
            upper_bounds.append(float(unfilled_ub[sid]))
        elif sid in shortfall_ub:
            upper_bounds.append(float(shortfall_ub[sid]))
        elif sid in all_total:
            upper_bounds.append(5.0)
        elif sid in (max_sid, min_sid, gap_sid):
            upper_bounds.append(5.0)
        elif sid in all_has or sid in all_w9 or sid in all_w4:
            upper_bounds.append(1.0)
        elif sid in all_rs_diff:
            upper_bounds.append(1.0)
        else:
            upper_bounds.append(1.0)  # binary x vars

    # ── Constraints ──
    con_ids: list[str] = []
    con_lbs: list[float] = []
    con_ubs: list[float] = []
    # Sparse matrix entries
    row_ids: list[str] = []
    col_ids: list[str] = []
    coeffs: list[float] = []
    cid = 0

    def add_constraint(lb, ub, terms: list[tuple[str, float]]):
        nonlocal cid
        c = str(cid); cid += 1
        con_ids.append(c)
        con_lbs.append(lb)
        con_ubs.append(ub)
        for var_id, coeff in terms:
            row_ids.append(c)
            col_ids.append(var_id)
            coeffs.append(coeff)

    # C1: H2 — max 1 shift per day per dealer
    for d in dealers:
        for day in week_dates:
            terms = [(x[d.id, day, s], 1.0) for s in shifts]
            add_constraint(-BIG, 1.0, terms)

    # C2: H5 — approved time-off → x=0
    for d in dealers:
        for day in d.approved_time_off:
            if day in week_dates:
                for s in shifts:
                    add_constraint(0.0, 0.0, [(x[d.id, day, s], 1.0)])

    # C3: H1 — demand: needed <= assigned <= ceil(needed * 1.1)
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed <= 0:
                for d in dealers:
                    add_constraint(0.0, 0.0, [(x[d.id, day, s], 1.0)])
                continue
            upper = float(ceil(needed * 1.1))
            terms = [(x[d.id, day, s], 1.0) for d in dealers]
            # assigned + shortfall = needed  (shortfall >= 0, so assigned <= needed)
            # But we want assigned >= needed ideally, shortfall absorbs the gap
            # assigned + shortfall >= needed AND assigned <= upper
            add_constraint(float(needed), BIG, terms + [(shortfall[(day, s)], 1.0)])  # assigned + sf >= needed
            add_constraint(-BIG, upper, terms)  # assigned <= ceil(needed*1.1)
            # shortfall <= needed (already via upper bound on var)

    # C4: H4 — shift consistency (HARD): w9 + w4 <= 1 (no mixing shifts in a week)
    for d in dealers:
        s9_terms = [(x[d.id, day, "9AM"], 1.0) for day in week_dates]
        s4_terms = [(x[d.id, day, "4PM"], 1.0) for day in week_dates]
        # sum_9 <= 7*w9, sum_9 >= w9
        add_constraint(-BIG, 0.0, s9_terms + [(w9_vars[d.id], -7.0)])
        add_constraint(0.0, BIG, s9_terms + [(w9_vars[d.id], -1.0)])
        # sum_4 <= 7*w4, sum_4 >= w4
        add_constraint(-BIG, 0.0, s4_terms + [(w4_vars[d.id], -7.0)])
        add_constraint(0.0, BIG, s4_terms + [(w4_vars[d.id], -1.0)])
        # w9 + w4 <= 1 (HARD — cannot work both shift types)
        add_constraint(-BIG, 1.0, [(w9_vars[d.id], 1.0), (w4_vars[d.id], 1.0)])

    # C5: S4 ride-share — soft via diff vars: diff >= x[anchor] - x[m], diff >= x[m] - x[anchor]
    for gk, members in rs_groups_map.items():
        anchor = members[0]
        for m in members[1:]:
            for day in week_dates:
                for s in shifts:
                    dv = rs_diff_vars[anchor, m, day, s]
                    # diff >= x[anchor] - x[m]
                    add_constraint(0.0, BIG, [(dv, 1.0), (x[anchor, day, s], -1.0), (x[m, day, s], 1.0)])
                    # diff >= x[m] - x[anchor]
                    add_constraint(0.0, BIG, [(dv, 1.0), (x[m, day, s], -1.0), (x[anchor, day, s], 1.0)])

    # total_shifts[d] = sum(x[d,*,*])
    for d in dealers:
        terms = [(x[d.id, day, s], 1.0) for day in week_dates for s in shifts]
        terms.append((total_vars[d.id], -1.0))
        add_constraint(0.0, 0.0, terms)

    # S5: has_shift — total >= has, total <= 5*has
    for d in dealers:
        add_constraint(0.0, BIG, [(total_vars[d.id], 1.0), (has_vars[d.id], -1.0)])
        add_constraint(-BIG, 0.0, [(total_vars[d.id], 1.0), (has_vars[d.id], -5.0)])

    # max_shifts >= total[d], min_shifts <= total[d]
    for d in dealers:
        add_constraint(0.0, BIG, [(max_sid, 1.0), (total_vars[d.id], -1.0)])
        add_constraint(-BIG, 0.0, [(min_sid, 1.0), (total_vars[d.id], -1.0)])

    # gap = max - min
    add_constraint(0.0, 0.0, [(gap_sid, 1.0), (max_sid, -1.0), (min_sid, 1.0)])

    # ── Objective ──
    seniority = _compute_seniority_scores(dealers, week_start, weights.seniority_max_score)

    # S0-demand: Penalize shortfall
    for (day, s), sf_id in shortfall.items():
        obj_coeffs[sf_id] += weights.shortfall_penalty

    # S0-over: Reward over-staffing within 10%
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed > 0:
                for d in dealers:
                    obj_coeffs[x[d.id, day, s]] += weights.overstaff_reward

    # S1: seniority priority (0~seniority_max_score)
    for d in dealers:
        score = seniority.get(d.id, 0)
        if score > 0:
            for day in week_dates:
                for s in shifts:
                    obj_coeffs[x[d.id, day, s]] += score

    # S2: shift preference
    for d in dealers:
        pref = d.availability_shift
        for day in week_dates:
            if pref == "day":
                obj_coeffs[x[d.id, day, "9AM"]] += weights.shift_pref_match
                obj_coeffs[x[d.id, day, "4PM"]] += weights.shift_pref_mismatch
            elif pref == "swing":
                obj_coeffs[x[d.id, day, "4PM"]] += weights.shift_pref_match
                obj_coeffs[x[d.id, day, "9AM"]] += weights.shift_pref_mismatch
            else:
                for s in shifts:
                    obj_coeffs[x[d.id, day, s]] += weights.shift_flexible_bonus

    # S3: preferred days off penalty
    for d in dealers:
        py_pref = _convert_days_off(d.preferred_days_off)
        for day in week_dates:
            if day.weekday() in py_pref:
                for s in shifts:
                    obj_coeffs[x[d.id, day, s]] += weights.preferred_day_off_penalty

    # S4: ride-share — penalize diff
    for dv_id in rs_diff_vars.values():
        obj_coeffs[dv_id] += weights.ride_share_mismatch

    # S5: everyone gets at least 1 shift
    for d in dealers:
        obj_coeffs[has_vars[d.id]] += weights.min_one_shift_reward

    # S6: fairness
    obj_coeffs[gap_sid] += weights.fairness_gap_penalty

    # Build objective sparse
    obj_ids = [k for k, v in obj_coeffs.items() if v != 0.0]
    obj_vals = [obj_coeffs[k] for k in obj_ids]

    # Merge duplicate (row, col) entries and sort columns within each row
    from collections import defaultdict
    merged: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r, c, v in zip(row_ids, col_ids, coeffs):
        merged[r][c] += v
    final_rows, final_cols, final_coeffs = [], [], []
    for r in con_ids:
        if r not in merged:
            continue
        for c in sorted(merged[r].keys(), key=int):
            if merged[r][c] != 0.0:
                final_rows.append(r)
                final_cols.append(c)
                final_coeffs.append(merged[r][c])

    model_json = {
        "variables": {
            "ids": var_ids,
            "lowerBounds": lower_bounds,
            "upperBounds": upper_bounds,
            "integers": integers,
            "names": var_names,
        },
        "objective": {
            "maximize": True,
            "linearCoefficients": {
                "ids": obj_ids,
                "values": obj_vals,
            },
        },
        "linearConstraints": {
            "ids": con_ids,
            "lowerBounds": con_lbs,
            "upperBounds": con_ubs,
        },
        "linearConstraintMatrix": {
            "rowIds": final_rows,
            "columnIds": final_cols,
            "coefficients": final_coeffs,
        },
    }

    return model_json, var_map, unfilled


def _solve_cloud(
    dealers: list[DealerInfo],
    demands: list[SlotDemand],
    ride_share_groups: list[RideShareGroup],
    week_start: date,
    weights: SchedulerWeights,
    timeout_seconds: int = 60,
) -> ScheduleResult:
    """Call Google MathOpt API with CP-SAT solver."""
    start_time = time.time()
    model_json, var_map, unfilled = _build_cloud_model(dealers, demands, ride_share_groups, week_start, weights)

    payload = {
        "solverType": "SOLVER_TYPE_CP_SAT",
        "model": model_json,
    }

    url = f"{GOOGLE_OR_API_ENDPOINT}?key={GOOGLE_OR_API_KEY}"
    logger.info("Calling Google MathOpt CP-SAT: %d vars, %d constraints",
                len(model_json["variables"]["ids"]),
                len(model_json["linearConstraints"]["ids"]))

    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"},
                         timeout=max(timeout_seconds + 30, 120))

    if resp.status_code != 200:
        raise RuntimeError(f"Google OR API {resp.status_code}: {resp.text[:500]}")

    result = resp.json().get("result", {})
    termination = result.get("termination", {})
    reason = termination.get("reason", "UNKNOWN")
    solutions = result.get("solutions", [])

    status_map = {
        "TERMINATION_REASON_OPTIMAL": "CLOUD_OPTIMAL",
        "TERMINATION_REASON_FEASIBLE": "CLOUD_FEASIBLE",
        "TERMINATION_REASON_INFEASIBLE": "CLOUD_INFEASIBLE",
        "TERMINATION_REASON_NO_SOLUTION_FOUND": "CLOUD_NO_SOLUTION",
    }
    status_name = status_map.get(reason, f"CLOUD_{reason}")

    assignments = []
    total_unfilled = 0

    if solutions:
        sol = solutions[0].get("primalSolution", {})
        val_ids = sol.get("variableValues", {}).get("ids", [])
        val_vals = sol.get("variableValues", {}).get("values", [])
        sol_map = dict(zip(val_ids, val_vals))

        for vid, (did, day, s) in var_map.items():
            if sol_map.get(vid, 0) > 0.5:
                assignments.append((did, day, s))

    # Calculate unfilled from demand (no unfilled vars anymore)
    demand_map = {(d.date, d.shift): d.dealers_needed for d in demands}
    assigned_count: dict[tuple[date, str], int] = {}
    for _, day, s in assignments:
        assigned_count[(day, s)] = assigned_count.get((day, s), 0) + 1
    for (day, s), needed in demand_map.items():
        total_unfilled += max(0, needed - assigned_count.get((day, s), 0))

    elapsed_ms = int((time.time() - start_time) * 1000)
    return ScheduleResult(
        assignments=assignments, total_assignments=len(assignments),
        unfilled_slots=total_unfilled, solver_status=status_name,
        solve_time_ms=elapsed_ms,
    )


# ── Local OR-Tools solver (fallback) ──

def _compute_seniority_scores(dealers: list[DealerInfo], ref_date: date, max_score: int = 100) -> dict[str, int]:
    """Compute seniority score: smaller ee_number = more senior = higher score."""
    scored = []
    for d in dealers:
        if d.ee_number:
            try:
                scored.append((d.id, int(d.ee_number)))
            except ValueError:
                scored.append((d.id, None))
        else:
            scored.append((d.id, None))
    valid = [(did, num) for did, num in scored if num is not None]
    if not valid:
        return {}
    min_num = min(v[1] for v in valid)
    max_num = max(v[1] for v in valid)
    span = max_num - min_num or 1
    result = {}
    for did, num in scored:
        if num is not None:
            # smaller ee_number → higher score
            result[did] = int(max_score * (max_num - num) / span)
        else:
            result[did] = 0
    return result


def _solve_local(
    dealers: list[DealerInfo],
    demands: list[SlotDemand],
    ride_share_groups: list[RideShareGroup],
    week_start: date,
    weights: SchedulerWeights,
    timeout_seconds: int = 30,
) -> ScheduleResult:
    start_time = time.time()
    model = cp_model.CpModel()
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    shifts = ["9AM", "4PM"]
    demand_map = {(d.date, d.shift): d.dealers_needed for d in demands}
    dealer_map = {d.id: d for d in dealers}
    seniority = _compute_seniority_scores(dealers, week_start, weights.seniority_max_score)

    # ── Decision variables ──
    x = {}
    for d in dealers:
        for day in week_dates:
            for s in shifts:
                x[d.id, day, s] = model.new_bool_var(f"x_{d.id}_{day}_{s}")

    # shortfall[day, shift] for S0-demand penalty
    shortfall = {}
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed > 0:
                shortfall[day, s] = model.new_int_var(0, needed, f"sf_{day}_{s}")

    # ════════════════════════════════════════
    # HARD CONSTRAINTS
    # ════════════════════════════════════════

    # H1: Demand — needed <= assigned <= ceil(needed * 1.1)
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed <= 0:
                for d in dealers:
                    model.add(x[d.id, day, s] == 0)
            else:
                upper = ceil(needed * 1.1)
                assigned = sum(x[d.id, day, s] for d in dealers)
                # assigned + shortfall >= needed (shortfall absorbs gap when understaffed)
                model.add(assigned + shortfall[day, s] >= needed)
                # assigned <= ceil(needed * 1.1) (hard upper limit)
                model.add(assigned <= upper)

    # H2: Max 1 shift per day (can't work both 9AM and 4PM same day)
    for d in dealers:
        for day in week_dates:
            model.add(sum(x[d.id, day, s] for s in shifts) <= 1)

    # H3: Max 5 working days per week
    totals = {}
    for d in dealers:
        totals[d.id] = model.new_int_var(0, 5, f"tot_{d.id}")
        model.add(totals[d.id] == sum(x[d.id, day, s] for day in week_dates for s in shifts))

    # H4: Shift consistency (HARD) — cannot mix 9AM and 4PM in the same week
    for d in dealers:
        works_9am = model.new_bool_var(f"w9_{d.id}")
        works_4pm = model.new_bool_var(f"w4_{d.id}")
        sum_9 = sum(x[d.id, day, "9AM"] for day in week_dates)
        sum_4 = sum(x[d.id, day, "4PM"] for day in week_dates)
        model.add(sum_9 >= 1).only_enforce_if(works_9am)
        model.add(sum_9 == 0).only_enforce_if(works_9am.Not())
        model.add(sum_4 >= 1).only_enforce_if(works_4pm)
        model.add(sum_4 == 0).only_enforce_if(works_4pm.Not())
        model.add(works_9am + works_4pm <= 1)

    # H5: Approved time-off → cannot be assigned
    for d in dealers:
        for day in d.approved_time_off:
            if day in week_dates:
                for s in shifts:
                    model.add(x[d.id, day, s] == 0)

    # ════════════════════════════════════════
    # SOFT CONSTRAINTS (via objective)
    # ════════════════════════════════════════
    obj = []

    # S0-demand: Penalize shortfall
    for (day, s), sf in shortfall.items():
        obj.append(weights.shortfall_penalty * sf)

    # S0-over: Reward over-staffing within 10%
    for day in week_dates:
        for s in shifts:
            needed = demand_map.get((day, s), 0)
            if needed > 0:
                for d in dealers:
                    obj.append(weights.overstaff_reward * x[d.id, day, s])

    # S1: Seniority priority
    for d in dealers:
        score = seniority.get(d.id, 0)
        if score > 0:
            for day in week_dates:
                for s in shifts:
                    obj.append(score * x[d.id, day, s])

    # S2: Shift preference
    for d in dealers:
        pref = d.availability_shift
        for day in week_dates:
            if pref == "day":
                obj.append(weights.shift_pref_match * x[d.id, day, "9AM"])
                obj.append(weights.shift_pref_mismatch * x[d.id, day, "4PM"])
            elif pref == "swing":
                obj.append(weights.shift_pref_match * x[d.id, day, "4PM"])
                obj.append(weights.shift_pref_mismatch * x[d.id, day, "9AM"])
            else:
                for s in shifts:
                    obj.append(weights.shift_flexible_bonus * x[d.id, day, s])

    # S3: Preferred days off penalty
    for d in dealers:
        py_pref = _convert_days_off(d.preferred_days_off)
        for day in week_dates:
            if day.weekday() in py_pref:
                for s in shifts:
                    obj.append(weights.preferred_day_off_penalty * x[d.id, day, s])

    # S4: Ride-share — soft constraint
    for group in ride_share_groups:
        members = [m for m in group.member_ids if m in dealer_map]
        if len(members) < 2:
            continue
        anchor = members[0]
        for m in members[1:]:
            for day in week_dates:
                for s in shifts:
                    diff = model.new_bool_var(f"rsd_{anchor}_{m}_{day}_{s}")
                    model.add(x[anchor, day, s] - x[m, day, s] <= diff)
                    model.add(x[m, day, s] - x[anchor, day, s] <= diff)
                    obj.append(weights.ride_share_mismatch * diff)

    # S5: Everyone gets at least 1 shift per week
    for d in dealers:
        has_shift = model.new_bool_var(f"has_{d.id}")
        model.add(totals[d.id] >= 1).only_enforce_if(has_shift)
        model.add(totals[d.id] == 0).only_enforce_if(has_shift.Not())
        obj.append(weights.min_one_shift_reward * has_shift)

    # S6: Fairness — minimize gap between max and min shifts
    mx = model.new_int_var(0, 5, "mx")
    mn = model.new_int_var(0, 5, "mn")
    model.add_max_equality(mx, list(totals.values()))
    model.add_min_equality(mn, list(totals.values()))
    gap = model.new_int_var(0, 5, "gap")
    model.add(gap == mx - mn)
    obj.append(weights.fairness_gap_penalty * gap)

    model.maximize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_workers = 4
    status = solver.solve(model)

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE", cp_model.MODEL_INVALID: "MODEL_INVALID",
    }.get(status, "UNKNOWN")

    assignments = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for d in dealers:
            for day in week_dates:
                for s in shifts:
                    if solver.value(x[d.id, day, s]):
                        assignments.append((d.id, day, s))

    # Calculate unfilled from demand
    total_unfilled = 0
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assigned_count: dict[tuple[date, str], int] = {}
        for _, day, s in assignments:
            assigned_count[(day, s)] = assigned_count.get((day, s), 0) + 1
        for (day, s), needed in demand_map.items():
            total_unfilled += max(0, needed - assigned_count.get((day, s), 0))

    elapsed_ms = int((time.time() - start_time) * 1000)
    return ScheduleResult(
        assignments=assignments, total_assignments=len(assignments),
        unfilled_slots=total_unfilled, solver_status=status_name,
        solve_time_ms=elapsed_ms,
    )


# ── Main entry ──

def solve(
    dealers: list[DealerInfo],
    demands: list[SlotDemand],
    ride_share_groups: list[RideShareGroup],
    week_start: date,
    weights: SchedulerWeights | None = None,
    timeout_seconds: int = 30,
) -> ScheduleResult:
    if weights is None:
        weights = SchedulerWeights()
    if USE_CLOUD_SOLVER and GOOGLE_OR_API_KEY:
        try:
            return _solve_cloud(dealers, demands, ride_share_groups, week_start, weights, timeout_seconds)
        except Exception as e:
            logger.warning("Cloud solve failed, falling back to local: %s", e)
    return _solve_local(dealers, demands, ride_share_groups, week_start, weights, timeout_seconds)
