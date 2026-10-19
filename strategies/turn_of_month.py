"""Turn of the month (Gareth's quant hypothesis #4, Oct 19 2026).
HYPOTHESIS: stock prices tend to rise from the last trading day of a month through the
first few days of the next, because money arrives on a calendar (paychecks, retirement
contributions, fund flows) and gets invested then. A calendar effect, unlike anything
the other heroes trade.
BUY at the close of the second-to-last weekday of the month (so the buy fills at the open
of the last one). SELL after 4 days (the third weekday of the new month).
Holidays aren't known to it, so its timing can be a day off around them.
WOULD BE FALSIFIED BY: losing money after costs in the exam, or doing no better than
random entries held as long."""
from datetime import date, datetime, timedelta

NAME = "Turn of the month"
SOURCE = "Ariel (1987) 'A monthly effect in stock returns'; McConnell & Xu (2008) 'Equity returns at the turn of the month'"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def _day(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return datetime.fromisoformat(str(x).replace("Z", "+00:00")).date()


def _weekdays_left(d):
    """Weekdays after d that are still in d's month."""
    n, x = 0, d + timedelta(days=1)
    while x.month == d.month:
        if x.weekday() < 5:
            n += 1
        x += timedelta(days=1)
    return n


def signal(bars, position):
    t = bars.get("t") or []
    if not t:
        return None
    today = _day(t[-1])
    if position is None:
        return "buy" if _weekdays_left(today) == 1 else None
    return "sell" if position["bars_held"] >= 4 else None
