1. Column-Oriented Storage for Data Feeds ✅
Book Concept: Store data by column rather than row for analytical queries that scan many rows but few columns.

Backtrader Application: Price data (OHLCV) is accessed column-wise by indicators:

SMA reads close prices for N bars
ATR reads high, low, close
Current state: Backtrader uses LineBuffer which is already somewhat columnar - each line (open, high, low, close, volume) is a separate array.

Potential improvement:


# Instead of: list of Bar objects (row-oriented)
bars = [Bar(o=1, h=2, l=0.5, c=1.5), Bar(o=1.5, h=2.1, l=1, c=2), ...]

# Use: numpy arrays per column (column-oriented)
import numpy as np
class ColumnarFeed:
    def __init__(self, size):
        self.open = np.zeros(size, dtype=np.float64)
        self.high = np.zeros(size, dtype=np.float64)
        self.low = np.zeros(size, dtype=np.float64)
        self.close = np.zeros(size, dtype=np.float64)
        self.volume = np.zeros(size, dtype=np.int64)
Benefit: Cache-friendly sequential memory access, SIMD vectorization for indicator calculations.


5. OLTP vs OLAP Separation ✅
Book Concept: Separate transaction processing (writes) from analytical queries (reads) for different optimization.

Backtrader Application: During backtesting, we're doing OLTP (processing each bar). After backtesting, we want OLAP (analyzing results).

Potential improvement: Separate the hot path (bar processing) from analytics:


class Cerebro:
    def run(self):
        # OLTP phase: optimize for low-latency per-bar processing
        with self._oltp_mode():
            for bar in self.data:
                self._process_bar(bar)  # Minimal state tracking
        
        # OLAP phase: optimize for analytical queries
        return self._build_analytics()  # Can use heavier data structures
    
    def _oltp_mode(self):
        """Disable expensive tracking during simulation"""
        # Defer trade history building
        # Use lightweight position tracking
        # Batch notifications