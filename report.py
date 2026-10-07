"""
The Day's Ledger: an end-of-day report on how the heroes did, shown in the town.

Every buy and sell goes into a trade journal (in bot_state.json). From it, Goldmire builds:
  * "today so far", refreshed every 5 minutes (in status.json, for the town page), and
  * a saved report for each day, made at 4:05 PM New York time (3:05 PM Central),
    in world/reports/YYYY-MM-DD.json, so the town can page back through past days.
Days follow New York time, like the stock market. Crypto trades are counted on the
New York day they happened.
"""

import json
import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 - no time zone database: fall back to a fixed offset
    NY = None

import game

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(HERE, "world", "reports")
JOURNAL_DAYS = 45
CLOSE_HOUR, CLOSE_MINUTE = 16, 5      # New York time


def ny(dt=None):
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.astimezone()          # a local time without a zone: treat it as this PC's time
    return dt.astimezone(NY) if NY else dt.astimezone(timezone(timedelta(hours=-4)))


def day_of(iso):
    try:
        return ny(datetime.fromisoformat(iso)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# The trade journal
# ---------------------------------------------------------------------------
def note(memory, **entry):
    """Adds one line to the trade journal: side = buy / sell / gone."""
    j = memory.setdefault("journal", [])
    entry["t"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    memory.setdefault("journal_started", entry["t"])
    j.append(entry)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=JOURNAL_DAYS)).isoformat()
    memory["journal"] = [e for e in j if e.get("t", "") >= cutoff]


def why_kind(reason):
    r = (reason or "").lower()
    for key, label in (("bad news", "bad news"), ("good-news run", "good-news run ended"), ("trailing", "let it build"), ("stop-loss", "stop-loss"),
                       ("take-profit", "take-profit"), ("says sell", "its style said sell")):
        if key in r:
            return label
    return "sold"


# ---------------------------------------------------------------------------
# Building a report
# ---------------------------------------------------------------------------
def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build(memory, bots, positions=None, account=None, day=None, norm=lambda s: s.replace("/", "").upper()):
    """The report for one New York day. positions: {NORMSYMBOL: alpaca position} (only for today)."""
    day = day or ny().strftime("%Y-%m-%d")
    hero = {b["name"]: game.hero_of(b)[0] for b in bots}
    entries = [e for e in memory.get("journal", []) if day_of(e.get("t")) == day]
    closed, opened, gone = [], [], []
    for e in entries:
        row = {"time": e["t"], "bot": e.get("bot"), "hero": hero.get(e.get("bot"), e.get("bot")), "symbol": e.get("symbol")}
        if e.get("side") == "sell":
            pl = round(_f(e.get("pl")), 2)
            closed.append({**row, "pl": pl, "paid": e.get("paid"), "sold": e.get("price"), "cost": e.get("cost"),
                           "why": why_kind(e.get("reason")), "reason": e.get("reason", "")})
        elif e.get("side") == "buy":
            opened.append({**row, "dollars": e.get("dollars")})
        elif e.get("side") == "gone":
            gone.append({**row, "note": e.get("note", "")})
    holding = []
    if positions is not None:
        for b in bots:
            for sym, h in memory.get("held", {}).get(b["name"], {}).items():
                p = positions.get(norm(sym))
                if not p:
                    continue
                holding.append({"bot": b["name"], "hero": hero[b["name"]], "symbol": sym,
                                "paid": round(_f(getattr(p, "avg_entry_price", 0)), 4), "now": round(_f(getattr(p, "current_price", 0)), 4),
                                "pl": round(_f(getattr(p, "unrealized_pl", 0)), 2),
                                "today": round(_f(getattr(p, "unrealized_intraday_pl", 0)), 2),
                                "value": round(_f(getattr(p, "market_value", 0)), 2), "since": h.get("opened", "")})
    wins = [c for c in closed if c["pl"] > 0]
    closed_pl = round(sum(c["pl"] for c in closed), 2)
    per = {}
    for c in closed:
        d = per.setdefault(c["bot"], {"hero": c["hero"], "closed_pl": 0.0, "trades": 0, "wins": 0})
        d["closed_pl"] = round(d["closed_pl"] + c["pl"], 2)
        d["trades"] += 1
        d["wins"] += c["pl"] > 0
    for h in holding:
        d = per.setdefault(h["bot"], {"hero": h["hero"], "closed_pl": 0.0, "trades": 0, "wins": 0})
        d["open_today"] = round(d.get("open_today", 0.0) + h["today"], 2)
        d["holding"] = d.get("holding", 0) + 1
    rep = {
        "day": day, "made": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "closed": sorted(closed, key=lambda c: c["time"]), "bought": len(opened), "gone": gone,
        "holding": sorted(holding, key=lambda h: (h["hero"], h["symbol"])), "has_holdings": positions is not None,
        "closed_pl": closed_pl, "wins": len(wins), "losses": len(closed) - len(wins),
        "open_pl": round(sum(h["pl"] for h in holding), 2), "open_today": round(sum(h["today"] for h in holding), 2),
        "heroes": per,
    }
    if account is not None:
        eq, last = _f(getattr(account, "equity", 0)), _f(getattr(account, "last_equity", 0))
        rep["account"] = {"equity": round(eq, 2), "change": round(eq - last, 2) if last else None}
    started = memory.get("journal_started") or (memory.setdefault("journal_started", rep["made"]) if day == ny().strftime("%Y-%m-%d") else "")
    if started and day_of(started) == day:
        rep["partial_from"] = started          # the journal began partway through this day
    rep["headline"] = headline(rep)
    return rep


def _money(v):
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def headline(rep):
    n, pl = len(rep["closed"]), rep["closed_pl"]
    if not n and not rep["bought"]:
        parts = ["A quiet day: no trades."]
    else:
        mood = "A good day" if pl > 0.5 else "A rough day" if pl < -0.5 else "An even day"
        parts = [f"{mood}: {_money(pl)} on {n} closed trade{'s' if n != 1 else ''} ({rep['wins']} won, {rep['losses']} lost)"
                 + (f", and {rep['bought']} new buy{'s' if rep['bought'] != 1 else ''}." if rep["bought"] else ".")]
        if n:
            best = max(rep["closed"], key=lambda c: c["pl"])
            if best["pl"] > 0 and best["pl"] >= 0.5 * max(pl, 0.01) and n > 1:
                parts.append(f"{best['hero']}'s {best['symbol']} trade ({_money(best['pl'])}) led the way.")
            worst = min(rep["closed"], key=lambda c: c["pl"])
            if worst["pl"] < 0 and n > 1:
                parts.append(f"Worst: {worst['symbol']} ({_money(worst['pl'])}, {worst['why']}).")
    if rep.get("holding"):
        parts.append(f"Still holding {len(rep['holding'])}, which moved {_money(rep['open_today'])} today.")
    if rep.get("gone"):
        parts.append(f"{len(rep['gone'])} position{'s' if len(rep['gone']) != 1 else ''} closed outside Goldmire.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Saving a day
# ---------------------------------------------------------------------------
def _index():
    try:
        with open(os.path.join(REPORT_DIR, "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save(rep):
    os.makedirs(REPORT_DIR, exist_ok=True)
    tmp = os.path.join(REPORT_DIR, rep["day"] + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    os.replace(tmp, os.path.join(REPORT_DIR, rep["day"] + ".json"))
    idx = [d for d in _index() if d.get("day") != rep["day"]]
    idx.append({"day": rep["day"], "headline": rep["headline"], "closed_pl": rep["closed_pl"], "trades": len(rep["closed"])})
    idx.sort(key=lambda d: d["day"], reverse=True)
    with open(os.path.join(REPORT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=1)


def maybe_archive(memory, bots, positions, account, log=print, now=None):
    """Saves today's report once it's past 4:05 PM in New York, and any earlier day in the
    journal that never got one (say the PC was off at the close). Returns the days saved."""
    now = ny(now)
    today = now.strftime("%Y-%m-%d")
    done = set(memory.setdefault("reports_done", []))
    saved = []
    past_days = sorted({day_of(e.get("t")) for e in memory.get("journal", [])} - {today, ""})
    for day in past_days:
        if day not in done:
            rep = build(memory, bots, None, None, day)       # holdings unknown for a past day
            rep["late"] = True
            save(rep)
            saved.append(day)
    if (now.hour, now.minute) >= (CLOSE_HOUR, CLOSE_MINUTE):
        # after the close, today's saved report is kept current until midnight (crypto keeps trading)
        save(build(memory, bots, positions, account, today))
        if today not in done:
            saved.append(today)
    if saved:
        memory["reports_done"] = sorted(done | set(saved))[-JOURNAL_DAYS:]
        for d in saved:
            log(f"Day's Ledger: saved the report for {d}.")
    return saved


def index_days():
    return [d["day"] for d in _index()]
