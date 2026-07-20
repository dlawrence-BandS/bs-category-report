# B&S Item Category Report — live / OAuth build

GitHub Pages replacement for the Looker Studio "Item Category Report - NEW".

This version no longer ships pre-baked JSON. A single-file `index.html`:

1. gates access behind **Google sign-in**, restricted to the
   `barkerandstonehouse.co.uk` Workspace domain, and
2. queries **BigQuery live** (per signed-in user, BigQuery-readonly scope) for
   whatever **date range** you pick — so the data is always current and the
   `data/` folder is gone (no B&S numbers sitting at a public URL any more).

The SQL is identical to the old `refresh_data.py` (kept in the repo for
reference), just ported into the page and parameterised by the selected range.

## One-time setup (required before it works)

1. **OAuth client ID.** Open `index.html` and set `CLIENT_ID` near the top of
   the script. The same Web-application client you use on bs-search works here,
   provided `https://dlawrence-bands.github.io` is listed under *Authorised
   JavaScript origins* for that client. If not, add it (Google Cloud Console →
   APIs & Services → Credentials).
2. **Scopes on the consent screen.** The client needs
   `openid`, `email`, and `https://www.googleapis.com/auth/bigquery.readonly`.
3. **BigQuery access for viewers.** This is the big change from the service-
   account model: each person now queries BigQuery as *themselves*, not as
   `bs-dashboard@…`. Every B&S Google account that should see the dashboard
   needs, on project `commanding-air-450109-p0`:
   - **BigQuery Data Viewer** on dataset `analytics_287404213` (or project-wide), and
   - **BigQuery Job User** on the project (so they can run queries).
   Without both, queries come back 403 and the tab shows "Query failed".
4. **Delete `data/` from the live repo.** This build already removes it. If the
   old JSON is still in your Pages history, remove it so the numbers aren't
   publicly fetchable — the login only protects data that isn't also sitting in
   a public file.

## Using it

- Sign in with your B&S Google account.
- **Period** selector: Last full week (default), Last 4 / 13 / 26 weeks, or a
  custom From→To range. Everything ("vs prior") compares your selected period
  against the immediately preceding period of equal length. The weekly summary
  tabs snap the comparison to whole Mon–Sun weeks.
- **↻ Refresh** re-runs the current period against BigQuery (use it to pull
  today's newest data mid-session).
- Tabs load lazily and results are cached per period, so switching tabs is
  instant and only the tabs you open get queried.

## Notes on cost / speed

- The Category tab (default) runs 2 queries: a ~15-month weekly series and a
  ~2-year monthly seasonal mix.
- The focus tabs (Garden/Sofas/…) share one heavier query: ~26 months of daily
  focus data (needed for the 56-week view plus the 364-day YoY overlay). It runs
  once on first open and is cached. Widening the custom range widens the scan.
- These are bounded per-range scans, not the full-history rebuild the old
  refresh script did, so live querying is fine cost-wise for interactive use.

## Auth internals

GIS token client, `bigquery.readonly` scope, `hd` hint + an explicit
`endsWith('@barkerandstonehouse.co.uk')` check on the userinfo email (the `hd`
hint alone isn't enforcement). Token refresh uses the `tokenInFlight`
promise-coalescing pattern so parallel tab queries don't trigger multiple popups.
