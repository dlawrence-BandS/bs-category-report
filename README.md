# B&S Item Category Report

GitHub Pages replacement for the Looker Studio "Item Category Report - NEW".
Same pattern as the other dashboards: static `index.html` + JSON data files
generated from BigQuery by a Python refresh script.

## Tabs

1. **Category Summary (Weekly)** — KPI cards (last full week WoW), category KPI
   table with heatmap + deltas, 100% stacked weekly share charts (transactions /
   revenue), CVR lines, monthly sessions mix.
2. **Sub-Category Summary (Weekly)** — same, driven by `item_category2`, top-6
   trend lines for transactions / CVR / revenue / sessions.
3. **Garden / Sofas / Dining Tables / Dining Chairs / Mattresses Sales** — one
   deep-dive template per focus category: KPI cards, top-25 item table with WoW
   deltas, revenue/sessions/CVR vs last year (364-day aligned), revenue by range
   and by item type (daily, last 28 days).
4. **Item Ranges & Item Sales** — item-level WoW table. Search, category filter,
   sortable columns, pagination, CSV export.
5. **Item Detail & Channels** — item table with item IDs + CSV export, channel
   performance last week vs prior, daily revenue by channel.

## Data definitions

- **Sessions** = distinct GA4 sessions containing a `view_item` event for an
  item in that category (item-scoped, matching the Looker report).
- **Transactions / items purchased / revenue** = from `purchase` event `items`
  array (`transaction_id`, `quantity`, `item_revenue`).
- **CVR** = transactions / sessions. **AOV** = revenue / transactions.
- **Range** = `item_brand`, falling back to the first word of the item name.
- Channel tab sessions are whole-site sessions by
  `session_traffic_source_last_click` default channel group (not item-scoped).
- Header KPIs and tables compare **last full week (Mon–Sun) vs the week before**.

## Setup

1. Drop a copy of the `bs-dashboard` service account key JSON in this folder or
   `C:\Users\dlawrence\Documents\BQ` — the script auto-discovers it. The
   `.gitignore` blocks key files from being committed; keep it that way.
2. `py -m pip install google-cloud-bigquery`
3. Run `refresh.bat` (or `py refresh_data.py`). Writes everything to `data/`.
4. Commit + push via GitHub Desktop. Enable GitHub Pages on the repo.

Local preview: `py -m http.server` in this folder, then http://localhost:8000.
`py make_sample_data.py` fills `data/` with fake numbers if you want to see the
UI before the first real refresh.

## Refresh & cost

`refresh_data.py` runs 7 queries. The weekly/monthly/daily-focus queries scan
`view_item` + `purchase` events from 2023-04-03 — that full-history scan runs
every refresh, so this one is best scheduled **weekly** (Task Scheduler, Monday
morning) rather than daily. Item-level, breakdown and channel queries only scan
2 weeks / 28 days / 14 days.

Use `py refresh_data.py --start 2024-01-01` to shorten the history window and
cut scan cost.

## Tweaking the focus tabs

Edit the `FOCUS` dict at the top of `refresh_data.py` — key, label, and which
GA4 field/value it matches (`item_category` or `item_category2`). The frontend
picks up tabs automatically from `meta.json`.
