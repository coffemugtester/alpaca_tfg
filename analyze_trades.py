#!/usr/bin/env python3
"""Quick trade analytics analyzer."""
import csv
import sys

symbol = sys.argv[1] if len(sys.argv) > 1 else 'SPY'

# Read analytics
try:
    with open(f'global_comparison/trade_analytics_{symbol}.csv', 'r') as f:
        reader = csv.DictReader(f)
        trades = list(reader)
except FileNotFoundError:
    print(f"Error: trade_analytics_{symbol}.csv not found")
    sys.exit(1)

# Calculate statistics
total_trades = len(trades)
winners = [t for t in trades if float(t['pnl_dollars']) > 0]
losers = [t for t in trades if float(t['pnl_dollars']) <= 0]

win_count = len(winners)
loss_count = len(losers)
win_rate = win_count / total_trades * 100 if total_trades > 0 else 0

avg_win_pct = sum(float(t['pnl_pct']) for t in winners) / win_count if win_count > 0 else 0
avg_loss_pct = sum(float(t['pnl_pct']) for t in losers) / loss_count if loss_count > 0 else 0

total_pnl = sum(float(t['pnl_dollars']) for t in trades)

stop_loss_exits = len([t for t in trades if t['exit_reason'] == 'STOP_LOSS'])
take_profit_exits = len([t for t in trades if t['exit_reason'] == 'TAKE_PROFIT'])
reversal_exits = len([t for t in trades if t['exit_reason'] == 'TREND_REVERSAL'])

# Winners vs losers by exit reason
tp_winners = len([t for t in winners if t['exit_reason'] == 'TAKE_PROFIT'])
tp_losers = len([t for t in losers if t['exit_reason'] == 'TAKE_PROFIT'])
sl_winners = len([t for t in winners if t['exit_reason'] == 'STOP_LOSS'])
sl_losers = len([t for t in losers if t['exit_reason'] == 'STOP_LOSS'])

avg_hold_hours = sum(float(t['hold_duration_hours']) for t in trades) / total_trades if total_trades > 0 else 0

print(f"{symbol} Trade Analytics Summary")
print(f"="*60)
print(f"Total Trades: {total_trades}")
print(f"Win Rate: {win_rate:.1f}% ({win_count}W / {loss_count}L)")
print(f"Avg Win: {avg_win_pct:.2f}% | Avg Loss: {avg_loss_pct:.2f}%")
print(f"Total P&L: ${total_pnl:.2f}")
print(f"")
print(f"Exit Breakdown:")
print(f"  STOP_LOSS:   {stop_loss_exits:4d} ({stop_loss_exits/total_trades*100:5.1f}%) - {sl_winners}W / {sl_losers}L")
print(f"  TAKE_PROFIT: {take_profit_exits:4d} ({take_profit_exits/total_trades*100:5.1f}%) - {tp_winners}W / {tp_losers}L")
if reversal_exits > 0:
    print(f"  REVERSAL:    {reversal_exits:4d} ({reversal_exits/total_trades*100:5.1f}%)")
print(f"")
print(f"Avg Hold Time: {avg_hold_hours:.2f} hours")
print(f"")
if avg_loss_pct != 0:
    print(f"Risk/Reward Ratio: {abs(avg_win_pct/avg_loss_pct):.2f}")

# Transaction cost estimate
round_trips = total_trades
transaction_cost_pct = round_trips * 0.05  # 0.05% per round trip (commission + slippage)
print(f"\nEstimated Transaction Costs: {transaction_cost_pct:.2f}% of initial capital")

# Show best and worst trades
print(f"\nBest 5 Trades:")
best_trades = sorted(winners, key=lambda t: float(t['pnl_pct']), reverse=True)[:5]
for t in best_trades:
    print(f"  {t['entry_time']}: +{t['pnl_pct']}% (${t['pnl_dollars']}) - {t['exit_reason']} - {t['hold_duration_hours']}h")

print(f"\nWorst 5 Trades:")
worst_trades = sorted(losers, key=lambda t: float(t['pnl_pct']))[:5]
for t in worst_trades:
    print(f"  {t['entry_time']}: {t['pnl_pct']}% (${t['pnl_dollars']}) - {t['exit_reason']} - {t['hold_duration_hours']}h")
