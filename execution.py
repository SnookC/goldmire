"""
Ysolde the Execution Manager: every order gets an ID, nothing is sent twice, and Goldmire's
records are checked against Alpaca's.

  * ORDER IDS   every buy and every protective stop carries its own client order ID
                ("gm-<hero>-<symbol>-<side>-<random>"), so each order can be traced to the
                hero that made it.
  * NO RESENDS  if sending an order fails (a timeout, a dropped connection), Ysolde first asks
                Alpaca whether that ID arrived. If it did, the order counts as sent and is NOT
                sent again.
  * RECONCILE   at start-up and once after each market close she compares:
                  - positions at Alpaca that no hero owns (opened by hand, or a record lost)
                  - the whole account's change today vs. the heroes' own results today;
                    any gap is "unexplained" and goes in the log (and in bot_state.json)
                She reports; she doesn't buy or sell anything because of it.
"""
import uuid
from datetime import datetime

UNEXPLAINED_WARN = 25.0        # dollars: a gap bigger than this is logged as a warning


def new_id(bot_name, symbol, side):
    clean = "".join(ch for ch in symbol.upper() if ch.isalnum())[:10]
    who = "".join(ch for ch in bot_name if ch.isalnum() or ch == "-")[:16]
    return f"gm-{who}-{clean}-{side}-{uuid.uuid4().hex[:10]}"


def find(trading, client_id):
    """The order Alpaca has under this client ID, or None."""
    try:
        return trading.get_order_by_client_id(client_id)
    except Exception:  # noqa: BLE001 - "not found" comes back as an error
        return None


def submit(trading, request, client_id, log=print, who=""):
    """Send one order. If sending fails, check whether Alpaca got it before giving up:
    returns the order if Alpaca has it, otherwise raises the original error."""
    try:
        return trading.submit_order(request)
    except Exception as e:
        got = find(trading, client_id)
        if got is not None:
            log(f"{who} Ysolde: sending {client_id} reported an error ({e}), but Alpaca has it: not sending again")
            return got
        raise


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def reconcile(trading, memory, positions, today, day_of, norm, market_open=False, log=print):
    """Compare Goldmire's records with Alpaca's. Returns the findings (also kept in memory).

    Today's hero result = today's move in what they still hold, plus each sale today measured
    from the stock's value at the last check (so a stock bought last week and sold today counts
    only today's part, the same way Alpaca's account change does)."""
    ours = {norm(s) for h in memory.get("held", {}).values() for s in h}
    orphans = sorted(s for s in positions if s not in ours)
    try:
        acct = trading.get_account()
        account_change = round(float(acct.equity) - float(acct.last_equity), 2)
    except Exception as e:  # noqa: BLE001
        log(f"Ysolde: couldn't read the account for the daily check ({e})")
        account_change = None
    snap = memory.get("close_values", {})                       # {symbol: value at the last check}
    snap_day = memory.get("close_values_day", "")
    closed = 0.0
    for e in memory.get("journal", []):
        if e.get("side") != "sell" or day_of(e.get("t")) != today:
            continue
        pl, sym = _f(e.get("pl")), norm(e.get("symbol", ""))
        if snap_day and snap_day < today and sym in snap and e.get("cost") is not None:
            pl -= snap[sym] - _f(e.get("cost"))                 # the part earned before today
        closed += pl
    open_today = sum(_f(getattr(p, "unrealized_intraday_pl", 0)) for s, p in positions.items() if s in ours)
    heroes = round(closed + open_today, 2)
    orphan_change = round(sum(_f(getattr(positions[s], "unrealized_intraday_pl", 0)) for s in orphans), 2)
    unexplained = None if account_change is None else round(account_change - heroes - orphan_change, 2)
    found = {"day": today, "checked": datetime.now().isoformat(timespec="seconds"), "account_change": account_change,
             "heroes": heroes, "heroes_closed": round(closed, 2), "heroes_open": round(open_today, 2),
             "orphans": orphans, "orphans_change": orphan_change, "unexplained": unexplained}
    memory.setdefault("reconcile", {})[today] = found
    for d in sorted(memory["reconcile"])[:-30]:                 # keep a month
        memory["reconcile"].pop(d, None)
    if snap_day != today and not market_open:                   # closing values, to measure tomorrow's sales from
        memory["close_values"] = {s: round(_f(getattr(p, "market_value", 0)), 2) for s, p in positions.items()}
        memory["close_values_day"] = today
    line = (f"Ysolde: daily check {today}: account ${account_change:+,.2f}" if account_change is not None
            else f"Ysolde: daily check {today}: account ?")
    line += f", heroes ${heroes:+,.2f} (sales ${closed:+,.2f}, still held ${open_today:+,.2f})"
    if orphans:
        line += f", not owned by any hero: {', '.join(orphans)} (${orphan_change:+,.2f})"
    if unexplained is not None:
        line += f", unexplained ${unexplained:+,.2f}"
    log(line)
    if unexplained is not None and abs(unexplained) > UNEXPLAINED_WARN:
        log(f"Ysolde: WARNING ${unexplained:+,.2f} of today's account change isn't explained by the heroes' trades. "
            "Check Alpaca's activity page (fees, a manual trade, or a correction).")
    return found
