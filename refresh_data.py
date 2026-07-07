"""
B&S Item Category Report - BigQuery data refresh
Replaces Looker Studio 'Item Category Report - NEW'

Queries GA4 export (view_item sessions + purchase items) and writes JSON
files into ./data for the GitHub Pages dashboard.

Usage:
  py refresh_data.py                # full refresh, history from 2023-04-03
  py refresh_data.py --start 2024-01-01
"""

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict

from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT = "commanding-air-450109-p0"
DATASET = "analytics_287404213"
LOCATION = "europe-west2"
HISTORY_START = "2023-04-03"  # matches the Looker report range start

# Focus tabs (deep-dive pages). match: (field, value) - case-insensitive.
FOCUS = {
    "garden":        {"label": "Garden",        "field": "item_category",  "value": "GARDEN"},
    "sofas":         {"label": "Sofas",         "field": "item_category2", "value": "SOFAS"},
    "dining_tables": {"label": "Dining Tables", "field": "item_category2", "value": "DINING TABLES"},
    "dining_chairs": {"label": "Dining Chairs", "field": "item_category2", "value": "DINING CHAIRS"},
    "mattresses":    {"label": "Mattresses",    "field": "item_category2", "value": "MATTRESSES"},
}

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

KEY_SEARCH_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.getcwd(),
    r"C:\Users\dlawrence\Documents\BQ",
]


def find_service_account_key():
    """Auto-discover a service account key JSON (same pattern as other dashboards)."""
    for d in KEY_SEARCH_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            path = os.path.join(d, f)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and "client_email" in data and "private_key" in data:
                    return path
            except Exception:
                continue
    return None


def get_client():
    key_path = find_service_account_key()
    if key_path:
        print(f"Using service account key: {key_path}")
        creds = service_account.Credentials.from_service_account_file(key_path)
        return bigquery.Client(project=PROJECT, credentials=creds, location=LOCATION)
    print("No key file found - falling back to application default credentials")
    return bigquery.Client(project=PROJECT, location=LOCATION)


def suffix(d):  # date -> _TABLE_SUFFIX string
    return d.strftime("%Y%m%d")


def week_start(d):
    return d - dt.timedelta(days=d.weekday())  # Monday


def run(client, sql, label):
    print(f"  running: {label} ...")
    job = client.query(sql)
    rows = [dict(r) for r in job.result()]
    gb = (job.total_bytes_processed or 0) / 1e9
    print(f"    {len(rows)} rows, {gb:.2f} GB processed")
    return rows


# ---------------------------------------------------------------- SQL builders

def sql_weekly(dim, start_sfx, end_sfx):
    """Weekly sessions/views/purchases by item_category or item_category2."""
    return f"""
WITH v AS (
  SELECT
    DATE_TRUNC(PARSE_DATE('%Y%m%d', event_date), WEEK(MONDAY)) AS wk,
    IFNULL(NULLIF(TRIM(i.{dim}), ''), '(not set)') AS cat,
    CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)) AS sid,
    i.item_name AS nm
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'view_item'
    AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
p AS (
  SELECT
    DATE_TRUNC(PARSE_DATE('%Y%m%d', event_date), WEEK(MONDAY)) AS wk,
    IFNULL(NULLIF(TRIM(i.{dim}), ''), '(not set)') AS cat,
    ecommerce.transaction_id AS tid,
    IFNULL(i.quantity, 1) AS q,
    IFNULL(i.item_revenue, 0) AS rev
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
va AS (
  SELECT wk, cat, COUNT(DISTINCT sid) AS s, COUNT(DISTINCT nm) AS iv
  FROM v GROUP BY wk, cat
),
pa AS (
  SELECT wk, cat, COUNT(DISTINCT tid) AS t, SUM(q) AS ip, ROUND(SUM(rev), 2) AS r
  FROM p GROUP BY wk, cat
)
SELECT
  FORMAT_DATE('%Y-%m-%d', COALESCE(va.wk, pa.wk)) AS w,
  COALESCE(va.cat, pa.cat) AS c,
  IFNULL(va.s, 0) AS s, IFNULL(va.iv, 0) AS iv,
  IFNULL(pa.t, 0) AS t, IFNULL(pa.ip, 0) AS ip, IFNULL(pa.r, 0) AS r
FROM va FULL OUTER JOIN pa USING (wk, cat)
ORDER BY w, c
"""


def sql_monthly_sessions(start_sfx, end_sfx):
    """Calendar-month (Jan-Dec, all years combined) sessions by category."""
    return f"""
SELECT
  EXTRACT(MONTH FROM PARSE_DATE('%Y%m%d', event_date)) AS m,
  IFNULL(NULLIF(TRIM(i.item_category), ''), '(not set)') AS c,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING))) AS s
FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
WHERE event_name = 'view_item'
  AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
GROUP BY m, c
ORDER BY m, c
"""


def focus_case():
    parts = []
    for k, f in FOCUS.items():
        parts.append(f"WHEN UPPER(TRIM(i.{f['field']})) = '{f['value']}' THEN '{k}'")
    return "CASE " + " ".join(parts) + " ELSE NULL END"


def sql_daily_focus(start_sfx, end_sfx):
    """Daily sessions/transactions/revenue for each focus key (full history, YoY overlays)."""
    fc = focus_case()
    return f"""
WITH v AS (
  SELECT PARSE_DATE('%Y%m%d', event_date) AS d, {fc} AS k,
    CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)) AS sid
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'view_item' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
p AS (
  SELECT PARSE_DATE('%Y%m%d', event_date) AS d, {fc} AS k,
    ecommerce.transaction_id AS tid, IFNULL(i.quantity, 1) AS q, IFNULL(i.item_revenue, 0) AS rev
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'purchase' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
va AS (SELECT d, k, COUNT(DISTINCT sid) AS s FROM v WHERE k IS NOT NULL GROUP BY d, k),
pa AS (SELECT d, k, COUNT(DISTINCT tid) AS t, SUM(q) AS ip, ROUND(SUM(rev), 2) AS r
       FROM p WHERE k IS NOT NULL GROUP BY d, k)
SELECT FORMAT_DATE('%Y-%m-%d', COALESCE(va.d, pa.d)) AS d, COALESCE(va.k, pa.k) AS k,
  IFNULL(va.s, 0) AS s, IFNULL(pa.t, 0) AS t, IFNULL(pa.ip, 0) AS ip, IFNULL(pa.r, 0) AS r
FROM va FULL OUTER JOIN pa USING (d, k)
ORDER BY d, k
"""


def sql_items_two_weeks(start_sfx, end_sfx, cur_start):
    """Item-level metrics for last week + previous week (one pass, pivoted in Python)."""
    fc = focus_case()
    return f"""
WITH v AS (
  SELECT
    IF(PARSE_DATE('%Y%m%d', event_date) >= DATE '{cur_start}', 'cur', 'prev') AS pd,
    TRIM(i.item_name) AS nm,
    CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)) AS sid
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'view_item' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
    AND i.item_name IS NOT NULL AND TRIM(i.item_name) != ''
),
p AS (
  SELECT
    IF(PARSE_DATE('%Y%m%d', event_date) >= DATE '{cur_start}', 'cur', 'prev') AS pd,
    TRIM(i.item_name) AS nm,
    ecommerce.transaction_id AS tid, IFNULL(i.quantity, 1) AS q, IFNULL(i.item_revenue, 0) AS rev
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name = 'purchase' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
    AND i.item_name IS NOT NULL AND TRIM(i.item_name) != ''
),
attrs AS (
  SELECT TRIM(i.item_name) AS nm,
    APPROX_TOP_COUNT(i.item_id, 1)[OFFSET(0)].value AS id,
    APPROX_TOP_COUNT(IFNULL(NULLIF(TRIM(i.item_category), ''), '(not set)'), 1)[OFFSET(0)].value AS c,
    APPROX_TOP_COUNT(IFNULL(NULLIF(TRIM(i.item_category2), ''), '(not set)'), 1)[OFFSET(0)].value AS c2,
    APPROX_TOP_COUNT(NULLIF(TRIM(i.item_brand), ''), 1)[OFFSET(0)].value AS b,
    APPROX_TOP_COUNT({fc}, 1)[OFFSET(0)].value AS k
  FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
  WHERE event_name IN ('view_item', 'purchase')
    AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
    AND i.item_name IS NOT NULL AND TRIM(i.item_name) != ''
  GROUP BY nm
),
va AS (SELECT pd, nm, COUNT(DISTINCT sid) AS s FROM v GROUP BY pd, nm),
pa AS (SELECT pd, nm, COUNT(DISTINCT tid) AS t, SUM(q) AS ip, ROUND(SUM(rev), 2) AS r
       FROM p GROUP BY pd, nm)
SELECT
  COALESCE(va.pd, pa.pd) AS pd, COALESCE(va.nm, pa.nm) AS nm,
  IFNULL(va.s, 0) AS s, IFNULL(pa.t, 0) AS t, IFNULL(pa.ip, 0) AS ip, IFNULL(pa.r, 0) AS r,
  attrs.id, attrs.c, attrs.c2, attrs.b, attrs.k
FROM va FULL OUTER JOIN pa USING (pd, nm)
LEFT JOIN attrs ON attrs.nm = COALESCE(va.nm, pa.nm)
"""


def sql_focus_daily_breakdown(start_sfx, end_sfx):
    """Daily purchase revenue by range (item_brand, fallback first word) and by
    item_category2 within each focus key - last 28 days, for the stacked charts."""
    fc = focus_case()
    return f"""
SELECT
  FORMAT_DATE('%Y-%m-%d', PARSE_DATE('%Y%m%d', event_date)) AS d,
  {fc} AS k,
  IFNULL(NULLIF(TRIM(i.item_brand), ''), SPLIT(TRIM(i.item_name), ' ')[SAFE_OFFSET(0)]) AS rg,
  IFNULL(NULLIF(TRIM(i.item_category2), ''), '(not set)') AS c2,
  ROUND(SUM(IFNULL(i.item_revenue, 0)), 2) AS r
FROM `{PROJECT}.{DATASET}.events_*`, UNNEST(items) AS i
WHERE event_name = 'purchase'
  AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
  AND {fc} IS NOT NULL
GROUP BY d, k, rg, c2
HAVING r > 0
ORDER BY d
"""


def sql_channels(start_sfx, end_sfx):
    """Daily sessions / transactions / revenue by session default channel group - last 14 days."""
    return f"""
WITH s AS (
  SELECT PARSE_DATE('%Y%m%d', event_date) AS d,
    IFNULL(session_traffic_source_last_click.cross_channel_campaign.default_channel_group, 'Unassigned') AS ch,
    CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING)) AS sid
  FROM `{PROJECT}.{DATASET}.events_*`
  WHERE event_name = 'session_start' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
p AS (
  SELECT PARSE_DATE('%Y%m%d', event_date) AS d,
    IFNULL(session_traffic_source_last_click.cross_channel_campaign.default_channel_group, 'Unassigned') AS ch,
    ecommerce.transaction_id AS tid, IFNULL(ecommerce.purchase_revenue, 0) AS rev
  FROM `{PROJECT}.{DATASET}.events_*`
  WHERE event_name = 'purchase' AND _TABLE_SUFFIX BETWEEN '{start_sfx}' AND '{end_sfx}'
),
sa AS (SELECT d, ch, COUNT(DISTINCT sid) AS s FROM s GROUP BY d, ch),
pa AS (SELECT d, ch, COUNT(DISTINCT tid) AS t, ROUND(SUM(rev), 2) AS r FROM p GROUP BY d, ch)
SELECT FORMAT_DATE('%Y-%m-%d', COALESCE(sa.d, pa.d)) AS d, COALESCE(sa.ch, pa.ch) AS ch,
  IFNULL(sa.s, 0) AS s, IFNULL(pa.t, 0) AS t, IFNULL(pa.r, 0) AS r
FROM sa FULL OUTER JOIN pa USING (d, ch)
ORDER BY d, ch
"""


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=HISTORY_START, help="history start date YYYY-MM-DD")
    args = ap.parse_args()

    today = dt.date.today()
    this_week = week_start(today)
    cur_start = this_week - dt.timedelta(days=7)     # last full week Mon
    cur_end = this_week - dt.timedelta(days=1)       # last full week Sun
    prev_start = cur_start - dt.timedelta(days=7)
    hist_start = dt.date.fromisoformat(args.start)
    bd_start = cur_end - dt.timedelta(days=27)       # 28-day breakdown window
    ch_start = cur_end - dt.timedelta(days=13)       # 14-day channel window

    print(f"Last full week: {cur_start} -> {cur_end} (prev week from {prev_start})")

    client = get_client()
    os.makedirs(OUT_DIR, exist_ok=True)

    def save(name, obj):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"), default=str)
        print(f"  wrote {name} ({os.path.getsize(path)/1024:.0f} KB)")

    # 1. weekly by category
    rows = run(client, sql_weekly("item_category", suffix(hist_start), suffix(cur_end)), "weekly by category")
    save("weekly_category.json", rows)

    # 2. weekly by sub-category (keep top 40 by revenue, bucket the rest)
    rows = run(client, sql_weekly("item_category2", suffix(hist_start), suffix(cur_end)), "weekly by sub-category")
    totals = defaultdict(float)
    for r in rows:
        totals[r["c"]] += r["r"] or 0
    keep = {c for c, _ in sorted(totals.items(), key=lambda x: -x[1])[:40]}
    agg = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows:
        c = r["c"] if r["c"] in keep else "Other"
        a = agg[(r["w"], c)]
        a[0] += r["s"]; a[1] += r["iv"]; a[2] += r["t"]; a[3] += r["ip"]; a[4] += r["r"] or 0
    out = [{"w": w, "c": c, "s": a[0], "iv": a[1], "t": a[2], "ip": a[3], "r": round(a[4], 2)}
           for (w, c), a in sorted(agg.items())]
    save("weekly_subcategory.json", out)

    # 3. monthly sessions by category
    rows = run(client, sql_monthly_sessions(suffix(hist_start), suffix(cur_end)), "monthly sessions")
    save("monthly_category.json", rows)

    # 4. daily focus history
    rows = run(client, sql_daily_focus(suffix(hist_start), suffix(cur_end)), "daily focus history")
    save("daily_focus.json", rows)

    # 5. item-level two weeks -> pivot
    rows = run(client, sql_items_two_weeks(suffix(prev_start), suffix(cur_end), cur_start.isoformat()), "item level (2 weeks)")
    items = {}
    for r in rows:
        it = items.setdefault(r["nm"], {
            "n": r["nm"], "id": r.get("id"), "c": r.get("c"), "c2": r.get("c2"),
            "b": r.get("b"), "k": r.get("k"),
            "s": 0, "t": 0, "ip": 0, "r": 0, "s_p": 0, "t_p": 0, "ip_p": 0, "r_p": 0,
        })
        sfx_key = "" if r["pd"] == "cur" else "_p"
        it["s" + sfx_key] = r["s"]; it["t" + sfx_key] = r["t"]
        it["ip" + sfx_key] = r["ip"]; it["r" + sfx_key] = round(r["r"] or 0, 2)
        # attrs may only be present on one of the rows
        for f in ("id", "c", "c2", "b", "k"):
            if not it.get(f) and r.get(f):
                it[f] = r[f]
    allitems = list(items.values())
    # items WoW table: top 1500 by current sessions (plus anything that sold)
    wow = sorted(allitems, key=lambda x: (-(x["s"]), -(x["r"])))
    wow = [x for x in wow if x["s"] > 0 or x["r"] > 0 or x["r_p"] > 0][:1500]
    save("items_wow.json", wow)

    # 6. focus daily breakdown (range + item type, 28 days)
    rows = run(client, sql_focus_daily_breakdown(suffix(bd_start), suffix(cur_end)), "focus 28d breakdown")
    save("focus_breakdown.json", rows)

    # 7. channels 14 days
    rows = run(client, sql_channels(suffix(ch_start), suffix(cur_end)), "channels 14d")
    save("channels.json", rows)

    # 8. meta
    save("meta.json", {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hist_start": hist_start.isoformat(),
        "cur_start": cur_start.isoformat(), "cur_end": cur_end.isoformat(),
        "prev_start": prev_start.isoformat(),
        "focus": {k: v["label"] for k, v in FOCUS.items()},
    })

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
