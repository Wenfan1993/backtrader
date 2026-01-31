# Backtrader Lines Architecture

This document walks through the core "lines" system in backtrader, which is the foundation for all data storage, indicators, and strategies.

## Overview: What is a "Line"?

In backtrader, a **line** is a time-series of values - essentially an array where:
- Index `0` always points to the **current** value
- Positive indices (`[1]`, `[2]`, ...) access **past** values
- Negative indices (`[-1]`, `[-2]`, ...) access **future** values (when available)

This "0-centered" indexing is the key innovation - you never need to track "what bar am I on?"

---

## File Hierarchy

```
lineroot.py      → Base classes (LineRoot, LineSingle, LineMultiple)
    ↓
linebuffer.py    → Actual storage (LineBuffer) + operations (LineActions)
    ↓
lineseries.py    → Multi-line containers (Lines, LineSeries)
    ↓
lineiterator.py  → Iteration logic (LineIterator, indicators, strategies)
```

---

## 1. `lineroot.py` - The Foundation

### Class Hierarchy

```
LineRoot (abstract base)
    ├── LineSingle   → holds ONE line (e.g., a single indicator output)
    └── LineMultiple → holds MULTIPLE lines (e.g., OHLCV data, Bollinger Bands)
```

### `LineRoot` - The Abstract Base

**Purpose:** Defines the common interface for all line objects:
- Period management (`_minperiod`)
- Iteration callbacks (`prenext`, `nextstart`, `next`, `once`)
- Arithmetic operators (`+`, `-`, `*`, `/`, comparisons)
- Stage management (stage1 = building, stage2 = running)

```python
class LineRoot:
    _minperiod = 1      # Minimum bars needed before producing values
    _opstage = 1        # 1 = building phase, 2 = running phase
    
    # Types for classification
    IndType, StratType, ObsType = range(3)
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `updateminperiod(p)` | Set minperiod to max(current, p) |
| `addminperiod(p)` | Add to minperiod (for chained indicators) |
| `prenext()` | Called during warmup period |
| `nextstart()` | Called once when warmup completes |
| `next()` | Called for each bar after warmup |
| `once(start, end)` | Vectorized calculation (runonce mode) |

**Stage System:**

```python
# Stage 1: Building phase - operations create new LineActions
self.sma = SMA(self.data.close, period=20)  # Creates a LinesOperation

# Stage 2: Running phase - operations return actual values
if self.data.close[0] > self.sma[0]:  # Returns True/False
    self.buy()
```

**Arithmetic Operators:**

```python
# In stage 1, operators create new line objects
diff = self.data.close - self.sma  # Creates LinesOperation

# In stage 2, operators return values
if self.data.close > self.sma:  # Returns boolean
    pass
```

### `LineSingle` - Single Line Base

**Purpose:** Base for objects holding exactly one line of data.

```python
class LineSingle(LineRoot):
    def addminperiod(self, minperiod):
        # Add minperiod, subtracting the overlapping 1
        self._minperiod += minperiod - 1
```

### `LineMultiple` - Multiple Lines Base

**Purpose:** Base for objects holding multiple lines (like OHLCV data).

```python
class LineMultiple(LineRoot):
    def addminperiod(self, minperiod):
        # Pass minperiod to all contained lines
        for line in self.lines:
            line.addminperiod(minperiod)
    
    def reset(self):
        self._stage1()
        self.lines.reset()
```

---

## 2. `linebuffer.py` - The Storage Engine

### `LineBuffer` - Core Data Storage

**Purpose:** The actual array that stores time-series data with 0-centered indexing.

```python
class LineBuffer(LineSingle):
    UnBounded, QBuffer = (0, 1)  # Storage modes
    
    def __init__(self):
        self.lines = [self]
        self.mode = self.UnBounded
        self.bindings = list()
        self.reset()
```

#### Storage Modes

| Mode | Implementation | Use Case |
|------|---------------|----------|
| `UnBounded` | `array.array('d')` | Full history, unlimited growth |
| `QBuffer` | `collections.deque(maxlen=N)` | Memory-saving, rolling window |

```python
# UnBounded mode - keeps all data
self.array = array.array('d')  # Dynamic array of doubles

# QBuffer mode - keeps only last N values
self.array = collections.deque(maxlen=self.maxlen + self.extrasize)
```

#### The 0-Centered Index System

```
Array:     [100, 101, 102, 103, 104, 105]
                                    ↑
                                   idx (current position)

self[0]  → 105 (current value)
self[1]  → 104 (1 bar ago)
self[2]  → 103 (2 bars ago)
self[-1] → future (if extended)
```

**Implementation:**

```python
def __getitem__(self, ago):
    return self.array[self.idx + ago]

def __setitem__(self, ago, value):
    self.array[self.idx + ago] = value
    # Propagate to bindings
    for binding in self.bindings:
        binding[ago] = value
```

#### Buffer Operations

| Method | Purpose |
|--------|---------|
| `forward(value, size)` | Move index forward, append values |
| `backwards(size)` | Move index backward, pop values |
| `home()` | Reset index to beginning |
| `advance(size)` | Move index forward without appending |
| `extend(value, size)` | Append future values (for lookahead) |
| `get(ago, size)` | Get a slice of values |

**Example: Buffer Lifecycle**

```python
buf = LineBuffer()

# Initially empty
# array: []
# idx: -1

buf.forward(100)  # Add first value
# array: [100]
# idx: 0
# buf[0] = 100

buf.forward(101)  # Add second value
# array: [100, 101]
# idx: 1
# buf[0] = 101, buf[1] = 100

buf.forward(102)
# array: [100, 101, 102]
# idx: 2
# buf[0] = 102, buf[1] = 101, buf[2] = 100

buf.home()  # Reset to beginning for replay
# idx: -1

buf.advance()  # Move forward without adding
# idx: 0
# buf[0] = 100 (first value again)
```

#### Bindings System

Lines can be "bound" to other lines - when a value is set, it propagates:

```python
line_a = LineBuffer()
line_b = LineBuffer()

line_a.addbinding(line_b)

# Now when you set line_a[0], line_b[0] is also set
line_a[0] = 42  # Also sets line_b[0] = 42
```

**Use Case:** Indicator outputs binding to strategy lines.

### `LineActions` - Operation Base

**Purpose:** Base class for line operations that create new lines from existing ones.

```python
class LineActions(LineBuffer):
    _ltype = LineBuffer.IndType
    
    def _next(self):
        clock_len = len(self._clock)
        if clock_len > len(self):
            self.forward()
        
        if clock_len > self._minperiod:
            self.next()
        elif clock_len == self._minperiod:
            self.nextstart()  # First valid value
        else:
            self.prenext()  # Warmup period
```

### `LinesOperation` - Binary Operations

**Purpose:** Represents operations between two operands (e.g., `close - sma`).

```python
class LinesOperation(LineActions):
    def __init__(self, a, b, operation, r=False):
        self.operation = operation
        self.a = a  # Left operand
        self.b = b  # Right operand
        self.r = r  # Reversed operation
    
    def next(self):
        if self.bline:  # Both are lines
            self[0] = self.operation(self.a[0], self.b[0])
        else:  # One is a constant
            self[0] = self.operation(self.a[0], self.b)
```

**Example:**

```python
# This creates a LinesOperation internally
diff = self.data.close - self.sma

# On each bar, diff.next() computes:
# diff[0] = close[0] - sma[0]
```

### `LineOwnOperation` - Unary Operations

**Purpose:** Operations on a single operand (e.g., `abs(close)`).

```python
class LineOwnOperation(LineActions):
    def __init__(self, a, operation):
        self.operation = operation
        self.a = a
    
    def next(self):
        self[0] = self.operation(self.a[0])
```

### `LineDelay` / `_LineDelay` / `_LineForward`

**Purpose:** Access past or future values of a line.

```python
# Access past values
delayed = LineDelay(close, -2)  # close[0] from 2 bars ago

# On each bar:
delayed[0] = close[-2]  # Gets value from 2 bars ago
```

---

## 3. `lineseries.py` - Multi-Line Containers

### `Lines` - Line Container Class

**Purpose:** Holds multiple `LineBuffer` objects as a collection.

```python
class Lines:
    def __init__(self):
        self.lines = list()
        for line, linealias in enumerate(self._getlines()):
            self.lines.append(LineBuffer())
    
    def __getitem__(self, line):
        return self.lines[line]
    
    def forward(self, value=NAN, size=1):
        for line in self.lines:
            line.forward(value, size)
```

**Dynamic Derivation:**

```python
@classmethod
def _derive(cls, name, lines, extralines, otherbases, ...):
    """
    Creates a new Lines subclass with specified line names.
    
    Example:
        Lines._derive('OHLC', ('open', 'high', 'low', 'close'), 0, [])
        # Creates a class with .open, .high, .low, .close attributes
    """
```

### `LineAlias` - Descriptor for Line Access

**Purpose:** Allows accessing lines by name as attributes.

```python
class LineAlias:
    def __init__(self, line):
        self.line = line  # Index of the line
    
    def __get__(self, obj, cls=None):
        return obj.lines[self.line]
    
    def __set__(self, obj, value):
        # Setting creates a binding
        value.addbinding(obj.lines[self.line])
```

**Example:**

```python
class MyIndicator(Indicator):
    lines = ('signal', 'histogram')
    
    def __init__(self):
        # Thanks to LineAlias descriptors:
        self.lines.signal   # Access by attribute
        self.l.signal       # Shortcut
        self.lines[0]       # Access by index
```

### `LineSeries` - The Main Multi-Line Class

**Purpose:** High-level class combining lines, params, and plotting info.

```python
class LineSeries(LineMultiple):
    plotinfo = dict(plot=True, plotmaster=None, legendloc=None)
    
    @property
    def array(self):
        return self.lines[0].array
    
    def __getattr__(self, name):
        # Delegate to lines if attribute not found
        return getattr(self.lines, name)
    
    def __getitem__(self, key):
        # Default to first line
        return self.lines[0][key]
```

### `MetaLineSeries` - The Metaclass

**Purpose:** Processes `lines`, `plotinfo`, `plotlines` class definitions.

```python
class MetaLineSeries(LineMultiple.__class__):
    def __new__(meta, name, bases, dct):
        # Extract lines definition
        newlines = dct.pop('lines', ())
        
        # Create Lines subclass
        cls.lines = lines._derive(name, newlines, ...)
        
        # Create plotinfo/plotlines classes
        cls.plotinfo = plotinfo._derive(...)
        cls.plotlines = plotlines._derive(...)
    
    def donew(cls, *args, **kwargs):
        # Create instances of lines, plotinfo, plotlines
        _obj.lines = cls.lines()
        _obj.plotinfo = cls.plotinfo()
        _obj.plotlines = cls.plotlines()
        
        # Add shortcuts
        _obj.l = _obj.lines
        _obj.line = _obj.lines[0]
```

---

## 4. `lineiterator.py` - Iteration Engine

### `LineIterator` - The Core Iterator

**Purpose:** Manages iteration over data, executing indicators in order.

```python
class LineIterator(LineSeries):
    _mindatas = 1  # Minimum data feeds required
    
    def _next(self):
        clock_len = self._clk_update()
        
        # First, calculate all indicators
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator._next()
        
        # Then call appropriate method based on period
        if clock_len > self._minperiod:
            self.next()
        elif clock_len == self._minperiod:
            self.nextstart()
        else:
            self.prenext()
    
    def _once(self):
        # Vectorized mode - process all data at once
        self.forward(size=self._clock.buflen())
        
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator._once()
        
        self.home()
        self.preonce(0, self._minperiod - 1)
        self.oncestart(self._minperiod - 1, self._minperiod)
        self.once(self._minperiod, self.buflen())
```

### `MetaLineIterator` - Iterator Metaclass

**Purpose:** Sets up data feeds, calculates minperiods, registers with owner.

```python
class MetaLineIterator(LineSeries.__class__):
    def donew(cls, *args, **kwargs):
        # Collect data feeds from arguments
        _obj.datas = []
        for arg in args:
            if isinstance(arg, LineRoot):
                _obj.datas.append(LineSeriesMaker(arg))
        
        # Set up data shortcuts
        _obj.data = _obj.datas[0]
        _obj.data_close = _obj.data.lines.close
        # etc.
    
    def dopreinit(cls, _obj, *args, **kwargs):
        # Clock is first data feed
        _obj._clock = _obj.datas[0]
        
        # Calculate minperiod from all datas
        _obj._minperiod = max([x._minperiod for x in _obj.datas])
    
    def dopostinit(cls, _obj, *args, **kwargs):
        # Register with owner
        if _obj._owner is not None:
            _obj._owner.addindicator(_obj)
```

### Base Classes for Components

```python
class DataAccessor(LineIterator):
    """Provides price constants like PriceClose, PriceLow, etc."""
    PriceClose = DataSeries.Close
    PriceLow = DataSeries.Low
    # ...

class IndicatorBase(DataAccessor):
    """Base for all indicators"""
    pass

class ObserverBase(DataAccessor):
    """Base for all observers"""
    pass

class StrategyBase(DataAccessor):
    """Base for all strategies"""
    pass
```

### Coupler Classes

**Purpose:** Handle data with different timeframes/lengths.

```python
class SingleCoupler(LineActions):
    """Couples a single line to a different clock"""
    def next(self):
        if len(self.cdata) > self.dlen:
            self.val = self.cdata[0]
            self.dlen += 1
        self[0] = self.val

class MultiCoupler(LineIterator):
    """Couples multiple lines to a different clock"""
    pass
```

---

## Complete Example: How It All Works Together

```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    params = (('sma_period', 20),)
    
    def __init__(self):
        # This triggers the entire lines machinery:
        
        # 1. MetaLineSeries creates self.lines with strategy lines
        # 2. MetaLineIterator sets up self.datas from cerebro
        # 3. SMA creates its own lines via its metaclass
        # 4. SMA registers with strategy via findowner + addindicator
        # 5. minperiod flows up: SMA needs 20 bars → strategy needs 20 bars
        
        self.sma = bt.indicators.SMA(
            self.data.close,  # LineBuffer for close prices
            period=self.p.sma_period
        )
        
        # This creates a LinesOperation (close - sma)
        self.diff = self.data.close - self.sma
    
    def next(self):
        # Called after minperiod bars have passed
        # self.data.close[0] → current close price
        # self.sma[0] → current SMA value
        # self.diff[0] → current difference
        
        if self.diff[0] > 0:  # Stage 2: returns actual value
            self.buy()

# Running the strategy
cerebro = bt.Cerebro()
cerebro.adddata(bt.feeds.YahooFinanceData(dataname='AAPL'))
cerebro.addstrategy(MyStrategy)

# cerebro.run() does:
# 1. For each bar:
#    - data.forward() adds new OHLCV values
#    - strategy._next() is called
#    - which calls sma._next() first
#    - which calls diff._next()
#    - then calls strategy.next()
```

---

## Memory Management: QBuffer Mode

For large datasets, backtrader can use rolling buffers:

```python
cerebro = bt.Cerebro()
cerebro.run(exactbars=True)  # Enable memory savings

# How it works:
# 1. Each line calculates its minbuffer requirement
# 2. Lines use deque(maxlen=minbuffer) instead of array
# 3. Old values are automatically discarded
```

```python
class LineBuffer:
    def qbuffer(self, savemem=0, extrasize=0):
        self.mode = self.QBuffer
        self.maxlen = self._minperiod
        self.array = collections.deque(maxlen=self.maxlen + extrasize)
```

---

## Execution Modes

### Step Mode (`runonce=False`)

```python
# Bar by bar execution
for each_bar in data:
    for indicator in indicators:
        indicator._next()  # Calculate one value
    strategy._next()       # Make one decision
```

### Vectorized Mode (`runonce=True`, default)

```python
# Process all data at once
for indicator in indicators:
    indicator._once()  # Calculate all values at once

for each_bar in data:
    strategy._next()  # Only strategy runs bar-by-bar
```

---

## Summary: Class Responsibilities

| Class | File | Purpose |
|-------|------|---------|
| `LineRoot` | lineroot.py | Abstract base with operators & period management |
| `LineSingle` | lineroot.py | Base for single-line objects |
| `LineMultiple` | lineroot.py | Base for multi-line objects |
| `LineBuffer` | linebuffer.py | Actual array storage with 0-indexed access |
| `LineActions` | linebuffer.py | Base for computed lines |
| `LinesOperation` | linebuffer.py | Binary operations (a + b) |
| `LineOwnOperation` | linebuffer.py | Unary operations (abs(a)) |
| `LineDelay` | linebuffer.py | Access past/future values |
| `Lines` | lineseries.py | Container for multiple LineBuffers |
| `LineAlias` | lineseries.py | Descriptor for named line access |
| `LineSeries` | lineseries.py | High-level multi-line class |
| `LineIterator` | lineiterator.py | Iteration and execution logic |
| `IndicatorBase` | lineiterator.py | Base for indicators |
| `StrategyBase` | lineiterator.py | Base for strategies |
| `ObserverBase` | lineiterator.py | Base for observers |

---

## Key Takeaways

1. **0-Indexed Access**: `line[0]` is always "now", `line[1]` is "yesterday"

2. **Automatic Period Calculation**: Indicators declare their period, and it propagates up the chain

3. **Lazy Line Creation**: Operations like `close - sma` create new line objects during `__init__`, not during execution

4. **Two-Stage System**: Stage 1 (building) creates line graphs; Stage 2 (running) evaluates them

5. **Binding System**: Lines can be bound so setting one automatically sets another

6. **Memory Efficiency**: QBuffer mode uses deques to limit memory for long backtests
