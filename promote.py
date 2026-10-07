"""
Teach a hero a new strategy: switch one hero to a strategy from the strategies folder
(or back to a built-in style). Run it with 7_teach_a_hero.bat.

Best practice: only teach a strategy that PASSES in the Proving Grounds (6_test_strategies.bat).
The change takes effect the next time Goldmire starts.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BOTS_FILE = os.path.join(HERE, "bots.json")

import backtest  # noqa: E402

BUILTIN = {"ma_cross": "Trend follower (built in)", "rsi": "Dip buyer (built in)", "breakout": "Breakout hunter (built in)"}
RANK = {"PASSES": 0, "PROMISING": 1, None: 2, "FAILS": 3, "BROKEN": 4}


def ask(prompt, default=""):
    answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def pick(prompt, options):
    """options: list of (value, text). Returns the chosen value."""
    print(prompt)
    for i, (_, text) in enumerate(options, 1):
        print(f"  {i:2}. {text}")
    while True:
        a = ask("Type a number")
        if a.isdigit() and 1 <= int(a) <= len(options):
            return options[int(a) - 1][0]
        print("  Please type one of the numbers above.")


def main():
    if not os.path.exists(BOTS_FILE):
        print("bots.json wasn't found. Start Goldmire once first, then try again.")
        return 1
    with open(BOTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    bots = data["bots"]
    learned = backtest.file_strategies()
    verdicts = backtest.last_verdicts()
    if not verdicts:
        print("Tip: run 'Goldmire - Test strategies' first, so you can see which strategies passed.\n")

    print("=== Teach a hero a new strategy ===\n")
    hero = pick("Which hero?", [(b, f"{b.get('hero', b['name'])} ({b['name']}, {b['kind']}) - now: "
                                    f"{BUILTIN.get(b['strategy']) or (learned[b['strategy']].name if b['strategy'] in learned else b['strategy'])}")
                               for b in bots])
    market = "crypto" if hero["kind"] == "crypto" else "stock"
    options = []
    for key, st in learned.items():
        if market not in st.markets:
            continue
        r = verdicts.get((key, market))
        v = r["verdict"] if r else None
        extra = f"{v}: {r['why']}" if r else "not tested yet"
        options.append((RANK.get(v, 2), key, f"{st.name}  [{st.timeframe} bars]  - {extra}", v))
    options.sort(key=lambda o: (o[0], o[2]))
    choices = [(key, text) for _, key, text, _ in options] + [(k, t) for k, t in BUILTIN.items()]
    key = pick(f"\nWhich strategy should {hero.get('hero', hero['name'])} use?", choices)
    v = next((o[3] for o in options if o[1] == key), "BUILTIN")
    if v not in ("PASSES", "BUILTIN"):
        print(f"\nCareful: that strategy {'has not been tested yet' if v is None else 'got ' + v + ' in the Proving Grounds'}.")
        if ask("Teach it anyway? Type yes or no", "no").lower() not in ("y", "yes"):
            print("Nothing changed.")
            return 0
    shutil.copy2(BOTS_FILE, BOTS_FILE + ".bak")
    old = hero["strategy"]
    hero["strategy"] = key
    with open(BOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    name = BUILTIN.get(key) or learned[key].name
    print(f"\nDone. {hero.get('hero', hero['name'])} now uses: {name}  (was: {old}).")
    print("Restart Goldmire to put it into action: right-click the Goldmire icon by the clock > Stop Goldmire,")
    print("then start Goldmire again from the Start menu. (The old settings are saved in bots.json.bak.)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nNothing changed.")
