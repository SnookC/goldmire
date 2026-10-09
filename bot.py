"""
Goldmire trading bots  --  PAPER TRADING ONLY (fake money)

Your bots live in bots.json (add more with add_bot.bat). Each bot:
  * has a watchlist of stocks or coins, kept fresh by the stock researcher or the
    crypto researcher (research.py) unless you set "research": false
    (penny bots find their own),
  * can hold several of them at once (max_positions),
  * splits its pot into equal slots, one slot per position,
  * reinvests profits; pot limits, savings and promotions live in bank.py.

Every few minutes each bot checks what it holds (sell?) and then its
watchlist (buy?). Everything is written to bot_log.txt.

These are learning bots, not money-makers.
"""

import os
import sys
import json
import time
import logging
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

import game
import bank
import research
import updater
import news
import exits
import report

# ---------------------------------------------------------------------------
# SETTINGS  (bots themselves are in bots.json)
# ---------------------------------------------------------------------------
BAR_MINUTES = 15              # size of each price bar
CHECK_EVERY_SECONDS = 300     # how often the bots wake up (5 minutes)

# Penny bots: what counts as a penny stock worth trading
PENNY_MIN_PRICE = 1.00        # skip stocks under $1 (delisting risk, wild spreads)
PENNY_MAX_PRICE = 5.00        # "penny stock" = under $5
PENNY_MIN_VOLUME = 1_000_000  # shares traded today, so it is easy to get in and out
PENNY_SCAN_SIZE = 15          # how many candidates to check each round
# ---------------------------------------------------------------------------

WORLD_PORT = 8777             # the world opens at http://localhost:8777/world.html

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS_FILE = os.path.join(HERE, "bots.json")
LOG_FILE = os.path.join(HERE, "bot_log.txt")
STATE_FILE = os.path.join(HERE, "bot_state.json")     # pots, savings, levels, what each bot holds
WORLD_DIR = os.path.join(HERE, "world")               # only this folder is shown in the browser
STATUS_FILE = os.path.join(WORLD_DIR, "status.json")

STRATEGY_NAMES = {"ma_cross": "trend follower", "rsi": "dip buyer", "breakout": "breakout hunter"}
KINDS = ("stock", "crypto", "penny")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("bot")

STOP = threading.Event()        # set by the tray icon's "Stop Goldmire"
RESTART = threading.Event()     # set after an update is installed: start Goldmire again
UPDATE_EVERY_HOURS = 6
LOCK_PORT = 8779                # held while Goldmire runs, so only one copy can trade at a time
PID_FILE = os.path.join(HERE, "goldmire.pid")
_lock = None


def single_instance():
    """True if this is the only Goldmire running. Two copies would place every trade twice."""
    global _lock
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        s.close()
        return False
    _lock = s
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    return True


def release_instance():
    global _lock
    if _lock:
        _lock.close()
        _lock = None
        try:
            os.remove(PID_FILE)
        except OSError:
            pass


def norm(symbol):
    """Alpaca shows crypto positions as BTCUSD; orders use BTC/USD. Compare without the slash."""
    return symbol.replace("/", "").upper()


# ---------------------------------------------------------------------------
# BOTS FILE
# ---------------------------------------------------------------------------
DEFAULT_BOTS = [
    {"name": "Stock-1", "hero": "Gareth the Steadfast", "class": "Knight", "kind": "stock", "strategy": "ma_cross",
     "dollars": 100, "max_positions": 3, "watchlist": ["SPY", "AAPL", "MSFT", "JPM"]},
    {"name": "Stock-2", "hero": "Wren of the Thicket", "class": "Ranger", "kind": "stock", "strategy": "rsi",
     "dollars": 100, "max_positions": 3, "watchlist": ["QQQ", "NVDA", "AMD", "AMZN"]},
    {"name": "Penny", "hero": "Pip Quickfingers", "class": "Rogue", "kind": "penny", "strategy": "breakout",
     "dollars": 100, "max_positions": 3, "watchlist": [], "stop_loss": 0.08, "take_profit": 0.15},
    {"name": "Crypto-1", "hero": "Old Bram", "class": "Alchemist", "kind": "crypto", "strategy": "ma_cross",
     "dollars": 100, "max_positions": 2, "watchlist": ["BTC/USD", "SOL/USD", "LTC/USD"]},
    {"name": "Crypto-2", "hero": "Ysolde the Hexweaver", "class": "Mage", "kind": "crypto", "strategy": "rsi",
     "dollars": 100, "max_positions": 2, "watchlist": ["ETH/USD", "DOGE/USD", "AVAX/USD"]},
]


# One-time changes to your heroes' settings, delivered with an update. Each is applied once,
# after backing up bots.json (bots.json.before-<id>.bak), and only to heroes with these names.
SETTINGS_UPDATES = [
    ("2026-10-07-proving-grounds", "changes from the first Proving Grounds report", {
        "Stock-2": {"strategy": "bollinger_bounce"},                     # the strategy that passed
        "Stock-1": {"stop_loss": "smart", "exit": "build"},              # let winners build
        "Penny": {"exit": "build", "take_profit": None},                 # no +15% cap; trail instead
        "Crypto-1": {"strategy": "parabolic_sar"},                       # slower, daily: far fewer fees
        "Crypto-2": {"strategy": "ichimoku_cloud"},
    }),
    ("2026-10-07-bench-pip", "Pip benched after the penny test (no new buys; holdings sold by his rules)", {
        "Penny": {"benched": True},
    }),
    ("2026-10-08-wider-nets", "more slots, trades sized by risk, Wren scans the 300 busiest stocks", {
        "Stock-1": {"max_positions": 12, "sizing": "risk"},
        "Stock-2": {"max_positions": 15, "sizing": "risk", "scan": 300},
        "Penny": {"max_positions": 10, "sizing": "risk"},
        "Crypto-1": {"max_positions": 10, "sizing": "risk"},
        "Crypto-2": {"max_positions": 10, "sizing": "risk"},
    }),
    ("2026-10-09-pip-back", "Pip back to work (trades sized by risk, so losses stay small)", {
        "Penny": {"benched": False},
    }),
]
TRAINING = []      # what the latest settings update changed, for the town chronicle


def apply_settings_updates():
    import shutil
    try:
        with open(BOTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    done = set(data.get("applied_updates", []))
    pending = [u for u in SETTINGS_UPDATES if u[0] not in done]
    if not pending:
        return
    for uid, title, changes in pending:
        shutil.copy2(BOTS_FILE, BOTS_FILE + f".before-{uid}.bak")
        for b in data.get("bots", []):
            for k, v in changes.get(b.get("name"), {}).items():
                if k == "strategy" and v not in STRATEGIES and v not in LEARNED:
                    log.error(f"Settings update: [{b['name']}] strategy '{v}' isn't installed; left as {b.get('strategy')}")
                    continue
                old = b.get(k, "(default)")
                if v is None:
                    b[k] = None
                else:
                    b[k] = v
                log.info(f"Settings update ({title}): [{b['name']}] {k}: {old} -> {v}")
                TRAINING.append((b, k, v))
        done.add(uid)
    data["applied_updates"] = sorted(done)
    tmp = BOTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, BOTS_FILE)


def load_bots():
    if not os.path.exists(BOTS_FILE):
        with open(BOTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"bots": DEFAULT_BOTS, "applied_updates": [u[0] for u in SETTINGS_UPDATES]}, f, indent=2)
    apply_settings_updates()
    with open(BOTS_FILE, encoding="utf-8") as f:
        bots = json.load(f)["bots"]
    for b in bots:
        b.setdefault("watchlist", [])
        b.setdefault("max_positions", 1)
        b["watchlist"] = [s.strip().upper() for s in b["watchlist"] if s.strip()]
    return bots


def check_config(bots):
    problems = []
    names = [b.get("name") for b in bots]
    if len(set(names)) != len(names):
        problems.append("two bots have the same name")
    for b in bots:
        n = b.get("name", "?")
        if b.get("kind") not in KINDS:
            problems.append(f"[{n}] kind must be one of {', '.join(KINDS)}")
        if b.get("strategy") not in STRATEGIES and b.get("strategy") not in LEARNED:
            problems.append(f"[{n}] strategy must be one of {', '.join(list(STRATEGIES) + list(LEARNED))}")
        if not isinstance(b.get("dollars"), (int, float)) or b["dollars"] <= 0:
            problems.append(f"[{n}] dollars must be a number above 0")
        if not isinstance(b.get("max_positions"), int) or b["max_positions"] < 1:
            problems.append(f"[{n}] max_positions must be 1 or more")
        if b.get("sizing", "split") not in ("split", "risk"):
            problems.append(f"[{n}] sizing must be \"split\" or \"risk\"")
        if b.get("scan") and (b.get("kind") != "stock" or not isinstance(b["scan"], int) or not 10 <= b["scan"] <= 1000):
            problems.append(f"[{n}] scan is for stock heroes: a number from 10 to 1000")
        if b.get("kind") in ("stock", "crypto") and not b["watchlist"] and not b.get("research", True):
            problems.append(f"[{n}] needs at least one symbol in its watchlist (or turn research on)")
        if b.get("kind") == "crypto" and any("/" not in s for s in b["watchlist"]):
            problems.append(f"[{n}] crypto symbols look like BTC/USD")
    if problems:
        for p in problems:
            log.error("SETTINGS PROBLEM in bots.json: " + p)
        sys.exit(1)


def load_keys():
    """Read keys from the .env file next to this script. Stops if anything is wrong."""
    load_dotenv(os.path.join(HERE, ".env"))
    key = os.getenv("ALPACA_API_KEY", "").strip()
    secret = os.getenv("ALPACA_SECRET_KEY", "").strip()
    paper = os.getenv("ALPACA_PAPER", "true").strip().lower()

    if not key or not secret or "PASTE" in key or "PASTE" in secret:
        log.error("Your keys are not filled in yet. Double-click open_keys_file.bat, paste them in, save, and try again.")
        sys.exit(1)

    # Safety lock: this kit refuses to touch real money.
    if paper != "true":
        log.error("SAFETY LOCK: ALPACA_PAPER must be 'true'. These bots only run on paper trading.")
        sys.exit(1)
    if not key.startswith("PK"):
        log.error("SAFETY LOCK: that key does not look like a PAPER key (paper keys start with 'PK'). "
                  "Make the keys from the Paper Trading dashboard.")
        sys.exit(1)
    return key, secret


# ---------------------------------------------------------------------------
# STRATEGIES  -- each takes a list of closing prices, returns "buy", "sell" or None
# ---------------------------------------------------------------------------
def _avg(values, n):
    return sum(values[-n:]) / n


def ma_cross(closes, fast=10, slow=30):
    """Trend follower: buy when the 10-bar average crosses above the 30-bar average, sell on the reverse."""
    if len(closes) < slow + 1:
        return None
    fast_now, slow_now = _avg(closes, fast), _avg(closes, slow)
    fast_prev, slow_prev = _avg(closes[:-1], fast), _avg(closes[:-1], slow)
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "buy"
    if fast_prev >= slow_prev and fast_now < slow_now:
        return "sell"
    return None


def rsi_value(closes, period=14):
    gains = losses = 0.0
    for a, b in zip(closes[-period - 1:-1], closes[-period:]):
        change = b - a
        if change > 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


def rsi(closes, period=14, low=30, high=70):
    """Dip buyer: buy when RSI drops below 30 (oversold), sell when it rises above 70 (overbought)."""
    if len(closes) < period + 1:
        return None
    value = rsi_value(closes, period)
    if value < low:
        return "buy"
    if value > high:
        return "sell"
    return None


def breakout(closes, entry=20, exit_=10):
    """Breakout: buy when price beats the highest close of the last 20 bars, sell when it falls below the lowest of the last 10."""
    if len(closes) < entry + 1:
        return None
    price = closes[-1]
    if price > max(closes[-entry - 1:-1]):
        return "buy"
    if price < min(closes[-exit_ - 1:-1]):
        return "sell"
    return None


STRATEGIES = {"ma_cross": ma_cross, "rsi": rsi, "breakout": breakout}

# Strategies learned from books and websites (the strategies folder). A hero uses one by
# setting "strategy" to its file name in bots.json (promote.py does that for you), ideally
# only after it PASSES in the Proving Grounds (backtest.py).
try:
    import backtest as _bt
    LEARNED = _bt.file_strategies(lambda msg: log.error(f"Strategies folder: {msg}"))
except Exception as _e:  # noqa: BLE001 - a broken strategies folder must never stop the heroes
    log.error(f"Strategies folder couldn't be read ({_e}); heroes use the built-in styles only.")
    LEARNED = {}
for _k, _st in LEARNED.items():
    STRATEGY_NAMES.setdefault(_k, _st.name)
    research.STYLES[_k] = _st.style
TIMEFRAME_SECONDS = {"15Min": 900, "1Hour": 3600, "1Day": 86400}
HISTORY_FOR = {"15Min": 20, "1Hour": 70, "1Day": 460}     # calendar days of bars to fetch (~300 bars)
_DAILY_BARS = {}           # (kind, symbol) -> (New York date, finished daily bars), shared by every round that day


# ---------------------------------------------------------------------------
# ONE ROUND OF MARKET DATA (fetched once, shared by every bot)
# ---------------------------------------------------------------------------
class Round:
    def __init__(self, trading, stock_data, crypto_data, screener, market_open):
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        self.trading, self.stock_data, self.crypto_data, self.screener = trading, stock_data, crypto_data, screener
        self.market_open = market_open
        self.positions = {norm(p.symbol): p for p in trading.get_all_positions()}
        self.open_orders = {norm(o.symbol) for o in trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))}

    def closes(self, symbols, kind):
        """Price history for several symbols in one request: {symbol: [closes]}."""
        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed
        if not symbols:
            return {}
        tf = TimeFrame(BAR_MINUTES, TimeFrameUnit.Minute)
        start = datetime.now(timezone.utc) - timedelta(days=5)
        if kind == "crypto":
            bars = self.crypto_data.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=list(symbols), timeframe=tf, start=start))
        else:
            bars = self.stock_data.get_stock_bars(StockBarsRequest(symbol_or_symbols=list(symbols), timeframe=tf, start=start, feed=DataFeed.IEX))
        return {s: [b.close for b in bars.data.get(s, [])] for s in symbols}

    def bars(self, symbols, kind, timeframe):
        """Finished bars (open/high/low/close/volume/time) at a learned strategy's timeframe.
        The bar still in progress is left out, exactly like the Proving Grounds."""
        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed
        symbols = [s for s in symbols if s]
        cache = self.__dict__.setdefault("_bars", {})
        if timeframe == "1Day":                   # finished daily bars only change once a day: keep them all day
            stamp = report.ny().strftime("%Y-%m-%d")
            for s in symbols:
                kept = _DAILY_BARS.get((kind, s))
                if kept and kept[0] == stamp:
                    cache.setdefault((s, timeframe), kept[1])
        need = [s for s in symbols if (s, timeframe) not in cache]
        if need:
            tf = {"15Min": TimeFrame(15, TimeFrameUnit.Minute), "1Hour": TimeFrame.Hour, "1Day": TimeFrame.Day}[timeframe]
            start = datetime.now(timezone.utc) - timedelta(days=HISTORY_FOR[timeframe])
            for i in range(0, len(need), 100):    # 100 symbols per request
                part = need[i:i + 100]
                if kind == "crypto":
                    got = self.crypto_data.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=part, timeframe=tf, start=start))
                else:
                    got = self.stock_data.get_stock_bars(StockBarsRequest(symbol_or_symbols=part, timeframe=tf, start=start, feed=DataFeed.IEX))
                now = datetime.now(timezone.utc)
                for s in part:
                    rows = [r for r in got.data.get(s, []) if (now - r.timestamp).total_seconds() >= TIMEFRAME_SECONDS[timeframe]]
                    cache[(s, timeframe)] = {"o": [float(r.open) for r in rows], "h": [float(r.high) for r in rows],
                                             "l": [float(r.low) for r in rows], "c": [float(r.close) for r in rows],
                                             "v": [float(r.volume or 0) for r in rows], "t": [r.timestamp for r in rows]}
                    if timeframe == "1Day":
                        _DAILY_BARS[(kind, s)] = (report.ny().strftime("%Y-%m-%d"), cache[(s, timeframe)])
        return {s: cache.get((s, timeframe), {"o": [], "h": [], "l": [], "c": [], "v": [], "t": []}) for s in symbols}


# ---------------------------------------------------------------------------
# PENNY STOCK SCANNER
# ---------------------------------------------------------------------------
_asset_cache = {}


def penny_ok_asset(trading, symbol):
    """Only plain, active, tradable stocks on major US exchanges (no OTC, warrants, units, or leveraged/inverse funds)."""
    if not symbol.isalpha() or len(symbol) > 5:
        return False
    if len(symbol) == 5 and symbol[-1] in "WRU":   # warrants, rights, units
        return False
    if symbol not in _asset_cache:
        try:
            a = trading.get_asset(symbol)
            exch = str(getattr(a.exchange, "value", a.exchange)).upper()
            status = str(getattr(a.status, "value", a.status)).lower()
            _asset_cache[symbol] = bool(a.tradable) and status == "active" and exch in (
                "NYSE", "NASDAQ", "AMEX", "ARCA", "NYSEARCA", "BATS") and not research.is_leveraged_name(getattr(a, "name", ""))
        except Exception:
            _asset_cache[symbol] = False
    return _asset_cache[symbol]


def find_penny_candidates(trading, stock_data, screener, skip=()):
    """Most-traded stocks today, filtered to $1-$5 with real volume. Busiest first."""
    from alpaca.data.requests import MostActivesRequest, StockLatestTradeRequest
    from alpaca.data.enums import MostActivesBy
    from alpaca.data.enums import DataFeed
    actives = screener.get_most_actives(MostActivesRequest(top=100, by=MostActivesBy.VOLUME)).most_actives
    busy = {a.symbol: a.volume for a in actives if a.volume >= PENNY_MIN_VOLUME and norm(a.symbol) not in skip}
    if not busy:
        return []
    trades = stock_data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=list(busy), feed=DataFeed.IEX))
    picks = []
    for sym, vol in sorted(busy.items(), key=lambda kv: -kv[1]):
        t = trades.get(sym)
        if t and PENNY_MIN_PRICE <= float(t.price) <= PENNY_MAX_PRICE and penny_ok_asset(trading, sym):
            picks.append((sym, float(t.price)))
    return picks[:PENNY_SCAN_SIZE]


# ---------------------------------------------------------------------------
# BUY / SELL
# ---------------------------------------------------------------------------
def held_by(memory, bot):
    return memory.setdefault("held", {}).setdefault(bot["name"], {})


def taken_by_others(memory, bot, rnd):
    """Symbols this bot must not buy: held by another bot, or a position you opened by hand."""
    mine = {norm(s) for s in held_by(memory, bot)}
    ours = {norm(s) for name, h in memory.get("held", {}).items() for s in h}
    return (ours - mine) | (set(rnd.positions) - ours)


def place_buy(rnd, bot, memory, symbol, dollars, price=None):
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    tif = TimeInForce.GTC if bot["kind"] == "crypto" else TimeInForce.DAY
    order, cost, how = None, dollars, f"${dollars:,.2f}"
    if bot["kind"] != "penny":
        try:
            order = rnd.trading.submit_order(MarketOrderRequest(symbol=symbol, notional=round(dollars, 2), side=OrderSide.BUY, time_in_force=tif))
        except Exception as e:
            if not price:
                raise
            log.info(f"[{bot['name']}] {symbol}: dollar order refused ({e}); buying whole shares instead")
    if order is None:   # penny stocks, or stocks that can't be bought in fractions
        qty = int(dollars // price) if price else 0
        if qty < 1:
            log.info(f"[{bot['name']}] {symbol}: ${dollars:,.2f} is not enough for one share at ${price:,.2f}")
            return False
        order = rnd.trading.submit_order(MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=tif))
        cost, how = qty * price, f"{qty} shares at about ${price:,.2f}"
    held_by(memory, bot)[symbol] = {"cost": round(cost, 2), "opened": datetime.now().isoformat(timespec="seconds")}
    report.note(memory, side="buy", bot=bot["name"], symbol=symbol, dollars=round(cost, 2), price=price)
    rnd.open_orders.add(norm(symbol))
    game.record_buy(memory, bot, symbol)
    save_memory(memory)
    log.info(f"[{bot['name']}] BUY  {symbol}  {how}  (order {order.id})")
    return True


def place_sell(trading, bot, memory, symbol, position=None, reason=""):
    try:
        position = position or trading.get_open_position(norm(symbol))
        locked_in = float(position.unrealized_pl)
    except Exception:
        locked_in = 0.0
    trading.close_position(norm(symbol))
    h = held_by(memory, bot).pop(symbol, None) or {}
    report.note(memory, side="sell", bot=bot["name"], symbol=symbol, pl=round(locked_in, 2), reason=reason, cost=h.get("cost"),
                paid=getattr(position, "avg_entry_price", None), price=getattr(position, "current_price", None))
    memory["realized"][bot["name"]] = memory["realized"].get(bot["name"], 0.0) + locked_in
    memory["trades"] = memory.get("trades", 0) + 1
    game.record_sell(memory, bot, symbol, locked_in, reason)
    events = bank.apply_result(memory, bot, locked_in)
    game.record_bank(memory, bot, events)
    save_memory(memory)
    log.info(f"[{bot['name']}] SELL {symbol}  closed  (about ${locked_in:+.2f}){'  ' + reason if reason else ''}")
    for kind, amount in events:
        if kind == "saved":
            log.info(f"[{bot['name']}] SAVINGS  ${amount:,.2f} moved to savings (pot is at its limit)")
        elif kind == "promoted":
            log.info(f"[{bot['name']}] PROMOTED  pot limit raised to ${amount:,}")
        elif kind == "benched":
            log.info(f"[{bot['name']}] BENCHED  pot is down to ${amount:,.2f}, too small to trade")


# ---------------------------------------------------------------------------
# ONE BOT, ONE ROUND
# ---------------------------------------------------------------------------
def _learned_signal(st, bars, position=None):
    view = {k: bars[k][-st.lookback:] for k in ("o", "h", "l", "c", "v")}
    try:
        return st.signal(view, position) if st.wants_position else st.signal(view)
    except Exception as e:  # noqa: BLE001 - a strategy hiccup skips this symbol, it doesn't stop the hero
        log.error(f"strategy {st.key}: {type(e).__name__}: {e}")
        return None


def learned_strategy(bot, rnd, memory):
    """Turns a learned strategy (open/high/low/close bars, knows the entry price) into the
    closes-in, buy/sell-out shape run_bot uses, for the symbols it will look at this round."""
    st = LEARNED[bot["strategy"]]
    kind = "crypto" if bot["kind"] == "crypto" else "stock"
    held = held_by(memory, bot)

    def fetch(symbols):
        return rnd.bars(symbols, kind, st.timeframe)

    def decide(sym, bars):
        if norm(sym) in rnd.positions and sym in held:
            pos = rnd.positions[norm(sym)]
            opened = held[sym].get("opened", "")
            try:
                since = datetime.fromisoformat(opened).astimezone(timezone.utc)
                bars_held = sum(1 for t in bars["t"] if t >= since)
            except (TypeError, ValueError):
                bars_held = 0
            return _learned_signal(st, bars, {"entry": float(pos.avg_entry_price), "bars_held": bars_held})
        return _learned_signal(st, bars, None)
    return st, fetch, decide


def run_bot(bot, rnd, memory):
    name, kind = bot["name"], bot["kind"]
    if kind != "crypto" and not rnd.market_open:
        log.info(f"[{name}] market closed, waiting")
        return
    if bot["strategy"] in LEARNED:
        st, fetch_bars, decide = learned_strategy(bot, rnd, memory)
        bot = {**bot, "stop_loss": bot.get("stop_loss", st.stop_loss), "take_profit": bot.get("take_profit", st.take_profit)}
        strategy = None
    else:
        strategy = STRATEGIES[bot["strategy"]]
    held = held_by(memory, bot)

    # 1) Tidy up: forget buys that never filled (or positions you closed by hand)
    for sym in list(held):
        if norm(sym) not in rnd.positions and norm(sym) not in rnd.open_orders:
            log.info(f"[{name}] {sym}: no longer held (order didn't fill or was closed by hand)")
            report.note(memory, side="gone", bot=name, symbol=sym, note="the buy didn't fill, or it was closed outside Goldmire")
            held.pop(sym)
            save_memory(memory)

    # 2) Watch what we hold: bad news, stop-loss, "let it build" trailing stop, take-profit,
    #    or the style saying sell (see exits.py)
    holding = [s for s in held if norm(s) in rnd.positions]
    closes = fetch_bars(holding) if strategy is None else rnd.closes(holding, kind)
    stop_setting = bot.get("stop_loss", exits.DEFAULT_STOP)
    exit_mode = bot.get("exit", exits.DEFAULT_EXIT)
    tf = LEARNED[bot["strategy"]].timeframe if strategy is None else "15Min"
    market = "crypto" if kind == "crypto" else "stock"
    for sym in holding:
        pos = rnd.positions[norm(sym)]
        change = float(pos.unrealized_plpc)
        recent = closes[sym]["c"] if strategy is None else closes.get(sym, [])
        signal = decide(sym, closes[sym]) if strategy is None else strategy(recent)
        h = held[sym]
        if "stop" not in h:                       # bought before stops existed: size one now
            h["stop"] = exits.stop_fraction(stop_setting, recent, market, tf)
        stop = h["stop"]
        entry = float(getattr(pos, "avg_entry_price", 0) or 0)
        price = float(getattr(pos, "current_price", 0) or 0) or (entry * (1 + change) if entry else 0)
        if price:
            h["peak"] = max(h.get("peak") or price, price)
        boost = news.boost_for(memory, sym) if bot.get("news_hold", True) else None
        trail = stop or 0.08
        building = exits.trailing_active(exit_mode, stop, entry, h.get("peak") or 0) or bool(boost and h.get("peak"))
        log.info(f"[{name}] holding {sym}: {change:+.1%}  signal={signal}"
                 + (f"  stop {stop:.1%}" if stop else "")
                 + (f'  (riding good news: "{boost["headline"]}")' if boost else "  (letting it build)" if building else ""))
        reason = None
        alarm = news.alarm_for(memory, sym)
        if alarm and bot.get("news_exit", True):
            reason = f'(bad news: "{alarm["headline"]}")'
        elif building and price and price <= h["peak"] * (1 - trail):
            reason = (f"(good-news run over: trailing stop, {price / h['peak'] - 1:+.1%} from its best, trade at {change:+.1%})" if boost else
                      f"(let it build: trailing stop, {price / h['peak'] - 1:+.1%} from its best, trade at {change:+.1%})")
        elif not building and stop and change <= -stop:
            reason = f"(stop-loss at {change:+.1%})"
        elif bot.get("take_profit") and change >= bot["take_profit"]:
            reason = f"(take-profit at {change:+.1%})"
        elif signal == "sell" and not building:
            reason = f"({STRATEGY_NAMES[bot['strategy']]} says sell)"
        if reason:
            place_sell(rnd.trading, bot, memory, sym, pos, reason)
            if "stop-loss" in reason or "bad news" in reason:      # no buying it straight back
                until = datetime.now(timezone.utc) + timedelta(hours=exits.COOLDOWN_HOURS)
                memory.setdefault("cooldown", {}).setdefault(name, {})[sym] = until.isoformat(timespec="seconds")
                save_memory(memory)

    # 3) Look for new buys if there are free slots (not while you've benched this hero)
    if bot.get("benched"):
        if not held:
            log.info(f"[{name}] on the bench (you benched this hero): no new buys")
        return
    free_slots = bot["max_positions"] - len(held)
    if free_slots <= 0:
        return
    committed = sum(h["cost"] for h in held.values())
    size = bank.slot_size(memory, bot, committed)
    if bot.get("sizing") == "risk":           # sized per trade below; here just: is there money left?
        size = round(bank.trade_size(memory, bot) - committed, 2)
    if size < bank.MIN_TRADE:
        if not held:
            log.info(f"[{name}] benched: pot too small to trade")
        return
    skip = taken_by_others(memory, bot, rnd) | {norm(s) for s in held}
    cool = memory.get("cooldown", {}).get(name, {})
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for s_, until in list(cool.items()):
        if until <= now_iso:
            cool.pop(s_)                      # cool-down over
        else:
            skip.add(norm(s_))
    if kind == "penny":
        picks = find_penny_candidates(rnd.trading, rnd.stock_data, rnd.screener, skip=skip)
        prices = dict(picks)
        candidates = [s for s, _ in picks]
    else:
        candidates = [s for s in research.watchlist(bot, memory) if norm(s) not in skip]
        prices = {}
    blocked = [s for s in candidates if news.alarm_for(memory, s)]
    if blocked:
        log.info(f"[{name}] skipping {', '.join(blocked)}: fresh bad news")
        candidates = [s for s in candidates if s not in blocked]
    if not candidates:
        log.info(f"[{name}] nothing new to look at this round")
        return
    closes = fetch_bars(candidates) if strategy is None else rnd.closes(candidates, kind)
    bought = 0
    for sym in candidates:
        if strategy is None:
            c = closes[sym]["c"]
            if decide(sym, closes[sym]) != "buy":
                continue
        else:
            c = closes.get(sym, [])
            if strategy(c) != "buy":
                continue
        mk, tf = "crypto" if kind == "crypto" else "stock", LEARNED[bot["strategy"]].timeframe if strategy is None else "15Min"
        stop = exits.stop_fraction(bot.get("stop_loss", exits.DEFAULT_STOP), c, mk, tf)
        # risk sizing measures risk by the stop, or (a technique without a stop) by how jumpy the stock is
        risk = stop or exits.stop_fraction("smart", c, mk, tf)
        size = bank.slot_size(memory, bot, committed, risk)
        if size < bank.MIN_TRADE:
            break                                 # the pot is spent
        if bot.get("sizing") == "risk" and risk:
            log.info(f"[{name}] {sym}: {'stop' if stop else 'a typical bad move'} is {risk:.1%}, so ${size:,.2f} risks about ${size * risk:,.2f} of the pot")
        if place_buy(rnd, bot, memory, sym, size, prices.get(sym) or (c[-1] if c else None)):
            h = held_by(memory, bot)[sym]
            h["stop"] = stop
            h["peak"] = c[-1] if c else None
            save_memory(memory)
            bought += 1
            committed += h.get("cost", size)
            if bought >= free_slots:
                break
    if not bought:
        shown = ", ".join(candidates[:6]) + ("..." if len(candidates) > 6 else "")
        log.info(f"[{name}] checked {shown}: no buy signals")


# ---------------------------------------------------------------------------
# MEMORY + LIVING WORLD
# ---------------------------------------------------------------------------
def load_memory():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        m = {}
    m.setdefault("realized", {})
    m.setdefault("trades", 0)
    m.setdefault("held", {})
    if "penny" in m:   # older single-stock penny format
        old = m.pop("penny")
        if old.get("symbol"):
            m["held"].setdefault("Penny", {})[old["symbol"]] = {"cost": old.get("bought_at", 0) * old.get("qty", 0), "opened": ""}
    return m


def save_memory(memory):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
    os.replace(tmp, STATE_FILE)


def build_status(positions, memory, market_open, bots):
    """positions: {SYMBOL (no slash): alpaca position}. Returns the dict the world reads."""
    out = []
    rs = memory.get("research", {})
    for b in bots:
        held = held_by(memory, b)
        wl = research.watchlist(b, memory)
        pos_list = []
        for sym, h in held.items():
            p = positions.get(norm(sym))
            pos_list.append({"symbol": sym, "cost": h["cost"], "pl": round(float(p.unrealized_pl), 2) if p else 0.0,
                             "pending": p is None})
        realized = round(memory["realized"].get(b["name"], 0.0), 2)
        unrealized = round(sum(p["pl"] for p in pos_list), 2)
        out.append({
            "name": b["name"], "kind": b["kind"], "strategy": b["strategy"], "benched": bool(b.get("benched")),
            "strategy_name": STRATEGY_NAMES[b["strategy"]], "watchlist": [] if research.scan_size(b) else wl,
            "scan": research.scan_size(b), "scanning": len(wl) if research.scan_size(b) else 0,
            "researched": research.is_researched(b),
            "reasons": {} if research.scan_size(b) else rs.get("reasons", {}).get(b["name"], {}),
            "max_positions": b["max_positions"], "positions": pos_list, "holding": bool(pos_list),
            "symbol": ", ".join(p["symbol"] for p in pos_list) or ("penny stocks" if b["kind"] == "penny" else f"the {len(wl)} busiest stocks" if research.scan_size(b) else ", ".join(wl[:3])),
            "realized_pl": realized, "unrealized_pl": unrealized, "pl": round(realized + unrealized, 2),
            "hero": game.hero_block(memory, b), "bank": bank.status(memory, b), "dollars": bank.trade_size(memory, b),
        })
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "market_open": bool(market_open),
        "budget": max(500, round(sum(b["dollars"] for b in out))),
        "savings_total": round(sum(b["bank"]["savings"] for b in out), 2),
        "total_pl": round(sum(b["pl"] for b in out), 2),
        "trades": memory.get("trades", 0),
        "research": {m: {"name": game.RESEARCHERS[m], "last_run": rs.get(m, {}).get("last_run"),
                         "every_minutes": research.EVERY_MINUTES[m],
                         "leads_studied": rs.get(m, {}).get("leads_studied", 0),
                         "news_seen": rs.get(m, {}).get("news_seen", 0),
                         "good_news": rs.get(m, {}).get("good_news", 0),
                         "bad_news": rs.get(m, {}).get("bad_news", 0)} for m in research.MARKETS},
        "news": {"crier": memory.get("news", {}).get("crier", [])[:8],
                 "alarms": [{"symbol": a["symbol"], "headline": a["headline"], "time": a["time"]}
                            for a in memory.get("news", {}).get("alarms", {}).values()]},
        "bots": out,
    }


def write_status(status):
    os.makedirs(WORLD_DIR, exist_ok=True)
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp, STATUS_FILE)


def update_world(trading, memory, market_open, bots):
    try:
        positions = {norm(p.symbol): p for p in trading.get_all_positions()}
    except Exception as e:
        log.error(f"World: could not read positions -> {e}")
        return
    status = build_status(positions, memory, market_open, bots)
    status["game"] = game.tick(memory, status["bots"], status["total_pl"], status["budget"])
    try:
        account = trading.get_account()
    except Exception:  # noqa: BLE001
        account = None
    try:
        report.maybe_archive(memory, bots, positions, account, log.info)
        status["today"] = report.build(memory, bots, positions, account, norm=norm)
        status["today"]["archive"] = report.index_days()
    except Exception as e:  # noqa: BLE001 - the ledger is a bonus; never stop the heroes over it
        log.error(f"Day's Ledger: couldn't build today's report -> {e}")
    save_memory(memory)
    write_status(status)
    log.info(f"World: total bot profit/loss ${status['total_pl']:+.2f}")


class _QuietHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                      ".js": "text/javascript; charset=utf-8", ".webmanifest": "application/manifest+json"}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=WORLD_DIR, **k)

    def _json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/update":
            self.send_error(404)
            return
        # Only the Goldmire page sends this header; other websites can't (the browser blocks them).
        if self.headers.get("X-Goldmire") != "update":
            self.send_error(403)
            return
        ok, msg = start_update()
        self._json(202 if ok else 409, {**update_report(), "message": msg})

    def do_GET(self):
        if self.path.split("?")[0] == "/api/update":
            if "check=1" in self.path:
                check_for_update(quiet=True)
            self._json(200, update_report())
            return
        if self.path.split("?")[0] in ("/", "/index.html"):   # the phone app's home is the town page
            self.send_response(302)
            self.send_header("Location", "/world.html")
            self.end_headers()
            return
        super().do_GET()

    def list_directory(self, path):   # never show a file listing
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")   # phones always get the latest numbers and page
        super().end_headers()

    def log_message(self, *a):
        pass


def start_world_server(open_browser=True):
    os.makedirs(WORLD_DIR, exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", WORLD_PORT), _QuietHandler)  # this PC only
    except OSError:
        log.error(f"World: port {WORLD_PORT} is busy (is another bot window open?). Bots keep running without it.")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _servers.append(server)
    url = f"http://localhost:{WORLD_PORT}/world.html"
    log.info(f"World is live at {url}")
    link = os.path.join(HERE, "phone_link.txt")
    if os.path.exists(link):
        with open(link, encoding="utf-8") as f:
            log.info(f"On your phone (via Tailscale): {f.read().strip()}")
    if open_browser:
        webbrowser.open(url)
    return server


# ---------------------------------------------------------------------------
# UPDATES  (see updater.py)
# ---------------------------------------------------------------------------
_servers = []
UPDATE = {"state": "idle", "available": None, "error": "", "checked": None, "log": []}
_update_lock = threading.Lock()


def update_report():
    return {"version": updater.current_version(), "enabled": updater.source() is not None,
            "available": UPDATE["available"], "state": UPDATE["state"], "error": UPDATE["error"],
            "checked": UPDATE["checked"], "steps": UPDATE["log"][-6:]}


def check_for_update(quiet=False):
    """Looks for a newer version (at most once a minute). Returns the update found, or None."""
    last = UPDATE.get("_t", 0)
    if quiet and time.time() - last < 60:
        return UPDATE["available"]
    UPDATE["_t"] = time.time()
    try:
        found = updater.check()
    except updater.UpdateError as e:
        if not quiet:
            log.info(f"Updates: {e}")
        return UPDATE["available"]
    UPDATE["checked"] = datetime.now(timezone.utc).isoformat()
    if found and found != UPDATE["available"]:
        log.info(f"Updates: Goldmire {found['version']} is out. Press 'Update' in the town or the tray icon's menu.")
    UPDATE["available"] = found
    return found


def _update_watch():
    if STOP.wait(30):
        return
    while True:
        if updater.source():
            check_for_update()
        if STOP.wait(UPDATE_EVERY_HOURS * 3600):
            return


def start_update():
    """Installs the waiting update in the background, then restarts Goldmire. Returns (started, message)."""
    with _update_lock:
        if UPDATE["state"] in ("installing", "restarting"):
            return False, "An update is already being installed."
        if not UPDATE["available"]:
            check_for_update()
        if not UPDATE["available"]:
            return False, "You already have the latest version."
        UPDATE.update(state="installing", error="", log=[])
    target = UPDATE["available"]["version"]

    def say(msg):
        UPDATE["log"].append(msg)
        log.info(f"Updates: {msg}")

    def work():
        try:
            updater.install(target, say=say)
        except updater.UpdateError as e:
            UPDATE.update(state="failed", error=str(e))
            log.error(f"Updates: {e}")
            return
        except Exception as e:  # noqa: BLE001
            UPDATE.update(state="failed", error=f"{type(e).__name__}: {e}")
            log.exception("Updates: unexpected problem")
            return
        UPDATE.update(state="restarting")
        say("Restarting Goldmire...")
        RESTART.set()
        STOP.set()

    threading.Thread(target=work, name="goldmire-update", daemon=True).start()
    return True, f"Installing Goldmire {target}..."


def watch_news(news_client, bots, memory):
    """Every round: read the newest stories. Big good news sends a researcher out now;
    big bad news raises an alarm (no buys, and bots holding it sell)."""
    try:
        found = news.watch(news_client, memory, lambda msg: log.info(f"Town Crier: {msg}"))
    except Exception as e:  # noqa: BLE001 - news is a bonus; never stop the bots over it
        log.error(f"Town Crier: couldn't read the news this round -> {e}")
        return
    researched = {research.market_of(b) for b in bots if research.is_researched(b)}
    for market, tips in found["tips"].items():
        if not tips:
            continue
        sym, story = tips[0]
        game.record_news(memory, True, sym, news.short(story["headline"], 90), market)
        log.info(f"Town Crier: good news on {', '.join(dict.fromkeys(s for s, _ in tips))}: \"{news.short(story['headline'])}\"")
        if market in researched:
            research._research_memory(memory)[market]["rush"] = True
            log.info(f"Town Crier: {game.RESEARCHER_SHORT[market]} heads out early to look into it.")
    held = {research.newsdesk.to_trade_symbol(s).replace("/", "") for h in memory.get("held", {}).values() for s in h}
    told = set()
    for sym, story in found["alarms"]:
        if sym in told:
            continue
        told.add(sym)
        game.record_news(memory, False, sym, news.short(story["headline"], 90), "crypto" if "/" in sym else "stock")
        log.info(f"Town Crier: bad news on {sym}: \"{news.short(story['headline'])}\""
                 + (" - heroes holding it get out this round." if sym.replace("/", "") in held else " - no hero will buy it for now."))
    save_memory(memory)


def run_research(market, trading, stock_data, crypto_data, screener, news_client, bots, memory):
    who = game.RESEARCHER_SHORT[market]
    log.info(f"{who}: researching new {market} leads...")
    picks = research.run(market, trading, stock_data, crypto_data, screener, news_client, bots, memory,
                         lambda msg: log.info(f"{who}: {msg}"))
    for b in bots:
        p = picks.get(b["name"])
        if not p:
            continue
        if p.get("scan"):                         # a 300-stock list: a summary, not every name
            log.info(f"{who}: [{b['name']}] scanning the {len(p['watchlist'])} busiest stocks "
                     f"({', '.join(p['watchlist'][:8])}...), {len(p['added'])} new today, {len(p['dropped'])} dropped")
            continue                              # the town only hears about what she actually buys
        log.info(f"{who}: [{b['name']}] watchlist -> {', '.join(p['watchlist']) or '(nothing fits today)'}")
        for sym in p["added"]:
            log.info(f"    + {sym}: {p['reasons'].get(sym, '')}")
        if p["dropped"]:
            log.info(f"    - dropped {', '.join(p['dropped'])}")
        game.record_research(memory, b, p["added"], p["dropped"])
    info = memory.get("research", {}).get(market, {})
    when = (f"Next {market} research in {research.EVERY_MINUTES[market]} min"
            + (" of market hours." if market == "stock" else "."))
    log.info(f"{who}: studied {info.get('leads_studied', 0)} leads and {info.get('news_seen', 0)} news mentions. {when}")
    save_memory(memory)


def main():
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.historical.news import NewsClient

    if not single_instance():
        log.error("Goldmire is already running (look for its icon by the clock, or another Goldmire window). "
                  "Only one copy can run at a time.")
        sys.exit(2)
    try:
        _run(TradingClient, StockHistoricalDataClient, CryptoHistoricalDataClient, ScreenerClient, NewsClient)
    finally:
        for server in _servers:          # free the town's port, so a restarted Goldmire can use it
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        _servers.clear()
        release_instance()
        log.info("Goldmire is restarting with the new version." if RESTART.is_set() else "Goldmire stopped.")


def _run(TradingClient, StockHistoricalDataClient, CryptoHistoricalDataClient, ScreenerClient, NewsClient):
    bots = load_bots()
    check_config(bots)
    key, secret = load_keys()
    trading = TradingClient(key, secret, paper=True)   # paper=True is hard-coded on purpose
    stock_data = StockHistoricalDataClient(key, secret)
    crypto_data = CryptoHistoricalDataClient(key, secret)
    screener = ScreenerClient(key, secret)
    news_client = NewsClient(key, secret)

    memory = load_memory()
    taught = {}
    for b, k, v in TRAINING:
        h = game.hero_of(b)[0]
        what = (f"the {STRATEGY_NAMES.get(v, v)} technique" if k == "strategy" else "letting winners build" if (k, v) == ("exit", "build")
                else "a smart stop" if (k, v) == ("stop_loss", "smart")
                else f"juggling up to {v} trades at once" if k == "max_positions"
                else "sizing each trade by its risk" if (k, v) == ("sizing", "risk")
                else f"scanning the {v} busiest stocks" if k == "scan" else None)
        if (k, v) == ("benched", True):
            game.record_bench(memory, h)
            continue
        if k == "benched" and not v:
            game.record_unbench(memory, h)
            continue
        if what:
            taught.setdefault((h, k in ("max_positions", "sizing", "scan")), []).append(what)
    for (h, orders), whats in taught.items():
        joined = ", ".join(whats[:-1]) + (" and " if len(whats) > 1 else "") + whats[-1]
        (game.record_orders if orders else game.record_training)(memory, h, joined)
    TRAINING.clear()
    acct = trading.get_account()
    log.info(f"Connected to PAPER account. Cash: ${float(acct.cash):,.2f}")
    for b in bots:
        st = bank.status(memory, b)
        what = ("penny stocks it finds itself" if b["kind"] == "penny" else
                f"{game.RESEARCHER_SHORT[research.market_of(b)]}'s picks" if research.is_researched(b) else ", ".join(b["watchlist"]))
        log.info(f"  {b['name']:10} {STRATEGY_NAMES[b['strategy']]:15} up to {b['max_positions']} at once from {what}"
                 f"  | pot ${st['pot']:,.2f} of ${st['limit']:,}  savings ${st['savings']:,.2f}")
    log.info(f"Checking every {CHECK_EVERY_SECONDS // 60} min. Close this window to stop.")
    log.info(f"Goldmire version {updater.current_version()}"
             + ("" if updater.source() else " (automatic updates are switched off in update.json)"))
    threading.Thread(target=_update_watch, name="goldmire-update-check", daemon=True).start()

    once = "--once" in sys.argv
    start_world_server(open_browser=not once and "--no-browser" not in sys.argv)   # --no-browser: started at sign-in
    while not STOP.is_set():
        try:
            market_open = trading.get_clock().is_open
            rnd = Round(trading, stock_data, crypto_data, screener, market_open)
        except Exception as e:
            log.error(f"Could not reach Alpaca this round -> {e}")
            rnd = None
        if rnd:
            watch_news(news_client, bots, memory)
        for market in research.MARKETS:     # stock researcher, then crypto researcher
            if not rnd or not any(research.market_of(b) == market and research.is_researched(b) for b in bots):
                continue
            if research.due(memory, market, rnd.market_open):
                try:
                    run_research(market, trading, stock_data, crypto_data, screener, news_client, bots, memory)
                except Exception as e:
                    log.error(f"{game.RESEARCHER_SHORT[market]}: {market} research failed this time -> {e}")
                    research.mark_tried(memory, market)
        if rnd:
            game.MARKET_OPEN = rnd.market_open
            for bot in bots:
                try:
                    run_bot(bot, rnd, memory)
                except Exception as e:
                    log.error(f"[{bot['name']}] problem this round -> {e}")
            update_world(trading, memory, rnd.market_open, bots)
        if once:
            break
        if STOP.wait(CHECK_EVERY_SECONDS):   # wakes early when "Stop Goldmire" is chosen
            break


if __name__ == "__main__":
    main()
    sys.exit(3 if RESTART.is_set() else 0)   # 3 tells 3_run_bot.bat to start Goldmire again
