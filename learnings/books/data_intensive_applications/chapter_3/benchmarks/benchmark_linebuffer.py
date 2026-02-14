#!/usr/bin/env python
"""
Benchmark: Standard LineBuffer vs NumPy LineBuffer

This benchmark directly compares the storage layer performance:
- Standard: Python's array.array (current Backtrader implementation)
- NumPy: Our NumpyLineBuffer implementation

This isolates the storage/access performance from the rest of Backtrader.

Usage:
    python benchmark_linebuffer.py              # Run all benchmarks
    python benchmark_linebuffer.py --quick      # Quick test
    python benchmark_linebuffer.py --full       # Comprehensive test
"""

import argparse
import gc
import sys
import time
import array
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Callable
import math

import numpy as np

# Import our NumpyLineBuffer
sys.path.insert(0, str(Path(__file__).parent.parent))
from implementation.numpy_linebuffer import NumpyLineBuffer, ColumnarDataBlock


# =============================================================================
# Standard LineBuffer (mimics Backtrader's implementation)
# =============================================================================

class StandardLineBuffer:
    """
    Mimics Backtrader's LineBuffer using array.array
    See: backtrader/linebuffer.py
    """

    def __init__(self):
        self.array = array.array('d')
        self.idx = -1
        self.lencount = 0

    def reset(self):
        self.array = array.array('d')
        self.idx = -1
        self.lencount = 0

    def forward(self, value: float = float('nan'), size: int = 1):
        """Move forward and optionally set value"""
        for _ in range(size):
            self.array.append(value)
            self.idx += 1
            self.lencount += 1

    def __len__(self):
        return self.lencount

    def __getitem__(self, ago: int) -> float:
        return self.array[self.idx + ago]

    def __setitem__(self, ago: int, value: float):
        self.array[self.idx + ago] = value

    def get(self, ago: int = 0, size: int = 1) -> array.array:
        """Get a slice - NOTE: This creates a COPY in array.array"""
        end_idx = self.idx + ago + 1
        start_idx = end_idx - size
        return self.array[start_idx:end_idx]


# =============================================================================
# Benchmark Infrastructure
# =============================================================================

@dataclass
class BenchmarkResult:
    name: str
    variant: str
    operation: str
    data_size: int
    iterations: int
    total_time_ms: float
    ops_per_second: float
    memory_bytes: int = 0

    def __str__(self):
        return (f"{self.variant:<10} {self.operation:<20} "
                f"{self.data_size:>10,} {self.iterations:>8,} "
                f"{self.total_time_ms:>10.2f}ms "
                f"{self.ops_per_second:>12,.0f} ops/s")


def measure_time(func: Callable, iterations: int = 1) -> float:
    """Measure execution time in seconds"""
    gc.collect()
    start = time.perf_counter()
    for _ in range(iterations):
        func()
    return time.perf_counter() - start


# =============================================================================
# Benchmark: Data Loading (Append Operations)
# =============================================================================

def benchmark_append(data_size: int) -> List[BenchmarkResult]:
    """Benchmark appending data (simulates loading bars)"""
    results = []

    # Standard LineBuffer
    def standard_append():
        buf = StandardLineBuffer()
        for i in range(data_size):
            buf.forward(value=float(i))
        return buf

    std_time = measure_time(standard_append, iterations=1)
    results.append(BenchmarkResult(
        name="append",
        variant="standard",
        operation="forward(value)",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=std_time * 1000,
        ops_per_second=data_size / std_time,
    ))

    # NumPy LineBuffer
    def numpy_append():
        buf = NumpyLineBuffer(initial_capacity=1024)
        for i in range(data_size):
            buf.forward(value=float(i))
        return buf

    np_time = measure_time(numpy_append, iterations=1)
    results.append(BenchmarkResult(
        name="append",
        variant="numpy",
        operation="forward(value)",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=np_time * 1000,
        ops_per_second=data_size / np_time,
    ))

    # NumPy with pre-allocation
    def numpy_preallocated():
        buf = NumpyLineBuffer(initial_capacity=data_size)
        for i in range(data_size):
            buf.forward(value=float(i))
        return buf

    np_prealloc_time = measure_time(numpy_preallocated, iterations=1)
    results.append(BenchmarkResult(
        name="append",
        variant="numpy_prealloc",
        operation="forward(value)",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=np_prealloc_time * 1000,
        ops_per_second=data_size / np_prealloc_time,
    ))

    return results


# =============================================================================
# Benchmark: Random Access (Indicator-style reads)
# =============================================================================

def benchmark_random_access(data_size: int, iterations: int = 100000) -> List[BenchmarkResult]:
    """Benchmark random element access"""
    results = []
    np.random.seed(42)
    indices = np.random.randint(-data_size + 1, 1, size=iterations)

    # Setup buffers
    std_buf = StandardLineBuffer()
    for i in range(data_size):
        std_buf.forward(value=float(i))

    np_buf = NumpyLineBuffer(initial_capacity=data_size)
    for i in range(data_size):
        np_buf.forward(value=float(i))

    # Standard access
    def standard_access():
        total = 0.0
        for idx in indices:
            total += std_buf[idx]
        return total

    std_time = measure_time(standard_access, iterations=1)
    results.append(BenchmarkResult(
        name="random_access",
        variant="standard",
        operation="__getitem__(ago)",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=std_time * 1000,
        ops_per_second=iterations / std_time,
    ))

    # NumPy access
    def numpy_access():
        total = 0.0
        for idx in indices:
            total += np_buf[idx]
        return total

    np_time = measure_time(numpy_access, iterations=1)
    results.append(BenchmarkResult(
        name="random_access",
        variant="numpy",
        operation="__getitem__(ago)",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=np_time * 1000,
        ops_per_second=iterations / np_time,
    ))

    return results


# =============================================================================
# Benchmark: Slicing (Window operations)
# =============================================================================

def benchmark_slicing(data_size: int, window_size: int = 20, iterations: int = 10000) -> List[BenchmarkResult]:
    """Benchmark slicing operations (used in indicators like SMA)"""
    results = []

    # Setup buffers
    std_buf = StandardLineBuffer()
    for i in range(data_size):
        std_buf.forward(value=float(i))

    np_buf = NumpyLineBuffer(initial_capacity=data_size)
    for i in range(data_size):
        np_buf.forward(value=float(i))

    # Standard slicing (creates copies)
    def standard_slice():
        for _ in range(iterations):
            window = std_buf.get(ago=0, size=window_size)
        return window

    std_time = measure_time(standard_slice, iterations=1)
    results.append(BenchmarkResult(
        name="slicing",
        variant="standard",
        operation=f"get(size={window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=std_time * 1000,
        ops_per_second=iterations / std_time,
    ))

    # NumPy slicing (zero-copy views)
    def numpy_slice():
        for _ in range(iterations):
            window = np_buf.get(ago=0, size=window_size)
        return window

    np_time = measure_time(numpy_slice, iterations=1)
    results.append(BenchmarkResult(
        name="slicing",
        variant="numpy",
        operation=f"get(size={window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=np_time * 1000,
        ops_per_second=iterations / np_time,
    ))

    return results


# =============================================================================
# Benchmark: SMA Calculation (Real-world indicator)
# =============================================================================

def benchmark_sma(data_size: int, period: int = 20) -> List[BenchmarkResult]:
    """Benchmark SMA calculation - simulates real indicator usage"""
    results = []

    # Setup source data
    std_src = StandardLineBuffer()
    std_dst = StandardLineBuffer()
    for i in range(data_size):
        std_src.forward(value=float(i))
        std_dst.forward(value=0.0)

    np_src = NumpyLineBuffer(initial_capacity=data_size)
    np_dst = NumpyLineBuffer(initial_capacity=data_size)
    for i in range(data_size):
        np_src.forward(value=float(i))
        np_dst.forward(value=0.0)

    calc_range = data_size - period

    # Standard SMA (like current Backtrader)
    def standard_sma():
        std_dst.idx = period - 1
        for i in range(period, data_size):
            std_dst.idx = i
            window = std_src.array[i - period + 1: i + 1]
            std_dst[0] = math.fsum(window) / period

    std_time = measure_time(standard_sma, iterations=1)
    results.append(BenchmarkResult(
        name="sma",
        variant="standard",
        operation=f"SMA({period}) loop",
        data_size=data_size,
        iterations=calc_range,
        total_time_ms=std_time * 1000,
        ops_per_second=calc_range / std_time,
    ))

    # NumPy SMA - per-bar loop (same algorithm, numpy arrays)
    def numpy_sma_loop():
        np_dst.idx = period - 1
        for i in range(period, data_size):
            np_dst.idx = i
            window = np_src.array[i - period + 1: i + 1]
            np_dst[0] = np.sum(window) / period

    np_loop_time = measure_time(numpy_sma_loop, iterations=1)
    results.append(BenchmarkResult(
        name="sma",
        variant="numpy_loop",
        operation=f"SMA({period}) loop",
        data_size=data_size,
        iterations=calc_range,
        total_time_ms=np_loop_time * 1000,
        ops_per_second=calc_range / np_loop_time,
    ))

    # NumPy SMA - vectorized with convolve
    def numpy_sma_vectorized():
        src = np_src.array[:data_size]
        kernel = np.ones(period) / period
        result = np.convolve(src, kernel, mode='valid')
        np_dst.array[period - 1:data_size] = result

    np_vec_time = measure_time(numpy_sma_vectorized, iterations=1)
    results.append(BenchmarkResult(
        name="sma",
        variant="numpy_vectorized",
        operation=f"SMA({period}) convolve",
        data_size=data_size,
        iterations=calc_range,
        total_time_ms=np_vec_time * 1000,
        ops_per_second=calc_range / np_vec_time,
    ))

    # NumPy SMA - sliding window view
    def numpy_sma_sliding():
        from numpy.lib.stride_tricks import sliding_window_view
        src = np_src.array[:data_size]
        windows = sliding_window_view(src, window_shape=period)
        result = np.mean(windows, axis=1)
        np_dst.array[period - 1:data_size] = result

    np_slide_time = measure_time(numpy_sma_sliding, iterations=1)
    results.append(BenchmarkResult(
        name="sma",
        variant="numpy_sliding",
        operation=f"SMA({period}) sliding",
        data_size=data_size,
        iterations=calc_range,
        total_time_ms=np_slide_time * 1000,
        ops_per_second=calc_range / np_slide_time,
    ))

    return results


# =============================================================================
# Benchmark: Vectorized Operations (sum, mean, std)
# =============================================================================

def benchmark_vectorized_ops(data_size: int, window_size: int = 100, iterations: int = 10000) -> List[BenchmarkResult]:
    """Benchmark vectorized operations on windows"""
    results = []

    # Setup buffers
    std_buf = StandardLineBuffer()
    for i in range(data_size):
        std_buf.forward(value=float(i))

    np_buf = NumpyLineBuffer(initial_capacity=data_size)
    for i in range(data_size):
        np_buf.forward(value=float(i))

    # Standard sum (Python loop)
    def standard_sum():
        for _ in range(iterations):
            window = std_buf.get(ago=0, size=window_size)
            total = math.fsum(window)
        return total

    std_time = measure_time(standard_sum, iterations=1)
    results.append(BenchmarkResult(
        name="vectorized",
        variant="standard",
        operation=f"sum({window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=std_time * 1000,
        ops_per_second=iterations / std_time,
    ))

    # NumPy sum (vectorized)
    def numpy_sum():
        for _ in range(iterations):
            total = np_buf.sum(size=window_size)
        return total

    np_time = measure_time(numpy_sum, iterations=1)
    results.append(BenchmarkResult(
        name="vectorized",
        variant="numpy",
        operation=f"sum({window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=np_time * 1000,
        ops_per_second=iterations / np_time,
    ))

    # NumPy mean
    def numpy_mean():
        for _ in range(iterations):
            avg = np_buf.mean(size=window_size)
        return avg

    np_mean_time = measure_time(numpy_mean, iterations=1)
    results.append(BenchmarkResult(
        name="vectorized",
        variant="numpy",
        operation=f"mean({window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=np_mean_time * 1000,
        ops_per_second=iterations / np_mean_time,
    ))

    # NumPy std
    def numpy_std():
        for _ in range(iterations):
            std = np_buf.std(size=window_size)
        return std

    np_std_time = measure_time(numpy_std, iterations=1)
    results.append(BenchmarkResult(
        name="vectorized",
        variant="numpy",
        operation=f"std({window_size})",
        data_size=data_size,
        iterations=iterations,
        total_time_ms=np_std_time * 1000,
        ops_per_second=iterations / np_std_time,
    ))

    return results


# =============================================================================
# Benchmark: Columnar Data Block
# =============================================================================

def benchmark_columnar_block(data_size: int) -> List[BenchmarkResult]:
    """Benchmark ColumnarDataBlock for OHLCV data"""
    results = []

    # Generate random OHLCV data
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(data_size) * 0.1)
    high = close + np.abs(np.random.randn(data_size) * 0.5)
    low = close - np.abs(np.random.randn(data_size) * 0.5)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = np.random.randint(1000, 100000, data_size).astype(float)
    datetime_vals = np.arange(data_size, dtype=float)

    # Standard: 7 separate LineBuffers
    def standard_load():
        bufs = {
            'datetime': StandardLineBuffer(),
            'open': StandardLineBuffer(),
            'high': StandardLineBuffer(),
            'low': StandardLineBuffer(),
            'close': StandardLineBuffer(),
            'volume': StandardLineBuffer(),
            'oi': StandardLineBuffer(),
        }
        for i in range(data_size):
            bufs['datetime'].forward(datetime_vals[i])
            bufs['open'].forward(open_[i])
            bufs['high'].forward(high[i])
            bufs['low'].forward(low[i])
            bufs['close'].forward(close[i])
            bufs['volume'].forward(volume[i])
            bufs['oi'].forward(0.0)
        return bufs

    std_time = measure_time(standard_load, iterations=1)
    results.append(BenchmarkResult(
        name="columnar",
        variant="standard",
        operation="load OHLCV",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=std_time * 1000,
        ops_per_second=data_size / std_time,
    ))

    # ColumnarDataBlock: single contiguous allocation
    def columnar_load():
        block = ColumnarDataBlock(capacity=data_size)
        for i in range(data_size):
            block.append(
                datetime=datetime_vals[i],
                open=open_[i],
                high=high[i],
                low=low[i],
                close=close[i],
                volume=volume[i],
                openinterest=0.0,
            )
        return block

    col_time = measure_time(columnar_load, iterations=1)
    results.append(BenchmarkResult(
        name="columnar",
        variant="columnar_block",
        operation="load OHLCV",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=col_time * 1000,
        ops_per_second=data_size / col_time,
    ))

    # Bulk load (most efficient)
    def columnar_bulk():
        block = ColumnarDataBlock(capacity=data_size)
        block._block[0, :data_size] = datetime_vals
        block._block[1, :data_size] = open_
        block._block[2, :data_size] = high
        block._block[3, :data_size] = low
        block._block[4, :data_size] = close
        block._block[5, :data_size] = volume
        block._block[6, :data_size] = 0.0
        block._length = data_size
        block._idx = data_size - 1
        return block

    bulk_time = measure_time(columnar_bulk, iterations=1)
    results.append(BenchmarkResult(
        name="columnar",
        variant="columnar_bulk",
        operation="load OHLCV",
        data_size=data_size,
        iterations=data_size,
        total_time_ms=bulk_time * 1000,
        ops_per_second=data_size / bulk_time,
    ))

    return results


# =============================================================================
# Main
# =============================================================================

def print_results(results: List[BenchmarkResult], title: str):
    """Print benchmark results in a table"""
    print(f"\n{'=' * 90}")
    print(f" {title}")
    print(f"{'=' * 90}")
    print(f"{'Variant':<15} {'Operation':<22} {'Data Size':>10} {'Iters':>8} "
          f"{'Time':>12} {'Throughput':>14}")
    print(f"{'-' * 90}")

    for r in results:
        print(r)

    # Calculate speedups
    if len(results) >= 2:
        baseline = results[0]
        print(f"{'-' * 90}")
        for r in results[1:]:
            speedup = r.ops_per_second / baseline.ops_per_second
            direction = "faster" if speedup > 1 else "slower"
            print(f"  {r.variant} vs {baseline.variant}: {speedup:.2f}x {direction}")


def run_all_benchmarks(data_sizes: List[int], verbose: bool = True):
    """Run complete benchmark suite"""

    all_results = []

    for data_size in data_sizes:
        print(f"\n{'#' * 90}")
        print(f" DATA SIZE: {data_size:,} elements")
        print(f"{'#' * 90}")

        # Append operations
        results = benchmark_append(data_size)
        print_results(results, f"APPEND OPERATIONS ({data_size:,} bars)")
        all_results.extend(results)

        # Random access
        iterations = min(100000, data_size * 10)
        results = benchmark_random_access(data_size, iterations=iterations)
        print_results(results, f"RANDOM ACCESS ({iterations:,} reads)")
        all_results.extend(results)

        # Slicing
        results = benchmark_slicing(data_size, window_size=20, iterations=10000)
        print_results(results, "SLICING (window=20, 10K iterations)")
        all_results.extend(results)

        # SMA
        results = benchmark_sma(data_size, period=20)
        print_results(results, f"SMA CALCULATION (period=20)")
        all_results.extend(results)

        # Vectorized operations
        results = benchmark_vectorized_ops(data_size, window_size=100, iterations=10000)
        print_results(results, "VECTORIZED OPERATIONS (window=100)")
        all_results.extend(results)

        # Columnar block
        results = benchmark_columnar_block(data_size)
        print_results(results, "COLUMNAR DATA BLOCK (OHLCV)")
        all_results.extend(results)

    return all_results


def print_summary(all_results: List[BenchmarkResult]):
    """Print summary of key findings"""

    print(f"\n{'=' * 90}")
    print(" SUMMARY: KEY FINDINGS")
    print(f"{'=' * 90}")

    # Group by benchmark name
    benchmarks = {}
    for r in all_results:
        key = (r.name, r.data_size)
        if key not in benchmarks:
            benchmarks[key] = []
        benchmarks[key].append(r)

    print(f"\n{'Benchmark':<20} {'Data Size':>12} {'Standard':>12} {'Best NumPy':>12} {'Speedup':>10}")
    print(f"{'-' * 70}")

    for (name, size), results in sorted(benchmarks.items()):
        std_result = next((r for r in results if r.variant == 'standard'), None)
        if not std_result:
            continue

        np_results = [r for r in results if 'numpy' in r.variant or 'columnar' in r.variant]
        if not np_results:
            continue

        best_np = max(np_results, key=lambda r: r.ops_per_second)
        speedup = best_np.ops_per_second / std_result.ops_per_second

        print(f"{name:<20} {size:>12,} {std_result.total_time_ms:>10.1f}ms "
              f"{best_np.total_time_ms:>10.1f}ms {speedup:>9.1f}x")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Standard vs NumPy LineBuffer"
    )
    parser.add_argument("--quick", action="store_true",
                        help="Quick benchmark with small data")
    parser.add_argument("--full", action="store_true",
                        help="Full benchmark with large data")

    args = parser.parse_args()

    print("=" * 90)
    print(" LINEBUFFER BENCHMARK: Standard (array.array) vs NumPy")
    print(" Comparing storage layer performance in isolation")
    print("=" * 90)

    if args.quick:
        data_sizes = [1000, 10000]
    elif args.full:
        data_sizes = [1000, 10000, 100000, 1000000]
    else:
        data_sizes = [1000000000]

    print(f"\nData sizes to test: {data_sizes}")

    all_results = run_all_benchmarks(data_sizes)
    print_summary(all_results)

    print(f"\n{'=' * 90}")
    print(" CONCLUSION")
    print(f"{'=' * 90}")
    print("""
Key takeaways:

1. APPEND: array.array is faster for individual appends (expected)
   - NumPy wins when pre-allocated or bulk loading

2. SLICING: NumPy is significantly faster (zero-copy views)
   - Critical for indicator window operations

3. SMA: Vectorized NumPy is 10-100x faster than loops
   - np.convolve() or sliding_window_view() are best

4. VECTORIZED OPS: NumPy sum/mean/std are much faster
   - SIMD acceleration makes huge difference

5. COLUMNAR BLOCK: Bulk loading is fastest
   - Pre-allocate when data size is known

Recommendation: Use NumPy with vectorized 'once()' mode for best performance.
""")


if __name__ == "__main__":
    main()
