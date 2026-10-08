"""
Two researchers keep the bots' watchlists fresh:

  STOCK researcher  (Mistress Quill the Loremaster)
      every STOCK_EVERY_MINUTES while the US market is open (and once at start-up)
      leads: today's most-traded stocks, the biggest movers up and down,
             and stocks in the news in the last 24 hours
  CRYPTO researcher (Corvin the Star-Reader)
      every CRYPTO_EVERY_MINUTES, day and night (crypto never closes)
      leads: every coin Alpaca can trade against USD, plus crypto news

Each one, for its own market:
  1. Gathers leads (above).
  2. Studies them   - 40 days of daily prices for each lead.
  3. Scores them    - separately for each trading style:
        trend follower  : steady climbers above their 20-day average
        dip buyer       : liquid names that just fell hard (low RSI) but aren't collapsing
        breakout hunter : pushing through their 20-day high on rising volume
     ...then reads the news (news.py): good news lifts a pick, bad news knocks it off
     the list, and a dip with bad news behind it is skipped (it may keep falling).
  4. Rewrites the watchlist of every bot in its market that has "research": true, keeping
     anything the bot holds right now and anything you "pinned" in bots.json.
     Two bots never get the same symbol.

Penny bots aren't researched: they scan for their own picks every round.
It's a screen, not a crystal ball: it finds symbols that fit each style today.
Nothing here places trades.
"""

import re
from datetime import datetime, timedelta, timezone

import news as newsdesk

STOCK_EVERY_MINUTES = 30   # stock researcher, only while the market is open
CRYPTO_EVERY_MINUTES = 15  # crypto researcher, around the clock
EVERY_MINUTES = {"stock": STOCK_EVERY_MINUTES, "crypto": CRYPTO_EVERY_MINUTES}
MARKETS = ("stock", "crypto")
WATCH_SIZE = 6              # symbols per bot (plus anything held or pinned)
MIN_PRICE = 5.00            # regular stock bots skip anything cheaper (that's penny-bot land)
MIN_DOLLAR_VOLUME = 20e6    # average daily $ traded, so orders fill easily
LOOKBACK_DAYS = 60          # calendar days of daily bars to fetch (~40 trading days)
MAX_LEADS = 150             # cap how many stocks get studied per run
NEWS_STORIES = 300          # stories read per research run (last 24 hours)
AVOID_TONE = -2             # this much bad news (recency-weighted) keeps a symbol off every list
STYLES = {}                 # learned strategies -> the built-in style they resemble (bot.py fills this)


def style_of(bot):
    return STYLES.get(bot.get("strategy"), bot.get("strategy"))


# Leveraged and inverse funds (2x, 3x, "Bear", "UltraShort"...) aren't stocks: they bet with borrowed
# force or against something, lose value over time by design, and confuse every signal. Nobody trades them.
_LEV = re.compile(r"(?<![\w.])-?\d+(\.\d+)?x\b|\binverse\b|\bleveraged\b|\bultrapro\b|\bultrashort\b|\bdaily target\b", re.I)
_FUNDISH = re.compile(r"\b(etf|etfs|etn|etns|shares|fund|trust|notes)\b", re.I)
_ISSUER = re.compile(r"^\s*(proshares (ultra|short)|direxion daily|microsectors|t-rex|tradr|leverage shares|volatility shares)", re.I)
_lev_cache = {"day": None, "symbols": set()}


def is_leveraged_name(name):
    name = name or ""
    return bool(_ISSUER.search(name) or (_LEV.search(name) and _FUNDISH.search(name)))


def leveraged_symbols(trading, log=print):
    """Every leveraged/inverse fund Alpaca lists (one request, refreshed daily)."""
    today = datetime.now().date()
    if _lev_cache["day"] != today:
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetClass
        try:
            assets = trading.get_all_assets(GetAssetsRequest(asset_class=AssetClass.US_EQUITY))
            _lev_cache["symbols"] = {a.symbol for a in assets if is_leveraged_name(getattr(a, "name", ""))}
            _lev_cache["day"] = today
        except Exception as e:  # noqa: BLE001 - keep yesterday's list if the request fails
            log(f"fund list unavailable ({e})")
    return _lev_cache["symbols"]


# ---------------------------------------------------------------------------
# MATH
# ---------------------------------------------------------------------------
def _sma(v, n):
    return sum(v[-n:]) / n


def _rsi(c, n=14):
    gains = losses = 0.0
    for a, b in zip(c[-n - 1:-1], c[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def study(closes, volumes):
    """Numbers the scorers use. Needs ~25+ daily bars."""
    if len(closes) < 25:
        return None
    c, v = closes, volumes
    sma20 = _sma(c, 20)
    return {
        "price": c[-1],
        "ret1": c[-1] / c[-2] - 1,
        "ret3": c[-1] / c[-4] - 1,
        "ret20": c[-1] / c[-21] - 1,
        "ret_all": c[-1] / c[0] - 1,
        "sma20": sma20,
        "sma20_rising": sma20 > _sma(c[:-5], 20),
        "high20": max(c[-21:-1]),
        "vol_ratio": v[-1] / max(1.0, _sma(v[:-1], 20)),
        "dollar_vol": _sma([a * b for a, b in zip(c[-20:], v[-20:])], 20),
        "rsi": _rsi(c),
    }


def news_info(news):
    """News for one symbol as {"tone", "count", "headline", "fresh"} (accepts a plain count too)."""
    if isinstance(news, dict):
        return {"tone": news.get("tone", 0.0), "count": news.get("count", 0), "headline": news.get("headline", ""),
                "fresh": news.get("fresh", 99.0)}
    return {"tone": 0.0, "count": int(news or 0), "headline": "", "fresh": 99.0}


def fit(style, s):
    """Does the price action fit this style? (score, reason) or None. News not included."""
    if not s:
        return None
    if style == "ma_cross":
        if s["price"] > s["sma20"] and s["sma20_rising"] and s["ret20"] > 0.02:
            return s["ret20"] * 100, f"climbing steadily: up {s['ret20']:.0%} in 20 days, above its 20-day average"
    elif style == "rsi":
        if s["rsi"] < 40 and s["ret3"] < -0.03 and s["ret_all"] > -0.25:
            return 40 - s["rsi"], f"sold off {abs(s['ret3']):.0%} in 3 days (RSI {s['rsi']:.0f}), not in a long collapse"
    elif style == "breakout":
        if s["price"] >= s["high20"] * 0.98 and s["vol_ratio"] > 1.2:
            return s["vol_ratio"] * 10 + s["ret3"] * 100, f"pressing its 20-day high on {s['vol_ratio']:.1f}x normal volume"
    return None


def score(style, s, news=None):
    """Higher is better. None = doesn't fit this style today (or the news is bad). Returns (score, reason)."""
    base = fit(style, s)
    if not base:
        return None
    pts, why = base
    n = news_info(news)
    t, c = n["tone"], n["count"]
    if t <= AVOID_TONE:
        return None                                   # bad news: stay away
    if style == "rsi":
        if t <= -1:
            return None                               # a drop with bad news behind it can keep dropping
        if t >= 0:
            pts += 5                                  # nothing bad in the news: more likely an overreaction
            why += ", and no bad news behind the drop" if c else ", with no bad news behind it"
    else:
        pts += t * 3 + min(c, 5) * 0.5
        if style == "breakout" and t >= 2 and n["fresh"] <= 6:
            pts += 5                                  # a breakout with fresh good news behind it
    if n["headline"] and abs(t) >= 1:
        why += f'; in the news: "{newsdesk.short(n["headline"], 70)}"'
    elif c:
        why += f", {c} news stor{'y' if c == 1 else 'ies'} today"
    return pts, why


def scan_size(bot):
    """How many of the busiest stocks a scanning hero watches ("scan": 300 in bots.json), else 0."""
    try:
        return max(0, int(bot.get("scan") or 0))
    except (TypeError, ValueError):
        return 0


MAJOR_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "NYSEARCA", "BATS"}


def busiest_stocks(trading, stock_data, memory, log, n=300):
    """The n busiest plain US stocks ($5+, can be bought in fractions, no leveraged/inverse funds),
    ranked by yesterday's dollars traded. Worked out once a day and kept in memory."""
    rs = memory.setdefault("research", {})
    today = datetime.now().date().isoformat()
    cached = rs.get("busiest") or {}
    if cached.get("day") == today and len(cached.get("list", [])) >= min(n, 50):
        return cached["list"][:n]
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass
    from alpaca.data.requests import StockSnapshotRequest
    from alpaca.data.enums import DataFeed
    try:
        assets = trading.get_all_assets(GetAssetsRequest(asset_class=AssetClass.US_EQUITY))
    except Exception as e:  # noqa: BLE001
        log(f"stock list unavailable ({e}); keeping the last busiest list")
        return cached.get("list", [])[:n]
    def exch(a):
        return str(getattr(getattr(a, "exchange", ""), "value", getattr(a, "exchange", ""))).upper()
    def stat(a):
        return str(getattr(getattr(a, "status", ""), "value", getattr(a, "status", ""))).lower()
    syms = sorted(a.symbol for a in assets
                  if getattr(a, "tradable", False) and getattr(a, "fractionable", False) and stat(a) == "active"
                  and exch(a) in MAJOR_EXCHANGES and _plain_stock(a.symbol) and not is_leveraged_name(getattr(a, "name", "")))
    volume = {}
    for i in range(0, len(syms), 200):
        chunk = syms[i:i + 200]
        try:
            snaps = stock_data.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=chunk, feed=DataFeed.IEX))
        except Exception as e:  # noqa: BLE001 - skip a chunk rather than fail the whole scan
            log(f"prices unavailable for some stocks ({e})")
            continue
        for sym, sn in (snaps or {}).items():
            bar = getattr(sn, "previous_daily_bar", None) or getattr(sn, "daily_bar", None)
            if not bar:
                continue
            price, vol = float(bar.close or 0), float(bar.volume or 0)
            if price >= MIN_PRICE and vol > 0:
                volume[sym] = price * vol
    ranked = sorted(volume, key=volume.get, reverse=True)
    if ranked:
        rs["busiest"] = {"day": today, "list": ranked[:max(n, 300)]}
        log(f"ranked {len(ranked)} stocks by dollars traded; the busiest are {', '.join(ranked[:5])}")
        return ranked[:n]
    return cached.get("list", [])[:n]


def market_of(bot):
    """'stock' or 'crypto' for researched kinds, None for penny bots (they find their own)."""
    return {"stock": "stock", "crypto": "crypto"}.get(bot.get("kind"))


def is_researched(bot):
    return bool(bot.get("research", True)) and market_of(bot) is not None


def pick_watchlists(bots, studies, news_counts, held, previous, market=None, busiest=None):
    """Decide the new watchlist of each researched bot (only bots in `market`, if given).

    bots      : bot configs (dicts from bots.json)
    studies   : {"stock": {sym: study}, "crypto": {sym: study}} (only the markets being researched)
    held      : {bot_name: [symbols held right now]}
    previous  : {bot_name: [last watchlist]}
    Returns {bot_name: {"watchlist": [...], "reasons": {sym: why}, "added": [...], "dropped": [...]}}
    """
    out, claimed = {}, set()
    for b in bots:            # held/pinned symbols are claimed first so nobody else takes them
        for s in held.get(b["name"], []) + b.get("pinned", []):
            claimed.add(s)
    for b in bots:
        if not is_researched(b) or (market and market_of(b) != market):
            continue
        name, mk = b["name"], market_of(b)
        keep = list(dict.fromkeys(held.get(name, []) + b.get("pinned", [])))
        reasons = {s: ("holding it now" if s in held.get(name, []) else "pinned by you") for s in keep}
        if scan_size(b) and mk == "stock" and busiest:
            # a scanning hero watches the N busiest stocks and lets its own technique pick the moment
            picks = []
            for rank, sym in enumerate(busiest, 1):
                if len(picks) >= max(0, scan_size(b) - len(keep)):
                    break
                if sym in claimed or sym in keep or news_info(news_counts.get(sym))["tone"] <= AVOID_TONE:
                    continue
                picks.append(sym)
                reasons[sym] = f"#{rank} busiest stock today"
                claimed.add(sym)
            new = keep + picks
            prev = previous.get(name, [])
            out[name] = {"watchlist": new, "reasons": {s: reasons[s] for s in new}, "scan": True,
                         "added": [s for s in new if s not in prev], "dropped": [s for s in prev if s not in new], "avoided": {}}
            continue
        ranked, avoided = [], {}
        for sym, st in studies.get(mk, {}).items():
            if sym in claimed:
                continue
            r = score(style_of(b), st, news_counts.get(sym))
            if r:
                ranked.append((r[0], sym, r[1]))
            elif fit(style_of(b), st) and news_info(news_counts.get(sym))["tone"] <= -1:
                avoided[sym] = news_info(news_counts.get(sym))["headline"]
        ranked.sort(reverse=True)
        picks = []
        for _, sym, why in ranked:
            if len(picks) >= max(0, WATCH_SIZE - len(keep)):
                break
            picks.append(sym)
            reasons[sym] = why
            claimed.add(sym)
        new = keep + picks
        if not picks and previous.get(name):   # nothing fits today: keep the old list rather than go empty
            new = list(dict.fromkeys(keep + [s for s in previous[name] if s not in claimed]))
            for s in new:
                reasons.setdefault(s, "kept from last time (nothing better fits today)")
                claimed.add(s)
        prev = previous.get(name, [])
        out[name] = {"watchlist": new, "reasons": {s: reasons[s] for s in new},
                     "added": [s for s in new if s not in prev], "dropped": [s for s in prev if s not in new],
                     "avoided": avoided}
    return out


# ---------------------------------------------------------------------------
# GATHERING (talks to Alpaca for market data only)
# ---------------------------------------------------------------------------
def _recent_news(news_client, log):
    """{symbol: news digest} from the last 24 hours of stories (crypto as BTC/USD)."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stories = newsdesk.fetch(news_client, since, log, limit=NEWS_STORIES)
    return newsdesk.digest(stories)


def _plain_stock(s):
    return s.isalpha() and len(s) <= 5 and not (len(s) == 5 and s[-1] in "WRU")   # no warrants/rights/units


def gather_stock_leads(screener, news_client, log):
    from alpaca.data.requests import MostActivesRequest, MarketMoversRequest
    from alpaca.data.enums import MarketType, MostActivesBy
    stocks = set()
    try:
        for a in screener.get_most_actives(MostActivesRequest(top=100, by=MostActivesBy.VOLUME)).most_actives:
            stocks.add(a.symbol)
    except Exception as e:
        log(f"most-actives list unavailable ({e})")
    try:
        mv = screener.get_market_movers(MarketMoversRequest(top=50, market_type=MarketType.STOCKS))
        for m in list(mv.gainers) + list(mv.losers):
            stocks.add(m.symbol)
    except Exception as e:
        log(f"movers list unavailable ({e})")
    news = {s: n for s, n in _recent_news(news_client, log).items() if "/" not in s}
    stocks |= {s for s, n in news.items() if n["tone"] > AVOID_TONE}     # no point studying a stock with bad news
    return {s for s in stocks if _plain_stock(s)}, news


def gather_crypto_leads(trading, news_client, log):
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass
    coins = set()
    try:
        for a in trading.get_all_assets(GetAssetsRequest(asset_class=AssetClass.CRYPTO)):
            if a.tradable and a.symbol.endswith("/USD"):
                coins.add(a.symbol)
    except Exception as e:
        log(f"crypto list unavailable ({e})")
    news = {s: n for s, n in _recent_news(news_client, log).items() if s in coins}
    return coins, news


def study_market(market, data_client, syms, log):
    """{symbol: study} for one market. Stocks must be $5+ and trade plenty of dollars a day."""
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed
    start = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    syms = sorted(syms)[:MAX_LEADS]
    out = {}
    for i in range(0, len(syms), 50):
        chunk = syms[i:i + 50]
        try:
            if market == "stock":
                bars = data_client.get_stock_bars(StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day, start=start, feed=DataFeed.IEX))
            else:
                bars = data_client.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day, start=start))
        except Exception as e:
            log(f"price history unavailable for some leads ({e})")
            continue
        for s in chunk:
            rows = bars.data.get(s, [])
            st = study([r.close for r in rows], [float(r.volume or 0) for r in rows])
            if not st:
                continue
            if market == "stock" and (st["price"] < MIN_PRICE or st["dollar_vol"] < MIN_DOLLAR_VOLUME / 50):
                # IEX volume is a slice of the real market (~2%), hence /50
                continue
            out[s] = st
    return out


def _research_memory(memory):
    rs = memory.setdefault("research", {})
    for old in ("last_run", "leads_studied", "news_seen"):   # from the one-researcher version
        rs.pop(old, None)
    rs.setdefault("lists", {})
    rs.setdefault("reasons", {})
    for m in MARKETS:
        rs.setdefault(m, {})
    return rs


def run(market, trading, stock_data, crypto_data, screener, news_client, bots, memory, log):
    """One research pass for one market ('stock' or 'crypto'). Returns {bot_name: picks}."""
    if market == "stock":
        leads, news = gather_stock_leads(screener, news_client, log)
        data_client = stock_data
    else:
        leads, news = gather_crypto_leads(trading, news_client, log)
        data_client = crypto_data
    if market == "stock":
        lev = leveraged_symbols(trading, log)
        skipped = sorted(s for s in leads if s in lev)
        if skipped:
            log(f"skipped {len(skipped)} leveraged/inverse funds ({', '.join(skipped[:6])}{'...' if len(skipped) > 6 else ''})")
        leads = {s for s in leads if s not in lev}
    rs = _research_memory(memory)
    mine = [b for b in bots if is_researched(b) and market_of(b) == market]
    previous = {b["name"]: rs["lists"].get(b["name"], b.get("watchlist", [])) for b in mine}
    for b in mine:                       # always re-check what's already on the lists (minus leveraged funds);
        if scan_size(b):                 # a scanning hero's long list isn't studied, its technique does the picking
            continue
        leads |= {s for s in previous[b["name"]] if market != "stock" or s not in leveraged_symbols(trading, log)}
    studies = {market: study_market(market, data_client, leads, log)}
    held = {b["name"]: list(memory.get("held", {}).get(b["name"], {})) for b in bots}
    widest = max([scan_size(b) for b in mine] + [0])
    busiest = busiest_stocks(trading, stock_data, memory, log, widest) if market == "stock" and widest else None
    picks = pick_watchlists(bots, studies, news, held, previous, market=market, busiest=busiest)
    for name, p in picks.items():
        rs["lists"][name] = p["watchlist"]
        rs["reasons"][name] = p["reasons"]
    rs[market] = {"last_run": datetime.now().isoformat(timespec="seconds"),
                  "leads_studied": len(studies[market]), "news_seen": sum(n["count"] for n in news.values()),
                  "good_news": sum(1 for n in news.values() if n["tone"] >= 2),
                  "bad_news": sum(1 for n in news.values() if n["tone"] <= AVOID_TONE)}
    return picks


def mark_tried(memory, market):
    """After a failed run: wait a full interval before trying again."""
    info = _research_memory(memory)[market]
    info["last_run"] = datetime.now().isoformat(timespec="seconds")
    info.pop("rush", None)


def watchlist(bot, memory):
    """The list a bot trades from right now: the researcher's list if it has one, else bots.json."""
    if is_researched(bot):
        lst = memory.get("research", {}).get("lists", {}).get(bot["name"])
        if lst:
            return lst
    return bot.get("watchlist", [])


def due(memory, market, market_open=True, now=None):
    """Is it time for this market's researcher to go out again?
    The stock researcher rests while the market is closed (after her first run)."""
    info = memory.get("research", {}).get(market, {})
    last = info.get("last_run")
    if not last:
        return True
    if market == "stock" and not market_open:
        return False
    if info.get("rush"):            # the Town Crier brought big news: go now
        return True
    return (now or datetime.now()) - datetime.fromisoformat(last) >= timedelta(minutes=EVERY_MINUTES[market])
