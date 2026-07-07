"""Generate realistic sample JSON so index.html can be previewed without BigQuery.
Overwritten by refresh_data.py on first real run.  Usage: py make_sample_data.py"""

import datetime as dt
import json
import math
import os
import random

random.seed(42)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

CATS = {
    "DINING AND LIVING": 36000, "UPHOLSTERY": 23000, "GARDEN": 13000,
    "BEDROOM": 12000, "ACCESSORIES": 6000, "BEDS": 4500, "OFFICE": 1500,
    "RUGS": 950, "BEDS AND BEDROOM": 800, "WARRANTIES": 40, "SUNDRIES": 12,
}
SUBCATS = {
    "Dining Chairs": 15000, "Sofas": 14000, "Chairs": 13000, "Dining Tables": 12000,
    "Corner Sofas": 10800, "Coffee Tables": 8000, "Bedside Tables": 6400,
    "Chest of Drawers": 6500, "Counter Stools": 5100, "Bedframes": 4600,
    "Garden Corner Sets": 3000, "Sideboards": 5500, "Mattresses": 4200,
    "Garden Dining Sets": 2100, "Wardrobes": 3900,
}
FOCUS = {"garden": "Garden", "sofas": "Sofas", "dining_tables": "Dining Tables",
         "dining_chairs": "Dining Chairs", "mattresses": "Mattresses"}
CHANNELS = ["Paid Search", "Organic Search", "Cross-network", "Direct", "Email",
            "Paid Shopping", "Organic Shopping", "Paid Social", "Affiliates", "Referral", "Unassigned"]
RANGES = ["Fierza", "Castello", "Branca", "Lisbon", "Boracay", "Reef", "Lux", "Tonga", "Bellano", "Valbrona"]
WORDS = ["Houston", "Monaco", "Runa", "Jasper", "Lexa", "Rivington", "Mirna", "Koda", "Otto",
         "Tansley", "Capella", "Soma", "Cresta", "Harbour", "Arles", "Aldo", "Boone", "Hoxton"]
TYPES = {
    "garden": ["Garden Corner Sets", "Garden Hanging Chairs", "Garden Lounge Sets", "Garden Dining Sets",
               "Garden Sun Loungers", "Garden Sofa Sets", "Garden Parasols"],
    "sofas": ["Sofas"], "dining_tables": ["Dining Tables"],
    "dining_chairs": ["Dining Chairs"], "mattresses": ["Mattresses"],
}

today = dt.date.today()
this_mon = today - dt.timedelta(days=today.weekday())
cur_start, cur_end = this_mon - dt.timedelta(days=7), this_mon - dt.timedelta(days=1)
prev_start = cur_start - dt.timedelta(days=7)
hist_start = dt.date(2023, 4, 3)


def season(d, amp=0.35):
    return 1 + amp * math.sin((d.timetuple().tm_yday / 365) * 2 * math.pi + 1.2)


def save(name, obj):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    print("wrote", name)


def weekly(cats):
    rows, w = [], hist_start
    while w <= cur_start:
        for c, base in cats.items():
            s = max(1, int(base * season(w) * random.uniform(0.8, 1.2)))
            cvr = random.uniform(0.001, 0.008)
            t = max(0, int(s * cvr))
            ip = int(t * random.uniform(1.1, 2.5))
            aov = random.uniform(300, 1200)
            rows.append({"w": w.isoformat(), "c": c, "s": s, "iv": int(s * 0.15),
                         "t": t, "ip": ip, "r": round(t * aov, 2)})
        w += dt.timedelta(days=7)
    return rows


save("weekly_category.json", weekly(CATS))
save("weekly_subcategory.json", weekly(SUBCATS))

save("monthly_category.json", [
    {"m": m, "c": c, "s": int(b * 4.3 * 3 * season(dt.date(2024, m, 15)) * random.uniform(0.9, 1.1))}
    for m in range(1, 13) for c, b in CATS.items()
])

rows, d = [], hist_start
while d <= cur_end:
    for k, lbl in FOCUS.items():
        base = {"garden": 1900, "sofas": 2000, "dining_tables": 1700,
                "dining_chairs": 2200, "mattresses": 900}[k]
        amp = 0.8 if k == "garden" else 0.2
        s = max(5, int(base * season(d, amp) * random.uniform(0.7, 1.3)))
        t = max(0, int(s * random.uniform(0.001, 0.006)))
        rows.append({"d": d.isoformat(), "k": k, "s": s, "t": t,
                     "ip": int(t * random.uniform(1, 2.4)),
                     "r": round(t * random.uniform(350, 1400), 2)})
    d += dt.timedelta(days=1)
save("daily_focus.json", rows)

items = []
kw = list(FOCUS) + [None] * 3
for i in range(600):
    k = random.choice(kw)
    c2 = random.choice(TYPES[k]) if k else random.choice(list(SUBCATS))
    c = "GARDEN" if k == "garden" else random.choice(["DINING AND LIVING", "UPHOLSTERY", "BEDROOM"])
    nm = f"{random.choice(WORDS)} {c2[:-1] if c2.endswith('s') else c2} {random.choice(['', '180cm', '3 Seater', 'Large', 'Set'])}".strip()
    s = int(random.paretovariate(1.2) * 120)
    t = max(0, int(s * random.uniform(0, 0.004)))
    r = round(t * random.uniform(250, 1500), 2)
    items.append({"n": f"{nm} {i}", "id": f"SKU{i:05d}", "c": c, "c2": c2,
                  "b": random.choice(RANGES + [None]), "k": k,
                  "s": s, "t": t, "ip": int(t * random.uniform(1, 3)), "r": r,
                  "s_p": max(0, int(s * random.uniform(0.5, 1.5))),
                  "t_p": max(0, t + random.randint(-2, 2)),
                  "ip_p": max(0, int(t * random.uniform(0.8, 3))),
                  "r_p": round(r * random.uniform(0.4, 1.8), 2)})
save("items_wow.json", items)

rows = []
d = cur_end - dt.timedelta(days=27)
while d <= cur_end:
    for k in FOCUS:
        for _ in range(random.randint(2, 6)):
            rows.append({"d": d.isoformat(), "k": k, "rg": random.choice(RANGES),
                         "c2": random.choice(TYPES[k]), "r": round(random.uniform(200, 4000), 2)})
    d += dt.timedelta(days=1)
save("focus_breakdown.json", rows)

rows = []
d = cur_end - dt.timedelta(days=13)
while d <= cur_end:
    for ch in CHANNELS:
        base = {"Paid Search": 9000, "Organic Search": 15000, "Cross-network": 4000, "Direct": 8000,
                "Email": 1500, "Paid Shopping": 3200, "Organic Shopping": 1000, "Paid Social": 2500,
                "Affiliates": 700, "Referral": 500, "Unassigned": 850}[ch]
        s = int(base * random.uniform(0.8, 1.2))
        t = max(0, int(s * random.uniform(0.002, 0.012)))
        rows.append({"d": d.isoformat(), "ch": ch, "s": s, "t": t,
                     "r": round(t * random.uniform(400, 900), 2)})
    d += dt.timedelta(days=1)
save("channels.json", rows)

save("meta.json", {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M") + " (SAMPLE DATA)",
                   "hist_start": hist_start.isoformat(),
                   "cur_start": cur_start.isoformat(), "cur_end": cur_end.isoformat(),
                   "prev_start": prev_start.isoformat(), "focus": FOCUS})
print("Sample data done.")
