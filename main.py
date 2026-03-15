from datetime import datetime, timezone
import argparse

import backtrader as bt

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from local_settings import alpaca_paper
from dcaplotting import DollarCostAveraging
from bnhplotting import BuyAndHold


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a backtest with configurable symbol, date range, and strategy."
    )

    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Ticker symbol to analyze, e.g. SPY, QQQ, AAPL",
    )

    parser.add_argument(
        "--start", type=str, required=True, help="Start date in YYYY-MM-DD format"
    )

    parser.add_argument(
        "--end", type=str, required=True, help="End date in YYYY-MM-DD format"
    )

    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=["dca, bnh"],
        help="Strategy to run",
    )

    parser.add_argument(
        "--cash", type=float, default=10000.0, help="Initial cash for the backtest"
    )

    parser.add_argument("--commission", type=float, default=0.0, help="Commission rate")

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def get_strategy_class(strategy_name: str):
    strategy_map = {
        "dca": DollarCostAveraging,
        "bnh": BuyAndHold,
    }
    return strategy_map[strategy_name]


def run_backtest(
    symbol: str,
    start: datetime,
    end: datetime,
    strategy_name: str,
    cash: float,
    commission: float,
):
    client = StockHistoricalDataClient(
        alpaca_paper["api_key"],
        alpaca_paper["api_secret"],
    )

    request = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment="raw",
    )

    bars = client.get_stock_bars(request)
    df = bars.df

    if df.index.nlevels == 2:
        df = df.xs(symbol)

    print(df.head())
    print("\nRows:", len(df))
    print("Columns:", list(df.columns))
    print("Index type:", type(df.index))

    df_bt = df[["open", "high", "low", "close", "volume"]].copy()

    if getattr(df_bt.index, "tz", None) is not None:
        df_bt.index = df_bt.index.tz_convert(None)

    print(df_bt.head())
    print("tz:", df_bt.index.tz)

    data = bt.feeds.PandasData(dataname=df_bt)

    cerebro = bt.Cerebro()
    cerebro.adddata(data, name=symbol)

    strategy_class = get_strategy_class(strategy_name)
    cerebro.addstrategy(strategy_class)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)

    print("Bars loaded:", len(df_bt))
    print("Starting value:", cerebro.broker.getvalue())

    cerebro.run()

    print("Final value:", cerebro.broker.getvalue())


def main():
    args = parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    run_backtest(
        symbol=args.symbol,
        start=start,
        end=end,
        strategy_name=args.strategy,
        cash=args.cash,
        commission=args.commission,
    )


if __name__ == "__main__":
    main()
