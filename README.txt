GOLDMIRE TRADING BOTS  (paper trading = fake money only)
===========================================================

Your bots run together in one window. Each one is a hero in Goldmire, a
living storybook town that opens in your browser while the bots run, and
that you can also check from your phone.

INSTALL
  Double-click GoldmireSetup.exe. It installs into Documents\Goldmire, sets up
  Python's packages, and adds Goldmire to your desktop and Start menu.
  (Windows may say "Windows protected your PC" because the installer isn't
  from a big company: click "More info", then "Run anyway".)
  No installer? The same steps work by hand with the .bat files (see the end).

RUNNING IN THE BACKGROUND (no black window)
  The Goldmire icon starts everything quietly. Look for the Goldmire icon by
  the clock (it may be hidden behind the ^ arrow):
    * click it          -> opens the town
    * right-click it    -> Open Goldmire / Show the log / Stop Goldmire
  Want to watch everything it does? Start menu > Goldmire (with log window).
  Only one Goldmire can run at a time, so trades never happen twice.

THE BOTS (all in bots.json)
  Stock-1   Gareth (Knight)    trend follower   holds up to 3 stocks
  Stock-2   Wren (Ranger)      dip buyer        holds up to 3 stocks
  Penny     Pip (Rogue)        breakout hunter  holds up to 3 penny stocks it finds itself
  Crypto-1  Old Bram (Alchem.) trend follower   holds up to 2 coins
  Crypto-2  Ysolde (Mage)      dip buyer        holds up to 2 coins
  The watchlists in bots.json are only starting ideas: the researchers replace them.

  * Each bot can hold several stocks at once ("max_positions").
  * Its pot is split into equal slots, one per holding.
  * Two bots never hold the same stock at the same time.
  * Positions you open by hand in Alpaca are left alone.
  * Stock and penny bots trade while the US market is open; crypto bots 24/7.
  * The symbols are examples to test the setup, not picks.

THE RESEARCHERS  -- research.py
  Two researchers keep the watchlists fresh, one per market:

  Mistress Quill, the Loremaster  (stocks)
    Researches at start-up, then every 30 minutes while the US market is open.
    She rests at night and on weekends, when stocks can't trade anyway.
    Leads: today's 100 most-traded stocks, the biggest movers up and down, and
    stocks mentioned in the last 24 hours of news.

  Corvin the Star-Reader  (crypto)
    Researches at start-up, then every 15 minutes, day and night, because crypto
    never closes.
    Leads: every coin Alpaca can trade against US dollars, plus crypto news.

  Each one, for its own heroes:
  1. Studies ~40 days of daily prices for each lead.
  2. Scores each lead for each hero's style:
       trend follower  - steady climbers above their 20-day average
       dip buyer       - liquid names that fell hard in 3 days (low RSI) but
                         aren't in a long collapse
       breakout hunter - pushing through their 20-day high on rising volume
  3. Reads the news: the last 24 hours of headlines (up to 300 stories), each
     scored as good or bad news; newer stories count more.
       good news  - lifts trend and breakout picks
       bad news   - knocks a symbol off every list
       dip buyer  - only buys drops with no bad news behind them
  4. Rewrites each hero's watchlist (6 symbols), always keeping what the hero
     holds right now and anything you "pinned". Two heroes never share a symbol.
  Every change and its reason goes into bot_log.txt, the Town Crier and the
  Researchers' Board on the town page.
  * Penny bots don't use a researcher: they find their own picks every round.
  * Leveraged and inverse funds (2x, 3x, "Bear", "UltraShort"...) are always
    skipped by the researchers and by Pip: they decay over time and confuse signals.
  * Turn research off for one bot: "research": false  (then its watchlist is fixed)
  * Always keep a symbol:          "pinned": ["MSFT"]
  * Change how often:   STOCK_EVERY_MINUTES and CRYPTO_EVERY_MINUTES in research.py
  * Change how many:    WATCH_SIZE in research.py
  * Bench a hero (no new buys; what it holds is still sold by its rules):
                        "benched": true   (remove it, or set false, to bring it back)
  It's a screen, not a crystal ball: it finds symbols that fit each style today.

THE TOWN CRIER: NEWS EVERY 5 MINUTES  -- news.py
  Every round (5 minutes) the crier reads the newest headlines.
  * Big good news (beats estimates, upgrade, FDA approval, big contract...):
    the researcher heads out straight away instead of waiting for the next run.
  * Big bad news (misses, downgrade, lawsuit, hack, bankruptcy...): no hero
    buys it for the next 3 hours, and a hero holding it sells this round.
    To stop one bot selling on news, add "news_exit": false to it in bots.json.
  * Big good news about something a hero HOLDS (now, or bought in the next 3
    days): the hero rides it. It ignores its style's sell signal and trails a
    stop behind the best price instead (its stop distance, or 8%), so a news run
    can keep going but a fade still gets sold. Bad news cancels the ride at once.
    To turn this off for one bot: "news_hold": false in bots.json.
  Big stories show on the town page under "The Town Crier's news".
  Honest note: big funds react to news within seconds, so this won't beat them
  to the first move. What it does well is keep the heroes out of trouble
  and catch stocks that keep drifting for days after good news.

HOW HEROES SELL: STOPS, "LET WINNERS BUILD" AND COOL-DOWNS  -- exits.py
  Every 5 minutes each hero checks what it holds and sells if:
  * there's big bad news about it (the Town Crier), or
  * it hits its stop-loss. Every hero has one now. The default is a SMART stop,
    sized to how jumpy the symbol is: 2.5 x its typical daily move, between 2%
    and 15%. Calm stocks (like SPY) get a tight stop, wild coins a wide one.
  * its style says sell (trend turned down, bounce is "overbought", and so on).
  After a stop-loss or bad-news sale, the hero won't buy that symbol back for
  24 hours. It buys something else from its watchlist instead.
  "Let winners build" (optional, per hero): once a trade is up by its stop
  distance, the hero ignores its style's sell signal and trails a stop behind
  the best price instead, so a strong run can keep going.
  Settings per hero in bots.json:
    "stop_loss": "smart"   (default)  or a number like 0.05 (= 5%)  or null (none)
    "exit": "signal"       (default)  or "build" (let winners build)
  The Proving Grounds tests every style with no stop, 3%, 5%, 8%, smart, and
  "let winners build", and marks the best for stocks and for crypto.

THE PROVING GROUNDS: TEST A STRATEGY BEFORE A HERO USES IT  -- backtest.py
  Start menu > Goldmire - Test strategies (or 6_test_strategies.bat).
  Replays years of real prices for 12 stocks and 8 coins and trades every
  strategy in the "strategies" folder the way a hero would: $100 a trade,
  trading costs included, no peeking at the future. The heroes' current
  styles are tested on the same data for comparison.
  The last 30% of history is an exam: a strategy has to make money there too.
  Verdicts: PASSES (better than what the heroes do now), PROMISING, FAILS.
  The report opens in your browser (proving_grounds/report.html).
  Pip gets his own test: today's busiest $1-$5 stocks over the last 6 months,
  with his old exits (8% stop, sell at +15%) against "let winners build". It's
  a rough guide: stocks that were pennies months ago but aren't now are missing.
  Most strategies fail. That's the point: they fail here, not with your heroes.
  New strategies (for example from trading PDFs) go in the strategies folder;
  see strategies/README.txt. It already holds 19 classic strategies (Turtle,
  RSI(2), Bollinger, MACD, Ichimoku, ADX, NR7 and more) from StockCharts'
  ChartSchool and the trading classics.
  Extra protection against luck: each strategy is compared with 300 make-
  believe traders who buy at random times (same number of trades, held as
  long). To pass, it must beat 95% of them.

SETTINGS UPDATES
  Sometimes an update also changes your heroes' settings (for example after a
  Proving Grounds report). Each change is applied once, logged in bot_log.txt and
  the town's chronicle, and your old bots.json is backed up first as
  bots.json.before-<name>.bak. Copy it back over bots.json to undo.

TEACH A HERO A NEW STRATEGY  -- promote.py
  Start menu > Goldmire - Teach a hero (or 7_teach_a_hero.bat).
  Pick a hero, then a strategy: the ones that PASSED are listed first. Then
  restart Goldmire. The hero trades it exactly as it was tested (same price
  bars, same rules, same stop). Your old settings are kept in bots.json.bak,
  and you can switch a hero back to its built-in style the same way.

ADD A NEW BOT
  Double-click add_bot.bat and answer the questions (what it trades, how it
  decides, whether the researcher picks its watchlist, how many at once,
  starting pot, hero name and class).
  Then close and reopen 3_run_bot.bat. A new hero moves into one of the
  "Plot reserved for a new hero" gardens on Heroes' Row.
  You can also edit bots.json in Notepad. A backup is kept as bots.json.bak.

PENNY BOTS
  Every 5 minutes they look at today's most-traded US stocks, keep the ones
  priced $1-$5 with at least 1 million shares traded (no OTC, warrants or units),
  and buy the ones breaking above their recent high. Each holding is sold on a
  failed breakout, an 8% loss (stop-loss) or a 15% gain (take-profit).
  Any bot can have a stop-loss / take-profit: add "stop_loss": 0.08 and
  "take_profit": 0.15 to it in bots.json (or say yes in add_bot.bat).

POTS, SAVINGS AND PROMOTIONS
  * Each bot starts with its pot (default $100) and reinvests its profits.
  * The pot is capped at the bot's limit ($1,000 to start). Anything over the
    limit is moved to that bot's savings (the vault) and never traded again.
  * Set aside half the limit 3 times within 7 days and the limit goes up:
      $1,000 limit  -> save $1,500 in 7 days ($500 x 3)   -> $5,000 limit
      $5,000 limit  -> save $7,500 in 7 days ($2,500 x 3) -> $10,000 limit
  * Losses only come out of the pot, never savings. A pot under $5 sits out.
  * Change the limits in TIERS at the top of bank.py.

GOLDMIRE (the living town)
  When Goldmire starts (desktop icon, or 3_run_bot.bat), your browser opens
  http://localhost:8777/world.html
  A storybook town on one screen, seen from above.
  * Townsfolk live their own day: merchants at the market, farmers in the
    fields, the smith at the anvil, guards on patrol, children at the pond.
    Most go home at night.
  * When a hero takes trades, they walk out the south gate to camp by the fire.
    When a trade closes they come home: wins go to the vault and then the
    tavern, losses go home to sulk.
  * Quill walks between her archive, the market and the guild board. Corvin
    lives in the star tower and is up all night. Each one hurries to the guild
    board to pin new leads after a research run.
  * Profit fills the town with people, houses, flower boxes, bunting and golden
    light. Losses bring a curse: empty lanes, ruins, rain, crows and graves.
  * Tap anyone to see who they are and what they're doing. "Find in town" on a
    hero card highlights that hero.
  * Below the town: hero cards, the Researchers' Board, quests, the Town Crier
    and deeds.
  * Only this PC can see it, plus your own phone if you turn on phone access.

THE DAY'S LEDGER: YOUR END-OF-DAY REPORT  -- report.py
  In the town, under the heroes: "Today so far", updated every 5 minutes, and
  a report saved for every day at 4:05 PM New York time (3:05 PM Central).
  Use the arrows to page back through earlier days.
  Each report shows: the headline (good, rough or even day), every closed
  trade (hero, paid, sold, result and WHY it sold: stop-loss, take-profit,
  bad news, its style said sell...), what's still held and how it moved
  today, and anything closed outside Goldmire.
  Reports are kept in the world/reports folder.

UPDATES (no reinstalling)
  When a new version of Goldmire is out, a gold "Update ready" button
  appears at the top of the town (on your phone too), and "Update to
  version ..." appears when you right-click the Goldmire icon by the clock.
  Press it. Goldmire downloads the update, checks every file, backs up the
  old files into the "backups" folder, swaps in the new ones and restarts
  by itself. The town page reloads on its own when it's back.
  Never touched by an update: your keys (.env), your heroes (bots.json),
  their gold, savings and levels (bot_state.json), the log, your phone link.
  If anything goes wrong, the old version is put back and keeps running.
  Goldmire looks for updates when it starts and every 6 hours after.
  Where updates come from is set in update.json ("repo" = a GitHub repo).

GOLDMIRE ON YOUR PHONE (works anywhere, private)
  Uses Tailscale (free), which links your PC and phone so only YOUR devices
  can open Goldmire. Nothing is opened to the internet, and keys never leave
  your PC.
  1. Install Tailscale on this PC (tailscale.com/download) and sign in.
  2. Install the Tailscale app on your phone and sign in with the SAME account.
  3. Start menu > Goldmire - Phone access (or 4_phone_access.bat).
     It shows a link and a QR code. Scan the code with your phone's camera.
  4. Add the icon: iPhone (Safari): Share > Add to Home Screen.
                   Android (Chrome): menu > Add to Home screen / Install app.
  Tap the Goldmire icon any time. Your PC must be on with Goldmire running for
  live numbers; if it isn't, the app shows the last report and says so.
  Tip: tick "Start Goldmire when I sign in" in the installer to keep it running.
  To stop sharing: 4_phone_access.bat stop

FIRST-TIME STEPS (Claude will walk you through each one):
  1. Run GoldmireSetup.exe
  2. Make a free account at alpaca.markets, open the PAPER dashboard,
     and generate API keys
  3. Start menu > Goldmire - Alpaca keys: paste the two keys, save (Ctrl+S)
  4. Start menu > Goldmire - Check connection  -> should say SUCCESS
  5. Double-click Goldmire on the desktop      -> runs in the background (icon by the clock)
  Without the installer: unzip, then 1_setup.bat, open_keys_file.bat,
  2_check_connection.bat and 3_run_bot.bat (or 5_run_in_background.bat) do the same steps.

SAFETY
  * The bots are locked to paper trading. They refuse real-money keys.
  * Never paste your keys into chat, email, or GitHub. They live only in .env.
  * The town page only shows the 'world' folder; your keys are never served.
  * Phone access goes only to devices signed in to your own Tailscale account.

FILES
  bots.json          your bots (edit or use add_bot.bat)
  bot_log.txt        everything the bots did
  bot_state.json     pots, savings, holdings, hero levels, deeds (delete to start over)
  world\status.json  what the town is showing right now
  phone_link.txt     your phone link (made by phone access)
