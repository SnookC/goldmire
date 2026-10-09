"""
Goldmire game layer.

Turns the bots' trades into an RPG: each bot is a hero who earns XP and levels
up, the guild earns deeds (achievements), daily quests reset each morning, and
the town crier writes a chronicle of everything that happened.

Pure bookkeeping: nothing here talks to Alpaca or places trades.
"""

import random
from datetime import datetime

# Each bot's hero, by bot name. Bots not listed get a hero picked by kind.
HEROES = {
    "Stock-1":  {"hero": "Gareth the Steadfast", "cls": "Knight"},
    "Stock-2":  {"hero": "Wren of the Thicket",  "cls": "Ranger"},
    "Penny":    {"hero": "Pip Quickfingers",     "cls": "Rogue"},
    "Crypto-1": {"hero": "Old Bram",             "cls": "Alchemist"},
    "Crypto-2": {"hero": "Ysolde the Hexweaver", "cls": "Mage"},
}
FALLBACK = {"stock": ("Sellsword", "Knight"), "penny": ("Cutpurse", "Rogue"), "crypto": ("Hedge Witch", "Mage")}

HERO_TITLES = [(1, "Novice"), (3, "Adept"), (5, "Veteran"), (8, "Champion"), (12, "Legend")]
GUILD_TITLES = [(1, "Village Upstart"), (3, "Market Squire"), (5, "Guild Treasurer"),
                (8, "Merchant Lord"), (12, "Gold Baron"), (16, "Legend of the Ledger")]

DEEDS = {
    "first_trade": ("First Coin",                 "Finish your first trade."),
    "first_win":   ("Gold in the Pocket",         "Win a trade."),
    "streak3":     ("On a Roll",                  "One hero wins 3 trades in a row."),
    "big_win":     ("Dragon's Hoard",             "Win $10 or more on one trade."),
    "ten_trades":  ("Seasoned",                   "Finish 10 trades."),
    "fifty":       ("Veteran of a Hundred Fairs", "Finish 50 trades."),
    "rogue_score": ("Pickpocket Prince",          "The Rogue sells a penny stock at its profit target."),
    "stop_saved":  ("Live to Fight Another Day",  "A stop-loss gets the Rogue out before it gets worse."),
    "night_owl":   ("Moonlit Dealings",           "A crypto hero closes a trade while the stock market sleeps."),
    "fellowship":  ("The Full Fellowship",        "Every hero finishes at least one trade."),
    "comeback":    ("Back from the Brink",        "Climb from $20 down back into profit."),
    "golden_age":  ("A Golden Age",               "Reach a Golden Age."),
    "level5":      ("Seasoned Blade",             "Any hero reaches level 5."),
    "first_save":  ("Into the Vault",             "A hero fills its purse and sets gold aside."),
    "promoted":    ("Rising Star",                "A hero is promoted to a $5,000 purse."),
    "top_tier":    ("Master of Coin",             "A hero is promoted to a $10,000 purse."),
}

QUESTS = [
    ("trades3", "Send heroes on 3 trades today", 3),
    ("wins2",   "Win 2 trades today", 2),
    ("green",   "Finish today with more gold than you started", 1),
]
QUEST_XP = 50

LINES = {
    "buy": [
        "{h} sets out for {s} at dawn, sword sharpened.",
        "{h} takes up a position in {s}. The village waits.",
        "{h} marches on {s} with a full purse and a hopeful heart.",
    ],
    "buy_Rogue": [
        "{h} slips into {s} while nobody is looking.",
        "{h} spots a shiny little stock called {s} and pockets some.",
    ],
    "buy_Mage": ["{h} weaves a hex over {s} and buys in."],
    "buy_Alchemist": ["{h} tips a pinch of gold into the {s} cauldron."],
    "win": [
        "{h} returns from {s} with {g}. The tavern buys the next round.",
        "{h} triumphs over {s}! {g} for the treasury.",
        "Bards already sing of {h}'s raid on {s}. Spoils: {g}.",
    ],
    "loss": [
        "{h} limps home from {s}, down {g}. The bards are being kind about it.",
        "{s} bested {h} today. {g} lost to the fog.",
        "{h} retreats from {s}. The village pretends not to notice the missing {g}.",
    ],
    "take": ["{h} snatches {g} from {s} and vanishes before the guards turn around."],
    "stop": ["{h} flees {s} before it all burns down. A loss of {g}, but alive to steal again."],
    "level": ["{h} reaches level {n}! The village rings the bell.",
              "Level {n}! {h} looks taller already."],
    "deed": ["Deed earned: {t}. A new mark on the guild wall."],
    "quest": ["Quest complete: {t}. +{x} guild renown."],
    "saved": ["{h}'s purse is full. {g} goes to the vault.",
              "{h} carries {g} down to the vault for safekeeping."],
    "promoted": ["{h} is promoted! Their purse can now hold ${n}.",
                 "Trumpets! {h} earns a bigger purse: ${n}."],
    "benched": ["{h} has spent nearly every coin and sits out until further notice."],
    "research": ["{r} pins new leads on the guild board for {h}: {a}.{d}",
                 "{r} returns from the archives with fresh leads for {h}: {a}.{d}",
                 "After a long night with the ledgers, {r} tells {h} to watch {a}.{d}"],
    "news_exit": ["{h} hears the Town Crier's warning about {s} and gets out before the crowd ({sg}).",
                  "Bad tidings from {s}! {h} slips away while the getting is good ({sg})."],
    "training": ["The Master-at-Arms has taught {h} {t}, proven in the Proving Grounds.",
                 "After long days in the Proving Grounds, {h} has learned {t}."],
    "orders": ["By order of the Guildmaster, {h} takes up {t}.",
               "New orders from the Guildmaster: {h} is {t}."],
    "suggestion": ["The Guildmaster slips {h} a note: \"Keep an eye on {s}.\"",
                   "{h} adds {s} to the watch, on the Guildmaster's word."],
    "bench_manual": ["By order of the Guildmaster, {h} takes a seat on the bench by the tavern door. No new quests until called back.",
                     "{h} hangs up their pack and sits out a while on the Guildmaster's orders."],
    "unbench": ["{h} gets up off the bench by the tavern door, stretches, and heads back out to work.",
                "The Guildmaster calls {h} back from the bench. Back to work!"],
    "bench": ["{h} takes a seat on the bench by the tavern door. The guild will call on them again once a better penny technique is proven.",
              "The Guildmaster benches {h} until the Proving Grounds find a penny technique worth trusting."],
    "crier_good": ["The Town Crier rings his bell: \"{n}\" {r} hurries off to look into {s}.",
                   "Hear ye! \"{n}\" {r} sets out early for {s}."],
    "crier_bad": ["The Town Crier's bell tolls: \"{n}\" The guild steers clear of {s}.",
                  "Ill news from the road: \"{n}\" No hero buys {s} today."],
    "research_crypto": ["{r} comes down from the star tower with new omens for {h}: {a}.{d}",
                        "The stars have shifted. {r} tells {h} to watch {a}.{d}",
                        "{r} pins a star chart on the guild board for {h}: {a}.{d}"],
}
# The two researchers: one for stocks, one for crypto (penny bots find their own picks)
RESEARCHERS = {"stock": "Mistress Quill the Loremaster", "crypto": "Corvin the Star-Reader"}
RESEARCHER_SHORT = {"stock": "Quill", "crypto": "Corvin"}
RESEARCHER = RESEARCHERS["stock"]

MARKET_OPEN = True   # bot.py sets this each round
_rng = random.Random()


# ---------------------------------------------------------------------------
def level_for(xp):
    """Level 2 at 100 XP, 3 at 300, 4 at 600, 5 at 1000 ... (50 * L * (L+1))."""
    level = 1
    while xp >= 50 * level * (level + 1):
        level += 1
    return level


def title_for(level, table):
    title = table[0][1]
    for need, name in table:
        if level >= need:
            title = name
    return title


CLASSES = ["Knight", "Ranger", "Rogue", "Alchemist", "Mage", "Bard", "Druid", "Paladin"]
SPARE_NAMES = ["Rowan Ashby", "Mirelle of the Mill", "Tobias Kettle", "Brannoc Ironhand", "Elsie Thistlewood",
               "Corwin Vale", "Hester Pike", "Aldous Grey", "Nettle Blackbriar", "Osric Fairweather"]


def hero_of(bot):
    """Hero name + class: from bots.json if given, else the classic five, else made up from the bot's name."""
    h = HEROES.get(bot["name"], {})
    name = bot.get("hero") or h.get("hero")
    cls = bot.get("class") or h.get("cls")
    seed = sum(ord(c) for c in bot["name"])
    if not cls:
        cls = FALLBACK.get(bot.get("kind", "stock"), FALLBACK["stock"])[1] if not name else CLASSES[seed % len(CLASSES)]
    if not name:
        name = SPARE_NAMES[seed % len(SPARE_NAMES)]
    return name, cls


def ensure(memory):
    memory.setdefault("heroes", {})
    memory.setdefault("deeds", {})
    memory.setdefault("chronicle", [])
    memory.setdefault("quest_xp", 0)
    memory.setdefault("low_water", 0.0)
    today = datetime.now().strftime("%Y-%m-%d")
    t = memory.get("today")
    if not t or t.get("date") != today:
        memory["today"] = {"date": today, "trades": 0, "wins": 0, "pl": 0.0, "done": []}
    return memory


def _hero_stats(memory, bot):
    return memory["heroes"].setdefault(bot["name"], {
        "xp": 0, "trades": 0, "wins": 0, "losses": 0, "streak": 0, "best": 0.0, "gold": 0.0})


def _say(memory, kind, tone, **kw):
    text = _rng.choice(LINES[kind]).format(**kw)
    memory["chronicle"].append({"t": datetime.now().isoformat(timespec="seconds"), "text": text, "tone": tone})
    del memory["chronicle"][:-40]


def _earn(memory, deed_id):
    if deed_id in memory["deeds"]:
        return False
    memory["deeds"][deed_id] = datetime.now().isoformat(timespec="seconds")
    _say(memory, "deed", "deed", t=DEEDS[deed_id][0])
    return True


def _add_xp(memory, bot, amount):
    st = _hero_stats(memory, bot)
    before = level_for(st["xp"])
    st["xp"] += max(0, int(amount))
    after = level_for(st["xp"])
    if after > before:
        _say(memory, "level", "level", h=hero_of(bot)[0], n=after)
        if after >= 5:
            _earn(memory, "level5")


def gold(pl):
    """Amounts in the chronicle: plain dollars and cents, e.g. $3.40."""
    return f"${abs(pl):,.2f}"


# ---------------------------------------------------------------------------
def record_buy(memory, bot, symbol):
    ensure(memory)
    name, cls = hero_of(bot)
    key = f"buy_{cls}" if f"buy_{cls}" in LINES else "buy"
    _say(memory, key, "info", h=name, s=symbol)
    _add_xp(memory, bot, 5)


def record_sell(memory, bot, symbol, pl, reason=""):
    ensure(memory)
    name, cls = hero_of(bot)
    st = _hero_stats(memory, bot)
    won = pl > 0
    st["trades"] += 1
    st["gold"] = round(st["gold"] + pl, 2)
    if won:
        st["wins"] += 1
        st["streak"] = st["streak"] + 1 if st["streak"] >= 0 else 1
        st["best"] = max(st["best"], round(pl, 2))
    else:
        st["losses"] += 1
        st["streak"] = st["streak"] - 1 if st["streak"] <= 0 else -1

    t = memory["today"]
    t["trades"] += 1
    t["wins"] += 1 if won else 0
    t["pl"] = round(t["pl"] + pl, 2)

    code = ("news_exit" if "bad news" in reason else "take" if "take-profit" in reason else
            "stop" if "stop-loss" in reason else ("win" if won else "loss"))
    _say(memory, code, "win" if won else "loss", h=name, s=symbol, g=gold(pl), sg=("+" if pl >= 0 else "-") + gold(pl))
    _add_xp(memory, bot, 20 + (10 + min(200, pl * 5) if won else 5))

    total_trades = sum(h["trades"] for h in memory["heroes"].values())
    _earn(memory, "first_trade")
    if won:
        _earn(memory, "first_win")
    if st["streak"] >= 3:
        _earn(memory, "streak3")
    if pl >= 10:
        _earn(memory, "big_win")
    if total_trades >= 10:
        _earn(memory, "ten_trades")
    if total_trades >= 50:
        _earn(memory, "fifty")
    if code == "take" and bot.get("kind") == "penny":
        _earn(memory, "rogue_score")
    if code == "stop" and bot.get("kind") == "penny":
        _earn(memory, "stop_saved")
    if bot.get("kind") == "crypto" and not MARKET_OPEN:
        _earn(memory, "night_owl")


def record_bank(memory, bot, events):
    """Chronicle + deeds for savings, promotions and benching (events from bank.apply_result)."""
    ensure(memory)
    name = hero_of(bot)[0]
    for kind, amount in events:
        if kind == "saved":
            _say(memory, "saved", "deed", h=name, g=gold(amount))
            _earn(memory, "first_save")
        elif kind == "promoted":
            _say(memory, "promoted", "level", h=name, n=f"{amount:,}")
            _add_xp(memory, bot, 250)
            _earn(memory, "promoted")
            if amount >= 10000:
                _earn(memory, "top_tier")
        elif kind == "benched":
            _say(memory, "benched", "loss", h=name)


def record_research(memory, bot, added, dropped):
    ensure(memory)
    if not added:
        return
    d = f" Struck off: {', '.join(dropped)}." if dropped else ""
    crypto = bot.get("kind") == "crypto"
    _say(memory, "research_crypto" if crypto else "research", "info",
         r=RESEARCHERS["crypto" if crypto else "stock"], h=hero_of(bot)[0], a=", ".join(added), d=d)


def tick(memory, bots_status, total_pl, budget):
    """Check whole-kingdom deeds and daily quests. Returns the 'game' block for status.json."""
    ensure(memory)
    names = [b["name"] for b in bots_status]
    if names and all(memory["heroes"].get(n, {}).get("trades", 0) > 0 for n in names):
        _earn(memory, "fellowship")
    memory["low_water"] = min(memory["low_water"], total_pl)
    if memory["low_water"] <= -20 and total_pl > 0:
        _earn(memory, "comeback")
    if budget and total_pl >= budget * 0.2 * 0.75:
        _earn(memory, "golden_age")

    t = memory["today"]
    progress = {"trades3": t["trades"], "wins2": t["wins"], "green": 1 if t["pl"] > 0 else 0}
    quests = []
    for qid, title, goal in QUESTS:
        done = progress[qid] >= goal
        if done and qid not in t["done"] and (qid != "green" or t["trades"] > 0):
            t["done"].append(qid)
            memory["quest_xp"] += QUEST_XP
            _say(memory, "quest", "deed", t=title, x=QUEST_XP)
        quests.append({"id": qid, "title": title, "goal": goal,
                       "progress": min(progress[qid], goal), "done": qid in t["done"]})

    guild_xp = sum(h["xp"] for h in memory["heroes"].values()) + memory["quest_xp"]
    glevel = level_for(guild_xp)
    return {
        "guild": {"xp": guild_xp, "level": glevel, "title": title_for(glevel, GUILD_TITLES)},
        "quests": quests,
        "quest_xp": QUEST_XP,
        "deeds": [{"id": k, "title": v[0], "desc": v[1], "earned": memory["deeds"].get(k)} for k, v in DEEDS.items()],
        "chronicle": list(reversed(memory["chronicle"][-20:])),
    }


def hero_block(memory, bot):
    ensure(memory)
    name, cls = hero_of(bot)
    st = _hero_stats(memory, bot)
    lvl = level_for(st["xp"])
    return {"hero": name, "cls": cls, "level": lvl, "title": title_for(lvl, HERO_TITLES),
            "xp": st["xp"], "trades": st["trades"], "wins": st["wins"], "losses": st["losses"],
            "streak": st["streak"], "best": st["best"]}


def record_news(memory, good, symbol, headline, market):
    """The Town Crier announces a big story (good: a researcher goes out early; bad: nobody buys it)."""
    ensure(memory)
    _say(memory, "crier_good" if good else "crier_bad", "info" if good else "loss",
         n=headline, s=symbol, r=RESEARCHERS.get(market, RESEARCHER))


def record_training(memory, hero_name, what):
    """A hero learned something new from the Proving Grounds."""
    ensure(memory)
    _say(memory, "training", "level", h=hero_name, t=what)


def record_orders(memory, hero_name, what):
    """You changed how a hero works (more slots, sizing, a wider scan)."""
    ensure(memory)
    _say(memory, "orders", "info", h=hero_name, t=what)


def record_suggestion(memory, hero_name, symbol):
    ensure(memory)
    _say(memory, "suggestion", "info", h=hero_name, s=symbol)


def record_bench_manual(memory, hero_name):
    ensure(memory)
    _say(memory, "bench_manual", "info", h=hero_name)


def record_unbench(memory, hero_name):
    ensure(memory)
    _say(memory, "unbench", "info", h=hero_name)


def record_bench(memory, hero_name):
    ensure(memory)
    _say(memory, "bench", "info", h=hero_name)
