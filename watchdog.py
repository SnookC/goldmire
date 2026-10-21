"""
The Watchdog: notices when something keeps going wrong, and tells you in the town.

It reads every line Goldmire writes to its log (it never changes anything). When the same
kind of problem shows up again and again, it raises an ALERT:

  * shown as a red banner at the top of the town page (on your PC and on your phone)
  * written to the log once, as "Watchdog: ALERT ..."
  * cleared by itself after the problem has stayed away for CLEAR_AFTER_MIN minutes
    (the banner then says it's resolved, for a while, so you know it happened)

Most problems need REPEAT_COUNT hits within REPEAT_WINDOW_MIN minutes before they count,
so one hiccup doesn't cry wolf. A few (Pip's daily stop, Ysolde's warning about money she
can't explain) are serious enough to alert on the first time.

The Watchdog doesn't fix anything and doesn't change how the heroes trade: the fixes for a
problem are written by hand, tested, and delivered as an update.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime

REPEAT_COUNT = 3
REPEAT_WINDOW_MIN = 60
CLEAR_AFTER_MIN = 120
RESOLVED_SHOWN_MIN = 360           # a resolved alert stays visible (greyed) this long
MAX_ALERTS = 8

# (pattern, kind, what to tell you, hits needed). The first match wins.
RULES = [
    (r"DAILY STOP", "daily-stop", "Pip's daily stop is on: the heroes are down $500+ today, so nobody buys until tomorrow.", 1),
    (r"Ysolde: WARNING", "unexplained", "Ysolde found money she can't explain in today's account change. Check Alpaca's activity page.", 1),
    (r"Ysolde: daily check failed", "reconcile-failed", "Ysolde's daily check against Alpaca keeps failing.", 2),
    (r"list unavailable", "asset-list", "Quill can't load Alpaca's list of stocks, so his picks aren't refreshing.", REPEAT_COUNT),
    (r"Could not reach Alpaca", "alpaca-down", "Goldmire can't reach Alpaca (internet or Alpaca down). No trading until it's back.", REPEAT_COUNT),
    (r"research failed", "research-failed", "A researcher's scan keeps failing.", REPEAT_COUNT),
    (r"problem this round", "hero-error", "A hero keeps hitting an error during its turn.", REPEAT_COUNT),
    (r"Pip: couldn.t download Nasdaq", "pip-industry", "Pip can't download the industry list, so the 50% industry limit isn't checking.", 2),
    (r"Scorecard: .* BEHIND", "scorecard", "A trader is doing worse live than its tests said (see the Scorecard).", 1),
    (r"Calendar Desk: couldn.t download", "calendar", "The earnings and economic calendars aren't downloading.", 2),
    (r"Market weather: couldn.t", "weather", "The market weather check can't read the S&P 500.", REPEAT_COUNT),
    (r"prices unavailable", "prices", "Price data from Alpaca is failing for some stocks.", REPEAT_COUNT),
    (r"could not read positions|couldn't build today's report", "world", "The town page can't update (positions or the day's ledger).", REPEAT_COUNT),
    (r"Updates: .*(fail|couldn't|error)", "update", "An update didn't install.", 1),
]
_COMPILED = [(re.compile(p, re.I), k, msg, n) for p, k, msg, n in RULES]
_GENERIC_N = REPEAT_COUNT


class Watchdog(logging.Handler):
    def __init__(self, path):
        super().__init__(level=logging.INFO)
        self.path = path
        self._mx = threading.RLock()       # (logging.Handler keeps its own self.lock)
        self.hits = {}          # kind -> [times]
        self.alerts = {}        # kind -> alert dict
        self._log = logging.getLogger("bot")
        self._load()

    # ---- reading the log
    def emit(self, record):
        try:
            text = record.getMessage().splitlines()[0] if record.getMessage() else ""
        except Exception:  # noqa: BLE001
            return
        if text.startswith("Watchdog:"):
            return
        for rx, kind, msg, need in _COMPILED:
            if rx.search(text):
                self._hit(kind, msg, need, text)
                return
        if record.levelno >= logging.ERROR:            # anything else logged as an error
            key = re.sub(r"[\d$.,:+\-]+", "#", text)[:60]
            self._hit("error:" + key, "A problem keeps repeating: " + text[:160], _GENERIC_N, text)

    def _hit(self, kind, msg, need, text):
        now = time.time()
        fire = None
        with self._mx:
            hs = [t for t in self.hits.get(kind, []) if now - t < REPEAT_WINDOW_MIN * 60]
            hs.append(now)
            self.hits[kind] = hs
            a = self.alerts.get(kind)
            if a and not a.get("resolved"):
                a["count"] += 1
                a["last"] = _iso(now)
                a["example"] = text[:200]
            elif len(hs) >= need:
                self.alerts[kind] = {"kind": kind, "message": msg, "first": _iso(hs[0]), "last": _iso(now),
                                     "count": len(hs), "example": text[:200], "resolved": None}
                fire = msg
            else:
                return
            self._save()
        if fire:
            self._log.warning(f"Watchdog: ALERT {fire}")

    # ---- housekeeping (called once a round)
    def tidy(self):
        now = time.time()
        changed, said = False, []
        with self._mx:
            for kind, a in list(self.alerts.items()):
                last = _ts(a["last"])
                if not a.get("resolved") and now - last > CLEAR_AFTER_MIN * 60:
                    a["resolved"] = _iso(now)
                    changed = True
                    said.append(a["message"])
                elif a.get("resolved") and now - _ts(a["resolved"]) > RESOLVED_SHOWN_MIN * 60:
                    del self.alerts[kind]
                    changed = True
            if changed:
                self._save()
        for m in said:                                   # logged outside the lock
            self._log.info(f"Watchdog: resolved, no repeats for {CLEAR_AFTER_MIN} min: {m}")

    def active(self):
        with self._mx:
            items = sorted(self.alerts.values(), key=lambda a: (bool(a.get("resolved")), a["last"]), reverse=False)
            open_ = [a for a in items if not a.get("resolved")]
            done = [a for a in items if a.get("resolved")]
            return (sorted(open_, key=lambda a: a["last"], reverse=True) + sorted(done, key=lambda a: a["last"], reverse=True))[:MAX_ALERTS]

    # ---- the alerts file (survives restarts)
    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"alerts": list(self.alerts.values())}, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                for a in json.load(f).get("alerts", []):
                    self.alerts[a["kind"]] = a
        except (OSError, ValueError, KeyError, TypeError):
            pass


def _iso(t):
    return datetime.fromtimestamp(t).isoformat(timespec="seconds")


def _ts(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0.0


DOG = None


def start(world_dir):
    """Attach the Watchdog to Goldmire's log. Safe to call once at start-up."""
    global DOG
    if DOG is None:
        DOG = Watchdog(os.path.join(world_dir, "alerts.json"))
        logging.getLogger().addHandler(DOG)
        logging.getLogger("bot").info(f"Watchdog: on watch ({len(DOG.alerts)} alert(s) carried over)")
    return DOG
