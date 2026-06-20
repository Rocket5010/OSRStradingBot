"""Ad-hoc: rank strategies over a mix of expensive value-bucket items and a
couple of liquid ones, to confirm expensive items produce real backtest scores.
Read-only. Run: python -m scripts.rank_check"""

import os
from bot.api_client import WikiClient
from bot.backtest_rank import rank_over_items


def main():
    ua = os.environ.get("OSRS_BOT_UA", "osrs-flip-bot/1.0 (set OSRS_BOT_UA)")
    c = WikiClient(user_agent=ua)
    basket = [27277, 28338, 22978, 31088, 29801, 19547, 26235, 26243, 4151, 561]
    tune = os.environ.get("TUNE", "1") != "0"
    print(f"ranking over {len(basket)} items (tune={tune})...")
    rows = rank_over_items(c, basket, budget=50_000_000, min_candles=30, tune=tune)
    hdr = f"{'strategy':<16}{'gp/day':>12}{'profit':>16}{'trades':>8}{'win%':>6}{'maxDD':>7}  params"
    print(hdr)
    for r in rows:
        print(f"{r['strategy']:<16}{r['profit_per_day']:>12,.0f}"
              f"{r['profit']:>16,}{r['trades']:>8}"
              f"{round(r['win_rate']*100):>5}%{round(r['max_drawdown']*100):>6}%  "
              f"{r.get('params', {})}")


if __name__ == "__main__":
    main()
