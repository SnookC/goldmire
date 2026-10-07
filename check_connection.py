"""Checks that your Alpaca paper keys work. Places NO trades."""
import sys
from bot import load_keys, log


def main():
    from alpaca.trading.client import TradingClient
    key, secret = load_keys()
    try:
        trading = TradingClient(key, secret, paper=True)
        acct = trading.get_account()
        clock = trading.get_clock()
    except Exception as e:
        log.error(f"Could not connect: {e}")
        log.error("Most common fix: re-copy both keys from the PAPER dashboard into .env (no spaces, no quotes).")
        sys.exit(1)

    print()
    print("=" * 50)
    print(" SUCCESS - connected to your PAPER account")
    print(f" Status:        {acct.status}")
    print(f" Fake cash:     ${float(acct.cash):,.2f}")
    print(f" Buying power:  ${float(acct.buying_power):,.2f}")
    print(f" Stock market:  {'OPEN' if clock.is_open else 'CLOSED'}")
    print("=" * 50)
    print(" Next step: double-click 3_run_bot.bat")
    print()


if __name__ == "__main__":
    main()
