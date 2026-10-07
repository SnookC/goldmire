"""
The news desk: reads recent headlines so the researchers and bots can react to them.

Every story from Alpaca's news feed (Benzinga) gets a TONE: positive for good news
(beats estimates, upgraded, FDA approval, big contract...), negative for bad news
(misses, downgraded, lawsuit, hack, bankruptcy...). It's a word list, not a mind
reader: it catches the clear headlines and ignores the murky ones.

Used three ways:
  * research   : the last 24 hours of stories shape each researcher's picks
                 (newer stories count more than older ones).
  * hot tips   : every bot round (5 min) the newest stories are checked. Strong good
                 news sends the researcher out straight away instead of waiting.
  * bad-news alarms : strong bad news on something a bot holds makes it sell
                 (turn off per bot with "news_exit": false in bots.json), and no bot
                 buys a symbol with fresh bad news.
"""

import re
from datetime import datetime, timedelta, timezone

HALF_LIFE_HOURS = 6          # a story's weight halves every 6 hours
STRONG = 3                   # tone that counts as a hot tip / alarm
ALARM_HOURS = 3              # bad news this fresh blocks buys and triggers news exits
TIP_HOURS = 2                # good news this fresh sends the researcher out early
BOOST_HOURS = 72             # big good news lets a held trade "build" for this long (news drift lasts days)
ROUNDUP = 4                  # stories naming more symbols than this are roundups ("10 stocks moving...")
CRIER_SIZE = 10              # headlines kept for the town crier

_POS = {
    3: ["beats estimates", "beat estimates", "tops estimates", "topped estimates", "beats expectations", "tops expectations",
        "raises guidance", "raised guidance", "raises outlook", "raises forecast", "lifts guidance", "boosts guidance",
        "fda approval", "fda approves", "receives approval", "wins approval", "to be acquired", "agrees to be acquired",
        "buyout offer", "takeover bid", "record revenue", "record quarter", "record earnings", "etf approved", "approves etf"],
    2: ["beats", "upgrade", "upgrades", "upgraded",
        "wins contract", "awarded contract", "awarded", "buyback", "share repurchase", "repurchase program",
        "partnership", "partners with", "strategic alliance", "all-time high", "record high", "surges", "soars",
        "skyrockets", "rockets", "jumps", "rallies", "spikes", "breakthrough", "outperform", "overweight",
        "strong demand", "dividend increase", "raises dividend", "lists on", "listing on", "inflows", "strong results"],
    1: ["price target raised", "raises price target", "raises target", "boosts price target",
        "rises", "gains", "climbs", "higher", "growth", "expands", "launches", "launch", "bullish", "upbeat",
        "optimistic", "beat", "adoption", "positive", "rebounds", "recovers", "accumulate"],
}
_NEG = {
    3: ["misses estimates", "missed estimates", "falls short", "fell short", "fall short", "cuts guidance", "lowers guidance", "lowered guidance",
        "cuts outlook", "slashes", "withdraws guidance", "bankruptcy", "chapter 11", "fraud", "sec charges", "charged by",
        "fda rejects", "complete response letter", "delisted", "delisting", "trading halted", "halts trading", "hacked",
        "exploit", "exploited", "rug pull", "depeg", "depegged", "insolvent", "going concern", "accounting irregularities"],
    2: ["misses", "downgrade", "downgrades", "downgraded",
        "lawsuit", "sued", "sues", "probe", "investigation", "subpoena", "recall", "recalls", "plunges", "tumbles",
        "crashes", "sinks", "craters", "nosedives", "breach", "layoffs", "lays off", "job cuts", "public offering",
        "share offering", "stock offering", "dilution", "underperform", "underweight", "sell rating", "short report",
        "short seller", "outflows", "resigns", "steps down", "default", "defaults", "warning", "warns", "guidance cut"],
    1: ["price target cut", "lowers price target", "cuts price target", "lowers target",
        "falls", "fell", "drops", "declines", "slips", "slides", "lower", "bearish", "concerns", "concern", "weak", "weaker",
        "slowdown", "delay", "delays", "delayed", "disappointing", "miss", "loss", "losses", "pressure", "volatile", "fear"],
}


def _compile(table):
    out = []
    for w, phrases in table.items():
        for p in phrases:
            *head, last = p.split()
            base = last[:-1] if last.endswith("s") and not last.endswith("ss") else last
            words = [re.escape(x) for x in head] + [re.escape(base) + r"(?:s|es|ed|d|ing|[a-z](?:ed|ing))?"]   # slip/slips/slipped...
            out.append((w, p, re.compile(r"\b" + r"\s+".join(words) + r"\b")))
    out.sort(key=lambda t: -len(t[1]))     # longest phrases first, so "beats estimates" wins over "beats"
    return out


_PHRASES = [(w, p, rx) for w, p, rx in _compile(_POS)] + [(-w, p, rx) for w, p, rx in _compile(_NEG)]


def tone(text):
    """Score one piece of text: positive = good news. Returns (score, [phrases found])."""
    t = " " + (text or "").lower() + " "
    score, found, used = 0, [], []
    for w, p, rx in sorted(_PHRASES, key=lambda x: -len(x[1])):
        for m in rx.finditer(t):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in used):   # part of a longer phrase already counted
                continue
            before = t[max(0, m.start() - 30):m.start()]
            flip = re.search(r"\b(not|no|never|fails? to|failed to|denies|denied|avoids|avoided|despite|without)(\s+[\w'-]+){0,2}\s+$", before)
            used.append((m.start(), m.end()))
            # "fails to win approval" is bad news; "denies fraud" is still not good news
            score += (-w if w > 0 else 0) if flip else w
            found.append(("not " if flip else "") + p)
    return score, found


ROUTINE = re.compile(r"\b(maintains|reiterates|keeps|initiates coverage|price target)\b", re.I)   # routine analyst notes
_WEIGHT = {p: w for w, ps in _POS.items() for p in ps} | {p: -w for w, ps in _NEG.items() for p in ps}


def story_tone(headline, summary=""):
    """Headline counts double; capped so one breathless story can't dominate.
    Routine analyst notes ("Maintains Neutral, lowers price target") count as small news at most."""
    h, hf = tone(headline)
    s, sf = tone(summary)
    t = max(-6, min(6, 2 * h + s))
    if ROUTINE.search(headline or "") and not any(_WEIGHT.get(f, 0) in (2, 3, -2, -3) and "grade" in f for f in hf):
        t = max(-2, min(2, t))
    return t, hf + [f for f in sf if f not in hf]


def headline_strength(headline):
    """(+1 if the headline itself has a strong good phrase, -1 if a strong bad one, 0 otherwise).
    Alarms and hot tips need the headline to say it plainly, not just a gloomy or upbeat summary."""
    _, found = tone(headline)
    strong = [_WEIGHT.get(f, 0) for f in found if not f.startswith("not ")]
    neg = any(w <= -2 for w in strong) or any(f.startswith("not ") and _WEIGHT.get(f[4:], 0) >= 2 for f in found)
    pos = any(w >= 2 for w in strong)
    return -1 if neg and not pos else 1 if pos and not neg else 0


def _aware(ts):
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def fetch(news_client, since, log, limit=300):
    """Stories since `since` (newest first) as plain dicts."""
    from alpaca.data.requests import NewsRequest
    try:
        raw = news_client.get_news(NewsRequest(start=since, limit=limit, exclude_contentless=False)).data.get("news", [])
    except Exception as e:
        log(f"news unavailable ({e})")
        return []
    out = []
    for n in raw:
        syms = list(getattr(n, "symbols", None) or [])
        if not syms:
            continue
        head = (getattr(n, "headline", "") or "").strip()
        when = getattr(n, "created_at", None) or datetime.now(timezone.utc)
        score, why = story_tone(head, getattr(n, "summary", "") or "")
        strength = 0 if ROUTINE.search(head) and abs(score) <= 2 else headline_strength(head)
        out.append({"id": str(getattr(n, "id", "") or hash((head, str(when)))), "headline": head, "time": _aware(when).isoformat(),
                    "symbols": syms, "tone": score, "why": why[:4], "roundup": len(syms) > ROUNDUP, "strength": strength})
    return out


def to_trade_symbol(s):
    """Alpaca news writes crypto as BTCUSD; orders and watchlists use BTC/USD."""
    if "/" not in s and s.endswith("USD") and len(s) > 3 and s not in ("USD",):
        return s[:-3] + "/USD"
    return s


def is_crypto(s):
    return "/" in s or (s.endswith("USD") and len(s) > 3)


def digest(stories, now=None):
    """{symbol: {"tone": recency-weighted tone, "count": stories, "headline": the story that matters most,
    "fresh": newest story's age in hours}} using trade symbols (BTC/USD)."""
    now = now or datetime.now(timezone.utc)
    out = {}
    for st in stories:
        age = max(0.0, (now - _aware(st["time"])).total_seconds() / 3600)
        w = 0.5 ** (age / HALF_LIFE_HOURS)
        for raw in st["symbols"]:
            s = to_trade_symbol(raw)
            d = out.setdefault(s, {"tone": 0.0, "count": 0, "headline": "", "_best": -1, "fresh": 99.0})
            d["count"] += 1
            if st["roundup"]:      # "10 stocks moving today": a mention, but its tone isn't about this one
                continue
            d["tone"] += st["tone"] * w
            d["fresh"] = min(d["fresh"], age)
            weight = abs(st["tone"]) * w
            if weight > d["_best"]:
                d["_best"], d["headline"], d["story_tone"] = weight, st["headline"], st["tone"]
    for d in out.values():
        d["tone"] = round(d["tone"], 2)
        d.pop("_best", None)
    return out


def short(headline, n=80):
    h = " ".join(headline.split())
    return h if len(h) <= n else h[: n - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# The every-round watch: hot tips and bad-news alarms
# ---------------------------------------------------------------------------
def _desk(memory):
    d = memory.setdefault("news", {})
    d.setdefault("alarms", {})       # {NORM SYMBOL: {"headline", "tone", "time"}}
    if d.get("rules") != 2:          # alarms raised by the older, jumpier rules are dropped
        d["alarms"], d["rules"] = {}, 2
    d.setdefault("crier", [])        # latest notable headlines for the town
    d.setdefault("seen", [])         # story ids already handled
    return d


def watch(news_client, memory, log, now=None):
    """Checks the newest stories. Returns {"tips": {"stock": [...], "crypto": [...]}, "alarms": [...], "new": n}."""
    now = now or datetime.now(timezone.utc)
    desk = _desk(memory)
    last = desk.get("last_check")
    since = max(_aware(last) - timedelta(minutes=10), now - timedelta(hours=6)) if last else now - timedelta(hours=3)
    stories = fetch(news_client, since, log, limit=50)
    desk["last_check"] = now.isoformat()
    seen = set(desk["seen"])
    fresh = sorted((s for s in stories if s["id"] not in seen), key=lambda s: s["time"], reverse=True)   # newest first
    tips, alarms = {"stock": [], "crypto": []}, []
    for st in reversed(fresh):                      # oldest first, so the crier reads in order
        age = (now - _aware(st["time"])).total_seconds() / 3600
        if abs(st["tone"]) >= 2 and not st["roundup"]:
            desk["crier"].insert(0, {"time": st["time"], "symbols": [to_trade_symbol(s) for s in st["symbols"]][:3],
                                     "headline": short(st["headline"], 110), "tone": st["tone"]})
        if st["roundup"]:
            continue
        for raw in st["symbols"]:
            sym = to_trade_symbol(raw)
            if st["tone"] <= -STRONG and st.get("strength", -1) < 0 and age <= ALARM_HOURS:
                desk["alarms"][sym.replace("/", "")] = {"symbol": sym, "headline": short(st["headline"]), "tone": st["tone"], "time": st["time"]}
                alarms.append((sym, st))
            elif st["tone"] >= STRONG and st.get("strength", 1) > 0:
                if age <= BOOST_HOURS:      # a hero holding it (now or later) lets the run build
                    desk.setdefault("boosts", {})[sym.replace("/", "")] = {"symbol": sym, "headline": short(st["headline"]), "tone": st["tone"], "time": st["time"]}
                if age <= TIP_HOURS:
                    tips["crypto" if is_crypto(raw) else "stock"].append((sym, st))
    desk["seen"] = ([s["id"] for s in fresh] + desk["seen"])[:400]
    desk["crier"] = desk["crier"][:CRIER_SIZE]
    for k, a in list(desk["alarms"].items()):       # alarms fade after a few hours
        if (now - _aware(a["time"])).total_seconds() > ALARM_HOURS * 3600:
            desk["alarms"].pop(k)
    for k, b in list(desk.get("boosts", {}).items()):
        if (now - _aware(b["time"])).total_seconds() > BOOST_HOURS * 3600 or k in desk["alarms"]:
            desk["boosts"].pop(k)                       # faded, or bad news since
    return {"tips": tips, "alarms": alarms, "new": len(fresh)}


def boost_for(memory, symbol):
    """Big fresh good news on a symbol (any spelling), or None."""
    return memory.get("news", {}).get("boosts", {}).get(symbol.replace("/", "").upper())


def alarm_for(memory, symbol):
    """The bad-news alarm on a symbol (any spelling), or None."""
    return memory.get("news", {}).get("alarms", {}).get(symbol.replace("/", "").upper())
