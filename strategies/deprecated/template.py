# Below is a minimal, fully‑commented **Backtrader strategy template** that you can drop into any of your projects and start filling in.  
# It includes the essential imports, a strategy skeleton, and a simple `run()` helper so you can test it right away.
#
# ```python
# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-

"""
Backtrader Strategy Template
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A clean, zero‑feature skeleton that shows the layout Backtrader expects.
Feel free to copy‑paste this into your own scripts and add your custom
logic in the designated places.

Key points:

* `__init__` – called once when the strategy object is created.
  Use this for indicators, parameters, etc.
* `next` – called on every bar (i.e., every new data point).
  Put your core trading logic here.
* `stop` – optional, called when the strategy ends (e.g., after all data is processed).
* The `if __name__ == "__main__":` block shows a minimal back‑testing setup.
"""

import backtrader as bt
import datetime
import os


# --------------------------------------------------------------------------- #
# Strategy Skeleton
# --------------------------------------------------------------------------- #
class MyStrategy(bt.Strategy):
    """
    Replace the name and description with your own.
    """

    # -----------------------------------------------------------------------
    # Optional: Define strategy parameters here
    # -----------------------------------------------------------------------
    params = (
        # ('period', 14),  # Example parameter
    )

    # -----------------------------------------------------------------------
    # Called once before any data is processed
    # -----------------------------------------------------------------------
    def __init__(self):
        """
        Initialize the strategy.

        Common tasks:
          * Create indicators
          * Define counters / flags
          * Cache references to data lines (e.g., self.data.close)
        """
        # Example: store a reference to the close price
        self.dataclose = self.datas[0].close

        # Example: create a simple moving average indicator
        # self.sma = bt.indicators.SimpleMovingAverage(self.datas[0], period=self.params.period)

    # -----------------------------------------------------------------------
    # Called for each new bar (i.e., each time step)
    # -----------------------------------------------------------------------
    def next(self):
        """
        Execute your trading logic here.

        Typical pattern:
          * Check positions
          * Generate signals
          * Submit orders
        """
        # Example: simple moving‑average crossover (commented out)
        # if not self.position:  # no position opened
        #     if self.dataclose[0] > self.sma[0]:
        #         self.buy()   # enter long
        # else:
        #     if self.dataclose[0] < self.sma[0]:
        #         self.close()  # close position

        # Replace the following with your own logic
        pass

    # -----------------------------------------------------------------------
    # Optional: Called at the very end of the strategy run
    # -----------------------------------------------------------------------
    def stop(self):
        """
        Called when the strategy is finished. Useful for printing final
        statistics, logging, or cleanup.
        """
        # Example: print final portfolio value
        print(f"Final portfolio value: {self.broker.getvalue():.2f}")


# --------------------------------------------------------------------------- #
# Demo Backtesting Setup (remove or replace with your own)
# --------------------------------------------------------------------------- #
def run_backtest():
    """
    Set up Cerebro, load data, add strategy, and run.
    """
    # Create a cerebro engine
    cerebro = bt.Cerebro()

    # Add our strategy
    cerebro.addstrategy(MyStrategy)

    # ------------------------------------------------------------
    # Data feed – replace with your own source
    # ------------------------------------------------------------
    # For demo purposes, we use the built‑in `YahooFinanceData`.
    # Replace with your own CSV, Pandas DataFrame, etc.
    data = bt.feeds.YahooFinanceData(
        dataname="AAPL",
        fromdate=datetime.datetime(2019, 1, 1),
        todate=datetime.datetime(2020, 1, 1),
    )
    cerebro.adddata(data)

    # ------------------------------------------------------------
    # Optional: set broker settings, commission, slippage, etc.
    # ------------------------------------------------------------
    cerebro.broker.setcash(100000.0)           # initial cash
    cerebro.broker.setcommission(commission=0.001)  # 0.1% commission

    # ------------------------------------------------------------
    # Run the strategy
    # ------------------------------------------------------------
    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())

    # ------------------------------------------------------------
    # Plot the results (requires matplotlib)
    # ------------------------------------------------------------
    cerebro.plot(style='candlestick')


if __name__ == "__main__":
    run_backtest()
#```
#
# ### How to use
#
# 1. **Copy the file** into your project directory.
# 2. **Rename** `MyStrategy` to a more descriptive class name (e.g., `SMA_CrossStrategy`).
# 3. **Implement** your own logic in `__init__`, `next`, and optionally `stop`.
# 4. **Replace** the demo data feed with your own data source if needed.
# 5. Run the script:  
#    ```bash
#    python3 my_strategy_template.py
#    ```
#
Feel free to extend this skeleton with more indicators, parameters, or a custom data feed. Happy coding!
