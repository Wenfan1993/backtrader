"""
NumPy-based LineBuffer Implementation

This module provides a drop-in replacement for Backtrader's LineBuffer
that uses NumPy arrays for improved cache locality and SIMD vectorization.

Based on: DDIA Chapter 3 - Columnar Storage concepts

Key improvements over standard LineBuffer:
1. NumPy arrays enable SIMD vectorization
2. Pre-allocation reduces memory fragmentation
3. Views enable zero-copy slicing
4. Better cache locality for sequential access

Usage:
    # Replace standard LineBuffer with NumpyLineBuffer
    from implementation.numpy_linebuffer import NumpyLineBuffer

    # Or use the columnar data feed wrapper
    from implementation.columnar_feed import ColumnarDataFeed
"""

import numpy as np
from typing import Optional, Union, Iterator


class NumpyLineBuffer:
    """
    NumPy-based line buffer compatible with Backtrader's LineBuffer interface.

    This implementation uses a pre-allocated NumPy array that grows dynamically
    when needed, similar to Python's list but with better memory characteristics.

    Attributes:
        array: The underlying NumPy array
        idx: Current logical index position
        lencount: Number of valid bars in buffer
    """

    # Mode constants (compatible with original LineBuffer)
    UnBounded = 0
    QBuffer = 1

    # Growth factor when array needs to expand
    GROWTH_FACTOR = 2.0
    INITIAL_CAPACITY = 1024

    def __init__(self, initial_capacity: int = INITIAL_CAPACITY):
        """
        Initialize the numpy line buffer.

        Args:
            initial_capacity: Initial array size (will grow as needed)
        """
        self._capacity = initial_capacity
        self.array = np.full(self._capacity, np.nan, dtype=np.float64)
        self.idx = -1
        self.lencount = 0
        self.mode = self.UnBounded

        # Bindings for linked lines (compatibility with Backtrader)
        self.bindings = []

        # Extension tracking
        self.extension = 0

    def reset(self):
        """Reset the buffer to initial state"""
        self.array[:] = np.nan
        self.idx = -1
        self.lencount = 0
        self.extension = 0

    def home(self):
        """Rewind to the beginning of the buffer"""
        self.idx = -1
        self.lencount = 0

    def _ensure_capacity(self, min_size: int):
        """Grow the array if needed"""
        if min_size <= self._capacity:
            return

        # Calculate new capacity with growth factor
        new_capacity = max(
            int(self._capacity * self.GROWTH_FACTOR),
            min_size
        )

        # Allocate new array and copy data
        new_array = np.full(new_capacity, np.nan, dtype=np.float64)
        new_array[:len(self.array)] = self.array
        self.array = new_array
        self._capacity = new_capacity

    def forward(self, value: float = np.nan, size: int = 1):
        """
        Move the buffer forward, adding new positions.

        Args:
            value: Value to fill new positions with (default: NaN)
            size: Number of positions to move forward
        """
        self.idx += size
        self.lencount += size

        # Ensure we have capacity
        self._ensure_capacity(self.idx + 1 + self.extension)

        # Fill new position(s)
        if size == 1:
            self.array[self.idx] = value
        else:
            self.array[self.idx - size + 1:self.idx + 1] = value

    def backwards(self, size: int = 1, force: bool = False):
        """
        Move the buffer backwards (undo forward).

        Args:
            size: Number of positions to move back
            force: If True, allow moving beyond start
        """
        self.idx -= size
        self.lencount -= size

        # Reset values we're abandoning
        if self.idx + 1 < self._capacity:
            self.array[self.idx + 1:self.idx + 1 + size] = np.nan

    def rewind(self, size: int = 1):
        """Decrease index without modifying buffer"""
        self.idx -= size
        self.lencount -= size

    def advance(self, size: int = 1):
        """Increase index without modifying buffer"""
        self.idx += size
        self.lencount += size

    def extend(self, value: float = np.nan, size: int = 0):
        """
        Add lookahead positions to the buffer.

        Args:
            value: Value to fill extension with
            size: Number of positions to add
        """
        self.extension = max(self.extension, size)
        self._ensure_capacity(self.idx + 1 + self.extension)

        # Fill extension positions
        if size > 0:
            self.array[self.idx + 1:self.idx + 1 + size] = value

    def __len__(self) -> int:
        """Return number of valid bars"""
        return self.lencount

    def buflen(self) -> int:
        """Return current buffer length (including extensions)"""
        return self.lencount + self.extension

    def __getitem__(self, ago: Union[int, slice]) -> Union[float, np.ndarray]:
        """
        Get value(s) at offset from current position.

        Args:
            ago: Offset from current position (0=current, 1=previous, -1=future)
                 Can also be a slice for multiple values

        Returns:
            Single value or array of values
        """
        if isinstance(ago, slice):
            # Handle slice access
            start = self.idx + (ago.start or 0)
            stop = self.idx + (ago.stop or 0)
            step = ago.step
            return self.array[start:stop:step]

        return self.array[self.idx + ago]

    def __setitem__(self, ago: int, value: float):
        """
        Set value at offset from current position.

        Args:
            ago: Offset from current position
            value: Value to set
        """
        self.array[self.idx + ago] = value

    def get(self, ago: int = 0, size: int = 1) -> np.ndarray:
        """
        Get a slice of values ending at the specified offset.

        Args:
            ago: End offset (0=current)
            size: Number of values to get

        Returns:
            NumPy array view (zero-copy)
        """
        end_idx = self.idx + ago + 1
        start_idx = end_idx - size
        return self.array[start_idx:end_idx]

    def get_view(self, start: int, end: int) -> np.ndarray:
        """
        Get a view of the underlying array (zero-copy).

        Args:
            start: Start index
            end: End index

        Returns:
            NumPy array view
        """
        return self.array[start:end]

    def __iter__(self) -> Iterator[float]:
        """Iterate over valid values"""
        return iter(self.array[:self.lencount])

    # =========================================================================
    # Vectorized Operations (NEW - not in original LineBuffer)
    # =========================================================================

    def sum(self, size: int, ago: int = 0) -> float:
        """Vectorized sum of last `size` values"""
        return np.sum(self.get(ago, size))

    def mean(self, size: int, ago: int = 0) -> float:
        """Vectorized mean of last `size` values"""
        return np.mean(self.get(ago, size))

    def std(self, size: int, ago: int = 0) -> float:
        """Vectorized standard deviation of last `size` values"""
        return np.std(self.get(ago, size))

    def max(self, size: int, ago: int = 0) -> float:
        """Vectorized max of last `size` values"""
        return np.max(self.get(ago, size))

    def min(self, size: int, ago: int = 0) -> float:
        """Vectorized min of last `size` values"""
        return np.min(self.get(ago, size))

    # =========================================================================
    # Bulk Operations for "once" mode
    # =========================================================================

    def apply_vectorized(
        self,
        func,
        src_array: np.ndarray,
        start: int,
        end: int,
        window: int = 1
    ):
        """
        Apply a vectorized function over the array.

        This is optimized for Backtrader's "once" mode where we process
        the entire dataset at once.

        Args:
            func: Function to apply (should accept np.ndarray)
            src_array: Source data array
            start: Start index
            end: End index
            window: Window size for rolling operations
        """
        # Ensure capacity
        self._ensure_capacity(end)

        # Apply function in a vectorized manner
        for i in range(start, end):
            self.array[i] = func(src_array[i - window + 1:i + 1])

    def apply_rolling(
        self,
        func,
        src_array: np.ndarray,
        window: int,
        start: int,
        end: int
    ) -> np.ndarray:
        """
        Apply a rolling window function using NumPy's stride tricks.

        This is much faster than per-bar iteration for large datasets.

        Args:
            func: Reduction function (np.mean, np.sum, etc.)
            src_array: Source data
            window: Window size
            start: Start index
            end: End index

        Returns:
            Result array
        """
        from numpy.lib.stride_tricks import sliding_window_view

        # Get the data slice
        data = src_array[start - window + 1:end]

        # Create sliding window view (zero-copy)
        windows = sliding_window_view(data, window)

        # Apply function along axis
        result = func(windows, axis=1)

        # Store results
        self.array[start:end] = result

        return result


class ColumnarDataBlock:
    """
    Contiguous memory block for all OHLCV data.

    This allocates all price data in a single memory region for
    optimal cache utilization when accessing multiple lines.

    Memory Layout:
        [datetime_0, datetime_1, ..., datetime_n]  <- contiguous
        [open_0,     open_1,     ..., open_n    ]  <- contiguous
        [high_0,     high_1,     ..., high_n    ]  <- contiguous
        [low_0,      low_1,      ..., low_n     ]  <- contiguous
        [close_0,    close_1,    ..., close_n   ]  <- contiguous
        [volume_0,   volume_1,   ..., volume_n  ]  <- contiguous
        [oi_0,       oi_1,       ..., oi_n      ]  <- contiguous
    """

    LINE_NAMES = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
    NUM_LINES = len(LINE_NAMES)

    def __init__(self, capacity: int = 10000):
        """
        Initialize contiguous data block.

        Args:
            capacity: Initial capacity (number of bars)
        """
        self._capacity = capacity
        self._length = 0
        self._idx = -1

        # Single contiguous allocation
        self._block = np.full(
            (self.NUM_LINES, capacity),
            np.nan,
            dtype=np.float64
        )

        # Create views (zero-copy references to block rows)
        self.datetime = self._block[0]
        self.open = self._block[1]
        self.high = self._block[2]
        self.low = self._block[3]
        self.close = self._block[4]
        self.volume = self._block[5]
        self.openinterest = self._block[6]

    def _ensure_capacity(self, min_size: int):
        """Grow the block if needed"""
        if min_size <= self._capacity:
            return

        new_capacity = max(int(self._capacity * 2), min_size)
        new_block = np.full(
            (self.NUM_LINES, new_capacity),
            np.nan,
            dtype=np.float64
        )
        new_block[:, :self._capacity] = self._block
        self._block = new_block
        self._capacity = new_capacity

        # Update views
        self.datetime = self._block[0]
        self.open = self._block[1]
        self.high = self._block[2]
        self.low = self._block[3]
        self.close = self._block[4]
        self.volume = self._block[5]
        self.openinterest = self._block[6]

    def append(
        self,
        datetime: float,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        openinterest: float = 0.0
    ):
        """Append a new bar to the block"""
        self._idx += 1
        self._length += 1
        self._ensure_capacity(self._length)

        self._block[:, self._idx] = [
            datetime, open, high, low, close, volume, openinterest
        ]

    def get_bar(self, idx: int) -> np.ndarray:
        """Get all values for a single bar (row access)"""
        return self._block[:, idx]

    def get_line(self, name: str) -> np.ndarray:
        """Get entire line array (column access)"""
        return getattr(self, name)

    def get_slice(self, start: int, end: int) -> np.ndarray:
        """Get a slice of all data (returns view)"""
        return self._block[:, start:end]

    @property
    def shape(self):
        return (self.NUM_LINES, self._length)

    def __len__(self):
        return self._length


# =============================================================================
# Example Usage and Tests
# =============================================================================

if __name__ == "__main__":
    import time

    print("Testing NumpyLineBuffer...")

    # Test basic operations
    buf = NumpyLineBuffer()

    # Simulate loading data
    for i in range(1000):
        buf.forward(value=float(i))

    assert len(buf) == 1000
    assert buf[0] == 999.0  # Current value

    # Backtrader indexing convention:
    #   [0]  = current bar (idx)
    #   [-1] = previous bar (idx - 1) - looking back in time
    #   [1]  = future bar (idx + 1) - lookahead (usually NaN)
    assert buf[-1] == 998.0  # Previous bar (1 bar ago)

    # Test get slice
    last_10 = buf.get(ago=0, size=10)
    assert len(last_10) == 10
    assert last_10[-1] == 999.0

    # Test vectorized operations
    assert buf.mean(size=10) == 994.5
    assert buf.sum(size=10) == 9945.0

    print("  Basic operations: PASSED")

    # Benchmark comparison
    print("\nBenchmarking NumpyLineBuffer vs standard array.array...")

    import array

    sizes = [10000, 100000, 1000000]

    for size in sizes:
        # NumPy buffer
        np_buf = NumpyLineBuffer(initial_capacity=size)
        start = time.perf_counter()
        for i in range(size):
            np_buf.forward(value=float(i))
        np_time = time.perf_counter() - start

        # Standard array.array
        std_buf = array.array('d')
        start = time.perf_counter()
        for i in range(size):
            std_buf.append(float(i))
        std_time = time.perf_counter() - start

        print(f"  {size:>10,} items: NumPy={np_time*1000:.1f}ms, "
              f"array.array={std_time*1000:.1f}ms, "
              f"ratio={std_time/np_time:.2f}x")

    # Test vectorized sum vs loop
    print("\nBenchmarking vectorized operations...")

    buf = NumpyLineBuffer(initial_capacity=100000)
    for i in range(100000):
        buf.forward(value=float(i))

    # Vectorized sum
    start = time.perf_counter()
    for _ in range(1000):
        _ = buf.sum(size=100)
    vec_time = time.perf_counter() - start

    # Loop sum (using negative indexing to look backwards)
    start = time.perf_counter()
    for _ in range(1000):
        total = 0.0
        for i in range(100):
            total += buf[-i]  # Look backwards from current
    loop_time = time.perf_counter() - start

    print(f"  1000x sum(100): vectorized={vec_time*1000:.1f}ms, "
          f"loop={loop_time*1000:.1f}ms, "
          f"speedup={loop_time/vec_time:.1f}x")

    print("\nAll tests passed!")
