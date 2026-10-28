"""
The Calendar Desk: what's coming up that could move the heroes' stocks.

Two free calendars from Nasdaq, refreshed once a day (calendar.json keeps them):
  * EARNINGS   which companies report in the next CALENDAR_DAYS weekdays, before the open
               or after the close, with the expected earnings per share
  * ECONOMY    the big US releases in that time: inflation (CPI, PCE, PPI), jobs, the Fed,
               GDP, retail sales and similar, with the forecast and the actual when it's out

The heroes' rules don't change because of this (you chose to hold through earnings). It's
shown in the town so you can see what's coming, and on each stock a hero holds.
"""
import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CAL_FILE = os.path.join(HERE, "calendar.json")
CALENDAR_DAYS = 7
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Goldmire", "Accept": "application/json"}
EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings?date={d}"
ECONOMY_URL = "https://api.nasdaq.com/api/calendar/economicevents?date={d}"
BIG_EVENTS = ("cpi", "consumer price", "pce", "ppi", "producer price", "nonfarm", "payroll", "unemployment rate",
              "initial jobless claims", "fomc", "fed interest rate", "federal reserve", "fed chair", "interest rate decision",
              "gdp", "retail sales", "ism manufacturing", "ism services", "ism non-manufacturing", "consumer confidence",
              "michigan consumer sentiment", "jolts", "durable goods orders", "powell")
SKIP_EVENTS = ("gdpnow", "core durable", "reserve balances", "member", " prices", "employment", "new orders", "business activity",
               "gdp price", "gdp sales", "dallas fed", "productivity", "4-week", "continuing", "excluding")
ECONOMY_SHIFT_DAYS = 1      # Nasdaq's economic calendar for date D lists the events of the day BEFORE
                            # (found Oct 28 2026: asking for Oct 29 returned that day's Fed decision and
                            # GDPNow reading; asking for Oct 23 returned Thursday Oct 22's jobless claims)
CAL_VERSION = 3
NASDAQ_UTC_OFFSET_H = 4     # its "gmt" times are really UTC-4 all year (right in summer, an hour late in winter)


def _ny_time(day, hhmm):
    """Nasdaq's time (UTC-4) on that day -> New York time, HH:MM."""
    try:
        from zoneinfo import ZoneInfo
        h, m = (int(x) for x in hhmm.split(":")[:2])
        utc = datetime.fromisoformat(f"{day}T{h:02d}:{m:02d}:00+00:00") + timedelta(hours=NASDAQ_UTC_OFFSET_H)
        return utc.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return hhmm
RETRY_AFTER_FAIL = 3600


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _clean(v):
    return str(v or "").replace("&nbsp;", " ").strip()


def _when(t):
    t = (t or "").lower()
    return "before the open" if "pre" in t else "after the close" if "after" in t else ""


class Desk:
    def __init__(self, path=CAL_FILE):
        self.path = path
        self.data = {}
        self.failed_at = 0.0
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    def refresh(self, today=None, log=print, force=False):
        """Download the next CALENDAR_DAYS weekdays once a day. Never raises."""
        today = today or date.today()
        if not force and self.data.get("day") == today.isoformat() and self.data.get("v") == CAL_VERSION:
            return False
        if time.time() - self.failed_at < RETRY_AFTER_FAIL:
            return False
        earnings, economy, errors = {}, [], 0
        for d in _weekdays(today, CALENDAR_DAYS):
            ds = d.isoformat()
            try:
                rows = ((_get(EARNINGS_URL.format(d=ds)).get("data") or {}).get("rows")) or []
                for r in rows:
                    sym = (r.get("symbol") or "").upper().strip()
                    if sym and sym not in earnings:
                        earnings[sym] = {"date": ds, "when": _when(r.get("time")), "eps_forecast": r.get("epsForecast") or "",
                                         "name": (r.get("name") or "").strip()}
            except Exception:  # noqa: BLE001
                errors += 1
        last = _weekdays(today, CALENDAR_DAYS)[-1]
        q, seen = today + timedelta(days=ECONOMY_SHIFT_DAYS), set()
        while q <= last + timedelta(days=ECONOMY_SHIFT_DAYS):          # every calendar day: Friday's events sit under Saturday
            ds = (q - timedelta(days=ECONOMY_SHIFT_DAYS)).isoformat()   # the day they really happen
            try:
                rows = ((_get(ECONOMY_URL.format(d=q.isoformat())).get("data") or {}).get("rows")) or []
                for r in rows:
                    name = (r.get("eventName") or "").strip()
                    low = name.lower() + " "
                    if r.get("country") != "United States" or not any(k in low for k in BIG_EVENTS) or any(k in low for k in SKIP_EVENTS):
                        continue
                    key = (ds, name.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    economy.append({"date": ds, "time_et": _ny_time(ds, _clean(r.get("gmt"))), "event": name, "actual": _clean(r.get("actual")),
                                    "consensus": _clean(r.get("consensus")), "previous": _clean(r.get("previous"))})
            except Exception:  # noqa: BLE001
                errors += 1
            q += timedelta(days=1)
        economy.sort(key=lambda e: (e["date"], e["time_et"]))
        if errors >= CALENDAR_DAYS * 2:                # everything failed: keep the old calendar
            self.failed_at = time.time()
            log("Calendar Desk: couldn't download the earnings and economic calendars; trying again in an hour")
            return False
        self.data = {"v": CAL_VERSION, "day": today.isoformat(), "fetched": datetime.now().isoformat(timespec="seconds"),
                     "earnings": earnings, "economy": economy}
        self._save()
        log(f"Calendar Desk: {len(earnings)} companies report earnings and {len(economy)} big US economic releases "
            f"in the next {CALENDAR_DAYS} weekdays" + (f" ({errors} day(s) didn't download)" if errors else ""))
        return True

    def earnings_for(self, symbol):
        return (self.data.get("earnings") or {}).get(symbol.upper().replace("/", ""))

    def summary(self, held):
        """{"earnings": [held stocks reporting soon], "economy": [...]} for the town. held: {symbol: hero name}."""
        rows = []
        for sym, hero in held.items():
            e = self.earnings_for(sym)
            if e:
                rows.append({"symbol": sym, "hero": hero, **e})
        rows.sort(key=lambda r: (r["date"], r["symbol"]))
        return {"earnings": rows, "economy": self.data.get("economy", [])[:12], "fetched": self.data.get("fetched")}
