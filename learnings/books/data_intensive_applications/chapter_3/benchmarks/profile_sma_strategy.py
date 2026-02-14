#!/usr/bin/env python
"""
cProfile Example: Profiling SMAStrategy with Backtrader

This script demonstrates how to use cProfile to profile Python code,
following concepts from "High Performance Python" Chapter 2.

Usage:
    python profile_sma_strategy.py                    # Run with stats printed
    python profile_sma_strategy.py --save profile.prof  # Save to file for pstats
    python profile_sma_strategy.py --cumulative       # Sort by cumulative time
    python profile_sma_strategy.py --callers          # Show callers info

Analyzing saved profile:
    python -m pstats profile.prof
    >>> sort cumtime
    >>> stats 20
"""

import argparse
import cProfile
import pstats
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add backtrader to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import backtrader as bt


# =============================================================================
# Data Generation
# =============================================================================

def generate_ohlcv_dataframe(size: int, seed: int = 42) -> pd.DataFrame:
    """Generate realistic OHLCV data for profiling."""
    np.random.seed(seed)

    dates = pd.date_range('2000-01-01', periods=size, freq='1min')
    returns = np.random.randn(size) * 0.001
    close = 100 * np.exp(np.cumsum(returns))

    volatility = np.abs(np.random.randn(size) * 0.002)
    high = close * (1 + volatility)
    low = close * (1 - volatility)

    open_ = np.roll(close, 1) * (1 + np.random.randn(size) * 0.0005)
    open_[0] = close[0]

    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = np.random.lognormal(mean=10, sigma=1, size=size).astype(int)

    return pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)


# =============================================================================
# Strategy Definition
# =============================================================================

class SMAStrategy(bt.Strategy):
    """Strategy with multiple SMA indicators"""
    params = (('num_indicators', 5),)

    def __init__(self):
        periods = [10, 20, 50, 100, 200]
        self.smas = []
        for i in range(min(self.p.num_indicators, len(periods))):
            self.smas.append(bt.indicators.SMA(period=periods[i]))

    def next(self):
        for sma in self.smas:
            _ = sma[0]


# =============================================================================
# Profiling Functions
# =============================================================================

def run_backtest(data_size: int = 100_000, num_indicators: int = 5):
    """Run the backtest - this is what we profile."""
    df = generate_ohlcv_dataframe(data_size)
    data = bt.feeds.PandasData(dataname=df)

    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    cerebro.addstrategy(SMAStrategy, num_indicators=num_indicators)

    cerebro.run()


def profile_with_cprofile(
    data_size: int = 100_000,
    sort_by: str = 'tottime',
    num_lines: int = 30,
    save_to: str = None,
    show_callers: bool = False,
):
    """
    Profile the backtest using cProfile.

    Args:
        data_size: Number of bars to process
        sort_by: How to sort results ('tottime', 'cumtime', 'calls', 'ncalls')
        num_lines: Number of top functions to show
        save_to: Path to save profile data (optional)
        show_callers: Whether to show caller information

    Sort key meanings:
        - tottime: Total time spent IN the function (excluding sub-calls)
        - cumtime: Cumulative time (including all sub-calls)
        - calls: Number of calls to the function
        - ncalls: Same as calls
    """
    # Create profiler
    profiler = cProfile.Profile()

    print(f"\n{'='*70}")
    print(f"PROFILING SMAStrategy with {data_size:,} bars")
    print(f"{'='*70}")

    # Profile the backtest
    profiler.enable()
    run_backtest(data_size=data_size)
    profiler.disable()

    # Save raw profile data if requested
    if save_to:
        profiler.dump_stats(save_to)
        print(f"\nProfile data saved to: {save_to}")
        print(f"Analyze with: python -m pstats {save_to}")

    # Create stats object for analysis
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)

    # Strip directory names for cleaner output
    stats.strip_dirs()

    # Sort and print stats
    print(f"\n{'='*70}")
    print(f"TOP {num_lines} FUNCTIONS (sorted by {sort_by})")
    print(f"{'='*70}")

    stats.sort_stats(sort_by)
    stats.print_stats(num_lines)
    print(stream.getvalue())

    # Show callers if requested
    if show_callers:
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.strip_dirs()
        stats.sort_stats(sort_by)

        print(f"\n{'='*70}")
        print(f"CALLERS (who called these functions)")
        print(f"{'='*70}")
        stats.print_callers(10)
        print(stream.getvalue())

    return profiler


def explain_profile_output():
    """Print explanation of cProfile output columns."""
    print("""
================================================================================
UNDERSTANDING cPROFILE OUTPUT
================================================================================

Column explanations:
--------------------
  ncalls    : Number of calls to this function
              Format: "X/Y" means X total calls, Y primitive (non-recursive) calls

  tottime   : Total time spent IN this function (excluding time in sub-functions)
              This helps identify functions with expensive internal operations

  percall   : tottime / ncalls (average time per call, excluding sub-calls)

  cumtime   : Cumulative time spent in this function AND all sub-functions
              This shows the "total cost" of calling this function

  percall   : cumtime / ncalls (average total time per call, including sub-calls)

  filename:lineno(function) : Location of the function


Key insights for optimization:
------------------------------
1. High tottime = Function doing heavy work itself → optimize internal code
2. High cumtime, low tottime = Function calling expensive sub-functions
3. High ncalls = Function called many times → consider caching or batching
4. tottime ≈ cumtime = Function is a "leaf" (doesn't call other functions)


Common backtrader hotspots:
---------------------------
- linebuffer.py: __getitem__, __setitem__, forward → Data access patterns
- lineiterator.py: next, _next, prenext → Strategy iteration
- lineseries.py: __getattr__ → Attribute access overhead
- indicators.py: SMA calculations → Numerical operations
""")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Profile SMAStrategy using cProfile"
    )
    parser.add_argument(
        "--size", type=int, default=100_000,
        help="Number of data bars (default: 100,000)"
    )
    parser.add_argument(
        "--save", type=str, metavar="FILE",
        help="Save profile to file for later analysis with pstats"
    )
    parser.add_argument(
        "--cumulative", action="store_true",
        help="Sort by cumulative time instead of total time"
    )
    parser.add_argument(
        "--callers", action="store_true",
        help="Show caller information"
    )
    parser.add_argument(
        "--lines", type=int, default=30,
        help="Number of top functions to show (default: 30)"
    )
    parser.add_argument(
        "--explain", action="store_true",
        help="Show explanation of profile output columns"
    )

    args = parser.parse_args()

    if args.explain:
        explain_profile_output()
        return

    sort_by = 'cumtime' if args.cumulative else 'tottime'

    profile_with_cprofile(
        data_size=args.size,
        sort_by=sort_by,
        num_lines=args.lines,
        save_to=args.save,
        show_callers=args.callers,
    )

    # Print tips
    print(f"""
================================================================================
NEXT STEPS
================================================================================
1. Identify the hotspot functions (high tottime or cumtime)

2. For saved profiles, use pstats interactively:
   python -m pstats {args.save or 'profile.prof'}
   >>> sort cumtime
   >>> stats 20
   >>> callers <function_name>

3. Common optimization targets in backtrader:
   - LineBuffer.__getitem__: Data access (consider vectorization)
   - Strategy.next: Called every bar (minimize work per call)
   - Indicator calculations: NumPy vectorization can help

4. Run with --cumulative to see total cost including sub-functions
   Run with --callers to see who calls expensive functions

5. Use --explain to understand the output columns
""")


if __name__ == "__main__":
    main()
