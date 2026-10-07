THE STRATEGIES FOLDER  (the Proving Grounds test everything in here)

Each strategy is one small .py file. Claude writes these from the trading
PDFs you share: one file per strategy, with the book and page it came from.
Test them all with 6_test_strategies.bat (or: python backtest.py).

A strategy file looks like this:

    """Plain-English rules, exactly as the source describes them."""
    NAME = "Short name"
    SOURCE = "Book title, chapter/page"
    TIMEFRAME = "1Day"          # "15Min", "1Hour" or "1Day" price bars
    MARKETS = ("stock", "crypto")
    STOP_LOSS = 0.08            # optional: sell if down 8% (None = no stop)
    TAKE_PROFIT = None          # optional: sell if up this much

    def signal(bars, position):
        # bars: lists of prices up to now, oldest first:
        #   bars["o"] open, bars["h"] high, bars["l"] low, bars["c"] close, bars["v"] volume
        # position: None when not holding, else {"entry": price paid, "bars_held": n}
        # return "buy", "sell" or None
        ...

Files starting with _ are ignored (handy for parking a strategy).
Only strategies that PASS get handed to a hero, and on paper money first.
