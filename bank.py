"""
Each bot's pot (bankroll), savings and promotions.

Rules:
  * A bot starts with its "dollars" from BOTS (e.g. $100) and trades its WHOLE pot.
  * Wins and losses go back into the pot, so profits get reinvested.
  * The pot is capped at the bot's limit. Anything above the limit is moved to
    savings and is never traded again.
  * Every time a bot sets aside half its limit (a "set-aside"), it counts.
    3 set-asides within any 7 days = promotion to the next limit.

Pure bookkeeping: nothing here talks to Alpaca.
"""

from datetime import datetime, timedelta

# limit, size of one set-aside, how many set-asides in 7 days to get promoted
TIERS = [
    {"limit": 1000,  "chunk": 500},
    {"limit": 5000,  "chunk": 2500},
    {"limit": 10000, "chunk": None},     # top tier, no further promotion
]
SET_ASIDES_NEEDED = 3
WINDOW_DAYS = 7
MIN_TRADE = 5.00          # below this the bot is benched (nothing left to trade)


def _acct(memory, bot):
    bank = memory.setdefault("bank", {})
    return bank.setdefault(bot["name"], {
        "pot": float(bot["dollars"]), "tier": 0, "savings": 0.0, "deposits": []})


def trade_size(memory, bot):
    """Dollars this bot may put into its next trade (its whole pot)."""
    return round(_acct(memory, bot)["pot"], 2)


def slot_size(memory, bot, committed=0.0):
    """Dollars for ONE new position: the pot split into max_positions equal slots,
    never more than what isn't already in other open positions."""
    pot = _acct(memory, bot)["pot"]
    slots = max(1, int(bot.get("max_positions", 1)))
    return round(max(0.0, min(pot / slots, pot - committed)), 2)


def can_trade(memory, bot):
    return trade_size(memory, bot) >= MIN_TRADE


def _week_saved(acct, now):
    since = now - timedelta(days=WINDOW_DAYS)
    return round(sum(amt for t, amt, tier in acct["deposits"]
                     if tier == acct["tier"] and datetime.fromisoformat(t) >= since), 2)


def apply_result(memory, bot, pl, now=None):
    """Settle a finished trade. Returns a list of events for the chronicle:
    ("saved", amount), ("promoted", new_limit), ("benched", pot)."""
    now = now or datetime.now()
    a = _acct(memory, bot)
    events = []
    a["pot"] = round(a["pot"] + pl, 2)
    limit = TIERS[a["tier"]]["limit"]
    if a["pot"] > limit:
        extra = round(a["pot"] - limit, 2)
        a["pot"] = float(limit)
        a["savings"] = round(a["savings"] + extra, 2)
        a["deposits"].append([now.isoformat(timespec="seconds"), extra, a["tier"]])
        events.append(("saved", extra))
    chunk = TIERS[a["tier"]]["chunk"]
    if chunk and _week_saved(a, now) >= chunk * SET_ASIDES_NEEDED:
        a["tier"] += 1
        events.append(("promoted", TIERS[a["tier"]]["limit"]))
    # keep 30 days of deposit history
    cutoff = now - timedelta(days=30)
    a["deposits"] = [d for d in a["deposits"] if datetime.fromisoformat(d[0]) >= cutoff]
    if a["pot"] < MIN_TRADE:
        events.append(("benched", a["pot"]))
    return events


def status(memory, bot, now=None):
    now = now or datetime.now()
    a = _acct(memory, bot)
    t = TIERS[a["tier"]]
    chunk = t["chunk"]
    saved = _week_saved(a, now)
    return {
        "pot": round(a["pot"], 2),
        "limit": t["limit"],
        "savings": round(a["savings"], 2),
        "tier": a["tier"] + 1,
        "top_tier": chunk is None,
        "chunk": chunk,
        "week_saved": saved,
        "set_asides": min(SET_ASIDES_NEEDED, int(saved // chunk)) if chunk else 0,
        "needed": SET_ASIDES_NEEDED,
        "next_limit": TIERS[a["tier"] + 1]["limit"] if chunk else None,
        "benched": a["pot"] < MIN_TRADE,
    }
