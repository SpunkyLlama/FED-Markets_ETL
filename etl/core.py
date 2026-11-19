"""Pure logic: CSV I/O, transforms, reconciliation. No network, so it is unit-testable."""
import csv
from dataclasses import dataclass, field

COLS = ["obs_date", "freq", "metric", "value", "unit", "quality", "source", "edition", "note"]


@dataclass
class Obs:
    obs_date: str      # YYYY-MM-DD (monthly = first of reference month)
    freq: str
    metric: str
    value: float
    unit: str
    source: str
    note: str = ""


@dataclass
class Report:
    added: list = field(default_factory=list)
    upgraded: list = field(default_factory=list)    # unverified/estimate -> verified, same value
    revised: list = field(default_factory=list)     # monthly value changed (normal revision)
    corrected: list = field(default_factory=list)   # stored unverified daily value was wrong
    conflicts: list = field(default_factory=list)   # verified daily value disagrees; NOT overwritten

    def summary(self):
        return {k: len(v) for k, v in vars(self).items()}


# ---------- formatting / comparison ----------
def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def same(a, b):
    a, b = float(a), float(b)
    return abs(a - b) <= max(0.005, 1e-5 * abs(a))


# ---------- CSV ----------
def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows):
    rows = sorted(rows, key=lambda r: (r["metric"], r["obs_date"]))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ---------- transforms (monthly index -> yoy / mom / diff) ----------
def _shift_month(date_str, months):
    y, m = int(date_str[:4]), int(date_str[5:7])
    t = y * 12 + (m - 1) + months
    return "%04d-%02d-01" % (t // 12, t % 12 + 1)


def transform_monthly(points, kind):
    """points: {YYYY-MM-01: float}. Returns {date: float} for dates where the base exists.

    A missing base month (e.g. Oct 2025, no BLS collection during the shutdown) yields no
    observation rather than a guess.
    """
    out = {}
    for d, v in points.items():
        if kind == "yoy":
            base = points.get(_shift_month(d, -12))
            if base:
                out[d] = round((v / base - 1) * 100, 1)
        elif kind == "mom":
            base = points.get(_shift_month(d, -1))
            if base:
                out[d] = round((v / base - 1) * 100, 1)
        elif kind == "diff":
            base = points.get(_shift_month(d, -1))
            if base is not None:
                out[d] = round(v - base, 0)
        else:
            out[d] = v
    return out


def change_points(daily):
    """daily: {date: float}. Returns {date: value} only where the value differs from the prior day."""
    out, prev = {}, None
    for d in sorted(daily):
        if prev is None or not same(daily[d], prev):
            out[d] = daily[d]
        prev = daily[d]
    return out


# ---------- reconciliation ----------
def _join(*parts):
    return "; ".join(p for p in parts if p)


def reconcile(rows, observations, edition):
    """Merge new observations into rows (list of dict). Returns (rows, Report).

    Rules (from the market-briefing skill):
      - new (metric, date)            -> append as verified
      - same value, not verified      -> upgrade to verified, keep everything else
      - same value, already verified  -> no-op
      - different value, monthly      -> revision: replace value, old value goes in note
      - different value, daily/event, stored row unverified/estimate
                                      -> correction: replace value, old value goes in note
      - different value, daily/event, stored row verified
                                      -> conflict: leave the row, report it for a human
                                         (feeds differ: futures vs spot, H.10 vs intraday)
      - rows are never deleted
    """
    rep = Report()
    index = {(r["metric"], r["obs_date"]): r for r in rows}
    for o in observations:
        key = (o.metric, o.obs_date)
        r = index.get(key)
        if r is None:
            new = dict(obs_date=o.obs_date, freq=o.freq, metric=o.metric, value=fmt(o.value),
                       unit=o.unit, quality="verified", source=o.source, edition=edition, note=o.note)
            rows.append(new)
            index[key] = new
            rep.added.append(key)
            continue
        if same(r["value"], o.value):
            if r["quality"] != "verified":
                was = r["quality"]
                r.update(quality="verified", source=o.source,
                         note=_join(r["note"], "was %s; confirmed %s" % (was, edition)))
                rep.upgraded.append(key)
            continue
        old = r["value"]
        monthly = r["freq"] == "M"
        if not monthly and r["quality"] == "verified":
            rep.conflicts.append((key, old, fmt(o.value), o.source))
            continue
        verb = "revised" if monthly else "corrected"
        r.update(value=fmt(o.value), quality="verified", source=o.source,
                 note=_join(r["note"], "%s from %s on %s" % (verb, old, edition)))
        (rep.revised if monthly else rep.corrected).append((key, old, fmt(o.value)))
    return rows, rep
