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

## Deploy to GitHub + Streamlit Community Cloud

The fastest way to share this with an interviewer.

### A. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: AI-Assisted Agile Planning Dashboard"
git branch -M main

# Create a new public repo on github.com first (no README, no .gitignore),
# then add it as a remote:
git remote add origin https://github.com/<your-username>/ai-agile-planning.git
git push -u origin main
```

> Confirm `.streamlit/secrets.toml` is NOT pushed — it's in `.gitignore`.

### B. Deploy on Streamlit Community Cloud (free)

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. Click **"New app"** → pick your repo, branch `main`, main file `app.py`.
3. Under **Advanced settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   (Or leave it blank — the fallback summariser will still produce summaries.)
4. Click **Deploy**. Your app gets a public URL like
   `https://ai-agile-planning-<hash>.streamlit.app` — perfect to put on your CV.

### C. Alternative: deploy on Hugging Face Spaces

1. Create a new Space → SDK = **Streamlit**.
2. Add the repo files. In **Settings → Secrets**, add `ANTHROPIC_API_KEY`.
3. The Space rebuilds and the live URL appears at the top.

### D. Alternative: Docker / Render / Fly.io

Add a `Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python data/generate_data.py
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
```
Then `docker build -t agile-dashboard . && docker run -p 8501:8501 agile-dashboard`.

---

## Showing this in an interview

A short narrative that lands well:

> "I prototyped a dashboard that ingests Jira-style sprint data and produces
> three things engineering leads actually want: a risk-scored portfolio view,
> a per-sprint capacity-vs-commit picture, and AI-drafted briefings for sprint
> review, backlog refinement, and leadership updates. The analytics layer is
> pure-Pandas and unit-tested; the LLM only writes the narrative, never the
> numbers — so summaries can't hallucinate metrics. It exports CSVs for
> Tableau so it slots into existing reporting."

Talking points:
- **Prompt engineering** — three audience-specific system prompts in `src/ai_summary.py`; the model is grounded by passing structured JSON with explicit "use only these numbers" instructions.
- **Risk model** — explainable score in `src/analytics.py:delivery_risk` driven by blocked %, scope size, dependency count, and priority, banded Low/Medium/High/Critical.
- **Graceful degradation** — `_anthropic_summary` falls back to a deterministic summary when no API key is present, so the demo never crashes.

---

## License

MIT — see [LICENSE](LICENSE).
