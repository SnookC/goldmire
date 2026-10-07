"""
Add a new trading bot (and its hero) to bots.json by answering a few questions.
Run it with add_bot.bat. The bots pick up the change the next time you start 3_run_bot.bat.
"""

import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS_FILE = os.path.join(HERE, "bots.json")

CLASSES = ["Knight", "Ranger", "Rogue", "Alchemist", "Mage", "Bard", "Druid", "Paladin"]
STRATEGIES = [("ma_cross", "Trend follower - buys when prices start climbing, sells when they turn down"),
              ("rsi", "Dip buyer - buys after a sharp drop, sells after a sharp rise"),
              ("breakout", "Breakout hunter - buys new highs, sells new lows")]
KINDS = [("stock", "Stocks (trades while the US market is open)"),
         ("crypto", "Crypto coins (trades 24/7)"),
         ("penny", "Penny stocks ($1-$5, finds its own)")]
NAME_IDEAS = ["Rowan Ashby", "Mirelle of the Mill", "Tobias Kettle", "Brannoc Ironhand", "Elsie Thistlewood",
              "Corwin Vale", "Hester Pike", "Aldous Grey", "Nettle Blackbriar", "Osric Fairweather"]


def ask(prompt, default=None):
    shown = f" [{default}]" if default not in (None, "") else ""
    answer = input(f"{prompt}{shown}: ").strip()
    return answer if answer else (default if default is not None else "")


def choose(prompt, options):
    print(prompt)
    for i, (_, text) in enumerate(options, 1):
        print(f"  {i}. {text}")
    while True:
        pick = ask("Type a number", "1")
        if pick.isdigit() and 1 <= int(pick) <= len(options):
            return options[int(pick) - 1][0]
        print("  Please type one of the numbers above.")


def number(prompt, default, low, high, cast=float):
    while True:
        raw = ask(prompt, default)
        try:
            value = cast(raw)
            if low <= value <= high:
                return value
        except ValueError:
            pass
        print(f"  Please type a number from {low} to {high}.")


def main():
    if not os.path.exists(BOTS_FILE):
        print("bots.json was not found. Run 3_run_bot.bat once first (it creates the file), then try again.")
        return 1
    with open(BOTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    bots = data["bots"]
    taken_names = {b["name"].lower() for b in bots}
    taken_heroes = {b.get("hero", "") for b in bots}

    print("\n=== Add a new trading bot ===")
    print(f"You have {len(bots)} bots: {', '.join(b['name'] for b in bots)}\n")

    while True:
        name = ask("Short name for the bot (like Stock-3 or Crypto-3)")
        if not name:
            print("  Please type a name.")
        elif name.lower() in taken_names:
            print("  That name is taken. Try another.")
        else:
            break

    kind = choose("\nWhat should it trade?", KINDS)
    strategy = choose("\nHow should it decide when to buy and sell?", STRATEGIES)

    watchlist, use_research = [], False
    if kind != "penny":
        who = "Corvin (the crypto researcher)" if kind == "crypto" else "Quill (the stock researcher)"
        use_research = ask(f"\nLet {who} pick and keep updating its watchlist? (y/n)", "y").lower().startswith("y")
        example = "BTC/USD, SOL/USD" if kind == "crypto" else "AAPL, MSFT, KO"
        while not watchlist:
            raw = ask(f"\n{'Any starting ideas? ' if use_research else ''}Which {'coins' if kind == 'crypto' else 'stocks'} should it watch? "
                      f"Separate with commas (example: {example}){' - or press Enter to let the researcher choose' if use_research else ''}")
            if not raw and use_research:
                break
            for s in raw.replace(" ", "").upper().split(","):
                if not s:
                    continue
                if kind == "crypto" and "/" not in s:
                    s += "/USD"
                watchlist.append(s)
            if not watchlist:
                print("  Please type at least one symbol.")

    most = len(watchlist) if watchlist and not use_research else 5
    max_positions = number(f"\nHow many can it hold at once? (1-{most})", min(3, most), 1, most, int)
    dollars = number("\nStarting pot in dollars (paper money)", 100, 5, 100000)

    stop_loss = take_profit = None
    if ask("\nAdd an automatic stop-loss and take-profit? (y/n)", "y" if kind == "penny" else "n").lower().startswith("y"):
        stop_loss = number("  Sell if a holding drops this many percent", 8, 1, 90) / 100
        take_profit = number("  Sell if a holding rises this many percent", 15, 1, 1000) / 100

    idea = random.choice([n for n in NAME_IDEAS if n not in taken_heroes] or NAME_IDEAS)
    hero = ask("\nHero's name in Goldmire", idea)
    cls = choose("\nHero's class", [(c, c) for c in CLASSES])

    bot = {"name": name, "hero": hero, "class": cls, "kind": kind, "strategy": strategy,
           "dollars": dollars, "max_positions": max_positions, "watchlist": watchlist, "research": use_research}
    if stop_loss:
        bot["stop_loss"], bot["take_profit"] = stop_loss, take_profit

    print("\nNew bot:")
    print(json.dumps(bot, indent=2))
    if not ask("Save it? (y/n)", "y").lower().startswith("y"):
        print("Nothing saved.")
        return 0

    shutil.copyfile(BOTS_FILE, BOTS_FILE + ".bak")
    bots.append(bot)
    with open(BOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved! {hero} the {cls} joins the guild. (Old file kept as bots.json.bak)")
    print("Close 3_run_bot.bat if it is running, then open it again to start the new bot.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing saved.")
