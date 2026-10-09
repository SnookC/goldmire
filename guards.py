"""
Protective stop orders held by Alpaca ("guards").

Goldmire checks prices every 5 minutes, so a fast drop can blow through a stop-loss between
checks. A guard is a real stop order sitting at Alpaca: the moment the price falls through it,
Alpaca sells, no waiting.

  * Stocks: a stop order good for the day (Alpaca doesn't allow longer ones for fractional
    shares), so Goldmire places it again each morning once the market opens.
  * Crypto: a stop-limit order good until cancelled (that's what Alpaca offers for crypto).
  * "Let winners build": as the trailing stop moves up, the guard is moved up with it.
  * Before Goldmire sells for any other reason, it cancels the guard first.
  * When a guard fires, the sale is recorded like any other (ledger, chronicle, purse).
"""

GUARD_LIMIT_GAP = 0.01        # crypto stop-limit: sell no lower than 1% under the stop price
MOVE_AT_LEAST = 0.003         # only move a guard when its price would change by 0.3% or more


def is_sell(o):
    return "sell" in str(getattr(o, "side", "")).lower()


def is_stop(o):
    return "stop" in str(getattr(o, "order_type", None) or getattr(o, "type", "")).lower()


def tick(price):
    """Round a stop price the way Alpaca accepts it."""
    if price >= 1:
        return round(price, 2)
    return round(price, 4) if price >= 0.01 else round(price, 6)


def wanted_price(h, entry, stop, building, trail):
    """Where the guard should sit: under the entry at the stop, or under the best price when trailing."""
    if building and h.get("peak"):
        return h["peak"] * (1 - trail)
    if stop and entry:
        return entry * (1 - stop)
    return None


def place(trading, symbol, qty, price, crypto, log=print):
    from alpaca.trading.requests import StopOrderRequest, StopLimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    if crypto:
        req = StopLimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                                    stop_price=tick(price), limit_price=tick(price * (1 - GUARD_LIMIT_GAP)))
    else:
        req = StopOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY, stop_price=tick(price))
    return trading.submit_order(req)


def move(trading, order, qty, price, crypto):
    from alpaca.trading.requests import ReplaceOrderRequest
    kw = {"stop_price": tick(price)}          # the amount stays as it is (Alpaca only takes whole numbers here)
    if crypto:
        kw["limit_price"] = tick(price * (1 - GUARD_LIMIT_GAP))
    return trading.replace_order_by_id(order.id, ReplaceOrderRequest(**kw))


def keep(rnd, h, symbol, nsym, pos, price, crypto, log=print, who=""):
    """Make sure one holding has a guard at about the right price. Never raises."""
    if not price or price <= 0:
        return
    try:
        qty = float(getattr(pos, "qty_available", None) or getattr(pos, "qty", 0) or 0)
        held_qty = float(getattr(pos, "qty", 0) or 0)
        existing = [o for o in rnd.guard_orders.get(nsym, [])]
        if existing:
            o = existing[0]
            cur = float(getattr(o, "stop_price", 0) or 0)
            h["guard"] = str(o.id)
            if cur and abs(price - cur) / cur < MOVE_AT_LEAST:
                return                                    # already about right
            if price < cur:
                return                                    # never loosen a guard (a trailing stop only climbs)
            new = move(rnd.trading, o, float(getattr(o, "qty", 0) or held_qty), price, crypto)
            h["guard"], h["guard_price"] = str(new.id), tick(price)
            log(f"{who} {symbol}: guard moved up to ${tick(price):,} (held by Alpaca)")
            return
        if qty <= 0:
            return
        o = place(rnd.trading, symbol, qty, price, crypto, log)
        h["guard"], h["guard_price"] = str(o.id), tick(price)
        log(f"{who} {symbol}: guard placed at ${tick(price):,} (Alpaca sells instantly if it drops there)")
    except Exception as e:  # noqa: BLE001 - a guard that can't be placed must never stop the hero
        if not h.get("guard_error"):
            log(f"{who} {symbol}: couldn't place a guard ({e}); Goldmire's own 5-minute stop check still applies")
        h["guard_error"] = str(e)[:120]


def cancel_for(trading, symbol, log=print):
    """Cancel any guard on this symbol before Goldmire sells it some other way."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    n = 0
    try:
        for o in trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])):
            if is_sell(o):
                trading.cancel_order_by_id(o.id)
                n += 1
    except Exception as e:  # noqa: BLE001
        log(f"{symbol}: couldn't cancel its guard ({e})")
    return n


def filled(trading, h):
    """If this holding's guard sold it, return (qty, price); else None."""
    gid = h.get("guard")
    if not gid:
        return None
    try:
        o = trading.get_order_by_id(gid)
    except Exception:  # noqa: BLE001
        return None
    if "filled" not in str(getattr(o, "status", "")).lower() or "partially" in str(getattr(o, "status", "")).lower():
        return None
    try:
        return float(o.filled_qty), float(o.filled_avg_price)
    except (TypeError, ValueError):
        return None
