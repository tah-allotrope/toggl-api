# Issue: Web App Feature Parity with Streamlit

Date: 2026-03-29
Status: Planned
Priority: High

## Objective

Bring the React web app (deployed on GitHub Pages) to feature parity with the legacy Streamlit app. The Streamlit app has rich visualizations and filtering that are currently missing from the web app.

## Background

The project has two frontend stacks:
1. **Legacy Streamlit** - Local Python app with SQLite, full feature set
2. **New React/Vite** - Hosted on GitHub Pages, connected to Supabase

The React app currently has:
- Basic page structure (Homepage, Dashboard, Retrospect, Chat)
- Supabase RPC functions for data queries
- Mock data mode when credentials not configured
- Cyberpunk-themed CSS (basic)

Missing features are primarily around:
- Interactive data visualizations (charts, heatmaps)
- Filter controls (year, date range, view mode)
- Rich UI components (date pickers, expanders, tabs)
- Enhanced chat quick-actions

## Implementation Plan

### Phase 1: Dashboard Enhancement (High Priority)

#### 1.1 Add View Mode Filter
**Files:** `web/src/pages/Dashboard.tsx`

Add a sidebar or filter bar with view mode selector:
- Single Year (dropdown with available years)
- All Time
- Custom Range (date pickers)

Need to fetch available years first via RPC or direct query.

#### 1.2 Add Visualizations with react-plotly.js
**Files:** `web/src/pages/Dashboard.tsx`, new components

Install: `npm install react-plotly.js plotly.js`

Create chart components:
- `components/Charts/ProjectPieChart.tsx` - Pie chart for project breakdown
- `components/Charts/ProjectBarChart.tsx` - Horizontal bar chart
- `components/Charts/TagBarChart.tsx` - Tag breakdown bar chart
- `components/Charts/ClientBarChart.tsx` - Client breakdown
- `components/Charts/MonthlyTrendChart.tsx` - Line chart with area fill

#### 1.3 Add Metrics Display
**Files:** `web/src/pages/Dashboard.tsx`

Replace simple text metrics with styled metric cards:
- Total Hours
- Total Entries
- Unique Projects
- Active Days
- Avg Hours/Day

#### 1.4 Add Project Drill-Down
**Files:** `web/src/pages/Dashboard.tsx`, new component

When user selects a project:
- Show total hours, entries, date range
- Expandable section: Top descriptions table
- Expandable section: Linked tasks (if available)
- Client association

#### 1.5 Add Daily Activity Heatmap
**Files:** `web/src/components/Charts/DailyHeatmap.tsx`

GitHub-style contribution heatmap:
- Fetch daily aggregated data
- Render as calendar grid
- Color intensity based on hours
- Tooltip on hover

Requires new RPC: `get_daily_hours` (aggregate by start_date)

---

### Phase 2: Retrospect Enhancement (Medium Priority)

#### 2.1 Add Date Picker
**Files:** `web/src/pages/Retrospect.tsx`

Add date input to select any date (not just today).

#### 2.2 Add Week View Tab
**Files:** `web/src/pages/Retrospect.tsx`

Add ISO week selector and display:
- Hours by year for selected week
- Stacked bar chart: Project breakdown by year

Requires existing RPC: `get_week_across_years` (already implemented)

#### 2.3 Add Year Comparison Tab
**Files:** `web/src/pages/Retrospect.tsx`

Two dropdowns to select Year A and Year B:
- Monthly hours comparison (grouped bar chart)
- Project comparison table with difference column
- Summary stats table

---

### Phase 3: Chat Enhancement (Medium Priority)

#### 3.1 Add Quick Query Buttons
**Files:** `web/src/pages/Chat.tsx`

Add quick action buttons below chat:
- "Today in history"
- "This week"
- "Total stats"
- "Top projects"
- "Top tags"
- "Yesterday"

Clicking a button submits the query automatically.

#### 3.2 Enhance Chat Display
**Files:** `web/src/pages/Chat.tsx`

Improve message display:
- Distinguish user vs assistant messages with styling
- Add typing indicator
- Auto-scroll to latest message

---

### Phase 4: Homepage Enhancement (Lower Priority)

#### 4.1 Card-Based Journal Layout
**Files:** `web/src/pages/Homepage.tsx`

Replace simple list with styled cards:
- Border container for each entry
- Day label (e.g., "Mon, Mar 29")
- Time label (e.g., "09:15")
- Project name
- Duration (formatted: "2.5h" or "45m")
- Description in bold

#### 4.2 Week Range Display
**Files:** `web/src/pages/Homepage.tsx`

Show week range: "Week 13 — Mar 23 to Mar 29, 2026"

---

### Phase 5: Cross-Cutting Concerns

#### 5.1 Install Dependencies
```bash
cd web
npm install react-plotly.js plotly.js react-datepicker date-fns
npm install -D @types/plotly.js
```

#### 5.2 Create Shared Chart Components
**Location:** `web/src/components/Charts/`

Reusable components:
- `NeonPieChart.tsx`
- `NeonBarChart.tsx`
- `NeonLineChart.tsx`
- `NeonHeatmap.tsx`

Each accepts data props and applies cyberpunk color scheme.

#### 5.3 Update Theme Colors
**Location:** `web/src/styles/theme.css`

Add color constants for charts:
```css
:root {
  --chart-cyan: #00ffcc;
  --chart-magenta: #ff00ff;
  --chart-yellow: #ffff00;
  --chart-orange: #ff6600;
  /* ... */
}
```

#### 5.4 Add Loading States
All data-fetching components should show:
- Skeleton loaders or spinner while loading
- Error state with retry button
- Empty state with helpful message

#### 5.5 Responsive Layout
Ensure charts and tables work on mobile:
- Stack columns on small screens
- Horizontal scroll for wide tables

---

## Technical Notes

### Supabase RPC Functions Already Available
- `get_overview_metrics` - Overview stats
- `get_project_breakdown` - Project hours/entries
- `get_tag_breakdown` - Tag hours/entries
- `get_client_breakdown` - Client hours/entries
- `get_task_breakdown` - Task hours/entries
- `get_on_this_day` - Historical date data
- `get_week_across_years` - ISO week across years

### RPC Functions to Add
- `get_daily_hours` - For heatmap (start_date, hours, entries)
- `get_monthly_hours` - Month-year breakdown for trend chart
- `get_available_years` - List of years with data
- `get_top_descriptions` - For project drill-down
- `get_year_comparison` - Optimized year vs year query

### Mock Data Updates
Update `web/src/lib/supabase.ts` mock functions to match new RPC signatures.

---

## Files to Modify

### Pages (High Priority)
- `web/src/pages/Dashboard.tsx` - Major enhancement
- `web/src/pages/Retrospect.tsx` - Add tabs + date picker
- `web/src/pages/Chat.tsx` - Quick buttons + enhanced UI
- `web/src/pages/Homepage.tsx` - Card layout

### Components (New)
- `web/src/components/Charts/*.tsx` - New chart components
- `web/src/components/MetricCard.tsx` - Reusable metric display
- `web/src/components/DateRangePicker.tsx` - Date range selector
- `web/src/components/LoadingSpinner.tsx` - Loading state

### API Layer
- `web/src/lib/api.ts` - Add new fetch functions

### Styles
- `web/src/styles/theme.css` - Add chart colors, responsive utilities

---

## Testing Strategy

1. **Demo Mode Testing**: All features work with mock data
2. **Real Supabase**: Connect to live database and verify
3. **Responsive**: Test on mobile viewport
4. **Performance**: Verify page load times < 3s

---

## Success Criteria

- [ ] Dashboard shows all charts (projects, tags, clients, tasks)
- [ ] Dashboard has working filters (year, all time, custom range)
- [ ] Project drill-down works
- [ ] Daily heatmap displays correctly
- [ ] Retrospect has all 3 tabs (On This Day, Week View, Year Comparison)
- [ ] Chat has quick query buttons
- [ ] Homepage shows card-based layout
- [ ] All pages have loading/error states
- [ ] Responsive on mobile devices
