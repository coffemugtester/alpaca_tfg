"""
Base Strategy with Trade Tracking Mixin

Provides unified trade tracking functionality for all strategies.
Handles both:
1. Completed round-trip trades (entry + exit) - for intraday strategies (COMPLETED)
2. Accumulated entries (entry only) - for accumulation strategies (ACCUMULATED)

All strategies should inherit from TradeTrackingMixin to enable analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, TYPE_CHECKING

import backtrader as bt


class _StrategyProtocol(Protocol):
    """Protocol defining attributes expected from bt.Strategy."""
    data: bt.feeds.DataBase
    broker: bt.brokers.BackBroker

    def getposition(self, data: bt.feeds.DataBase | None = None) -> bt.Position: ...


class TradeTrackingMixin:
    """
    Mixin class for tracking trades across all strategies.

    This mixin expects to be used with a class that provides:
    - self.data (bt.feeds.DataBase)
    - self.broker (bt.brokers.BackBroker)
    - self.getposition() method

    Typically used with bt.Strategy subclasses.
    """

    # Declare attributes that will be provided by bt.Strategy
    if TYPE_CHECKING:
        data: bt.feeds.DataBase
        broker: bt.brokers.BackBroker

        def getposition(self, data: bt.feeds.DataBase | None = None) -> bt.Position: ...

    def _init_trade_tracking(self) -> None:
        """Initialize trade tracking variables. Call this in strategy __init__()."""
        # All order executions (buy/sell) - for internal tracking
        self._trades_log: list[dict[str, Any]] = []

        # All trades: OPEN, ACCUMULATED (no exit), or COMPLETED (with exit)
        self._all_trades: list[dict[str, Any]] = []

        # Map to track open trades by a unique ID for updating on exit
        self._open_trade_map: dict[str, int] = {}  # trade_id -> index in _all_trades
        self._trade_id_counter: int = 0

        # Strategy name (set by subclass or auto-detected)
        self._strategy_name: str = self.__class__.__name__

    def _track_order_execution(self, order: bt.Order) -> None:
        """
        Track order execution in trades_log (internal use only).
        Call this from notify_order() when order is completed.
        """
        if order.status != order.Completed:
            return

        action = "BUY" if order.isbuy() else "SELL"
        execution_time = self.data.datetime.datetime(0)  # type: ignore[attr-defined]

        # Log the order execution internally
        self._trades_log.append(
            {
                "datetime": execution_time,
                "action": action,
                "price": order.executed.price,
                "size": order.executed.size,
                "value": order.executed.value,
                "comm": order.executed.comm,
            }
        )

    def _record_trade_entry(
        self,
        order: bt.Order,
        direction: str = "LONG",
        stop_price: float | None = None,
        trade_id: str | None = None,
    ) -> str:
        """
        Record a trade entry immediately when position is opened.

        For ALL strategies - both accumulation and round-trip.
        Call this from notify_order() after _track_order_execution() for BUY orders.

        Args:
            order: The completed BUY order
            direction: 'LONG' or 'SHORT'
            stop_price: Stop loss price if applicable
            trade_id: Optional trade ID for tracking (auto-generated if None)

        Returns:
            trade_id: Unique identifier for this trade (for updating on exit)
        """
        if order.status != order.Completed:
            return ""

        # Generate unique trade ID if not provided
        if trade_id is None:
            trade_id = f"trade_{self._trade_id_counter}"
            self._trade_id_counter += 1

        execution_time = self.data.datetime.datetime(0)  # type: ignore[attr-defined]
        entry_price = order.executed.price
        position_size = order.executed.size
        cash_deployed = entry_price * position_size

        # Get portfolio state from broker
        portfolio_value = float(self.broker.getvalue())  # type: ignore[attr-defined]
        remaining_cash = float(self.broker.getcash())  # type: ignore[attr-defined]
        cumulative_exposure = portfolio_value - remaining_cash
        cumulative_shares = float(self.getposition().size)  # type: ignore[attr-defined]

        trade_record = {
            "trade_id": trade_id,
            "direction": direction,
            "entry_time": execution_time,
            "exit_time": None,
            "entry_price": entry_price,
            "exit_price": None,
            "position_size": position_size,
            "cash_deployed": cash_deployed,
            "cumulative_shares": cumulative_shares,
            "cumulative_exposure": cumulative_exposure,
            "remaining_cash": remaining_cash,
            "total_portfolio_value": portfolio_value,
            "pnl_dollars": None,
            "pnl_pct": None,
            "trade_status": "OPEN",
            "exit_reason": None,
            "hold_duration_seconds": None,
            "stop_price": stop_price,
        }

        # Store trade and track its index
        trade_index = len(self._all_trades)
        self._all_trades.append(trade_record)
        self._open_trade_map[trade_id] = trade_index

        return trade_id

    def _update_trade_exit(
        self,
        trade_id: str,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
    ) -> None:
        """
        Update an existing OPEN trade with exit information.

        For round-trip strategies (Intraday Vol Bands).
        Call this from strategy code when a position is closed.

        Args:
            trade_id: Unique identifier for the trade (returned from _record_trade_entry)
            exit_time: Exit datetime
            exit_price: Exit price
            exit_reason: Reason for exit (e.g., 'TAKE_PROFIT', 'STOP_LOSS', 'SIGNAL')
        """
        # Find the trade in our map
        if trade_id not in self._open_trade_map:
            print(f"WARNING: Trade ID {trade_id} not found in open trades map")
            return

        trade_index = self._open_trade_map[trade_id]
        trade = self._all_trades[trade_index]

        # Calculate P&L
        entry_price = trade["entry_price"]
        position_size = trade["position_size"]
        direction = trade["direction"]

        if direction == "LONG":
            pnl_pct = (exit_price - entry_price) / entry_price
            pnl_dollars = (exit_price - entry_price) * position_size
        else:  # SHORT
            pnl_pct = (entry_price - exit_price) / entry_price
            pnl_dollars = (entry_price - exit_price) * position_size

        hold_duration_seconds = (exit_time - trade["entry_time"]).total_seconds()

        # Get updated portfolio state
        portfolio_value = float(self.broker.getvalue())  # type: ignore[attr-defined]
        remaining_cash = float(self.broker.getcash())  # type: ignore[attr-defined]
        cumulative_exposure = portfolio_value - remaining_cash

        # Update the trade record
        trade.update(
            {
                "exit_time": exit_time,
                "exit_price": exit_price,
                "pnl_pct": pnl_pct,
                "pnl_dollars": pnl_dollars,
                "exit_reason": exit_reason,
                "hold_duration_seconds": hold_duration_seconds,
                "trade_status": "COMPLETED",
                "cumulative_exposure": cumulative_exposure,
                "remaining_cash": remaining_cash,
                "total_portfolio_value": portfolio_value,
            }
        )

        # Remove from open trades map
        del self._open_trade_map[trade_id]

    def _finalize_open_trades(self) -> None:
        """
        Mark any remaining OPEN trades as ACCUMULATED at backtest end.

        Call this in strategy stop() method for all strategies.
        Trades that never exited remain as accumulated positions.
        """
        for trade_id in list(self._open_trade_map.keys()):
            trade_index = self._open_trade_map[trade_id]
            trade = self._all_trades[trade_index]

            # Mark as accumulated (no exit occurred)
            trade["trade_status"] = "ACCUMULATED"

            # Remove from open map
            del self._open_trade_map[trade_id]

    def get_all_trades(self) -> list[dict[str, Any]]:
        """
        Get all trades (OPEN, ACCUMULATED, and COMPLETED).

        Returns:
            List of trade dictionaries with standardized fields:

            Common fields (all trades):
            - trade_id: string
            - direction: 'LONG' or 'SHORT'
            - entry_time: datetime
            - entry_price: float
            - position_size: float (shares/units)
            - cash_deployed: float (entry_price × position_size)
            - cumulative_shares: float (total position size after this trade)
            - cumulative_exposure: float (total position value at current price)
            - remaining_cash: float (cash left after this trade)
            - total_portfolio_value: float (cash + exposure)
            - trade_status: 'OPEN', 'ACCUMULATED', or 'COMPLETED'
            - stop_price: float | None

            ACCUMULATED/OPEN (None for exit fields):
            - exit_time: None
            - exit_price: None
            - pnl_dollars: None
            - pnl_pct: None
            - exit_reason: None
            - hold_duration_seconds: None

            COMPLETED (all fields populated):
            - exit_time: datetime
            - exit_price: float
            - pnl_dollars: float
            - pnl_pct: float
            - exit_reason: string
            - hold_duration_seconds: float
            - cumulative_exposure/remaining_cash/total_portfolio_value updated at exit
        """
        return self._all_trades.copy()

    def get_strategy_name(self) -> str:
        """Get the strategy name for analytics export."""
        return self._strategy_name

    def set_strategy_name(self, name: str) -> None:
        """Set custom strategy name for analytics export."""
        self._strategy_name = name
