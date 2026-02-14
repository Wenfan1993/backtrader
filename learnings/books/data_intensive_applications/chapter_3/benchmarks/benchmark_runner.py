#!/usr/bin/env python
"""
Benchmark Runner: Compare Standard vs Columnar Storage Performance

This script benchmarks Backtrader with different storage backends:
- standard: Original array.array implementation
- columnar: NumPy-based NumpyLineBuffer implementation

Usage:
    python benchmark_runner.py                         # Standard storage
    python benchmark_runner.py --variant=columnar      # NumPy storage
    python benchmark_runner.py --compare               # Run both and compare
    python benchmark_runner.py --quick                 # Quick test
    python benchmark_runner.py --save results.json     # Save results

Author: Based on DDIA Chapter 3 - Columnar Storage concepts
"""

import argparse
import array
import gc
import json
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

import numpy as np
import pandas as pd

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our NumPy implementation
from implementation.numpy_linebuffer import NumpyLineBuffer


# =============================================================================
# Monkey Patching for Columnar Storage
# =============================================================================

# Store original methods for restoration
_original_linebuffer_methods = {}
_patched = False


def patch_linebuffer_for_numpy():
    """
    Monkey-patch Backtrader's LineBuffer to use NumPy arrays.

    This replaces the core storage mechanism while maintaining API compatibility.
    Must be called BEFORE importing backtrader or after reload.
    """
    global _patched, _original_linebuffer_methods

    if _patched:
        return

    import backtrader.linebuffer as lb

    # Store originals
    _original_linebuffer_methods = {
        'reset': lb.LineBuffer.reset,
        '__getitem__': lb.LineBuffer.__getitem__,
        '__setitem__': lb.LineBuffer.__setitem__,
        'forward': lb.LineBuffer.forward,
        'backwards': lb.LineBuffer.backwards,
        'get': lb.LineBuffer.get,
        'buflen': lb.LineBuffer.buflen,
    }

    # New reset method using NumPy
    def numpy_reset(self):
        """Reset with NumPy array instead of array.array"""
        self.lencount = 0
        self.idx = -1
        self.extension = 0

        # Use NumPy array with pre-allocation
        if self.mode == lb.LineBuffer.QBuffer:
            # QBuffer mode - fixed size
            self.array = np.full(self.maxlen + self.extrasize, np.nan, dtype=np.float64)
            self._capacity = self.maxlen + self.extrasize
        else:
            # UnBounded mode - growable
            initial_capacity = getattr(self, '_initial_capacity', 4096)
            self.array = np.full(initial_capacity, np.nan, dtype=np.float64)
            self._capacity = initial_capacity

        self.useislice = self.mode == lb.LineBuffer.QBuffer

    def numpy_getitem(self, ago):
        """Get item using numpy array"""
        return self.array[self.idx + ago]

    def numpy_setitem(self, ago, value):
        """Set item using numpy array"""
        self.array[self.idx + ago] = value

    def numpy_forward(self, value=np.nan, size=1):
        """Move forward, growing array if needed"""
        self.idx += size
        self.lencount += size

        # Ensure capacity
        needed = self.idx + 1 + getattr(self, 'extension', 0)
        if needed > len(self.array):
            # Grow array with doubling strategy
            new_capacity = max(len(self.array) * 2, needed)
            new_array = np.full(new_capacity, np.nan, dtype=np.float64)
            new_array[:len(self.array)] = self.array
            self.array = new_array
            self._capacity = new_capacity

        # Set value(s)
        if size == 1:
            self.array[self.idx] = value
        else:
            self.array[self.idx - size + 1:self.idx + 1] = value

    def numpy_backwards(self, size=1, force=False):
        """Move backwards"""
        self.idx -= size
        self.lencount -= size
        # Clear the values we're abandoning
        if self.idx + 1 < len(self.array):
            end = min(self.idx + 1 + size, len(self.array))
            self.array[self.idx + 1:end] = np.nan

    def numpy_get(self, ago=0, size=1):
        """Get a slice - returns NumPy VIEW (zero-copy)"""
        end_idx = self.idx + ago + 1
        start_idx = end_idx - size
        return self.array[start_idx:end_idx]

    def numpy_buflen(self):
        """Buffer length"""
        return self.lencount + getattr(self, 'extension', 0)

    # Apply patches
    lb.LineBuffer.reset = numpy_reset
    lb.LineBuffer.__getitem__ = numpy_getitem
    lb.LineBuffer.__setitem__ = numpy_setitem
    lb.LineBuffer.forward = numpy_forward
    lb.LineBuffer.backwards = numpy_backwards
    lb.LineBuffer.get = numpy_get
    lb.LineBuffer.buflen = numpy_buflen

    _patched = True
    print("  [PATCHED] LineBuffer now using NumPy arrays")


def restore_linebuffer():
    """Restore original LineBuffer implementation"""
    global _patched, _original_linebuffer_methods

    if not _patched:
        return

    import backtrader.linebuffer as lb

    for method_name, original_method in _original_linebuffer_methods.items():
        setattr(lb.LineBuffer, method_name, original_method)

    _patched = False
    print("  [RESTORED] LineBuffer using standard array.array")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BenchmarkResult:
    """Result from a single benchmark run"""
    name: str
    variant: str  # "standard" or "columnar"
    data_size: int
    num_indicators: int
    execution_time_ms: float
    peak_memory_mb: float
    current_memory_mb: float
    bars_per_second: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonResult:
    """Comparison between two benchmark runs"""
    baseline: BenchmarkResult
    improved: BenchmarkResult
    speedup_factor: float
    memory_reduction_pct: float


# =============================================================================
# Data Generation
# =============================================================================

def generate_ohlcv_dataframe(size: int, seed: int = 42) -> pd.DataFrame:
    """
    Generate realistic OHLCV data for benchmarking.

    Creates a random walk price series with realistic OHLC relationships.
    """
    np.random.seed(seed)

    # Generate dates
    dates = pd.date_range('2000-01-01', periods=size, freq='1min')

    # Generate close prices as random walk
    returns = np.random.randn(size) * 0.001  # 0.1% volatility per bar
    close = 100 * np.exp(np.cumsum(returns))

    # Generate OHLC with realistic relationships
    volatility = np.abs(np.random.randn(size) * 0.002)
    high = close * (1 + volatility)
    low = close * (1 - volatility)

    # Open is close of previous bar with gap
    open_ = np.roll(close, 1) * (1 + np.random.randn(size) * 0.0005)
    open_[0] = close[0]

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    # Volume follows a log-normal distribution
    volume = np.random.lognormal(mean=10, sigma=1, size=size).astype(int)

    return pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)


# =============================================================================
# Benchmark Runner
# =============================================================================

def run_single_benchmark(
    data_size: int,
    strategy_class: type,
    num_indicators: int = 5,
    variant: str = "standard",
    preload: bool = True,
    runonce: bool = True,
) -> BenchmarkResult:
    """Run a single benchmark and return results"""
    import backtrader as bt

    # Force garbage collection before benchmark
    gc.collect()

    # Generate fresh data
    df = generate_ohlcv_dataframe(data_size)
    data = bt.feeds.PandasData(dataname=df)

    # Setup cerebro
    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    cerebro.addstrategy(strategy_class, num_indicators=num_indicators)

    # Configure execution mode
    cerebro.p.preload = preload
    cerebro.p.runonce = runonce

    # Start memory tracking
    tracemalloc.start()
    gc.collect()

    # Run benchmark
    start_time = time.perf_counter()
    cerebro.run()
    end_time = time.perf_counter()

    # Get memory stats
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Calculate metrics
    execution_time_ms = (end_time - start_time) * 1000
    bars_per_second = data_size / (end_time - start_time) if (end_time - start_time) > 0 else 0

    return BenchmarkResult(
        name=strategy_class.__name__,
        variant=variant,
        data_size=data_size,
        num_indicators=num_indicators,
        execution_time_ms=execution_time_ms,
        peak_memory_mb=peak / 1024 / 1024,
        current_memory_mb=current / 1024 / 1024,
        bars_per_second=bars_per_second,
        timestamp=datetime.now().isoformat(),
    )


def get_strategy_classes():
    """Get strategy classes - must be called after backtrader is imported"""
    import backtrader as bt

    class MinimalStrategy(bt.Strategy):
        """Minimal strategy - just iterates through data"""
        params = (('num_indicators', 0),)
        def next(self):
            pass

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

    class ComplexStrategy(bt.Strategy):
        """Strategy with multiple indicator types"""
        params = (('num_indicators', 10),)

        def __init__(self):
            n = self.p.num_indicators
            self.indicators = []

            # SMAs
            for i in range(n // 3):
                self.indicators.append(bt.indicators.SMA(period=10 + i * 10))

            # EMAs
            for i in range(n // 3):
                self.indicators.append(bt.indicators.EMA(period=10 + i * 10))

            # RSI
            if n > 6:
                self.indicators.append(bt.indicators.RSI())

            # MACD
            if n > 8:
                self.indicators.append(bt.indicators.MACD())

            # Bollinger Bands
            if n > 9:
                self.indicators.append(bt.indicators.BollingerBands())

        def next(self):
            for ind in self.indicators:
                _ = ind[0]

    return [
        ("MinimalStrategy", MinimalStrategy),
        ("SMAStrategy", SMAStrategy),
        ("ComplexStrategy", ComplexStrategy),
    ]


def run_benchmark_suite(
    data_sizes: List[int],
    indicator_counts: List[int],
    variant: str = "standard",
    iterations: int = 3,
    verbose: bool = True,
) -> List[BenchmarkResult]:
    """Run a full benchmark suite"""

    # Apply patch if columnar variant
    if variant == "columnar":
        patch_linebuffer_for_numpy()
    else:
        restore_linebuffer()

    # Import backtrader AFTER patching
    import importlib
    import backtrader
    importlib.reload(backtrader)
    import backtrader as bt

    strategies = get_strategy_classes()

    results = []
    total_benchmarks = len(data_sizes) * len(indicator_counts) * len(strategies) * iterations

    if verbose:
        print(f"\nRunning {total_benchmarks} benchmarks with variant='{variant}'...")
        print("=" * 70)

    benchmark_num = 0

    for data_size in data_sizes:
        for num_indicators in indicator_counts:
            for strategy_name, strategy_class in strategies:
                # Skip indicator count for minimal strategy
                if strategy_name == "MinimalStrategy" and num_indicators > 1:
                    continue

                times = []
                memories = []

                for iteration in range(iterations):
                    benchmark_num += 1

                    if verbose:
                        print(f"[{benchmark_num}/{total_benchmarks}] "
                              f"{strategy_name}, {data_size:,} bars, "
                              f"{num_indicators} indicators, "
                              f"iteration {iteration + 1}/{iterations}...",
                              end=" ", flush=True)

                    result = run_single_benchmark(
                        data_size=data_size,
                        strategy_class=strategy_class,
                        num_indicators=num_indicators,
                        variant=variant,
                    )

                    times.append(result.execution_time_ms)
                    memories.append(result.peak_memory_mb)

                    if verbose:
                        print(f"{result.execution_time_ms:.1f}ms, "
                              f"{result.peak_memory_mb:.1f}MB")

                # Store median result
                median_idx = len(times) // 2
                sorted_times = sorted(range(len(times)), key=lambda i: times[i])
                median_time = times[sorted_times[median_idx]]

                # Create summary result with median
                summary_result = BenchmarkResult(
                    name=strategy_name,
                    variant=variant,
                    data_size=data_size,
                    num_indicators=num_indicators if strategy_name != "MinimalStrategy" else 0,
                    execution_time_ms=median_time,
                    peak_memory_mb=max(memories),
                    current_memory_mb=memories[sorted_times[median_idx]],
                    bars_per_second=data_size / (median_time / 1000),
                    timestamp=datetime.now().isoformat(),
                )
                results.append(summary_result)

    return results


# =============================================================================
# Results Display
# =============================================================================

def print_results_table(results: List[BenchmarkResult], title: str = None):
    """Print results in a formatted table"""

    if not results:
        print("No results to display")
        return

    variant = results[0].variant
    title = title or f"BENCHMARK RESULTS ({variant.upper()} STORAGE)"

    print("\n" + "=" * 95)
    print(title)
    print("=" * 95)
    print(f"{'Strategy':<18} {'Variant':<10} {'Data Size':>12} {'Indicators':>11} "
          f"{'Time (ms)':>11} {'Memory (MB)':>12} {'Bars/sec':>12}")
    print("-" * 95)

    for r in results:
        print(f"{r.name:<18} {r.variant:<10} {r.data_size:>12,} {r.num_indicators:>11} "
              f"{r.execution_time_ms:>11.1f} {r.peak_memory_mb:>12.1f} "
              f"{r.bars_per_second:>12,.0f}")

    print("=" * 95)


def print_comparison(standard_results: List[BenchmarkResult],
                     columnar_results: List[BenchmarkResult]):
    """Print comparison between standard and columnar results"""

    print("\n" + "=" * 100)
    print("COMPARISON: STANDARD vs COLUMNAR")
    print("=" * 100)
    print(f"{'Strategy':<18} {'Data Size':>10} {'Ind':>4} "
          f"{'Std (ms)':>10} {'Col (ms)':>10} {'Speedup':>8} "
          f"{'Std (MB)':>10} {'Col (MB)':>10} {'Mem Δ':>8}")
    print("-" * 100)

    # Match results by (name, data_size, num_indicators)
    std_map = {(r.name, r.data_size, r.num_indicators): r for r in standard_results}
    col_map = {(r.name, r.data_size, r.num_indicators): r for r in columnar_results}

    for key in sorted(std_map.keys()):
        if key not in col_map:
            continue

        std = std_map[key]
        col = col_map[key]

        speedup = std.execution_time_ms / col.execution_time_ms if col.execution_time_ms > 0 else 0
        mem_delta = ((col.peak_memory_mb - std.peak_memory_mb) / std.peak_memory_mb * 100
                     if std.peak_memory_mb > 0 else 0)

        speedup_str = f"{speedup:.2f}x" if speedup >= 1 else f"{1/speedup:.2f}x slower"
        mem_str = f"{mem_delta:+.1f}%"

        print(f"{std.name:<18} {std.data_size:>10,} {std.num_indicators:>4} "
              f"{std.execution_time_ms:>10.1f} {col.execution_time_ms:>10.1f} {speedup_str:>8} "
              f"{std.peak_memory_mb:>10.1f} {col.peak_memory_mb:>10.1f} {mem_str:>8}")

    print("=" * 100)

    # Summary stats
    speedups = []
    for key in std_map.keys():
        if key in col_map:
            std = std_map[key]
            col = col_map[key]
            if col.execution_time_ms > 0:
                speedups.append(std.execution_time_ms / col.execution_time_ms)

    if speedups:
        avg_speedup = sum(speedups) / len(speedups)
        max_speedup = max(speedups)
        min_speedup = min(speedups)
        print(f"\nSpeedup Summary:")
        print(f"  Average: {avg_speedup:.2f}x")
        print(f"  Best:    {max_speedup:.2f}x")
        print(f"  Worst:   {min_speedup:.2f}x")


def print_scaling_analysis(results: List[BenchmarkResult]):
    """Analyze how performance scales with data size"""

    print("\n" + "=" * 70)
    print("SCALING ANALYSIS")
    print("=" * 70)

    # Group by strategy and variant
    groups = {}
    for r in results:
        key = (r.name, r.variant)
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    for (strategy, variant), strategy_results in sorted(groups.items()):
        if len(strategy_results) < 2:
            continue

        # Sort by data size
        strategy_results.sort(key=lambda r: r.data_size)

        print(f"\n{strategy} ({variant}):")
        print(f"  {'Data Size':>12} → {'Data Size':>12}  |  "
              f"{'Time Ratio':>10}  {'Memory Ratio':>12}")
        print("  " + "-" * 60)

        for i in range(1, len(strategy_results)):
            prev = strategy_results[i - 1]
            curr = strategy_results[i]

            data_ratio = curr.data_size / prev.data_size
            time_ratio = curr.execution_time_ms / prev.execution_time_ms
            memory_ratio = curr.peak_memory_mb / prev.peak_memory_mb if prev.peak_memory_mb > 0 else 0

            print(f"  {prev.data_size:>12,} → {curr.data_size:>12,}  |  "
                  f"{time_ratio:>10.2f}x  {memory_ratio:>12.2f}x")


def save_results(results: List[BenchmarkResult], filepath: str, variant: str = None):
    """Save results to JSON file"""
    import backtrader as bt

    output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "python_version": sys.version,
            "backtrader_version": getattr(bt, '__version__', 'unknown'),
            "variant": variant or results[0].variant if results else "unknown",
        },
        "results": [r.to_dict() for r in results],
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {filepath}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Backtrader data feed performance"
    )
    parser.add_argument(
        "--variant", type=str, choices=["standard", "columnar"], default="standard",
        help="Storage variant to benchmark (default: standard)"
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Run both variants and compare results"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Run quick benchmark with smaller data sizes"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run full benchmark including large data sizes"
    )
    parser.add_argument(
        "--iterations", type=int, default=3,
        help="Number of iterations per benchmark (default: 3)"
    )
    parser.add_argument(
        "--save", type=str, metavar="FILE",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output"
    )

    args = parser.parse_args()

    # Configure benchmark sizes
    if args.quick:
        data_sizes = [1_000, 1_000_000]
        indicator_counts = [5]
        iterations = 1
    elif args.full:
        data_sizes = [1_000, 10_000, 100_000, 1_000_000]
        indicator_counts = [1, 5, 10, 20]
        iterations = args.iterations
    else:
        # Default: moderate benchmark
        data_sizes = [1_000, 10_000, 100_000]
        indicator_counts = [1, 5, 10]
        iterations = args.iterations

    print("\n" + "=" * 70)
    print("BACKTRADER STORAGE BENCHMARK")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Variant: {args.variant if not args.compare else 'standard + columnar'}")
    print(f"  Data sizes: {data_sizes}")
    print(f"  Indicator counts: {indicator_counts}")
    print(f"  Iterations per benchmark: {iterations}")

    all_results = []

    if args.compare:
        # Run both variants
        print("\n" + "#" * 70)
        print(" RUNNING STANDARD VARIANT")
        print("#" * 70)
        standard_results = run_benchmark_suite(
            data_sizes=data_sizes,
            indicator_counts=indicator_counts,
            variant="standard",
            iterations=iterations,
            verbose=not args.quiet,
        )
        all_results.extend(standard_results)

        print("\n" + "#" * 70)
        print(" RUNNING COLUMNAR VARIANT")
        print("#" * 70)
        columnar_results = run_benchmark_suite(
            data_sizes=data_sizes,
            indicator_counts=indicator_counts,
            variant="columnar",
            iterations=iterations,
            verbose=not args.quiet,
        )
        all_results.extend(columnar_results)

        # Display comparison
        print_results_table(standard_results, "STANDARD STORAGE RESULTS")
        print_results_table(columnar_results, "COLUMNAR (NUMPY) STORAGE RESULTS")
        print_comparison(standard_results, columnar_results)

    else:
        # Run single variant
        results = run_benchmark_suite(
            data_sizes=data_sizes,
            indicator_counts=indicator_counts,
            variant=args.variant,
            iterations=iterations,
            verbose=not args.quiet,
        )
        all_results = results
        print_results_table(results)
        print_scaling_analysis(results)

    # Save results
    if args.save:
        save_results(all_results, args.save)
    else:
        variant_str = "comparison" if args.compare else args.variant
        default_path = Path(__file__).parent / "results" / f"{variant_str}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        default_path.parent.mkdir(exist_ok=True)
        save_results(all_results, str(default_path))

    # Restore original if we patched
    restore_linebuffer()

    print("\n" + "=" * 70)
    print("USAGE")
    print("=" * 70)
    print("""
Run different variants:
  python benchmark_runner.py --variant=standard   # Original array.array
  python benchmark_runner.py --variant=columnar   # NumPy arrays
  python benchmark_runner.py --compare            # Run both and compare
  python benchmark_runner.py --compare --quick    # Quick comparison
""")


if __name__ == "__main__":
    main()
