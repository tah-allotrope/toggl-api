# Layer 2: Deep Dive Analysis Module — Full Implementation Plan

## Overview

A self-contained `analysis/` directory that reads from the same `data/toggl.db` SQLite
database as the Streamlit dashboard, runs six independent analyzers over 10 years of
Toggl data, and produces a single comprehensive cyberpunk-themed HTML report.

**Run command:**
```bash
python -m analysis                          # full report, auto-timestamped filename
python -m analysis --output path/to/out.html
python -m analysis --only longitudinal,changepoints
python -m analysis --start 2020-01-01 --end 2025-12-31
```

---

## Stack Additions

| Package | Purpose |
|---------|---------|
| `scipy` | Statistical tests (Mann-Kendall, KS tests), distributions, seasonal decomposition |
| `ruptures` | Changepoint detection — PELT and binary segmentation algorithms |
| `scikit-learn` | TF-IDF vectorizer, LDA/NMF topic models, KMeans week clustering |
| `vaderSentiment` | Sentiment scoring optimized for short informal text |
| `jinja2` | HTML report templating (transitive Streamlit dep, now pinned explicitly) |

---

## Directory Structure

```
analysis/
├── __init__.py
├── __main__.py              # python -m analysis entry point
├── run.py                   # CLI orchestrator (argparse + pipeline runner)
├── data_access.py           # SQLite reads — zero coupling to src/ or Streamlit
├── analyzers/
│   ├── __init__.py
│   ├── longitudinal.py      # Life composition, stacked allocation, concentration
│   ├── changepoints.py      # Regime detection — PELT + Bayesian-style
│   ├── rhythms.py           # Time-of-day, day-of-week, seasonality, sleep/wake
│   ├── correlations.py      # Co-occurrence, crowding-out, week archetypes
│   ├── text_mining.py       # LDA + NMF topics, sentiment drift, vocabulary evolution
│   └── life_phases.py       # Auto-detected eras synthesizing all other analyzers
├── report/
│   ├── __init__.py
│   ├── renderer.py          # Assembles AnalysisResult objects into final HTML
│   └── template.html        # Jinja2 base template — cyberpunk CSS + Plotly CDN
└── output/                  # Generated reports land here — gitignored
    └── .gitkeep
```

---

## Data Layer: `analysis/data_access.py`

**Design principle:** imports only `sqlite3`, `pandas`, `json`, `pathlib`. No `src/`
imports, no Streamlit. Works standalone in any Python environment with the DB present.

### Functions

```python
load_entries(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame
```
Core time_entries query. Derived columns: `tags_list` (parsed JSON array),
`start_dt` (parsed datetime), `hour_of_day`, `day_of_week`, `is_weekend`.
Always filters `WHERE duration > 0`.

```python
load_daily_series() -> pd.DataFrame
```
Aggregated per calendar date: `date`, `hours`, `entry_count`, `unique_projects`,
`unique_tags`, `first_entry_hour`, `last_entry_hour`. The backbone for longitudinal,
changepoints, and rhythms analysis.

```python
load_weekly_matrix() -> pd.DataFrame
```
Per ISO week × project pivot table of hours. Used by correlations and life_phases.

```python
load_projects() -> pd.DataFrame
load_description_corpus() -> pd.Series
```

---

## Analyzers

All analyzers implement a uniform interface:

```python
@dataclass
class AnalysisResult:
    name: str                        # analyzer ID for report sections
    title: str                       # Human-readable section heading
    summary: dict[str, Any]          # Key findings (rendered as stat cards)
    figures: list[go.Figure]         # Plotly figures
    tables: list[pd.DataFrame]       # DataFrames (rendered as HTML tables)
    narrative: str                   # Plain-English paragraph summary
```

Each module exposes: `analyze(entries, daily, weekly) -> AnalysisResult`

---

### 1. `analyzers/longitudinal.py` — Life Composition Analysis

**Core question:** How has my time allocation shifted across 10 years?

#### Analyses

**1.1 Stacked Category Composition (the key chart)**
- Quarterly normalized 100% stacked area chart: top-N projects by total hours
  across all time, showing how their share of total tracked time evolved
- Same for tags
- Identifies visually when categories rose, plateaued, and faded

**1.2 Concentration Index Over Time**
- Herfindahl-Hirschman Index (HHI) computed per quarter:
  `HHI = Σ(share_i²)` where `share_i` = project i's fraction of quarterly hours
- HHI → 1.0 means total focus on one thing; HHI → 0 means fully diversified
- Plot as line chart to see the narrowing-vs-broadening arc of your work life

**1.3 Rolling Statistics**
- 30-day, 90-day rolling mean and std dev of daily tracked hours
- Highlights productivity streaks, burnout troughs, and recovery periods

**1.4 Year-over-Year Monthly Heatmap**
- 10×12 heatmap: years × months, cell = total hours
- Reveals seasonal patterns and year-level intensity shifts

**1.5 Category Transition Velocity**
- For each project, compute quarter-over-quarter change in share
- Identify top-5 fastest-rising and fastest-falling categories
- Ties changepoint timestamps back to which categories drove the shift

**1.6 Session Duration Trends**
- Distribution of entry durations (minutes) by year — are sessions getting longer or
  shorter? Violin plot per year.

**1.7 Active Days Rate**
- Rolling 90-day percentage of days with any tracking
- Shows engagement consistency over time

---

### 2. `analyzers/changepoints.py` — Transition Detection

**Core question:** When did my behavior fundamentally and statistically shift?

#### Analyses

**2.1 PELT Changepoint Detection (primary)**
- Apply `ruptures.Pelt(model="rbf")` to the daily hours time series
- Penalty parameter sweep: run at 5 values, report stable changepoints that appear
  across ≥3 penalties ("consensus changepoints")
- Repeat on secondary signals: weekly unique-projects, weekly active-days-rate,
  average entry duration

**2.2 Multi-Signal Aggregation**
- Combine changepoints from all signals; cluster nearby dates (within 4 weeks)
  into a single "transition event"
- For each transition event: compute before/after statistics on all signals
- Before/after: mean hours/day, top-3 projects by share, dominant tags,
  HHI (focus), weekend ratio

**2.3 Binary Segmentation (secondary)**
- `ruptures.Binseg` as a cross-check with a fixed number of breakpoints (n=8)
- Flag disagreements between PELT and Binseg as "uncertain" transitions

**2.4 Annotated Timeline Figure**
- Full daily hours time series with vertical lines at each consensus changepoint
- Color-coded by confidence (appeared in 3/5 vs 5/5 penalties)
- Tooltip shows before/after stats

**2.5 Transition Summary Table**
- Date | Signal | Before Mean | After Mean | % Change | Confidence

---

### 3. `analyzers/rhythms.py` — Rhythm and Routine Analysis

**Core question:** When do I work, and how has that changed?

#### Analyses

**3.1 Hour-of-Day Distribution by Year**
- For each year: histogram of entry start hours (0–23)
- Small-multiples line chart — see if your peak work hour shifted
- Identify year when "morning person" vs "night owl" pattern changed

**3.2 Day-of-Week Composition by Year**
- Stacked 100% bar: Mon–Sun, years as color groups
- Identifies shifts from weekday-only to weekend work or vice versa

**3.3 Sleep/Wake Proxy**
- Per day: first entry hour (proxy wake-up) and last entry hour (proxy sleep)
- Rolling 90-day mean of both
- Caution: only valid when entries are continuous; treat as behavioral proxy,
  not literal sleep data

**3.4 Seasonal Decomposition**
- Monthly total hours decomposed into trend + seasonal + residual using
  `scipy.signal` or STL-style rolling approach
- Identify your "busy season" and whether it's consistent year-over-year

**3.5 Weekend vs. Weekday Ratio Over Time**
- Rolling 90-day: weekend_hours / (weekend_hours + weekday_hours)
- Apply a simple changepoint check to find when this ratio shifted

**3.6 Consistency Score**
- Rolling 90-day coefficient of variation (std/mean) of daily hours
- Lower = more regular; higher = more bursty
- Plot as line chart with annotations at major life events (via changepoints)

---

### 4. `analyzers/correlations.py` — Network and Correlation Analysis

**Core question:** Which activities crowd each other out, and what are your actual trade-offs?

#### Analyses

**4.1 Weekly Co-Occurrence Matrix**
- Pivot: weeks × top-N projects, cell = hours that week
- Compute Pearson correlation matrix for all project pairs
- Visualize as heatmap with hierarchical clustering (dendrogram ordering)

**4.2 Crowding-Out Analysis**
- For each top-10 project: when it's in the top quartile of weekly hours,
  what's the mean hours of every other project?
- Compare to baseline (all weeks) to find crowded-out activities
- Bar chart: "What gets displaced when [Project X] spikes?"

**4.3 Trade-Off Pairs**
- Extract top-10 most negative Pearson correlations
- These are the genuine zero-sum trade-offs in your schedule
- Display as a ranked table with scatter plots for top-3 pairs

**4.4 Week Archetypes (KMeans Clustering)**
- Normalize weekly project-hour vectors, cluster into 6–8 archetypes
- Label each archetype by its dominant projects
  (e.g., "Heavy Consulting Week", "Side Project Sprint", "Light/Recovery Week")
- Show: how often each archetype occurred by year, and a calendar coloring
  each week by its archetype

**4.5 Lead/Lag Analysis**
- Cross-correlation with 1–4 week time offsets for top project pairs
- "Does a spike in [A] predict a spike or drop in [B] two weeks later?"
- Visualize as cross-correlogram for top-5 most interesting pairs

**4.6 Activity Network Graph**
- Plotly network: nodes = top-20 projects, sized by total hours
- Edges = significant correlations (|r| > 0.2), colored cyan (positive) / magenta (negative)
- Width = |r| magnitude

---

### 5. `analyzers/text_mining.py` — Description Text Mining

**Core question:** What do 10 years of entry descriptions reveal about what I was thinking about?

#### Analyses

**5.1 Text Preprocessing**
- Lowercase, remove punctuation, tokenize
- Remove stop words (English NLTK list embedded as a constant — no NLTK download)
- Filter tokens < 3 characters; strip project/tag names that dominate and obscure
- Build corpus: one "document" per entry description

**5.2 TF-IDF Vectorization**
- `sklearn.TfidfVectorizer(min_df=5, max_df=0.85, ngram_range=(1,2))`
- Produces term-document matrix used by both topic models

**5.3 Topic Extraction — NMF**
- `sklearn.NMF(n_components=12)` on TF-IDF matrix
- Each topic: top-10 keywords + total hours associated
- NMF topics tend to be more interpretable for short texts

**5.4 Topic Extraction — LDA**
- `sklearn.LatentDirichletAllocation(n_components=12)` on raw count matrix
- Cross-reference with NMF topics; surface topics present in one but not the other
- LDA topics used as feature in life_phases.py

**5.5 Topic Prevalence Over Time**
- Assign each entry its dominant topic (argmax of topic probability vector)
- Aggregate topic hours by quarter
- Stacked area chart: how topics rise and fall over time

**5.6 Sentiment Drift Analysis**
- Apply `vaderSentiment.SentimentIntensityAnalyzer` to each description
- Compute rolling 90-day mean compound score
- Plot as line chart: is your journaling tone getting more positive or negative over time?
- Highlight statistically significant drift periods (Mann-Kendall test via `scipy`)

**5.7 Vocabulary Evolution**
- Per year: compute TF-IDF top-50 terms
- New terms (first appear in year N): signals new projects or life areas entering
- Disappeared terms (last appear in year N): signals transitions out
- Table: "Emerging vocabulary" and "Fading vocabulary" per year

**5.8 Description Length Trends**
- Mean words per entry description by quarter
- Are entries getting more or less descriptive over time?

---

### 6. `analyzers/life_phases.py` — Automatic Life Phase Segmentation

**Core question:** What were the distinct eras of my tracked life, named and quantified?

This is the capstone analyzer. It consumes outputs from all other analyzers.

#### Analyses

**6.1 Feature Vector Construction**
Per week, build a normalized feature vector:
- Total tracked hours
- Shannon entropy of project distribution (diversity)
- Top-project concentration ratio (hours of #1 project / total)
- Weekend tracking ratio
- Mean entry duration (minutes)
- Dominant LDA topic ID (from text_mining)
- Active days count
- Consistency (1 / CoV of daily hours)

**6.2 Multivariate Changepoint Detection**
- Apply `ruptures.Pelt` to each feature dimension independently
- Aggregate across all features: weeks with ≥3 simultaneous feature changepoints
  are candidate phase boundaries
- Cluster boundaries within 3 weeks; keep the most signal-dense date

**6.3 Phase Characterization**
For each detected phase (date range):
- Total duration in days/months
- Mean daily hours ± std
- Top-3 projects by share (with percentages)
- Top-3 LDA topics (with percentages)
- Dominant tags
- Behavioral descriptors: focus (HHI), rhythm (consistency), intensity (mean hours)
- Weekend ratio

**6.4 Auto-Naming Heuristic**
Generate a human-readable label from:
- Top project name or client area
- Dominant topic keywords
- Intensity descriptor ("Intensive", "Moderate", "Exploratory", "Transitional")
- Example: "Intensive VIDA / Decarbonization Era", "Exploratory Consulting Phase"

**6.5 Visualizations**
- Gantt/timeline chart: phases as horizontal colored bands across the 10-year span
- Phase comparison table: all phases side-by-side on key metrics
- Radar/spider chart per phase: normalized metrics (hours, focus, diversity, rhythm, sentiment)

---

## Report: `report/renderer.py` + `report/template.html`

### Template Design
- Self-contained single `.html` file
- Plotly embedded via CDN (`include_plotlyjs="cdn"`)
- All CSS inline in `<style>` — no external stylesheet dependencies
- Cyberpunk color palette matches dashboard (`#0a0a1a` bg, `#00fff9` cyan, `#ff00ff` magenta)
- Table of contents with anchor links to each section
- Responsive layout with CSS grid

### Report Sections (in order)
1. **Header** — generation timestamp, data range, total entries/hours, data quality note
2. **Life Composition** — longitudinal allocation, concentration index, rolling stats
3. **Rhythms & Routines** — time-of-day, day-of-week, sleep/wake, seasonal
4. **Transition Detection** — annotated changepoint timeline, transition table
5. **Activity Correlations** — co-occurrence heatmap, trade-off pairs, week archetypes, network graph
6. **Text Mining** — topics (NMF + LDA), sentiment drift, vocabulary evolution
7. **Life Phases** — Gantt timeline, phase profiles, radar charts, comparison table
8. **Appendix** — methodology notes, data quality breakdown (CSV vs enriched entries)

### Renderer Logic
```python
def render_report(results: list[AnalysisResult], meta: dict) -> str:
    # For each result: serialize figures to HTML divs, render tables
    # Inject into Jinja2 template
    # Return complete HTML string
```

---

## CLI: `run.py` + `__main__.py`

```
python -m analysis [OPTIONS]

Options:
  --output PATH          Output HTML file path
                         Default: analysis/output/report_YYYY-MM-DD.html
  --only NAMES           Comma-separated subset of analyzers to run
                         Valid: longitudinal,changepoints,rhythms,
                                correlations,text_mining,life_phases
  --start DATE           Filter entries from this date (YYYY-MM-DD)
  --end DATE             Filter entries to this date (YYYY-MM-DD)
  --no-open              Don't auto-open report in browser after generation
  --quiet                Suppress progress output
```

**Execution flow:**
1. Parse args, validate DB exists at `data/toggl.db`
2. Print data summary: date range, total entries, enrichment coverage
3. Load data via `data_access.py` (entries, daily series, weekly matrix)
4. Run enabled analyzers in dependency order, showing progress
5. Life phases runs last (depends on text_mining LDA output)
6. Pass all `AnalysisResult` objects to `renderer.render_report()`
7. Write HTML to output path
8. Print report path and top-3 findings from life_phases summary
9. Auto-open in default browser (unless `--no-open`)

---

## Implementation Order

| Step | Files | Notes |
|------|-------|-------|
| 1 | `analysis/__init__.py`, `analyzers/__init__.py`, `report/__init__.py`, `output/.gitkeep` | Scaffolding |
| 2 | `analysis/data_access.py` | Foundation — all analyzers depend on this |
| 3 | `analyzers/longitudinal.py` | Independent of other analyzers |
| 4 | `analyzers/changepoints.py` | Independent of other analyzers |
| 5 | `analyzers/rhythms.py` | Independent of other analyzers |
| 6 | `analyzers/correlations.py` | Independent of other analyzers |
| 7 | `analyzers/text_mining.py` | Independent; provides LDA output for life_phases |
| 8 | `analyzers/life_phases.py` | Depends on outputs from steps 3–7 |
| 9 | `report/template.html` | Static template |
| 10 | `report/renderer.py` | Depends on AnalysisResult shape from all analyzers |
| 11 | `analysis/run.py` + `analysis/__main__.py` | Final wiring |
| 12 | `requirements.txt`, `.gitignore`, `AGENTS.md` | Housekeeping |

---

## Design Decisions

**No imports from `src/`**
The analysis module is deliberately decoupled from the Streamlit app. It reads the same
SQLite database but has its own `data_access.py`. Works without Streamlit installed.

**Uniform `AnalysisResult` protocol**
Each analyzer returns the same dataclass shape. The renderer is fully generic and doesn't
need to know about analyzer internals. Adding a new analyzer = zero renderer changes.

**Life phases as capstone**
`life_phases.py` is the synthesizing layer. It consumes the LDA topic assignments from
`text_mining.py` and (optionally) the changepoint dates from `changepoints.py` as
soft priors for its boundary candidates.

**Sentiment with vaderSentiment**
VADER is optimized for short, informal text (exactly what Toggl descriptions are).
It requires no model training and no internet access at runtime. ~50KB dependency.

**LDA + NMF both run**
NMF produces sharper, more interpretable topics for short texts. LDA produces
probabilistic topic vectors useful for life_phases feature construction. Both are
in scikit-learn — no extra dependency.

**Output is gitignored**
`analysis/output/` goes in `.gitignore`. Only the template and code are tracked.

**Cyberpunk theme continuity**
The HTML report template hardcodes the same hex values from `src/theme.py`'s `COLORS`
dict so reports visually match the dashboard without importing Streamlit.

---

## Key Insights This Module Is Designed to Surface

1. **The narrowing thesis:** The stacked composition chart in `longitudinal.py` should
   visually confirm (or complicate) the shift from broad energy work toward focused
   VIDA/industrial decarbonization — with exact dates and rates of change.

2. **Unconscious transitions:** `changepoints.py` will surface behavioral shifts that
   didn't feel like discrete decisions at the time — the data often sees phase changes
   before the person does.

3. **The micro-journal:** `text_mining.py` treats descriptions as a 10-year diary.
   Sentiment drift may reveal emotional arcs across work phases. Vocabulary evolution
   shows what concepts entered and left your thinking.

4. **Your actual trade-offs:** `correlations.py` will name the specific projects that
   compete for your time — the ones that go up when others go down — making implicit
   opportunity costs explicit.

5. **Rhythm as biography:** `rhythms.py` may show when you started working weekends,
   when your peak hour shifted, and whether your consistency has increased or decreased
   — a behavioral fingerprint of each life era.

6. **Named eras:** `life_phases.py` will produce a set of labeled epochs — your
   professional biography, quantified.
