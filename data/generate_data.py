"""Nova Commerce ("Project Aurora") — narrative synthetic dataset generator.

Generates a deterministic, Jira-style dataset for an e-commerce platform team:
9 sprints (the last one mid-flight at DEMO_TODAY), 8 people, 6 epics with a
coherent story arc, and handwritten issue titles.

Seeded anomalies the dashboard "discovers" (asserted by tests/test_generator.py):
  1. Priya Sharma is overloaded (>130% utilisation) in the current sprint.
  2. NOVA-2107 "Migrate to payment gateway SDK v3" blocks 4 other issues.
  3. Checkout Redesign (EPIC-101, Critical) trails badly -> Critical risk band.
  4. Sprint 5 completion dips to ~60% (production incident); sprint 7
     over-commits sharply (Loyalty scope added late).
  5. Every Blocked issue has a real blocker; the dependency graph is a DAG.

Outputs (in data/):
    sprints.csv, team.csv, epics.csv, issues.csv, meta.json

Run:
    python data/generate_data.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

RNG_SEED = 42
DATA_DIR = Path(__file__).resolve().parent

NUM_SPRINTS = 9
SPRINT_LENGTH_DAYS = 14
SPRINT_START = date(2026, 3, 16)          # Monday; sprint 9 runs Jul 6-19
DEMO_TODAY = date(2026, 7, 15)            # day 10 of sprint 9

PROJECT_NAME = "Nova Commerce"
PROJECT_CODENAME = "Project Aurora"
KEY_PREFIX = "NOVA"
KEY_START = 2001
BLOCKER_KEY = "NOVA-2107"                 # the SDK migration ends up on this key

TEAM = [
    ("Priya Sharma", "Backend", 10),
    ("Marcus Webb", "Backend", 9),
    ("Elena Petrova", "Frontend", 9),
    ("Devon Park", "Frontend", 8),
    ("Aisha Khan", "Data", 10),
    ("Tom Nguyen", "QA", 7),
    ("Grace Okafor", "Design", 6),
    ("Lukas Braun", "DevOps", 8),
]

EPICS = [
    ("EPIC-101", "Checkout Redesign", "Frontend", "Critical"),
    ("EPIC-102", "Payments Reliability", "Backend", "High"),
    ("EPIC-103", "Search Relevance v2", "Data", "Medium"),
    ("EPIC-104", "Mobile App Performance", "Frontend", "Medium"),
    ("EPIC-105", "Loyalty & Rewards", "Backend", "High"),
    ("EPIC-106", "Observability Uplift", "DevOps", "Low"),
]

ASSIGNEES_BY_EPIC = {
    "EPIC-101": ["Elena Petrova", "Devon Park", "Grace Okafor", "Tom Nguyen"],
    "EPIC-102": ["Priya Sharma", "Marcus Webb", "Tom Nguyen"],
    "EPIC-103": ["Aisha Khan", "Marcus Webb", "Tom Nguyen"],
    "EPIC-104": ["Devon Park", "Elena Petrova", "Tom Nguyen"],
    "EPIC-105": ["Marcus Webb", "Elena Petrova", "Grace Okafor"],
    "EPIC-106": ["Lukas Braun", "Tom Nguyen"],
}

# Per-epic activity weight for each sprint S01..S09 (0 = epic not active).
EPIC_SPRINT_WEIGHTS = {
    "EPIC-101": [2.5, 1.5, 1.5, 2.5, 2.0, 1.5, 1.0, 2.0, 2.5],
    "EPIC-102": [0.0, 0.0, 2.0, 2.0, 2.5, 2.0, 1.5, 2.5, 3.5],
    "EPIC-103": [4.0, 4.0, 3.0, 2.0, 2.0, 1.5, 1.0, 0.0, 0.0],
    "EPIC-104": [0.0, 2.0, 2.0, 2.0, 2.0, 2.0, 1.0, 2.0, 1.5],
    "EPIC-105": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.5, 1.5, 2.0],
    "EPIC-106": [2.0, 1.5, 1.0, 1.0, 1.0, 1.5, 0.0, 0.0, 0.0],
}

# Committed points per sprint (team capacity is 67).
# S07 over-commits ~+20% (Loyalty scope added late). S09's target is lower
# because the injected SDK-migration issue adds 8 points on top.
COMMIT_TARGETS = [64, 66, 67, 69, 67, 65, 88, 69, 66]

# Fraction of committed points completed. S05 dips (payments incident);
# S09 is mid-flight.
COMPLETION_RATES = [0.92, 0.88, 0.90, 0.85, 0.60, 0.82, 0.75, 0.88, 0.32]

# How strongly each epic's issues resist being marked Done when a sprint
# falls short of its commitment (higher = more likely to slip).
UNDONE_BIAS = {
    "EPIC-101": 1.8,
    "EPIC-102": 1.0,
    "EPIC-103": 0.6,
    "EPIC-104": 1.0,
    "EPIC-105": 1.2,
    "EPIC-106": 0.5,
}

# Handwritten issue pools: (points, type, title). Drawn in order per epic,
# so pool ordering shapes the narrative (e.g. Mobile bugs cluster late).
POOLS: dict[str, list[tuple[int, str, str]]] = {
    "EPIC-101": [
        (5, "Story", "Design new one-page checkout flow wireframes"),
        (8, "Story", "Implement address form with inline validation and autocomplete"),
        (5, "Story", "Build order summary sidebar with live tax and shipping estimates"),
        (3, "Task", "Migrate checkout routes to the new design system components"),
        (5, "Story", "Add express checkout entry points on cart and product pages"),
        (8, "Story", "Implement guest checkout with post-purchase account creation"),
        (3, "Story", "Support promo code stacking rules in the new cart summary"),
        (5, "Story", "Integrate Apple Pay and Google Pay buttons in payment step"),
        (2, "Task", "Add analytics events for each checkout step transition"),
        (5, "Story", "Build saved-cards picker with default card selection"),
        (3, "Story", "Implement shipping method selector with delivery date estimates"),
        (2, "Spike", "Spike: evaluate address-verification providers for EU markets"),
        (8, "Story", "Rebuild payment step on the new payments SDK components"),
        (5, "Story", "Add order review step with editable line items"),
        (3, "Bug", "Fix cart total mismatch when promo code is removed after login"),
        (2, "Bug", "Fix focus trap in the shipping address modal on Safari"),
        (5, "Story", "Accessibility pass for checkout (WCAG 2.1 AA)"),
        (3, "Task", "Set up A/B experiment scaffolding for one-page vs stepped flow"),
        (5, "Story", "Localise checkout copy and error states for DE and FR markets"),
        (3, "Bug", "Fix duplicate order confirmation emails on slow connections"),
        (8, "Story", "Implement checkout error recovery flow for failed payments"),
        (2, "Task", "Add feature flags for gradual checkout rollout"),
        (5, "Story", "Build mobile-optimised payment step layout"),
        (3, "Bug", "Fix promo banner overlapping sticky order summary on tablets"),
        (5, "Story", "Wire new checkout flow to loyalty points redemption"),
        (2, "Task", "Update checkout E2E test suite for the new flow"),
    ],
    "EPIC-102": [
        (8, "Story", "Implement idempotency keys for all charge-creation endpoints"),
        (5, "Story", "Add automatic retry with backoff for gateway timeouts"),
        (5, "Bug", "Fix duplicate charge on gateway timeout retry"),
        (8, "Story", "Implement 3DS2 challenge flow for EU cards"),
        (3, "Task", "Add structured logging to the payment orchestration service"),
        (5, "Story", "Build webhook reconciliation job for missed payment events"),
        (2, "Spike", "Spike: evaluate payment gateway SDK v3 migration effort"),
        (5, "Story", "Implement circuit breaker around the fraud-scoring service"),
        (3, "Bug", "Fix currency rounding mismatch on multi-currency refunds"),
        (8, "Story", "Rebuild refund pipeline with async status tracking"),
        (3, "Task", "Add payment-failure runbook and alerting thresholds"),
        (5, "Story", "Implement partial capture support for split shipments"),
        (2, "Bug", "Fix webhook signature validation failing on rotated keys"),
        (5, "Story", "Add payment audit trail with immutable event log"),
        (3, "Task", "Chaos-test gateway failover in staging"),
        (5, "Story", "Implement stored-credential framework flags for card networks"),
        (3, "Bug", "Fix refund double-processing when webhook races the API response"),
        (8, "Story", "Migrate settlement reports to the new gateway API"),
        (2, "Task", "Add dashboards for authorisation success rate by issuer"),
        (5, "Story", "Implement network tokenisation for saved cards"),
    ],
    "EPIC-103": [
        (5, "Story", "Implement typo tolerance with configurable edit distance"),
        (5, "Story", "Add synonym expansion for fashion and electronics categories"),
        (8, "Story", "Ship learning-to-rank model v1 for top queries"),
        (3, "Task", "Build offline evaluation harness with judged query set"),
        (5, "Story", "Implement autocomplete with popularity-weighted suggestions"),
        (2, "Bug", "Fix stale prices in search results after flash-sale start"),
        (5, "Story", "Add category facet counts to search response"),
        (3, "Story", "Build zero-results page with spelling suggestions"),
        (8, "Story", "Move product index rebuild to incremental updates"),
        (2, "Spike", "Spike: embeddings-based recall for long-tail queries"),
        (5, "Story", "Add personalised boosts from browsing history"),
        (3, "Task", "Add search latency budgets and alerts"),
        (5, "Story", "Implement query-intent classifier for navigational queries"),
        (2, "Bug", "Fix duplicate results when products belong to multiple categories"),
        (5, "Story", "Ship ranking model v2 with click-through features"),
        (3, "Task", "Integrate ranking experiments with the A/B test framework"),
        (5, "Story", "Add Redis cache for search suggestion queries"),
        (2, "Bug", "Fix search analytics undercounting on infinite scroll"),
        (3, "Story", "Expose sort-by-newest with recency decay blending"),
        (5, "Story", "Index seller ratings and shipping speed as ranking signals"),
    ],
    "EPIC-104": [
        (5, "Story", "Reduce cold-start time by deferring analytics SDK init"),
        (5, "Story", "Implement image caching with LRU eviction on product lists"),
        (3, "Task", "Split app bundle and lazy-load rarely used screens"),
        (8, "Story", "Virtualise long product lists to cut memory usage"),
        (2, "Spike", "Spike: profile scroll jank on mid-tier Android devices"),
        (5, "Story", "Move cart sync to background fetch with conflict resolution"),
        (3, "Task", "Add startup-time and frame-drop metrics to telemetry"),
        (5, "Story", "Implement offline browsing for recently viewed products"),
        (3, "Story", "Compress API payloads with brotli on mobile endpoints"),
        (5, "Story", "Adopt incremental rendering for the home feed"),
        (2, "Bug", "Fix crash on device rotation during checkout"),
        (3, "Bug", "Fix memory leak in product image carousel"),
        (2, "Bug", "Fix ANR when opening notifications with deep links"),
        (3, "Bug", "Fix janky scroll on search results with many badges"),
        (2, "Bug", "Fix white flash when switching tabs on Android 14"),
        (3, "Bug", "Fix stale cart badge count after order completion"),
        (2, "Bug", "Fix crash-report symbolication for the React Native layer"),
        (3, "Bug", "Fix keyboard covering promo input on small screens"),
        (2, "Bug", "Fix duplicate push notifications on token refresh"),
    ],
    "EPIC-105": [
        (8, "Story", "Design and implement points ledger with idempotent accrual"),
        (5, "Story", "Build tier calculation job with monthly re-evaluation"),
        (5, "Story", "Implement points redemption at checkout"),
        (3, "Story", "Add referral bonus flow with fraud guardrails"),
        (5, "Story", "Build rewards catalogue page with tier-gated offers"),
        (2, "Task", "Define loyalty events schema for the analytics pipeline"),
        (3, "Story", "Implement points expiry with 30-day warning notifications"),
        (5, "Story", "Add loyalty widget to the account dashboard"),
        (2, "Spike", "Spike: partner-brand rewards integration feasibility"),
        (3, "Task", "Load-test the accrual pipeline at flash-sale traffic"),
        (3, "Bug", "Fix points accrual double-count on split payments"),
        (5, "Story", "Implement birthday bonus and anniversary rewards"),
    ],
    "EPIC-106": [
        (5, "Story", "Roll out distributed tracing across checkout and payments"),
        (3, "Task", "Define SLOs and error budgets for the top five user journeys"),
        (5, "Story", "Build unified service dashboard with golden signals"),
        (2, "Task", "Cut log retention costs with tiered storage"),
        (3, "Story", "Add synthetic checks for the checkout happy path"),
        (2, "Task", "Standardise alert runbooks and ownership tags"),
        (3, "Story", "Instrument feature flags with exposure events"),
        (2, "Bug", "Fix noisy disk-space alerts on build agents"),
        (5, "Story", "Adopt the OpenTelemetry SDK across backend services"),
        (3, "Task", "Add release-health dashboard with crash-free sessions"),
        (2, "Task", "Wire deploy markers into dashboards"),
    ],
}

# Injected explicitly into sprint 9 so the blocker chain has a stable anchor.
SDK_MIGRATION = (8, "Story", "Migrate to payment gateway SDK v3")

CURRENT_SPRINT_ID = f"S{NUM_SPRINTS:02d}"


def build_sprints() -> pd.DataFrame:
    capacity = sum(c for _, _, c in TEAM)
    rows = []
    for i in range(1, NUM_SPRINTS + 1):
        start = SPRINT_START + timedelta(days=(i - 1) * SPRINT_LENGTH_DAYS)
        end = start + timedelta(days=SPRINT_LENGTH_DAYS - 1)
        rows.append(
            {
                "sprint_id": f"S{i:02d}",
                "sprint_name": f"Sprint {i}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "capacity_points": capacity,
            }
        )
    return pd.DataFrame(rows)


def build_team() -> pd.DataFrame:
    return pd.DataFrame(
        [{"member": n, "role": r, "capacity_per_sprint": c} for n, r, c in TEAM]
    )


def build_epics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"epic_id": e, "epic_name": n, "owner_team": t, "priority": p}
            for e, n, t, p in EPICS
        ]
    )


def _draw_priority(rng: random.Random, epic_priority: str, issue_type: str) -> str:
    if issue_type == "Bug":
        return rng.choices(["Critical", "High", "Medium"], weights=[0.15, 0.5, 0.35], k=1)[0]
    if rng.random() < 0.6:
        return epic_priority
    return rng.choices(["High", "Medium", "Medium", "Low"], k=1)[0]


def _pool_entry(epic_id: str, cursor: dict[str, int]) -> tuple[int, str, str]:
    """Sequential draw from the epic's pool; second lap gets a prefix."""
    pool = POOLS[epic_id]
    i = cursor[epic_id]
    cursor[epic_id] = i + 1
    points, itype, title = pool[i % len(pool)]
    if i >= len(pool):
        if title.startswith("Fix"):
            title = f"{title} (recurrence)"
        else:
            title = f"Hardening: {title[0].lower()}{title[1:]}"
    return points, itype, title


def build_issues(sprints: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(RNG_SEED)
    cursor = {e: 0 for e in POOLS}
    issues: list[dict] = []

    # ------------------------------------------------------------------
    # Pass 1: draw issues per sprint per epic to hit the commit targets
    # ------------------------------------------------------------------
    for s_idx, sprint in enumerate(sprints.itertuples()):
        weights = {e: w[s_idx] for e, w in EPIC_SPRINT_WEIGHTS.items() if w[s_idx] > 0}
        total_w = sum(weights.values())
        targets = {e: COMMIT_TARGETS[s_idx] * w / total_w for e, w in weights.items()}

        for epic_id, target in targets.items():
            epic_meta = next(e for e in EPICS if e[0] == epic_id)
            committed = 0
            while committed < target - 2.5:
                points, itype, title = _pool_entry(epic_id, cursor)
                assignee = rng.choice(ASSIGNEES_BY_EPIC[epic_id])
                role = next(r for n, r, _ in TEAM if n == assignee)
                issues.append(
                    {
                        "issue_key": "",  # assigned after all passes
                        "summary": title,
                        "issue_type": itype,
                        "epic_id": epic_id,
                        "sprint_id": sprint.sprint_id,
                        "story_points": points,
                        "status": "To Do",
                        "assignee": assignee,
                        "assignee_role": role,
                        "priority": _draw_priority(rng, epic_meta[3], itype),
                        "_sprint_idx": s_idx,
                    }
                )
                committed += points

    # Inject the blocker anchor into the current sprint.
    issues.append(
        {
            "issue_key": "",
            "summary": SDK_MIGRATION[2],
            "issue_type": SDK_MIGRATION[1],
            "epic_id": "EPIC-102",
            "sprint_id": CURRENT_SPRINT_ID,
            "story_points": SDK_MIGRATION[0],
            "status": "In Progress",
            "assignee": "Priya Sharma",
            "assignee_role": "Backend",
            "priority": "Critical",
            "_sprint_idx": NUM_SPRINTS - 1,
            "_pinned": True,  # never re-statused by later passes
        }
    )

    # ------------------------------------------------------------------
    # Pass 2: statuses — greedy Done allocation per sprint with epic bias
    # ------------------------------------------------------------------
    for s_idx in range(NUM_SPRINTS):
        sprint_issues = [i for i in issues if i["_sprint_idx"] == s_idx]
        committed = sum(i["story_points"] for i in sprint_issues)
        done_target = committed * COMPLETION_RATES[s_idx]

        candidates = [i for i in sprint_issues if not i.get("_pinned")]
        # Low score = completed first; UNDONE_BIAS makes troubled epics slip.
        candidates.sort(
            key=lambda i: UNDONE_BIAS[i["epic_id"]] * rng.uniform(0.5, 1.5)
        )
        done_pts = 0
        for issue in candidates:
            if done_pts + issue["story_points"] <= done_target + 2:
                issue["status"] = "Done"
                done_pts += issue["story_points"]
            else:
                is_current = s_idx == NUM_SPRINTS - 1
                if issue["epic_id"] == "EPIC-101" and s_idx >= 6:
                    issue["status"] = "Blocked"
                elif is_current:
                    issue["status"] = rng.choices(
                        ["In Progress", "To Do", "Blocked"], weights=[0.55, 0.35, 0.10], k=1
                    )[0]
                else:
                    issue["status"] = rng.choices(
                        ["In Progress", "To Do", "Blocked"], weights=[0.5, 0.3, 0.2], k=1
                    )[0]

    # ------------------------------------------------------------------
    # Pass 3: Checkout Redesign rebalance -> guarantee Critical risk band
    # (blocked >= 32% of epic scope; done capped at 50%).
    # Only touch S07-S09 so earlier sprint completion rates stay intact.
    # ------------------------------------------------------------------
    checkout = [i for i in issues if i["epic_id"] == "EPIC-101"]
    total_pts = sum(i["story_points"] for i in checkout)
    blocked_quota = 0.32 * total_pts

    def _checkout_blocked() -> float:
        return sum(i["story_points"] for i in checkout if i["status"] == "Blocked")

    # First convert undone issues (latest sprints first), then Done in S07-S09.
    for want_status in (("In Progress", "To Do"), ("Done",)):
        for issue in sorted(checkout, key=lambda i: -i["_sprint_idx"]):
            if _checkout_blocked() >= blocked_quota:
                break
            if issue["status"] in want_status and (
                want_status != ("Done",) or issue["_sprint_idx"] >= 6
            ):
                issue["status"] = "Blocked"

    done_cap = 0.5 * total_pts
    done_now = sum(i["story_points"] for i in checkout if i["status"] == "Done")
    for issue in sorted(checkout, key=lambda i: -i["_sprint_idx"]):
        if done_now <= done_cap:
            break
        if issue["status"] == "Done" and issue["_sprint_idx"] >= 6:
            issue["status"] = "In Progress"
            done_now -= issue["story_points"]

    # ------------------------------------------------------------------
    # Pass 4: ensure chain candidates — the SDK migration must block
    # >= 4 issues: Checkout S08/S09 and Payments S09.
    # ------------------------------------------------------------------
    def _force_blocked(epic_id: str, s_idx: int, n: int) -> list[dict]:
        pool = [
            i
            for i in issues
            if i["epic_id"] == epic_id
            and i["_sprint_idx"] == s_idx
            and not i.get("_pinned")
        ]
        blocked = [i for i in pool if i["status"] == "Blocked"]
        for i in pool:
            if len(blocked) >= n:
                break
            if i["status"] != "Blocked":
                i["status"] = "Blocked"
                blocked.append(i)
        return blocked[:n]

    chain_targets = (
        _force_blocked("EPIC-101", 8, 2)
        + _force_blocked("EPIC-101", 7, 1)
        + _force_blocked("EPIC-102", 8, 1)
    )

    # ------------------------------------------------------------------
    # Pass 5: Priya overload in the current sprint (>= 14 pts vs cap 10)
    # ------------------------------------------------------------------
    priya_pts = sum(
        i["story_points"]
        for i in issues
        if i["_sprint_idx"] == NUM_SPRINTS - 1 and i["assignee"] == "Priya Sharma"
    )
    for issue in issues:
        if priya_pts >= 14:
            break
        if (
            issue["_sprint_idx"] == NUM_SPRINTS - 1
            and issue["assignee"] != "Priya Sharma"
            and issue["epic_id"] in ("EPIC-102", "EPIC-101")
        ):
            issue["assignee"] = "Priya Sharma"
            issue["assignee_role"] = "Backend"
            priya_pts += issue["story_points"]

    # ------------------------------------------------------------------
    # Pass 5b: shape the current sprint so Priya sits at ~140-160% and
    # everyone else stays plausible (nobody above ~115% utilisation).
    # ------------------------------------------------------------------
    caps = {n: c for n, _, c in TEAM}
    roles = {n: r for n, r, _ in TEAM}
    cur = [i for i in issues if i["_sprint_idx"] == NUM_SPRINTS - 1]

    def _load(name: str) -> int:
        return sum(i["story_points"] for i in cur if i["assignee"] == name)

    # Trim Priya to ~16 pts (>= 14 guaranteed by pass 5), then redistribute
    # every other current-sprint issue greedily by projected utilisation,
    # nudged toward each epic's usual assignees.
    sheddable = sorted(
        (i for i in cur if i["assignee"] == "Priya Sharma" and not i.get("_pinned")),
        key=lambda i: i["story_points"],
    )
    shed: list[dict] = []
    for issue in sheddable:
        if _load("Priya Sharma") - sum(s["story_points"] for s in shed) <= 16:
            break
        shed.append(issue)

    others = [n for n in caps if n != "Priya Sharma"]
    shed_ids = {id(s) for s in shed}
    pool_issues = sorted(
        (i for i in cur if i["assignee"] != "Priya Sharma" or id(i) in shed_ids),
        key=lambda i: -i["story_points"],
    )
    load = {n: 0 for n in others}
    for issue in pool_issues:
        affinity = set(ASSIGNEES_BY_EPIC[issue["epic_id"]])

        def _projected(name: str) -> float:
            bonus = 0.1 if name in affinity else 0.0
            return (load[name] + issue["story_points"]) / caps[name] - bonus

        receiver = min(others, key=_projected)
        issue["assignee"] = receiver
        issue["assignee_role"] = roles[receiver]
        load[receiver] += issue["story_points"]

    # Local improvement: shave the worst-loaded member while any single
    # move strictly reduces their ratio without creating a worse one.
    for _ in range(30):
        ratios = {n: load[n] / caps[n] for n in others}
        worst = max(ratios, key=ratios.get)
        if ratios[worst] <= 1.15:
            break
        moved = False
        for issue in sorted(
            (i for i in cur if i["assignee"] == worst),
            key=lambda i: i["story_points"],
        ):
            for recv in sorted(others, key=lambda n: ratios[n]):
                if recv == worst:
                    continue
                if (load[recv] + issue["story_points"]) / caps[recv] < ratios[worst]:
                    load[worst] -= issue["story_points"]
                    load[recv] += issue["story_points"]
                    issue["assignee"] = recv
                    issue["assignee_role"] = roles[recv]
                    moved = True
                    break
            if moved:
                break
        if not moved:
            # No single move helps; try swapping a big issue for a smaller one.
            for issue in sorted(
                (i for i in cur if i["assignee"] == worst),
                key=lambda i: -i["story_points"],
            ):
                for other in sorted((n for n in others if n != worst), key=ratios.get):
                    for oissue in sorted(
                        (i for i in cur if i["assignee"] == other),
                        key=lambda i: i["story_points"],
                    ):
                        delta = issue["story_points"] - oissue["story_points"]
                        if delta <= 0:
                            continue
                        new_worst = (load[worst] - delta) / caps[worst]
                        new_other = (load[other] + delta) / caps[other]
                        if new_worst < ratios[worst] and new_other < ratios[worst]:
                            load[worst] -= delta
                            load[other] += delta
                            issue["assignee"], oissue["assignee"] = other, worst
                            issue["assignee_role"], oissue["assignee_role"] = (
                                roles[other],
                                roles[worst],
                            )
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break
        if not moved:
            break

    # ------------------------------------------------------------------
    # Pass 6: assign keys; land the SDK migration on BLOCKER_KEY
    # ------------------------------------------------------------------
    for n, issue in enumerate(issues):
        issue["issue_key"] = f"{KEY_PREFIX}-{KEY_START + n}"
    sdk = next(i for i in issues if i.get("_pinned"))
    holder = next((i for i in issues if i["issue_key"] == BLOCKER_KEY), None)
    if holder is None:
        raise RuntimeError(
            f"Dataset too small: {BLOCKER_KEY} not in range "
            f"({KEY_START}..{KEY_START + len(issues) - 1})"
        )
    holder["issue_key"], sdk["issue_key"] = sdk["issue_key"], holder["issue_key"]

    # ------------------------------------------------------------------
    # Pass 7: dependencies. Chain first; then every Blocked issue gets a
    # blocker; then a few historical Done->Done edges. Sources always have
    # blocked_by == "" themselves, so the graph is trivially acyclic.
    # ------------------------------------------------------------------
    for issue in issues:
        issue["blocked_by"] = ""
    for target in chain_targets:
        target["blocked_by"] = sdk["issue_key"]

    source_use: dict[str, int] = {sdk["issue_key"]: len(chain_targets)}

    def _eligible_sources(target: dict) -> list[dict]:
        return [
            i
            for i in issues
            if i is not target
            and i["blocked_by"] == ""
            and i["_sprint_idx"] <= target["_sprint_idx"]
            and source_use.get(i["issue_key"], 0) < 2
            and i["issue_key"] != sdk["issue_key"]
        ]

    for issue in issues:
        if issue["status"] != "Blocked" or issue["blocked_by"]:
            continue
        # Prefer a live blocker from the same epic, else any live one.
        live = [s for s in _eligible_sources(issue) if s["status"] != "Done"]
        same_epic = [s for s in live if s["epic_id"] == issue["epic_id"]]
        pool = same_epic or live
        if pool:
            src = rng.choice(pool)
            issue["blocked_by"] = src["issue_key"]
            source_use[src["issue_key"]] = source_use.get(src["issue_key"], 0) + 1

    done_issues = [i for i in issues if i["status"] == "Done"]
    for _ in range(8):
        target = rng.choice(done_issues)
        if target["blocked_by"] or target.get("_pinned"):
            continue
        sources = [s for s in _eligible_sources(target) if s["status"] == "Done"]
        if sources:
            src = rng.choice(sources)
            target["blocked_by"] = src["issue_key"]
            source_use[src["issue_key"]] = source_use.get(src["issue_key"], 0) + 1

    # ------------------------------------------------------------------
    # Pass 8: dates
    # ------------------------------------------------------------------
    for issue in issues:
        s_idx = issue["_sprint_idx"]
        start = SPRINT_START + timedelta(days=s_idx * SPRINT_LENGTH_DAYS)
        end = start + timedelta(days=SPRINT_LENGTH_DAYS - 1)
        issue["created_at"] = (start - timedelta(days=rng.randint(1, 21))).isoformat()
        if issue["status"] == "Done":
            # Completion dates spread through the sprint (slightly back-loaded)
            # so burn-down charts look like real sprints. In the current
            # sprint, nothing completes after "today".
            last_day = min(end, DEMO_TODAY) if s_idx == NUM_SPRINTS - 1 else end
            span = max((last_day - start).days, 1)
            day = max(rng.randint(span // 3, span), 1)
            issue["updated_at"] = (start + timedelta(days=day)).isoformat()
        else:
            issue["updated_at"] = min(DEMO_TODAY, end).isoformat()

    df = pd.DataFrame(issues).drop(columns=["_sprint_idx", "_pinned"], errors="ignore")
    cols = [
        "issue_key", "summary", "issue_type", "epic_id", "sprint_id",
        "story_points", "status", "assignee", "assignee_role", "priority",
        "created_at", "updated_at", "blocked_by",
    ]
    return df[cols]


def build_meta(issues: pd.DataFrame) -> dict:
    blocks = int((issues["blocked_by"] == BLOCKER_KEY).sum())
    return {
        "project_name": PROJECT_NAME,
        "project_codename": PROJECT_CODENAME,
        "project_key": KEY_PREFIX,
        "demo_today": DEMO_TODAY.isoformat(),
        "current_sprint_id": CURRENT_SPRINT_ID,
        "blurb": (
            f"{PROJECT_NAME} is a synthetic e-commerce platform team: 8 people, "
            f"{NUM_SPRINTS} sprints, 6 epics — rebuilding checkout, hardening "
            "payments, and shipping a loyalty programme. The data is seeded with "
            "realistic trouble to find: an overloaded engineer, a blocker chain, "
            "and a critical epic running late."
        ),
        "anomalies": [
            {
                "id": "blocker_chain",
                "title": "One migration is holding up four issues",
                "detail": (
                    f"{BLOCKER_KEY} 'Migrate to payment gateway SDK v3' blocks "
                    f"{blocks} issues across Checkout and Payments."
                ),
                "page": "dependencies",
                "issue_key": BLOCKER_KEY,
            },
            {
                "id": "overload",
                "title": "Priya is at ~140% capacity this sprint",
                "detail": (
                    "Payments work has funnelled to one engineer in Sprint 9 — "
                    "the utilisation chart shows the overload."
                ),
                "page": "sprint",
                "member": "Priya Sharma",
            },
            {
                "id": "critical_epic",
                "title": "Checkout Redesign is in the Critical risk band",
                "detail": (
                    "Only about a third of the scope is done after eight sprints "
                    "and roughly a third is blocked — mostly behind the payments "
                    "SDK migration."
                ),
                "page": "epics",
                "epic_id": "EPIC-101",
            },
        ],
    }


def write_outputs(out_dir: Path | None = None) -> None:
    out = Path(out_dir) if out_dir else DATA_DIR
    out.mkdir(parents=True, exist_ok=True)

    sprints = build_sprints()
    team = build_team()
    epics = build_epics()
    issues = build_issues(sprints)
    meta = build_meta(issues)

    sprints.to_csv(out / "sprints.csv", index=False)
    team.to_csv(out / "team.csv", index=False)
    epics.to_csv(out / "epics.csv", index=False)
    issues.to_csv(out / "issues.csv", index=False)
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(
        f"Wrote {len(sprints)} sprints, {len(team)} team members, "
        f"{len(epics)} epics, {len(issues)} issues to {out}"
    )


if __name__ == "__main__":
    write_outputs()
