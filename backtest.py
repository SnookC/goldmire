"""
The Proving Grounds: test a trading strategy on real price history before any hero uses it.

    python backtest.py                 test every strategy (built-in + the strategies folder)
    python backtest.py turtle          only strategies whose file or name contains "turtle"

What it does
  1. Downloads price history from Alpaca for a basket of stocks and coins
     (saved in proving_grounds/data, so later runs are quick).
  2. Replays history bar by bar for each strategy, like a hero would trade it:
       - $100 per trade, buying only (no shorting), one position per symbol
       - a signal at a bar's close is filled at the NEXT bar's open (no peeking)
       - stop-loss / take-profit hit inside a bar are filled at that price
       - trading costs on every buy and sell (0.05% stocks, 0.25% crypto)
  3. Splits history: the first 70% is the "training" part, the last 30% the "exam".
     A strategy must also make money in the exam, so it can't pass by luck of
     fitting old data.
  4. Compares it with the strategies the heroes use today on the same data.
  5. Writes proving_grounds/report.html (opens in your browser) and results.json.

Verdicts
  PASSES     50+ trades, earns at least $1.25 for every $1 it loses, profitable in the exam,
             makes money on at least 60% of the symbols (not one lucky one), does better
             than 95% of 300 make-believe traders who buy at random times (same number of
             trades, held as long), and beats the heroes' current best on the same market.
  PROMISING  earns more than it loses and is profitable in the exam, but isn't clearly
             better than what the heroes already do.
  FAILS      everything else. Most strategies fail. That's what this is for.

A new strategy is a small file in the "strategies" folder; see strategies/README.txt.
Nothing here places trades.
"""

import glob
import html
import importlib.util
import inspect
import json
import math
import os
import random
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone

import exits

HERE = os.path.dirname(os.path.abspath(__file__))
STRAT_DIR = os.path.join(HERE, "strategies")
OUT_DIR = os.path.join(HERE, "proving_grounds")
DATA_DIR = os.path.join(OUT_DIR, "data")

BASKET = {
    "stock": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "AMZN", "JPM", "XOM", "TSLA", "KO", "PLTR"],
    "crypto": ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "AVAX/USD", "LTC/USD", "LINK/USD"],
}
HISTORY_DAYS = {"15Min": 180, "1Hour": 365, "1Day": 365 * 4}
COST = {"stock": 0.0005, "crypto": 0.0025, "penny": 0.002}     # per side: fees + slippage (penny spreads are wide)
PENNY_BASKET_SIZE = 25
TRADE_DOLLARS = 100.0
EXAM_SHARE = 0.30
LOOKBACK = 300                                  # bars a strategy can see (plenty for a 200-bar average)
MIN_TRADES = 30                                 # fewer trades than this can't tell skill from luck
PASS_TRADES = 50
PASS_PROFIT_FACTOR = 1.25
PASS_BREADTH = 0.60                             # profitable on at least 60% of the symbols, not one lucky one
RANDOM_TRADERS = 300                            # make-believe traders who buy at random times
PASS_BEATS_RANDOM = 0.95                        # must do better than 95% of them
PROMISING_BEATS_RANDOM = 0.80
DATA_MAX_AGE_HOURS = 20                         # re-download history once a day


# ---------------------------------------------------------------------------
# STRATEGIES
# ---------------------------------------------------------------------------
class Strategy:
    def __init__(self, key, name, signal, timeframe="15Min", markets=("stock", "crypto"), stop_loss=None,
                 take_profit=None, source="", rules="", builtin=False, lookback=LOOKBACK, style=None,
                 exit_mode="signal", variant=None, base=None):
        self.key, self.name, self.signal, self.timeframe = key, name, signal, timeframe
        self.markets, self.stop_loss, self.take_profit = tuple(markets), stop_loss, take_profit
        self.source, self.rules, self.builtin, self.lookback = source, rules, builtin, lookback
        self.style = style or key      # which researcher scoring fits it: ma_cross / rsi / breakout
        self.exit_mode, self.variant, self.base = exit_mode, variant, base or key
        try:   # signal(bars) or signal(bars, position): position = {"entry": price paid, "bars_held": n} or None
            self.wants_position = len(inspect.signature(signal).parameters) >= 2
        except (TypeError, ValueError):
            self.wants_position = False


# Ways to get out of a trade, tried on each of the heroes' current styles.
# (label, stop setting, exit mode); the first is how the heroes traded before stops were added.
EXIT_VARIANTS = [("no stop", None, "signal"), ("3% stop", 0.03, "signal"), ("5% stop", 0.05, "signal"),
                 ("8% stop", 0.08, "signal"), ("smart stop", "smart", "signal"),
                 ("5% stop + let winners build", 0.05, "build"), ("smart stop + let winners build", "smart", "build")]


def builtin_strategies(variants=True):
    """The three styles the heroes use (from bot.py) on the 15-minute bars they trade, each tried
    with every way of getting out of a trade in EXIT_VARIANTS."""
    import bot   # noqa: WPS433 - only for its strategy functions
    names = {"ma_cross": "Trend follower", "rsi": "Dip buyer", "breakout": "Breakout hunter"}
    out = []
    for key, fn in bot.STRATEGIES.items():
        for i, (label, stop, mode) in enumerate(EXIT_VARIANTS if variants else EXIT_VARIANTS[:1]):
            out.append(Strategy(key if i == 0 else f"{key}@{i}", f"{names.get(key, key)} ({label})",
                                (lambda f: lambda bars: f(bars["c"]))(fn), "15Min", rules=(fn.__doc__ or "").strip(),
                                builtin=True, stop_loss=stop, exit_mode=mode, variant=label, base=key))
    # Pip, the penny hero: his breakout on today's busiest $1-$5 stocks, with his old exits and new ones
    for i, (label, stop, mode, tp) in enumerate(PENNY_VARIANTS if variants else PENNY_VARIANTS[:1]):
        out.append(Strategy("pip" if i == 0 else f"pip@{i}", f"Pip's penny breakout ({label})",
                            (lambda f: lambda bars: f(bars["c"]))(bot.STRATEGIES["breakout"]), "15Min", markets=("penny",),
                            rules="Breakout hunter on penny stocks", builtin=True, stop_loss=stop, take_profit=tp,
                            exit_mode=mode, variant=label, base="pip"))
    return out


PENNY_VARIANTS = [("8% stop, sells at +15%", 0.08, "signal", 0.15), ("8% stop, no +15% cap", 0.08, "signal", None),
                  ("8% stop + let winners build", 0.08, "build", None), ("smart stop + let winners build", "smart", "build", None),
                  ("smart stop, sells at +15%", "smart", "signal", 0.15)]


def penny_basket(key, secret, log=print):
    """Today's busiest plain $1-$5 stocks (what Pip would be looking at), leveraged funds left out.
    Rough on purpose: stocks that were pennies months ago but aren't now are missing."""
    import research
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MostActivesRequest, StockLatestTradeRequest
    from alpaca.data.enums import MostActivesBy, DataFeed
    from alpaca.trading.client import TradingClient
    actives = ScreenerClient(key, secret).get_most_actives(MostActivesRequest(top=100, by=MostActivesBy.VOLUME)).most_actives
    syms = [a.symbol for a in actives if a.symbol.isalpha() and len(a.symbol) <= 5 and not (len(a.symbol) == 5 and a.symbol[-1] in "WRU")]
    lev = research.leveraged_symbols(TradingClient(key, secret, paper=True), log)
    trades = StockHistoricalDataClient(key, secret).get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=syms, feed=DataFeed.IEX))
    out = [s for s in syms if s not in lev and s in trades and 1.0 <= float(trades[s].price) <= 5.0]
    return out[:PENNY_BASKET_SIZE]


def load_strategy_file(path):
    spec = importlib.util.spec_from_file_location("strategy_" + os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "signal", None)):
        raise ValueError("it has no signal(bars) function")
    tf = getattr(mod, "TIMEFRAME", "15Min")
    if tf not in HISTORY_DAYS:
        raise ValueError(f"TIMEFRAME must be one of {', '.join(HISTORY_DAYS)}")
    return Strategy(os.path.basename(path)[:-3], getattr(mod, "NAME", os.path.basename(path)[:-3]), mod.signal, tf,
                    getattr(mod, "MARKETS", ("stock", "crypto")), getattr(mod, "STOP_LOSS", None),
                    getattr(mod, "TAKE_PROFIT", None), getattr(mod, "SOURCE", ""), (mod.__doc__ or "").strip(),
                    lookback=getattr(mod, "LOOKBACK", LOOKBACK), style=getattr(mod, "STYLE", "ma_cross"),
                    exit_mode=getattr(mod, "EXIT", "signal"))


def file_strategies(log=print):
    """{key: Strategy} for every file in the strategies folder (files starting with _ are skipped)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(STRAT_DIR, "*.py"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            st = load_strategy_file(path)
            out[st.key] = st
        except Exception as e:  # noqa: BLE001
            log(f"Skipping {os.path.basename(path)}: {e}")
    return out


def last_verdicts():
    """{(key, market): verdict} from the latest Proving Grounds run."""
    try:
        with open(os.path.join(OUT_DIR, "results.json"), encoding="utf-8") as f:
            return {(r["key"], r["market"]): r for r in json.load(f).get("results", [])}
    except (OSError, ValueError):
        return {}


def all_strategies(only=None, log=print):
    out = builtin_strategies()
    for path in sorted(glob.glob(os.path.join(STRAT_DIR, "*.py"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            out.append(load_strategy_file(path))
        except Exception as e:  # noqa: BLE001 - one broken file shouldn't stop the others
            log(f"Skipping {os.path.basename(path)}: {e}")
    if only:
        o = only.lower()
        out = [s for s in out if o in s.key.lower() or o in s.name.lower() or s.builtin]
    return out


# ---------------------------------------------------------------------------
# PRICE HISTORY (Alpaca, cached on disk)
# ---------------------------------------------------------------------------
def _keys():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
    key, secret = os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret or "PASTE" in key:
        raise SystemExit("Your Alpaca keys aren't set up yet (the .env file). Run 'Alpaca keys' from the Start menu first.")
    return key, secret


def _cache_path(market, tf):
    return os.path.join(DATA_DIR, f"{market}_{tf}.json")


def fetch_history(market, tf, log=print):
    """{symbol: {"t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}}"""
    path = _cache_path(market, tf)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < DATA_MAX_AGE_HOURS * 3600:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed
    frame = {"15Min": TimeFrame(15, TimeFrameUnit.Minute), "1Hour": TimeFrame.Hour, "1Day": TimeFrame.Day}[tf]
    start = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS[tf])
    end = datetime.now(timezone.utc) - timedelta(minutes=20)     # free data plans can't see the last 15 minutes
    key, secret = _keys()
    syms = penny_basket(key, secret, log) if market == "penny" else BASKET[market]
    log(f"Downloading {HISTORY_DAYS[tf]} days of {tf} {market} prices for {len(syms)} symbols...")
    if market in ("stock", "penny"):
        bars = StockHistoricalDataClient(key, secret).get_stock_bars(
            StockBarsRequest(symbol_or_symbols=syms, timeframe=frame, start=start, end=end, feed=DataFeed.IEX))
    else:
        bars = CryptoHistoricalDataClient(key, secret).get_crypto_bars(
            CryptoBarsRequest(symbol_or_symbols=syms, timeframe=frame, start=start, end=end))
    out = {}
    for s in syms:
        rows = bars.data.get(s, [])
        if len(rows) < 60:
            log(f"  {s}: not enough history, skipped")
            continue
        out[s] = {"t": [r.timestamp.isoformat() for r in rows], "o": [float(r.open) for r in rows],
                  "h": [float(r.high) for r in rows], "l": [float(r.low) for r in rows],
                  "c": [float(r.close) for r in rows], "v": [float(r.volume or 0) for r in rows]}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


# ---------------------------------------------------------------------------
# THE REPLAY
# ---------------------------------------------------------------------------
def simulate(strategy, series, market, errors=None):
    """Replays one symbol. Returns a list of trades: {entry_t, exit_t, ret (after costs), exit_i, why}.
    Errors raised by the strategy are counted in `errors` (a dict) rather than stopping the test."""
    o, h, l, c, t = series["o"], series["h"], series["l"], series["c"], series["t"]
    n, cost, lb = len(c), COST[market], strategy.lookback
    ts = series.get("_ts")
    if ts is None:
        ts = series["_ts"] = [datetime.fromisoformat(x).timestamp() for x in t]
    trades, entry, entry_i, pending = [], None, None, None
    stop, peak, cool_until = None, 0.0, float("-inf")
    for i in range(1, n):
        # 1) fill yesterday's decision at this bar's open
        if pending == "buy" and entry is None and ts[i] >= cool_until:
            entry, entry_i, peak = o[i] * (1 + cost), i, o[i]
            stop = exits.stop_fraction(strategy.stop_loss, c[max(0, i - exits.VOL_WINDOW - 1):i], market, strategy.timeframe)
        elif pending == "sell" and entry is not None:
            trades.append({"entry_i": entry_i, "exit_i": i, "ret": o[i] * (1 - cost) / entry - 1, "why": "signal"})
            entry = None
        pending = None
        # 2) stops inside this bar
        if entry is not None:
            raw_entry = entry / (1 + cost)
            if exits.trailing_active(strategy.exit_mode, stop, raw_entry, peak):
                level = peak * (1 - stop)                      # let it build: trail behind the best price
                if l[i] <= level:
                    fill = min(o[i], level)
                    trades.append({"entry_i": entry_i, "exit_i": i, "ret": fill * (1 - cost) / entry - 1, "why": "trailing stop"})
                    entry = None
            elif stop:
                level = raw_entry * (1 - stop)
                if l[i] <= level:
                    fill = min(o[i], level) if i > entry_i else level
                    trades.append({"entry_i": entry_i, "exit_i": i, "ret": fill * (1 - cost) / entry - 1, "why": "stop-loss"})
                    entry = None
                    cool_until = ts[i] + exits.COOLDOWN_HOURS * 3600     # no buying it back for 24 hours
            if entry is not None:
                peak = max(peak, h[i])
            if entry is not None and strategy.take_profit:
                target = raw_entry * (1 + strategy.take_profit)
                if h[i] >= target:
                    fill = max(o[i], target) if i > entry_i else target
                    trades.append({"entry_i": entry_i, "exit_i": i, "ret": fill * (1 - cost) / entry - 1, "why": "take-profit"})
                    entry = None
        # 3) the strategy looks at everything up to this bar's close
        lo = max(0, i + 1 - lb)
        view = {k: series[k][lo:i + 1] for k in ("o", "h", "l", "c", "v")}
        try:
            if strategy.wants_position:
                pos = None if entry is None else {"entry": entry / (1 + cost), "bars_held": i - entry_i}
                sig = strategy.signal(view, pos)
            else:
                sig = strategy.signal(view)
        except Exception as e:  # noqa: BLE001 - a strategy that errors on odd data just stays out
            sig = None
            if errors is not None:
                errors["count"] = errors.get("count", 0) + 1
                errors.setdefault("first", f"{type(e).__name__}: {e}")
        if sig == "buy" and entry is None:
            pending = "buy"
        elif sig == "sell" and entry is not None and not exits.trailing_active(strategy.exit_mode, stop, entry / (1 + cost), peak):
            pending = "sell"        # (while letting a winner build, the style's sell signal is ignored)
    if entry is not None:     # still holding at the end: close at the last price
        trades.append({"entry_i": entry_i, "exit_i": n - 1, "ret": c[-1] * (1 - cost) / entry - 1, "why": "end of test"})
    for tr in trades:
        tr["exit_t"] = t[tr["exit_i"]]
        tr["bars"] = tr["exit_i"] - tr["entry_i"]
    return trades


def _stats(trades):
    pl = [tr["ret"] * TRADE_DOLLARS for tr in trades]
    wins, losses = [p for p in pl if p > 0], [p for p in pl if p <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    curve, peak, dd = 0.0, 0.0, 0.0
    for tr in sorted(trades, key=lambda x: x["exit_t"]):
        curve += tr["ret"] * TRADE_DOLLARS
        peak = max(peak, curve)
        dd = max(dd, peak - curve)
    return {"trades": len(pl), "pl": round(sum(pl), 2), "win_rate": round(len(wins) / len(pl), 3) if pl else 0.0,
            "avg_win": round(gross_win / len(wins), 2) if wins else 0.0, "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0),
            "max_drawdown": round(dd, 2), "avg_bars": round(sum(tr["bars"] for tr in trades) / len(trades), 1) if trades else 0}


def random_traders(trades_by_symbol, data, market, count=RANDOM_TRADERS, seed=7):
    """P/L of make-believe traders who make the same number of trades, each held as long,
    on the same symbols, but buy at random moments. Returns their sorted results."""
    rng, cost, out = random.Random(seed), COST[market], []
    jobs = [(data[sym], tr["bars"]) for sym, trs in trades_by_symbol.items() for tr in trs]
    if not jobs:
        return []
    for _ in range(count):
        pl = 0.0
        for series, held in jobs:
            o, c = series["o"], series["c"]
            n = len(c)
            held = max(1, min(held, n - 3))
            i = rng.randint(1, n - held - 1)
            pl += (c[min(n - 1, i + held)] * (1 - cost) / (o[i] * (1 + cost)) - 1) * TRADE_DOLLARS
        out.append(pl)
    return sorted(out)


def test(strategy, market, data):
    every, exam = [], []
    per_symbol = {}
    hold = []
    errors = {}
    by_symbol = {}
    for sym, series in data.items():
        trades = simulate(strategy, series, market, errors)
        by_symbol[sym] = trades
        cut = series["t"][int(len(series["t"]) * (1 - EXAM_SHARE))]
        every += trades
        exam += [tr for tr in trades if tr["exit_t"] >= cut]
        per_symbol[sym] = round(sum(tr["ret"] for tr in trades) * TRADE_DOLLARS, 2)
        hold.append(series["c"][-1] / series["c"][0] - 1)
    s = _stats(every)
    s["exam_pl"] = _stats(exam)["pl"]
    s["exam_trades"] = len(exam)
    s["per_symbol"] = per_symbol
    s["buy_and_hold"] = round(sum(hold) / len(hold) * TRADE_DOLLARS, 2) if hold else 0.0
    luck = random_traders(by_symbol, data, market)
    s["beats_random"] = round(sum(1 for x in luck if x < s["pl"]) / len(luck), 3) if luck else 0.0
    s["random_median"] = round(luck[len(luck) // 2], 2) if luck else 0.0
    winners = [v for v in per_symbol.values() if v > 0]
    s["breadth"] = round(len(winners) / len(per_symbol), 2) if per_symbol else 0.0
    s["errors"] = errors.get("count", 0)
    s["first_error"] = errors.get("first", "")
    return s


def verdict(s, best_builtin_pl):
    if s.get("errors"):
        return "BROKEN", f"the strategy crashed {s['errors']} times ({s['first_error']}): needs fixing"
    if s["trades"] < MIN_TRADES:
        return "FAILS", f"only {s['trades']} trades: too few to trust either way"
    if s["profit_factor"] < 1.05 or s["pl"] <= 0:
        return "FAILS", "loses money, or barely breaks even after trading costs"
    if s["exam_pl"] <= 0:
        return "FAILS", "made money on the older data but lost it in the exam (recent 30%): likely luck"
    if s.get("beats_random", 1) < PROMISING_BEATS_RANDOM:
        return "FAILS", (f"no better than luck: {1 - s['beats_random']:.0%} of traders buying at random times "
                         "(same number of trades, held as long) did as well or better")
    if s["breadth"] < 0.5:
        return "FAILS", f"made money on only {s['breadth']:.0%} of the symbols: a few lucky ones carried it"
    if (s["trades"] >= PASS_TRADES and s["profit_factor"] >= PASS_PROFIT_FACTOR and s["breadth"] >= PASS_BREADTH
            and s.get("beats_random", 1) >= PASS_BEATS_RANDOM
            and (best_builtin_pl is None or s["pl"] > best_builtin_pl)):
        return "PASSES", (f"profitable overall, in the exam and on {s['breadth']:.0%} of symbols, beats "
                          f"{s['beats_random']:.0%} of random traders, and beats the heroes' current best here")
    return "PROMISING", "profitable overall and in the exam, but not yet strong or broad enough to trust fully"


# ---------------------------------------------------------------------------
# RUN + REPORT
# ---------------------------------------------------------------------------
def run(only=None, log=print, fetch=fetch_history):
    strategies = all_strategies(only, log)
    results = []
    cache = {}
    for st in strategies:
        for market in st.markets:
            k = (market, st.timeframe)
            if k not in cache:
                try:
                    cache[k] = fetch(market, st.timeframe, log)
                except SystemExit:
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"Couldn't download {market} {st.timeframe} prices ({e})")
                    cache[k] = {}
            if not cache[k]:
                continue
            t0 = time.time()
            s = test(st, market, cache[k])
            results.append({"key": st.key, "name": st.name, "market": market, "timeframe": st.timeframe, "builtin": st.builtin,
                            "variant": st.variant, "base": st.base, "exit_mode": st.exit_mode,
                            "source": st.source, "rules": st.rules, "stop_loss": st.stop_loss, "take_profit": st.take_profit,
                            "symbols": len(cache[k]), "bars": sum(len(v["c"]) for v in cache[k].values()), **s})
            log(f"  {st.name} [{market}, {st.timeframe}]: {s['trades']} trades, ${s['pl']:+,.2f}, "
                f"exam ${s['exam_pl']:+,.2f}  ({time.time() - t0:.1f}s)"
                + (f"  !! {s['errors']} errors: {s['first_error']}" if s["errors"] else ""))
    # verdicts: compare each new strategy with the heroes' best on the same market + timeframe
    today = {(b["base"], b["market"]): b for b in results if b["builtin"] and b["key"] == b["base"]}
    for r in results:
        if r["builtin"]:
            if r["key"] == r["base"]:
                r["verdict"], r["why"] = "TODAY", ("how Pip traded until now" if r["base"] == "pip" else
                                                   "how the heroes traded before stops were added")
            else:
                ref = today.get((r["base"], r["market"]))
                diff = r["pl"] - (ref["pl"] if ref else 0.0)
                if abs(diff) < 0.01:
                    r["verdict"], r["why"] = "SAME", "same result: this change never came into play"
                    continue
                r["verdict"] = "BETTER" if diff > 0 and r["exam_pl"] >= (ref["exam_pl"] if ref else 0) else "WORSE"
                r["why"] = f"{_money(diff)} compared with " + ("how Pip traded until now" if r["base"] == "pip" else "no stop") + ("" if r["exam_pl"] >= (ref["exam_pl"] if ref else 0) else ", and weaker in the exam")
            continue
        same = [b["pl"] for b in today.values() if b["market"] == r["market"] and b["timeframe"] == r["timeframe"]]
        best = max(same) if same else max([b["pl"] for b in today.values() if b["market"] == r["market"]] or [0.0])
        r["verdict"], r["why"] = verdict(r, best)
        r["best_builtin_pl"] = best
    os.makedirs(OUT_DIR, exist_ok=True)
    report = {"run": datetime.now().isoformat(timespec="seconds"), "trade_dollars": TRADE_DOLLARS,
              "exam_share": EXAM_SHARE, "costs": COST, "results": results}
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(OUT_DIR, "report.html"), "w", encoding="utf-8") as f:
        f.write(render_html(report))
    return report


def _money(v):
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def render_html(report):
    rows = []
    order = {"PASSES": 0, "PROMISING": 1, "FAILS": 2, "BROKEN": 3, "TODAY": 4}
    tune = []
    for r in sorted([r for r in report["results"] if r["builtin"]], key=lambda r: (r["market"], r["base"], -r["pl"])):
        e = html.escape
        best = r["pl"] == max(x["pl"] for x in report["results"] if x["builtin"] and x["base"] == r["base"] and x["market"] == r["market"])
        tune.append(f"""<tr class="{'best' if best else ''}"><td>{e(r['name'])}{' <b class="up">best</b>' if best else ''}</td><td>{e(r['market'])}</td>
<td class="n">{r['trades']}</td><td class="n">{r['win_rate']:.0%}</td><td class="n {'up' if r['pl'] >= 0 else 'dn'}">{_money(r['pl'])}</td>
<td class="n {'up' if r['exam_pl'] >= 0 else 'dn'}">{_money(r['exam_pl'])}</td><td class="n">{_money(r['avg_win'])} / {_money(r['avg_loss'])}</td>
<td class="n">{r['avg_bars'] / exits.BARS_PER_DAY.get(r['market'], {}).get(r['timeframe'], 26) * 24:.1f} h</td><td class="n">{_money(-r['max_drawdown'])}</td></tr>""")
    for r in sorted([r for r in report["results"] if not r["builtin"] or r["key"] == r["base"]],
                    key=lambda r: (r["market"], order.get(r["verdict"], 9), -r["pl"])):
        e = html.escape
        cls = r["verdict"].lower()
        rows.append(f"""<tr class="{cls}"><td><b>{e(r['name'])}</b><div class="src">{e(r['source'] or ('built in' if r['builtin'] else ''))}</div></td>
<td>{e(r['market'])}<div class="src">{e(r['timeframe'])} bars</div></td><td class="v {cls}">{e(r['verdict'])}<div class="src">{e(r['why'])}</div></td>
<td class="n">{r['trades']}</td><td class="n">{r['win_rate']:.0%}</td><td class="n {'up' if r['pl'] >= 0 else 'dn'}">{_money(r['pl'])}</td>
<td class="n {'up' if r['exam_pl'] >= 0 else 'dn'}">{_money(r['exam_pl'])}</td><td class="n">{r['profit_factor']:.2f}</td>
<td class="n">{_money(-r['max_drawdown'])}</td><td class="n">{r.get('breadth', 0):.0%}</td><td class="n">{r.get('beats_random', 0):.0%}</td><td class="n">{_money(r['buy_and_hold'])}</td></tr>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Proving Grounds</title><style>
:root{{--bg:#11160f;--panel:#182016;--ink:#efe6cf;--muted:#a9a48f;--gilt:#e2b65c;--up:#7fc46a;--dn:#e07a5f}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif;padding:20px 16px}}
h1{{font-family:Georgia,serif;color:var(--gilt);margin:0 0 4px}} h2{{font-family:Georgia,serif;color:var(--gilt);margin:28px 0 4px;font-size:20px}}
tr.best td{{background:#1d2a19}} p{{color:var(--muted);max-width:70ch}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:900px;background:var(--panel);border-radius:10px}}
th,td{{padding:8px 10px;border-bottom:1px solid #2c3628;text-align:left;vertical-align:top}} th{{color:var(--muted);font-weight:600;font-size:13px}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} .src{{color:var(--muted);font-size:12px;font-weight:400}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}} .v{{font-weight:700}} .v.passes{{color:var(--up)}} .v.promising{{color:var(--gilt)}} .v.fails{{color:var(--dn)}} .v.broken{{color:var(--dn)}} .v.today{{color:var(--muted)}}
tr.today td{{opacity:.85}}</style></head><body>
<h1>The Proving Grounds</h1>
<p>Tested {html.escape(report['run'].replace('T', ' at '))}. Every strategy traded ${report['trade_dollars']:.0f} per trade on real price history,
with trading costs, buying only. "Exam" is the most recent {report['exam_share']:.0%} of history: a strategy must make money there too.
"Buy &amp; hold" is what simply buying every symbol at the start and holding would have made, per $100.</p>
<div class="wrap"><table><thead><tr><th>Strategy</th><th>Market</th><th>Verdict</th><th class="n">Trades</th><th class="n">Wins</th>
<th class="n">Profit</th><th class="n">Exam</th><th class="n" title="money won ÷ money lost">Profit factor</th><th class="n" title="worst drop from a high point">Worst slump</th><th class="n" title="share of symbols it made money on">Symbols won</th><th class="n" title="share of make-believe traders, buying at random times, that it beat">Beats luck</th>
<th class="n">Buy &amp; hold</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Stops and exits for the heroes' current styles</h2>
<p>Each style tried with different ways of getting out: no stop, fixed stops, a smart stop sized to how jumpy each
symbol is, and "let winners build" (once a trade is up, ignore the sell signal and trail a stop behind the best
price). After any stop-loss, no buying that symbol back for 24 hours. The best for each style and market is marked.</p>
<div class="wrap"><table><thead><tr><th>Style and exit</th><th>Market</th><th class="n">Trades</th><th class="n">Wins</th>
<th class="n">Profit</th><th class="n">Exam</th><th class="n">Avg win / loss</th><th class="n">Avg hold</th><th class="n">Worst slump</th></tr></thead>
<tbody>{''.join(tune)}</tbody></table></div>
<p>Past results don't guarantee future ones. A strategy that passes here goes to a hero on paper money first.</p>
<p>The penny test uses today's busiest $1&ndash;$5 stocks and replays their last 6 months. It's a rough guide: stocks that
were pennies back then but aren't today are missing from it.</p></body></html>"""


def main():
    only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    print("The Proving Grounds: testing every strategy on real price history. This takes a few minutes.\n")
    report = run(only)
    print()
    for r in report["results"]:
        if not r["builtin"]:
            print(f"{r['verdict']:9}  {r['name']} [{r['market']}]  {_money(r['pl'])}, exam {_money(r['exam_pl'])}: {r['why']}")
    path = os.path.join(OUT_DIR, "report.html")
    print(f"\nFull report: {path}")
    if "--no-open" not in sys.argv:
        webbrowser.open("file:///" + path.replace("\\", "/"))


if __name__ == "__main__":
    main()
