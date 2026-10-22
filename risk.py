"""
Pip the Risk Manager: looks at the whole account before any hero buys.

Each hero already has its own pot, slots and stop-losses. Pip adds the account-wide rules
you set (Oct 2026), enforced here in code, before every buy:

  * DAILY STOP     if the heroes together are down DAILY_STOP_DOLLARS or more today
                   (finished trades + the day's change in what they still hold),
                   no hero buys anything else until the next trading day.
                   Selling, stop orders and bad-news exits keep working.
  * BIGGEST BET    no more than MAX_STOCK_SHARE of a hero's pot goes into one stock:
                   a bigger buy is shrunk to fit.
  * INDUSTRY LIMIT no more than MAX_INDUSTRY_SHARE of the working heroes' combined money
                   sits in one industry (everything the heroes hold counts, benched or not):
                   a buy is shrunk to fit, or skipped.

Industries come from Nasdaq's free stock screener list (every NYSE/Nasdaq/AMEX stock with
its sector, downloaded once a week), with the SEC's company records as a backup, all saved
in industries.json. Funds (ETFs) have no SIC code, so common
ones are listed below. A stock whose industry can't be found counts as its own industry
(so it never hides inside another one) and the log says so.

Pip never sells anything and never changes these limits by itself.
"""
import json
import os
import time
import urllib.request

DAILY_STOP_DOLLARS = 500.0
MAX_STOCK_SHARE = 0.20
MAX_INDUSTRY_SHARE = 0.50

HERE = os.path.dirname(os.path.abspath(__file__))
INDUSTRY_FILE = os.path.join(HERE, "industries.json")
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_HEADERS = {"User-Agent": "Goldmire personal paper-trading tool (github.com/SnookC/goldmire)", "Accept": "application/json"}
TICKER_MAP_DAYS = 7
NASDAQ_LIST = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
NASDAQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Goldmire", "Accept": "application/json"}
NASDAQ_SECTORS = {"Technology": "Technology", "Energy": "Energy", "Health Care": "Healthcare", "Finance": "Finance",
                  "Real Estate": "Real estate", "Utilities": "Utilities", "Industrials": "Industrials",
                  "Consumer Discretionary": "Consumer", "Consumer Staples": "Consumer",
                  "Basic Materials": "Materials", "Telecommunications": "Communication"}

FUNDS = {
    "SPY": "Broad market", "VOO": "Broad market", "IVV": "Broad market", "VTI": "Broad market", "DIA": "Broad market",
    "IWM": "Broad market", "RSP": "Broad market",
    "QQQ": "Technology", "XLK": "Technology", "VGT": "Technology", "SOXX": "Technology", "SMH": "Technology",
    "XLE": "Energy", "XOP": "Energy", "VDE": "Energy", "OIH": "Energy", "UNG": "Energy", "USO": "Energy",
    "XLF": "Finance", "KRE": "Finance", "KBE": "Finance", "VFH": "Finance",
    "XLV": "Healthcare", "XBI": "Healthcare", "IBB": "Healthcare", "VHT": "Healthcare",
    "XLI": "Industrials", "XLB": "Materials", "GDX": "Materials", "GLD": "Materials", "SLV": "Materials",
    "XLY": "Consumer", "XLP": "Consumer", "XRT": "Consumer",
    "XLU": "Utilities", "XLRE": "Real estate", "VNQ": "Real estate", "XLC": "Communication",
    "EEM": "International", "EFA": "International", "EWY": "International", "EWZ": "International",
    "FXI": "International", "EWJ": "International", "VEA": "International", "VWO": "International",
    "TLT": "Bonds", "IEF": "Bonds", "HYG": "Bonds", "LQD": "Bonds", "AGG": "Bonds",
}


def sector_for_sic(sic):
    """Broad industry from a 4-digit SIC code."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    if 3570 <= s <= 3579 or 3600 <= s <= 3699 or 3670 <= s <= 3679 or 7370 <= s <= 7379 or 3820 <= s <= 3829:
        return "Technology"
    if 1300 <= s <= 1399 or 2900 <= s <= 2999 or 4610 <= s <= 4619 or 1200 <= s <= 1299:
        return "Energy"
    if 2830 <= s <= 2836 or 3840 <= s <= 3851 or 8000 <= s <= 8099 or 5120 <= s <= 5122 or 8731 <= s <= 8734:
        return "Healthcare"
    if s == 6798:
        return "Real estate"
    if 6000 <= s <= 6799:
        return "Finance"
    if 4900 <= s <= 4999:
        return "Utilities"
    if 4800 <= s <= 4899 or 2710 <= s <= 2741 or 7810 <= s <= 7829:
        return "Communication"
    if 1000 <= s <= 1499 or 2800 <= s <= 2829 or 2840 <= s <= 2899 or 3300 <= s <= 3399 or 2600 <= s <= 2699:
        return "Materials"
    if 1500 <= s <= 1799 or 3400 <= s <= 3569 or 3580 <= s <= 3599 or 3700 <= s <= 3799 or 4000 <= s <= 4599 or 8700 <= s <= 8799:
        return "Industrials"
    if 6500 <= s <= 6599:
        return "Real estate"
    if 100 <= s <= 999 or 2000 <= s <= 2399 or 2500 <= s <= 2599 or 3100 <= s <= 3199 or 3900 <= s <= 3999 or 5000 <= s <= 5999 or 7000 <= s <= 7369 or 7380 <= s <= 7999:
        return "Consumer"
    return "Other"


# ---------------------------------------------------------------------------
# industry lookups (cached in industries.json)
# ---------------------------------------------------------------------------
_cache = None
_failed = [0.0]                 # when the SEC company list last failed to download
_nasdaq_failed = [0.0]          # ...and Nasdaq's


def _load():
    global _cache
    if _cache is None:
        try:
            with open(INDUSTRY_FILE, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
        _cache.setdefault("symbols", {})
    return _cache


def _save():
    tmp = INDUSTRY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cache, f, indent=1)
    os.replace(tmp, INDUSTRY_FILE)


def _get_json(url, timeout=8, headers=None):
    req = urllib.request.Request(url, headers=headers or SEC_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cik_for(symbol, log):
    c = _load()
    stale = not c.get("tickers") or time.time() - c.get("tickers_at", 0) > TICKER_MAP_DAYS * 86400
    if stale and time.time() - _failed[0] > 3600:              # after a failure, wait an hour before trying again
        try:
            raw = _get_json(SEC_TICKERS, timeout=20)
            c["tickers"] = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
            c["tickers_at"] = time.time()
            _save()
        except Exception as e:  # noqa: BLE001 - offline / SEC busy: use what we have
            _failed[0] = time.time()
            log(f"Pip: couldn't download the SEC company list ({e}); trying again in an hour")
    return (c.get("tickers") or {}).get(symbol.upper().replace(".", "-"))


def _nasdaq_sector(symbol, log):
    """Sector from Nasdaq's screener list (refreshed weekly), or None."""
    c = _load()
    stale = not c.get("nasdaq") or time.time() - c.get("nasdaq_at", 0) > TICKER_MAP_DAYS * 86400
    if stale and time.time() - _nasdaq_failed[0] > 3600:
        try:
            rows = _get_json(NASDAQ_LIST, timeout=30, headers=NASDAQ_HEADERS)["data"]["rows"]
            c["nasdaq"] = {r["symbol"].upper(): NASDAQ_SECTORS.get(r.get("sector") or "") for r in rows
                           if NASDAQ_SECTORS.get(r.get("sector") or "")}
            c["nasdaq_at"] = time.time()
            for v in c["symbols"].values():           # earlier "not found" answers get another try
                if not v.get("sector"):
                    v["at"] = 0
            _save()
            log(f"Pip: industry list downloaded ({len(c['nasdaq'])} stocks)")
        except Exception as e:  # noqa: BLE001
            _nasdaq_failed[0] = time.time()
            log(f"Pip: couldn't download Nasdaq's industry list ({e}); trying again in an hour")
    nq = c.get("nasdaq") or {}
    return nq.get(symbol.upper()) or nq.get(symbol.upper().replace(".", "/"))


def industry(symbol, log=print):
    """Broad industry for a stock symbol. Unknown ones come back as 'Unknown: <SYMBOL>'."""
    sym = symbol.upper()
    if "/" in sym:
        return "Crypto"
    if sym in FUNDS:
        return FUNDS[sym]
    found = _nasdaq_sector(sym, log)
    if found:
        return found
    c = _load()
    hit = c["symbols"].get(sym)
    if hit and (hit.get("sector") or time.time() - hit.get("at", 0) < 86400):
        return hit.get("sector") or f"Unknown: {sym}"
    sector, sic, desc = None, None, ""
    cik = _cik_for(sym, log)
    if cik:
        try:
            info = _get_json(SEC_COMPANY.format(cik=cik))
            sic, desc = info.get("sic"), info.get("sicDescription") or ""
            sector = sector_for_sic(sic)
        except Exception as e:  # noqa: BLE001
            log(f"Pip: couldn't look up {sym}'s industry ({e})")
    c["symbols"][sym] = {"sector": sector, "sic": sic, "desc": desc, "at": time.time()}
    _save()
    if not sector:
        log(f"Pip: no industry found for {sym}; it counts as its own industry")
    return sector or f"Unknown: {sym}"


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def heroes_day_pl(memory, positions, today, day_of, norm):
    """Today's result for all heroes: finished trades today + today's move in what they still hold."""
    snap, snap_day = memory.get("close_values", {}), memory.get("close_values_day", "")
    closed = 0.0
    for e in memory.get("journal", []):
        if e.get("side") != "sell" or day_of(e.get("t")) != today:
            continue
        pl, sym = _f(e.get("pl")), norm(e.get("symbol", ""))
        if snap_day and snap_day < today and sym in snap and e.get("cost") is not None:
            pl -= snap[sym] - _f(e.get("cost"))        # only the part earned today (Ysolde's closing values)
        closed += pl
    ours = {norm(s) for h in memory.get("held", {}).values() for s in h}
    open_today = sum(_f(getattr(p, "unrealized_intraday_pl", 0)) for s, p in positions.items() if s in ours)
    return round(closed + open_today, 2), round(closed, 2), round(open_today, 2)


def daily_stop_hit(memory, positions, today, day_of, norm, log):
    """True when the heroes are down DAILY_STOP_DOLLARS or more today. Logs once per day."""
    total, closed, open_today = heroes_day_pl(memory, positions, today, day_of, norm)
    hit = total <= -DAILY_STOP_DOLLARS
    flag = memory.setdefault("risk", {})
    if hit and flag.get("daily_stop_day") != today:
        flag["daily_stop_day"] = today
        log(f"Pip: DAILY STOP. Heroes are ${total:+,.2f} today (trades ${closed:+,.2f}, still held ${open_today:+,.2f}), "
            f"past the -${DAILY_STOP_DOLLARS:,.0f} limit: no new buys until the next trading day")
    return hit


def cap_buy(bot, memory, positions, symbol, dollars, pots, benched, norm, log):
    """Shrink (or refuse) one buy so it fits the biggest-bet and industry limits.
    pots: {hero name: pot}; benched: names of benched heroes (their pots don't count as
    room, but what they still hold does). Returns the dollars allowed (0 = skip)."""
    name = bot["name"]
    pot = _f(pots.get(name))
    allowed = dollars
    stock_cap = round(pot * MAX_STOCK_SHARE, 2)
    if allowed > stock_cap:
        log(f"[{name}] Pip: {symbol} shrunk from ${allowed:,.2f} to ${stock_cap:,.2f} (no more than {MAX_STOCK_SHARE:.0%} of the pot in one stock)")
        allowed = stock_cap
    if bot.get("kind") == "crypto" or "/" in symbol:
        return round(allowed, 2)
    working = [n for n in pots if n not in benched]
    combined = sum(_f(pots[n]) for n in working)
    if combined <= 0:
        return round(allowed, 2)
    sector = industry(norm(symbol), log)
    in_sector = 0.0
    for hero, held in memory.get("held", {}).items():
        for s, h in held.items():
            if "/" in s:
                continue
            p = positions.get(norm(s))
            value = _f(getattr(p, "market_value", 0)) if p else _f(h.get("cost"))
            if value and industry(norm(s), log) == sector:
                in_sector += value
    room = round(combined * MAX_INDUSTRY_SHARE - in_sector, 2)
    if room < allowed:
        log(f"[{name}] Pip: {sector} already has ${in_sector:,.2f} of ${combined:,.2f}; "
            + (f"{symbol} shrunk to ${max(room, 0):,.2f}" if room > 0 else f"{symbol} skipped")
            + f" (no more than {MAX_INDUSTRY_SHARE:.0%} in one industry)")
        allowed = max(room, 0.0)
    return round(allowed, 2)
