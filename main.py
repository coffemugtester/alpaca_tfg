from datetime import datetime, timedelta, timezone

# import pandas as pd
import backtrader as bt

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from local_settings import alpaca_paper

# from buyfirst_sellinstop import BuyFirstSellInStop
# from bnhplotting import BuyAndHold
from dcaplotting import DollarCostAveraging

client = StockHistoricalDataClient(
    alpaca_paper["api_key"],
    alpaca_paper["api_secret"],
)

symbol = "SPY"

end = datetime.now(timezone.utc) - timedelta(days=7)
start = end - timedelta(days=365)

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
print("\nRows", len(df))
print("Columns:", list(df.columns))
print("Index type:", type(df.index))

df_bt = df[["open", "high", "low", "close", "volume"]].copy()

df_bt.index = df_bt.index.tz_convert(None)

print(df_bt.head())
print("tz:", df_bt.index.tz)


data = bt.feeds.PandasData(dataname=df_bt)

cerebro = bt.Cerebro()
cerebro.adddata(data, name="SPY")

print("Bars loaded:", len(data))

cerebro.broker.setcash(10_000)
cerebro.broker.setcommission(commission=0.0)

print("Starting value", cerebro.broker.getvalue())

cerebro.addstrategy(DollarCostAveraging)
cerebro.run()

print("Final value:", cerebro.broker.getvalue())
