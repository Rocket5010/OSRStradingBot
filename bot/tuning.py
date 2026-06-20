# bot/tuning.py
"""Walk-forward-style parameter tuning for strategies.

Picking parameters that look best over the *whole* history is over-fitting:
they fit the noise and fall apart live. Instead we cut each item's candles into
disjoint contiguous time segments (blocked cross-validation) and score every
parameter combo on each segment *without ever fitting to it*. A combo only wins
if it earns consistently across segments — that is what generalizes.

Objective is deliberately conservative (matches "smaller margin, higher chance,
not aggressive"): we require a combo to be profitable in a healthy fraction of
windows first, and only then rank by mean score. The per-run score itself
(`conservative_score`) multiplies gp/day by hit-rate and double-penalizes
drawdown, so steady, high-probability params beat big-but-rare ones.
"""

from itertools import product

from bot.backtest.engine import run_backtest

# Small per-strategy grids over the knobs that matter. Kept tight so tuning
# stays cheap (combos * folds * items backtests, all local, no extra API).
# Values lean conservative (take profit sooner, tighter stops, calmer bands).
GRIDS = {
    "margin_flip":    {"target_pct": [0.02, 0.03, 0.05],
                       "stop_loss_pct": [0.03, 0.05],
                       "min_margin": [20, 50]},
    "mean_reversion": {"k": [1.5, 2.0, 2.5], "lookback": [20, 30],
                       "stop_loss_pct": [0.10, 0.15]},
    "bollinger":      {"k": [1.5, 2.0, 2.5], "period": [15, 20]},
    "rsi":            {"lo": [25, 30, 35], "hi": [65, 70]},
    "crash_recovery": {"drop_pct": [0.15, 0.20, 0.25],
                       "recover_pct": [0.85, 0.90]},
    "ma_crossover":   {"fast_ma": [5, 10], "slow_ma": [20, 30]},
    "momentum":       {"lookback": [3, 5, 7]},
    "breakout":       {"channel_days": [20, 30], "vol_mult": [1.5, 2.0],
                       "trail_pct": [0.08, 0.10]},
}

# A combo must be profitable in at least this fraction of scored windows to be
# eligible — the conservative gate. Falls back to best mean if none qualify.
POS_FRACTION_GATE = 0.6


def _combos(grid):
    keys = list(grid)
    for vals in product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def conservative_score(result):
    """gp/day weighted by hit-rate, double-penalized by drawdown. Rewards steady,
    high-probability params over volatile big-profit ones."""
    if result.n_trades == 0:
        return 0.0
    return (result.profit_per_day * result.hit_rate) / (1.0 + 2.0 * result.max_drawdown)


def folds(candles, n_folds, min_len=25):
    """Split candles into up to n_folds disjoint contiguous segments, each at
    least min_len long. Returns [] if there isn't even one usable segment."""
    n = len(candles)
    if n < min_len:
        return []
    if n < 2 * min_len:
        return [candles]
    k = min(n_folds, n // min_len)
    size = n // k
    out = []
    for i in range(k):
        start = i * size
        end = n if i == k - 1 else (i + 1) * size
        out.append(candles[start:end])
    return out


def tune_strategy(strategy_name, strategy_cls, candles_by_item, budget,
                  limits=None, n_folds=4, max_hold_steps=30, base_params=None):
    """Return the best parameter combo for a strategy across a basket, chosen by
    blocked cross-validation with the conservative objective. candles_by_item:
    {item_id: candles}. Returns (params, score). params is the combo only —
    strategy defaults fill the rest. If the strategy has no grid, returns
    (base_params or {}, 0.0)."""
    limits = limits or {}
    base = base_params or {}
    grid = GRIDS.get(strategy_name)
    if not grid:
        return dict(base), 0.0

    best_params, best_key = None, None
    for combo in _combos(grid):
        params = {**base, **combo}
        scores, positives, total = [], 0, 0
        for item_id, candles in candles_by_item.items():
            for seg in folds(candles, n_folds):
                r = run_backtest(strategy_cls(**params), seg, budget,
                                 item_id=item_id, buy_limit=limits.get(item_id, 0),
                                 max_hold_steps=max_hold_steps)
                if r.n_trades == 0:
                    continue
                s = conservative_score(r)
                scores.append(s)
                total += 1
                if s > 0:
                    positives += 1
        if total == 0:
            continue
        mean = sum(scores) / len(scores)
        pos_frac = positives / total
        # tuple key: combos clearing the positivity gate sort above those that
        # don't (True > False), then by mean score. This is the conservative bias.
        key = (pos_frac >= POS_FRACTION_GATE, mean)
        if best_key is None or key > best_key:
            best_key, best_params = key, dict(combo)

    if best_params is None:
        return dict(base), 0.0
    return best_params, best_key[1]
