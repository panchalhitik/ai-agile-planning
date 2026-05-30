# AI-Assisted Agile Planning & Analytics Dashboard

A Streamlit dashboard that turns Jira-style sprint data (epics, capacity,
dependencies, delivery risk) into structured decision support for engineering
leads — with AI-assisted summaries for sprint reviews, backlog refinement, and
leadership briefings.

> **Stack:** Python · Pandas · Streamlit · Plotly · NetworkX · Anthropic Claude · Tableau-ready exports.

## What it does

- **Portfolio overview** — KPIs, burn-chart, velocity trend, work-type mix.
- **Sprint deep-dive** — per-sprint capacity vs commit, per-person utilisation, overload warnings.
- **Epics & risk** — epic progress bars and a delivery-risk score (0–100) with explainable drivers (blocked %, scope size, dependencies, priority).
- **Dependencies** — interactive issue dependency graph + blocker-hotspot ranking.
- **AI summaries** — Claude-generated sprint review, backlog refinement, and leadership briefing from the same dataset. Falls back to a deterministic rules-based summariser when no API key is configured.
- **Tableau export** — one-click CSV exports for `sprint_metrics`, `epic_risk`, `dependencies`, etc.

## Project structure

```
AI_Agile_Planning/
├── app.py                      # Streamlit entry point
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example    # copy to secrets.toml + add your key
├── data/
│   ├── generate_data.py        # builds synthetic Jira-style CSVs
│   ├── sprints.csv             # generated
│   ├── team.csv                # generated
│   ├── epics.csv               # generated
│   └── issues.csv              # generated
├── src/
│   ├── data_loader.py
│   ├── analytics.py            # sprint metrics, risk score, capacity maths
│   ├── ai_summary.py           # Anthropic + rules-based fallback
│   └── visualizations.py       # Plotly charts
└── tests/
    └── test_analytics.py       # pytest coverage of the analytics layer
```

---

## Run it locally (Windows / macOS / Linux)

> Requires **Python 3.10+**. Tested on Python 3.11/3.12.

### 1. Clone and enter the project

```bash
git clone https://github.com/<your-username>/ai-agile-planning.git
cd ai-agile-planning
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Generate the synthetic dataset

```bash
python data/generate_data.py
```

You should see something like:
```
Wrote 8 sprints, 8 team members, 6 epics, ~370 issues to .../data
```

### 5. (Optional) Enable Claude-powered summaries

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit secrets.toml and paste your Anthropic API key
```

You can get a key from <https://console.anthropic.com/>. Without a key the dashboard still works — it uses a deterministic rules-based summariser.

### 6. Run the dashboard

```bash
streamlit run app.py
```

Streamlit opens <http://localhost:8501> automatically.

### 7. (Optional) Run the tests

```bash
pytest -q
```

---

## Bringing your own Jira data

The app reads four CSVs from `data/`. To use your own export, match these schemas:

**`sprints.csv`**
```
sprint_id,sprint_name,start_date,end_date,capacity_points
S01,Sprint 1,2026-01-06,2026-01-19,67
```

**`team.csv`**
```
member,role,capacity_per_sprint
Alice Chen,Backend,10
```

**`epics.csv`**
```
epic_id,epic_name,owner_team,priority
EPIC-101,Checkout Redesign,Frontend,High
```

**`issues.csv`**
```
issue_key,summary,issue_type,epic_id,sprint_id,story_points,status,assignee,assignee_role,priority,created_at,updated_at,blocked_by
AGL-0001,Story for Checkout Redesign,Story,EPIC-101,S01,5,Done,Alice Chen,Backend,High,2026-01-04,2026-01-19,
```

Statuses recognised: `Done`, `In Progress`, `To Do`, `Blocked`.

---


---

## License

MIT — see [LICENSE](LICENSE).
