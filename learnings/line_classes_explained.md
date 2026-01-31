# Backtrader Line Classes - Comprehensive Explanation

This document explains the core line-based data structure classes in backtrader, which form the foundation of how data flows through the framework.

## Table of Contents

1. [Overview](#overview)
2. [lineroot.py](#linerootpy)
3. [linebuffer.py](#linebufferpy)
4. [lineseries.py](#lineseriespy)
5. [lineiterator.py](#lineiteratorpy)
6. [Practical Examples](#practical-examples)

---

## Overview

Backtrader uses a "line" concept where data is stored in arrays with a special indexing system:
- **Index 0**: Current value (now)
- **Positive indices** (1, 2, 3...): Past values (1 = yesterday, 2 = 2 days ago)
- **Negative indices** (-1, -2...): Future values (for lookahead operations)

This design allows indicators and strategies to access historical data naturally without managing complex indexing.

---

## lineroot.py

This file defines the base classes and interfaces for all line-based objects in backtrader.

### Class: MetaLineRoot

**Purpose**: Metaclass that automatically finds and stores the "owner" of each line object during creation.

**Key Methods**:
- `donew(cls, *args, **kwargs)`: Called during object creation to find the owner object in the call stack.

### Class: LineRoot

**Purpose**: Base class defining common interfaces for all line objects (single or multiple lines).

**Key Attributes**:
- `_minperiod`: Minimum number of data points needed before the object can produce values
- `_opstage`: Operation stage (1 or 2) determining how operations are processed
- `IndType, StratType, ObsType`: Constants identifying object types (Indicator, Strategy, Observer)

**Key Methods**:

#### Period Management
- `setminperiod(minperiod)`: Directly set the minimum period
- `updateminperiod(minperiod)`: Update minperiod only if new value is larger
- `addminperiod(minperiod)`: Add to the minperiod (implemented by subclasses)
- `incminperiod(minperiod)`: Increment minperiod unconditionally

#### Iteration Methods
- `prenext()`: Called during the minperiod phase (warming up)
- `nextstart()`: Called once when minperiod is complete
- `next()`: Called for every bar after minperiod is satisfied

#### Operation Methods
- `_operation(other, operation, r=False, intify=False)`: Handle binary operations (add, subtract, etc.)
- `_operationown(operation)`: Handle unary operations (abs, neg, etc.)
- `_stage1()`: Set operation stage to 1 (during setup)
- `_stage2()`: Set operation stage to 2 (during execution)

#### Arithmetic Operators
All standard Python operators are overloaded:
- `__add__`, `__radd__`: Addition
- `__sub__`, `__rsub__`: Subtraction
- `__mul__`, `__rmul__`: Multiplication
- `__div__`, `__rdiv__`, `__truediv__`, `__rtruediv__`: Division
- `__pow__`, `__rpow__`: Power
- `__abs__`: Absolute value
- `__neg__`: Negation

#### Comparison Operators
- `__lt__`, `__gt__`, `__le__`, `__ge__`, `__eq__`, `__ne__`: Comparison operations
- `__nonzero__`, `__bool__`: Boolean conversion

### Class: LineMultiple

**Purpose**: Base class for objects that hold multiple lines (e.g., a data feed with OHLCV).

**Key Methods**:
- `reset()`: Reset all lines to initial state
- `addminperiod(minperiod)`: Pass minperiod to all contained lines
- `qbuffer(savemem=0)`: Enable memory-saving queue buffer mode for all lines
- `minbuffer(size)`: Set minimum buffer size for all lines

### Class: LineSingle

**Purpose**: Base class for objects that hold a single line.

**Key Methods**:
- `addminperiod(minperiod)`: Add to minperiod, accounting for overlap (minperiod - 1)
- `incminperiod(minperiod)`: Increment minperiod directly

---

## linebuffer.py

This file implements the actual data storage and manipulation for lines.

### Class: LineBuffer

**Purpose**: Core class that manages an array with special indexing where index 0 always points to the "current" value.

**Key Attributes**:
- `array`: The underlying storage (array.array or collections.deque)
- `idx`: Current position pointer (index 0 maps to array[idx])
- `lencount`: Logical length of data
- `bindings`: List of other LineBuffers that should receive the same values
- `mode`: Either `UnBounded` (regular array) or `QBuffer` (fixed-size queue)

**Buffer Modes**:
1. **UnBounded**: Uses Python's array.array, grows indefinitely
2. **QBuffer**: Uses collections.deque with maxlen, for memory-constrained environments

**Key Methods**:

#### Initialization
- `__init__()`: Initialize buffer with default settings
- `reset()`: Clear the buffer and reset indices
- `qbuffer(savemem=0, extrasize=0)`: Enable queue buffer mode with specified size

#### Data Access
- `__getitem__(ago)`: Get value at position ago (0=current, 1=yesterday, etc.)
  ```python
  current_close = close[0]  # Today's close
  yesterday_close = close[1]  # Yesterday's close
  ```
- `__setitem__(ago, value)`: Set value at position ago
- `get(ago=0, size=1)`: Get a slice of values
- `getzero(idx=0, size=1)`: Get values relative to buffer start (not current position)

#### Buffer Management
- `home()`: Reset index to beginning without clearing data
- `forward(value=NAN, size=1)`: Move forward, appending new positions
- `backwards(size=1, force=False)`: Move backward, removing positions
- `rewind(size=1)`: Move index back without modifying buffer
- `advance(size=1)`: Move index forward without modifying buffer
- `extend(value=NAN, size=0)`: Add positions beyond current index (for lookahead)

#### Bindings
- `addbinding(binding)`: Link another LineBuffer to receive same values
- `bind2lines(binding=0)`: Bind to a line from the owner object
- `oncebinding()`: Execute bindings in "once" mode (batch processing)

#### Date/Time Methods
- `datetime(ago=0, tz=None, naive=True)`: Get datetime object
- `date(ago=0, tz=None, naive=True)`: Get date part
- `time(ago=0, tz=None, naive=True)`: Get time part
- `dt(ago=0)`: Get numeric date part
- `tm(ago=0)`: Get numeric time part
- `tm_lt/tm_le/tm_eq/tm_gt/tm_ge(other, ago=0)`: Time comparison methods

#### Plotting
- `plot(idx=0, size=None)`: Get data for plotting
- `plotrange(start, end)`: Get specific range for plotting

### Class: MetaLineActions

**Purpose**: Metaclass for LineActions that implements caching and manages initialization.

**Key Methods**:
- `__call__()`: Implements caching to avoid duplicate line operations
- `dopreinit()`: Calculate minperiod from operands before initialization
- `dopostinit()`: Register with owner after initialization

### Class: LineActions

**Purpose**: Base class for line operations (extends LineBuffer with operation support).

**Key Methods**:
- `_next()`: Execute next() based on clock and minperiod
- `_once()`: Execute batch processing mode
- `prenext()`: Called during warmup (empty implementation)
- `nextstart()`: Called once when minperiod satisfied (empty implementation)
- `next()`: Calculate next value (empty implementation)
- `preonce(start, end)`: Batch warmup (empty implementation)
- `oncestart(start, end)`: Batch first value (empty implementation)
- `once(start, end)`: Batch calculation (empty implementation)

### Class: _LineDelay

**Purpose**: Delays a line by a specified number of periods.

**Example**:
```python
# Get close price from 5 days ago
delayed_close = close(-5)  # This creates a _LineDelay object
```

**Key Methods**:
- `__init__(a, ago)`: Initialize with source line and delay amount
- `next()`: Copy value from ago periods back
- `once(start, end)`: Batch copy with delay

### Class: _LineForward

**Purpose**: Store values in future positions (opposite of delay).

**Key Methods**:
- `next()`: Store current value in future position
- `once(start, end)`: Batch store with forward offset

### Class: LinesOperation

**Purpose**: Performs binary operations between two lines or a line and a scalar.

**Example**:
```python
# These create LinesOperation objects
spread = close - open  # Subtraction
ratio = high / low     # Division
scaled = close * 1.5   # Multiplication with scalar
```

**Key Methods**:
- `__init__(a, b, operation, r=False)`: Initialize operation
  - `a`: First operand (always a line)
  - `b`: Second operand (line or scalar)
  - `operation`: Function to apply (e.g., operator.__add__)
  - `r`: Reverse operation flag
- `next()`: Execute operation for current value
- `once(start, end)`: Batch execute operation

### Class: LineOwnOperation

**Purpose**: Performs unary operations on a single line.

**Example**:
```python
# These create LineOwnOperation objects
absolute_change = abs(close - open)
negative = -close
```

**Key Methods**:
- `__init__(a, operation)`: Initialize with source and operation
- `next()`: Execute operation for current value
- `once(start, end)`: Batch execute operation

---

## lineseries.py

This file provides higher-level abstractions for working with multiple lines together.

### Class: LineAlias

**Purpose**: Descriptor that provides named access to lines.

**Example**:
```python
# Inside a data feed:
self.close  # Returns self.lines[3] via LineAlias descriptor
```

**Key Methods**:
- `__get__(obj, cls=None)`: Return the line from owner's lines
- `__set__(obj, value)`: Create binding to set values

### Class: Lines

**Purpose**: Container for multiple LineBuffer objects with array-like interface.

**Key Methods**:

#### Class Methods
- `_derive(name, lines, extralines, otherbases, linesoverride=False, lalias=None)`: Create a subclass with additional lines
- `_getlinealias(i)`: Get name of line at index i
- `getlinealiases()`: Get all line names

#### Instance Methods
- `__init__(initlines=None)`: Create LineBuffer for each defined line
- `__len__()`: Return length of first line
- `size()`: Number of defined lines (excluding extra)
- `fullsize()`: Total number of lines (including extra)
- `__getitem__(line)`: Access line by index
- `get(ago=0, size=1, line=0)`: Get slice from specific line

#### Proxy Methods (forwarded to all lines)
- `forward(value=NAN, size=1)`: Move all lines forward
- `backwards(size=1, force=False)`: Move all lines backward
- `rewind(size=1)`: Rewind all lines
- `extend(value=NAN, size=0)`: Extend all lines
- `reset()`: Reset all lines
- `home()`: Home all lines
- `advance(size=1)`: Advance all lines

### Class: MetaLineSeries

**Purpose**: Metaclass that processes class definitions to create Lines classes and manage aliases.

**What It Does**:
1. Extracts `lines`, `linealias`, `plotinfo`, `plotlines` from class definition
2. Creates derived classes for these definitions
3. Sets up line name aliases as class attributes
4. Manages class hierarchy for proper inheritance

### Class: LineSeries

**Purpose**: High-level base class for objects with multiple lines (data feeds, indicators).

**Key Attributes**:
- `lines`: Instance of Lines class containing all line buffers
- `l`: Shortcut to lines
- `line`: Shortcut to first line
- `line_0, line_1, ...`: Access lines by index
- `plotinfo`: Plotting configuration
- `plotlines`: Per-line plotting configuration

**Key Methods**:
- `__getattr__(name)`: Delegate to lines for attribute access
- `__getitem__(key)`: Access first line by index
- `__setitem__(key, value)`: Set line value by index
- `__call__(ago=None, line=-1)`: Create delayed or coupled version
  - `ago=None`: Create LineCoupler for timeframe adaptation
  - `ago=int`: Create LineDelay for shifting
- `plotlabel()`: Generate label for plotting

#### Proxy Methods
- `forward(value=NAN, size=1)`: Forward all lines
- `backwards(size=1, force=False)`: Backward all lines
- `rewind(size=1)`: Rewind all lines
- `extend(value=NAN, size=0)`: Extend all lines
- `reset()`: Reset all lines
- `home()`: Home all lines
- `advance(size=1)`: Advance all lines

### Class: LineSeriesStub

**Purpose**: Wraps a single line to behave like a LineSeries (used for line operations).

**Key Attribute**:
- `slave`: If True, buffer operations are suppressed (master object handles them)

**Use Case**: When you operate on a single line but need LineSeries interface:
```python
close_line = data.close  # This is a LineBuffer
stub = LineSeriesStub(close_line)  # Now behaves like LineSeries
```

### Function: LineSeriesMaker

**Purpose**: Convert any object to LineSeries interface.

**Usage**:
```python
line_series = LineSeriesMaker(some_line_or_series)
```

---

## lineiterator.py

This file adds iteration capabilities for indicators and strategies.

### Class: MetaLineIterator

**Purpose**: Metaclass that manages data sources and sets up the iteration framework.

**What It Does**:
1. Scans constructor arguments for data sources (LineRoot objects)
2. Converts non-LineRoot args to LineNum if needed
3. Creates data aliases (data, data0, data1, etc.)
4. Creates line aliases (data_close, data_high, data0_close, etc.)
5. Calculates minperiod from all data sources

### Class: LineIterator

**Purpose**: Base class for indicators, strategies, and observers that iterate over data.

**Key Attributes**:
- `datas`: List of data sources
- `data`: First data source (convenience)
- `_clock`: Data source used as timing reference
- `_lineiterators`: Dictionary of child indicators/observers
- `_mindatas`: Minimum number of data sources required
- `_nextforce`: Force next mode (disable runonce optimization)

**Data Access Shortcuts**:
```python
self.data         # First data source
self.data0        # First data source (explicit)
self.data1        # Second data source
self.data_close   # Close line of first data
self.data_high    # High line of first data
self.data0_close  # Explicit close of first data
self.data1_close  # Close of second data
```

**Key Methods**:

#### Main Iteration
- `_next()`: Internal next iteration handler
  - Updates clock
  - Calls next() on all child indicators
  - Calls prenext(), nextstart(), or next() based on minperiod
- `_once()`: Internal batch processing handler
  - Forwards all lines
  - Calls _once() on child indicators
  - Calls preonce(), oncestart(), once() for batch processing

#### User-Overridable Methods
- `prenext()`: Called during warmup period (before minperiod satisfied)
- `nextstart()`: Called once when minperiod first satisfied (defaults to calling next())
- `next()`: Called for each bar after minperiod satisfied
- `preonce(start, end)`: Batch processing during warmup
- `oncestart(start, end)`: Batch processing for first value
- `once(start, end)`: Batch processing for all values

#### Management Methods
- `getindicators()`: Get list of child indicators
- `getobservers()`: Get list of child observers
- `addindicator(indicator)`: Register child indicator
- `bindlines(owner=None, own=None)`: Bind lines to owner's lines
- `_periodrecalc()`: Recalculate minperiod from children
- `_stage1()`: Setup stage for all children
- `_stage2()`: Execution stage for all children
- `qbuffer(savemem=0)`: Enable queue buffer mode

### Class: DataAccessor

**Purpose**: Provides constants for accessing data series columns.

**Constants**:
- `PriceClose = 0`
- `PriceLow = 1`
- `PriceHigh = 2`
- `PriceOpen = 3`
- `PriceVolume = 4`
- `PriceOpenInteres = 5`
- `PriceDateTime = 6`

### Class: IndicatorBase

**Purpose**: Base class for indicators (inherits DataAccessor and LineIterator).

### Class: ObserverBase

**Purpose**: Base class for observers (inherits DataAccessor and LineIterator).

### Class: StrategyBase

**Purpose**: Base class for strategies (inherits DataAccessor and LineIterator).

### Class: SingleCoupler

**Purpose**: Couples a single line to a different timeframe/clock.

**Use Case**: When you need to use a line from one timeframe in another:
```python
# Daily data used in an hourly strategy
daily_sma = SimpleMovingAverage(daily_data.close)
hourly_coupled = daily_sma()  # Creates coupler for hourly timeframe
```

**Key Methods**:
- `next()`: Update value when source data advances
  - Holds last value until new one available

### Class: MultiCoupler

**Purpose**: Couples multiple lines to a different timeframe/clock.

**Key Methods**:
- `next()`: Update all line values when source advances

### Function: LinesCoupler

**Purpose**: Factory function that creates appropriate coupler (Single or Multi).

**Usage**:
```python
# Automatic selection based on input
coupled = LinesCoupler(some_line_or_lines, clock=hourly_data)
```

---

## Practical Examples

### Example 1: Understanding Line Indexing

```python
# In an indicator's next() method:
def next(self):
    current_close = self.data.close[0]     # Today's close
    yesterday_close = self.data.close[1]   # Yesterday's close
    two_days_ago = self.data.close[2]      # Two days ago

    # Calculate simple moving average manually
    sma_3 = (current_close + yesterday_close + two_days_ago) / 3
    self.lines.sma[0] = sma_3
```

### Example 2: Line Operations

```python
class MyIndicator(bt.Indicator):
    lines = ('signal',)

    def __init__(self):
        # These all create operation objects
        self.diff = self.data.close - self.data.open
        self.ratio = self.data.high / self.data.low
        self.scaled = self.diff * 2.0

    def next(self):
        # Operation results are automatically calculated
        if self.diff[0] > 0:
            self.lines.signal[0] = 1
        else:
            self.lines.signal[0] = -1
```

### Example 3: Custom Indicator with Minperiod

```python
class SimpleMovingAverage(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)

    def __init__(self):
        # Tell framework we need 'period' bars before we can calculate
        self.addminperiod(self.params.period)

    def prenext(self):
        # Called during warmup - not enough data yet
        # Could calculate partial average here
        pass

    def nextstart(self):
        # Called once when we first have enough data
        # Calculate initial SMA from all available data
        sum_vals = sum(self.data.close.get(size=self.params.period))
        self.lines.sma[0] = sum_vals / self.params.period

    def next(self):
        # Called for each subsequent bar
        # Efficient incremental calculation
        sum_vals = sum(self.data.close.get(size=self.params.period))
        self.lines.sma[0] = sum_vals / self.params.period
```

### Example 4: Line Bindings

```python
class BindingExample(bt.Indicator):
    lines = ('output1', 'output2')

    def __init__(self):
        # Bind output2 to output1 - they'll always have same value
        self.lines.output2.addbinding(self.lines.output1)

    def next(self):
        # Only need to set output1
        self.lines.output1[0] = self.data.close[0] * 2
        # output2 automatically gets the same value
```

### Example 5: Delayed Lines

```python
class DelayExample(bt.Indicator):
    lines = ('delayed',)
    params = (('delay', 5),)

    def __init__(self):
        # Create a delayed version of close price
        self.lines.delayed = self.data.close(-self.params.delay)
        # This creates a _LineDelay object that automatically
        # stores close values with the specified delay
```

### Example 6: Multiple Data Sources

```python
class MultiDataStrategy(bt.Strategy):
    def __init__(self):
        # Access multiple data feeds
        self.data0_sma = bt.indicators.SMA(self.data0.close, period=20)
        self.data1_sma = bt.indicators.SMA(self.data1.close, period=20)

    def next(self):
        # Compare indicators from different data sources
        if self.data0_sma[0] > self.data1_sma[0]:
            print(f"Data0 SMA ({self.data0_sma[0]:.2f}) > Data1 SMA ({self.data1_sma[0]:.2f})")
```

### Example 7: Timeframe Coupling

```python
class MultiTimeframeStrategy(bt.Strategy):
    def __init__(self):
        # Daily SMA on hourly strategy
        daily_data = self.datas[1]  # Assuming daily data is second
        self.daily_sma = bt.indicators.SMA(daily_data.close, period=50)

        # Couple to hourly timeframe
        self.hourly_coupled_sma = self.daily_sma()

    def next(self):
        # hourly_coupled_sma holds the daily SMA value
        # and updates only when daily bar closes
        current_daily_sma = self.hourly_coupled_sma[0]
```

### Example 8: Using get() for Slices

```python
class SliceExample(bt.Indicator):
    def next(self):
        # Get last 5 close prices as a list
        last_5_closes = self.data.close.get(ago=0, size=5)
        # Returns: [close[0], close[1], close[2], close[3], close[4]]

        # Calculate standard deviation
        avg = sum(last_5_closes) / len(last_5_closes)
        variance = sum((x - avg) ** 2 for x in last_5_closes) / len(last_5_closes)
        std_dev = variance ** 0.5

        self.lines.stddev[0] = std_dev
```

### Example 9: Once Mode (Batch Processing)

```python
class EfficientSMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)

    def once(self, start, end):
        # Batch process all bars at once (much faster)
        src = self.data.close.array
        dst = self.lines.sma.array
        period = self.params.period

        for i in range(start, end):
            # Calculate SMA for position i
            total = sum(src[i-j] for j in range(period))
            dst[i] = total / period
```

### Example 10: Memory-Efficient QBuffer Mode

```python
class MemoryEfficientIndicator(bt.Indicator):
    lines = ('value',)
    params = (('period', 20),)

    def __init__(self):
        # Enable queue buffer mode - only keeps 'period' values in memory
        self.qbuffer()

    def next(self):
        # Can only access up to self.params.period values back
        # self.data.close[0] to self.data.close[19] available
        # self.data.close[20] would raise an error
        self.lines.value[0] = sum(self.data.close.get(size=self.params.period))
```

---

## Key Concepts Summary

### 1. Indexing Philosophy
- **0 is now**: Always use [0] for current value
- **Positive is past**: [1] is yesterday, [2] is two days ago
- **Negative is future**: [-1] is tomorrow (for lookahead operations)

### 2. Minperiod
- Every line/indicator has a minimum period
- Represents bars needed before producing valid output
- Automatically propagated through operations
- `prenext()` called during minperiod
- `next()` called after minperiod satisfied

### 3. Operation Stages
- **Stage 1** (Setup): Operations create new line objects
- **Stage 2** (Execution): Operations return calculated values
- Allows `close - open` to work both as object creation and value access

### 4. Buffer Management
- **UnBounded**: Normal mode, unlimited memory
- **QBuffer**: Memory-saving mode, fixed-size circular buffer
- Forward/backward manage buffer position
- Home/reset manage buffer state

### 5. Line Bindings
- Connect lines so they share values
- Used for output aliasing
- Automatic value propagation

### 6. Batch Processing (Once Mode)
- Processes all data at once for speed
- Uses array operations
- Falls back to next mode if not supported

### 7. Timeframe Coupling
- Links data from different timeframes
- Holds values until source updates
- Essential for multi-timeframe strategies

---

## Common Patterns

### Pattern 1: Simple Indicator
```python
class MyIndicator(bt.Indicator):
    lines = ('myline',)
    params = (('param1', 10),)

    def __init__(self):
        # Setup operations/calculations
        pass

    def next(self):
        # Calculate values
        self.lines.myline[0] = calculation
```

### Pattern 2: Multi-Line Indicator
```python
class BBands(bt.Indicator):
    lines = ('mid', 'top', 'bot',)

    def __init__(self):
        self.lines.mid = bt.indicators.SMA(self.data.close, period=20)
        stddev = bt.indicators.StdDev(self.data.close, period=20)
        self.lines.top = self.lines.mid + (2.0 * stddev)
        self.lines.bot = self.lines.mid - (2.0 * stddev)
```

### Pattern 3: Indicator Using Previous Values
```python
class EMA(bt.Indicator):
    lines = ('ema',)
    params = (('period', 20),)

    def __init__(self):
        self.alpha = 2.0 / (self.params.period + 1)

    def nextstart(self):
        # First value is SMA
        self.lines.ema[0] = sum(self.data.close.get(size=self.params.period)) / self.params.period

    def next(self):
        # Use previous EMA value
        self.lines.ema[0] = (self.data.close[0] * self.alpha) + (self.lines.ema[1] * (1 - self.alpha))
```

---

## Conclusion

These four files form the backbone of backtrader's data handling:

1. **lineroot.py**: Defines base interfaces and operator overloading
2. **linebuffer.py**: Implements data storage with special indexing
3. **lineseries.py**: Provides high-level multi-line containers
4. **lineiterator.py**: Adds iteration for indicators and strategies

Understanding these classes is crucial for:
- Creating custom indicators
- Understanding how backtrader processes data
- Optimizing performance
- Debugging data flow issues
- Implementing advanced features

The elegant design allows writing indicators that look like mathematical formulas while efficiently managing data buffers and timing.
