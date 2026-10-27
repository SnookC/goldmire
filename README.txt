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
  Stock-1   Gareth (Knight)    trend follower    up to 12 trades open at once
  Stock-2   Wren (Ranger)      Bollinger bounce  up to 15, scanning the 300 busiest stocks
  Penny     Pip (Rogue)        breakout hunter   up to 10 penny stocks
  Crypto-1  Old Bram (Alchem.) Parabolic SAR     up to 10 coins
  Crypto-2  Ysolde (Mage)      Ichimoku cloud    up to 10 coins
  The watchlists in bots.json are only starting ideas: the researchers replace them.

  * Each hero has its own pot (it starts at $100) and can hold several trades at
    once ("max_positions"). It doesn't have to fill every slot.
  * HOW MUCH EACH TRADE SPENDS ("sizing": "risk"): every trade risks the same
    small slice of the pot, about 75 cents of $100, if it goes wrong. A calm
    stock with a tight stop-loss gets more money; a wild one gets less:
        stop 2% away  -> $30 (the most: 30% of the pot)
        stop 4% away  -> $18.75
        stop 10% away -> $7.50
        stop 15% away -> $5 (the least)
    A technique with no stop-loss (Wren's) uses how jumpy the stock is instead.
    Buying stops when the pot is spent, so a hero usually holds 4 to 10 trades.
    Change the slice with "risk": 0.01 (1%) in bots.json; "sizing": "split"
    goes back to splitting the pot into equal slots.
  * "scan": 300 (stock heroes) - instead of a short researched list, the hero
    watches the 300 busiest stocks ($5+, no leveraged funds) and buys only when
    its technique says so. The list is rescanned every hour while the market
    is open: before 10:30 AM New York time (9:30 Central) by yesterday's dollars
    traded, after that by today's dollars traded so far.
    The town shows just what it buys, not the 300.
  * Crypto heroes with "scan" watch every coin Alpaca trades (about 35), most
    traded first. Their daily techniques decide when to buy; two heroes never
    hold the same coin.
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

PROTECTIVE STOPS HELD BY ALPACA  -- guards.py
  Goldmire checks prices every 5 minutes, so a fast drop could slip past a
  stop-loss between checks. Now every holding with a stop also gets a real stop
  order at Alpaca (a "guard"): if the price falls through it, Alpaca sells at
  once. Stocks get a day order, placed again each morning; crypto gets a
  good-till-cancelled stop-limit. With "let winners build" the guard climbs
  with the trailing stop (never down). Before any other sale Goldmire cancels
  the guard first. A guard sale shows in the ledger like any other sale.
  Turn guards off for a hero with "guards": false in bots.json.

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

THE HERO TRIALS: IS EACH HERO EARNING ITS KEEP?  -- hero_test.py
  Double-click 8_hero_trials.bat.
  The Proving Grounds tests a STRATEGY. The Hero Trials tests a HERO, exactly
  as it trades today: its own strategy, stop, "let winners build", slots,
  trade sizing and one $100 pot, on a wide list of busy stocks (or coins),
  and compares it with simply buying and holding SPY (or Bitcoin).
  It follows Alpaca's own backtesting rules (github.com/alpacahq/alpaca-skills):
  orders fill at the next bar's open (no peeking), costs on every buy and
  sell, and the "Teaching Five" for every hero:
    1. total return vs buy-and-hold   2. worst drop   3. trades
    4. win rate                       5. Sharpe (return per unit of bumpiness)
  Two extra checks against luck: history is cut into 4 stretches (a good hero
  makes money in most of them), and a stress test doubles trading costs (a
  hero that only wins when trading is cheap is fragile).
  Verdicts: EARNING, SO-SO, LOSING, TOO FEW (trades to judge).
  Report: proving_grounds/heroes.html. Every simulated trade and the day-by-
  day balance are in proving_grounds/heroes/<hero>/trades.csv and equity.csv.
  It can't see bad-news exits or heroes sharing symbols, and today's busy
  names leave out companies that crashed (that flatters results, most of all
  for pennies). Nothing here places trades.

STOCKS ONLY (from version 1.5.5)
  After the first Hero Trials, crypto was paused: Old Bram now trades stocks with
  the Turtle 55/20 breakout and Ysolde with the daily Ichimoku cloud (the two best
  stock strategies in the Trials). Any coins they still held are sold by themselves.
  Gareth, Wren, Old Bram and Ysolde each have a $300 pot; Pip keeps $100.

THE TEAM: TWO TRADERS AND THREE GUARDIANS (from version 1.5.11)
  In the town (from 1.5.15) the traders are under Heroes of the Guild and the
  guardians have their own section, The Guardians, showing what each one watches.
  A guardian ("role" in bots.json) never opens new trades, only finishes old ones.
  Gareth and Wren are the two stock traders, each with a $500 pot. Pip, Old Bram
  and Ysolde stop trading (anything they still hold is sold by their own rules)
  and take new jobs. Their checks are code, not suggestions:

  Pip, the Risk Manager  -- risk.py   (looks at the whole account before every buy)
    * Daily stop: if the heroes together are down $500 or more today (finished
      trades + today's move in what they hold), nobody buys until the next day.
    * Biggest bet: no more than 20% of a hero's pot in one stock (bigger buys shrink).
    * Industry limit: no more than 50% of the traders' money in one industry.
      Industries come from Nasdaq's free stock list (weekly), saved in industries.json.
    * Only one hero holds a stock at a time (Alpaca keeps one position per stock).

  Old Bram, the Validator  -- validator.py   (judges each trader at start-up)
    PASS / CONDITIONAL / FAIL / INSUFFICIENT EVIDENCE, from the Proving Grounds and
    the Hero Trials. FAIL or INSUFFICIENT EVIDENCE = no new buys. CONDITIONAL may
    trade on paper (paper trading is its next test). To overrule Bram for one hero,
    add  "owner_approved": true  to that hero in bots.json (logged at every start).

  Ysolde, the Execution Manager  -- execution.py
    * Every order carries its own ID (gm-<hero>-<symbol>-buy-...).
    * If sending an order fails, she asks Alpaca whether it arrived before anything
      is sent again, so a dropped connection can't buy twice.
    * Daily check (at start-up and after each close): positions no hero owns, and
      any part of the account's change today the heroes' trades don't explain.
      A gap over $25 is logged as a WARNING.

WREN TRADES ONLY HER TESTED RULES (from version 1.5.26)
  A test on the last year of real headlines (news_exit_test.py) found headline selling cost
  Wren money: her Bollinger rules alone +$85, with headline selling +$60. So for Wren:
  "news_exit": false (no selling or skipped buys on headlines) and "news_hold": false.
  She also makes fewer, bigger trades: "max_positions": 8 and "risk": 0.015 (each trade
  risks 1.5% of her pot if its stop is hit, about twice the size). She keeps what she holds
  and simply stops buying until she's under 8.

THE LAB: NEW IDEAS TESTED IN THE BACKGROUND (from version 1.5.26)  -- lab.py
  Tests a batch of ideas on the 12-stock list and the 60-stock list without touching the
  main results (results.json, which Bram and the Scorecard read). What each idea needs is
  written in strategies\EXPERIMENTS.txt before the run. Reports: proving_grounds\report_lab.html
  and report_lab_wide.html.

FINBERT: A SECOND NEWS READER, IN SHADOW (from version 1.5.21)  -- finbert.py, news_replay.py
  The Town Crier reads headlines with a word list. FinBERT is a small free AI model
  (ProsusAI/finbert, from Hugging Face) trained on financial news. It reads every
  headline too, but for now it DECIDES NOTHING: no sales, no blocked buys.
  * First start: Goldmire installs it by itself in the background (about 1.5 GB of
    downloads, a few minutes). Trading carries on meanwhile. Log: "FinBERT: ready".
  * Where the two readers disagree, it's written to news_shadow.jsonl, and to the log
    when it's about a stock a hero holds ("FinBERT (shadow): ...").
  * The replay test checks the last 60 days of real headlines: after each reader's
    bad-news calls, did the stock really do worse than the S&P 500 the next day?
    Goldmire runs it by itself once FinBERT is ready, then weekly; or double-click
    9_test_news_reader.bat. Report: proving_grounds\news_replay.html
  * FinBERT only gets a vote if it beats the word list by a margin that isn't luck,
    and then only with your OK.
  * The same replay also tests an "is this story really ABOUT this stock?" check
    (from 1.5.23): a bad-news sale only when the headline names the company or its
    ticker. (A Lam Research story also gets tagged SOXX, the chip fund.) Off until
    the test backs it and you OK it.

YOUR HOLDS: BUY SOMETHING AND KEEP IT UNTIL YOU SAY SELL (from version 1.5.18)
  In bots.json a hero can carry "owner_holds", like  "owner_holds": {"XRP/USD": 100}.
  The hero buys each one ONCE for that many dollars, then leaves it alone: no strategy sale,
  no stop-loss, no guard order, no bad-news exit. Bram and Pip don't stop the buy.
  It shows with a blue HOLD tag on the hero's card and doesn't count on the Scorecard.
  To sell it: take it out of owner_holds (or just tell Claude "sell the XRP").
  Raise the number to add more (it buys only the difference).
  Swap one for another and the hero buys the new one first, then sells the old.
  Gareth holds $300 of XRPN (Evernorth) for you this way (paper money, like everything else).
  When you say sell it, Gareth retires ("retire_to": "Stock-2"): his whole pot goes to Wren
  (anything over her pot limit goes to her savings) and he leaves the hero list.

THE WATCHDOG: ALERTS WHEN SOMETHING KEEPS GOING WRONG (from version 1.5.14)  -- watchdog.py
  The Watchdog reads Goldmire's log. When the same problem repeats (3 times within
  an hour for most; at once for Pip's daily stop or money Ysolde can't explain), a
  red alert appears at the top of the town page, on your PC and your phone, and in
  bot_log.txt as "Watchdog: ALERT". After 2 quiet hours it turns grey ("Resolved")
  and then disappears. It only reports: fixes come as tested updates.

THE SCORECARD, THE MARKET WEATHER AND THE CALENDAR (from version 1.5.17)
  The Scorecard (scorecard.py), in the town: for each trader, since its current
    strategy started: what its pot made, what the same money made in the S&P 500,
    and its live win rate and average per trade next to what the Proving Grounds
    measured. TOO EARLY under 20 finished trades; BEHIND (and a Watchdog alert) if
    it wins 15+ points less often than its test, or loses on average where the
    test made money. BEHIND doesn't stop a trader by itself: that's your call.
  Market weather (strategies/_weather.py), on Pip's card: FAIR (S&P 500 above its
    200-day average, not unusually jumpy), WINDY (jumpy) or STORMY (below it).
    Strategies with NEEDS_MARKET = True can use it; they are tested like any other.
  The Calendar (calendar_desk.py), in the town and on each held stock: earnings in
    the next 7 weekdays and the big US economic releases, from Nasdaq's free
    calendars, refreshed daily. Shown for you; the heroes still hold through earnings.

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

SUGGEST A LEAD
  Above the Researchers' Board: type a stock (NVDA) or a coin (BTC), pick a hero
  or "Any hero", and click Suggest. Goldmire checks it with Alpaca first (no
  typos, untradable symbols or leveraged funds). "Any hero" gives it to every
  hero who trades that kind of thing; whoever's technique signals first buys.
  A suggestion is something to watch, never an order to buy. It stays on the
  list ("pinned" in bots.json) until you click its X. Pip finds his own.

BENCHING A HERO
  Every hero card in the town has a Bench button. A benched hero makes no new
  trades; anything it holds is still sold by its normal rules. Click "Send
  back to work" to undo. It takes effect at once, is saved in bots.json
  ("benched": true), and the chronicle notes it. Works from your phone too.

THE DAY'S LEDGER: YOUR END-OF-DAY REPORT  -- report.py
  In the town, under the heroes: "Today so far", updated every 5 minutes, and
  a report saved for every day at 4:05 PM New York time (3:05 PM Central).
  Use the arrows to page back through earlier days.
  Each report shows: the headline (good, rough or even day), every closed
  trade (hero, paid, sold, result and WHY it sold: stop-loss, take-profit,
  bad news, its style said sell...), what's still held and how it moved
  today, and anything closed outside Goldmire.
  Reports are kept in the world/reports folder.
  To hand a day off (to Claude, or anyone): page to that day, then at the
  bottom of the ledger click
    Spreadsheet  - downloads goldmire-ledger-<date>.csv (opens in Excel)
    PDF          - opens the print window; pick "Save as PDF" as the printer
  The PDF is grouped by day, then by hero, with one line per finished trade
  (when it was bought, when it sold, prices, result and why) and what each
  hero still holds. The spreadsheet keeps one line per buy and per sell.
  Both list every buy and sell that day (time, hero, symbol, prices, amount,
  result and why it sold) and what's still held. Days saved before version
  1.4.2 show their sells only; buys are listed from 1.4.2 on.

  SEARCH THE LEDGERS (several days, some or all heroes)
    At the top of the ledger, open "Search the ledgers".
    From / To   - pick the first and last day (e.g. Mon Oct 12 to Fri Oct 16
                  for a week). Only days with a saved ledger are offered.
    Heroes      - tick "All", or untick All and tick just the heroes you want.
    Sort by     - optional. Date (oldest or newest first), biggest profit
                  first, biggest loss first, hero A-Z or symbol A-Z.
    Generate PDF - one click: runs the search with your choices and opens
                  the PDF (pick "Save as PDF" as the printer).
    Search      - shows the totals, a line per hero, every trade in that
                  range and what those heroes still held on the last day.
    The Spreadsheet / PDF buttons then save exactly that search, e.g.
    goldmire-ledger-2026-10-12_to_2026-10-16.csv. "Back to one day" returns
    to the day-by-day view.

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
