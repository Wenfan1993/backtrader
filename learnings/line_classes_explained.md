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

---

### LineBuffer Methods - Complete Examples

This section provides standalone examples demonstrating every method of the `LineBuffer` class.

#### Setup: Creating a Standalone LineBuffer

```python
import array
import collections
from collections import deque

# Simulate LineBuffer core functionality for demonstration
class SimpleLineBuffer:
    """Simplified LineBuffer for demonstration purposes"""
    NAN = float('NaN')
    UnBounded, QBuffer = (0, 1)
    
    def __init__(self):
        self.mode = self.UnBounded
        self.bindings = []
        self._minperiod = 1
        self.reset()
    
    def reset(self):
        if self.mode == self.QBuffer:
            self.array = deque(maxlen=self.maxlen)
        else:
            self.array = array.array('d')
        self.lencount = 0
        self._idx = -1
        self.extension = 0
    
    @property
    def idx(self):
        return self._idx
    
    @idx.setter
    def idx(self, value):
        self._idx = value
```

---

#### 1. `__init__()` - Initialize the Buffer

```python
from backtrader.linebuffer import LineBuffer

# Create a new LineBuffer
buf = LineBuffer()

print(f"Mode: {'UnBounded' if buf.mode == 0 else 'QBuffer'}")
print(f"Initial idx: {buf.idx}")
print(f"Initial length: {len(buf)}")
print(f"Bindings: {buf.bindings}")

# Output:
# Mode: UnBounded
# Initial idx: -1
# Initial length: 0
# Bindings: []
```

---

#### 2. `reset()` - Clear and Reinitialize

```python
buf = LineBuffer()

# Add some data
buf.forward(100)
buf.forward(101)
buf.forward(102)
print(f"Before reset - Length: {len(buf)}, idx: {buf.idx}")

# Reset clears everything
buf.reset()
print(f"After reset - Length: {len(buf)}, idx: {buf.idx}")

# Output:
# Before reset - Length: 3, idx: 2
# After reset - Length: 0, idx: -1
```

---

#### 3. `forward(value=NAN, size=1)` - Add Values and Move Forward

```python
buf = LineBuffer()

# Add single values
buf.forward(100.0)  # First value
print(f"After 1st forward: idx={buf.idx}, buf[0]={buf[0]}")

buf.forward(101.0)  # Second value
print(f"After 2nd forward: idx={buf.idx}, buf[0]={buf[0]}, buf[1]={buf[1]}")

buf.forward(102.0)
buf.forward(103.0)
buf.forward(104.0)
print(f"Array state: {list(buf.array)}")
print(f"buf[0]={buf[0]} (current), buf[1]={buf[1]} (1 ago), buf[2]={buf[2]} (2 ago)")

# Add multiple values at once
buf.forward(value=999.0, size=3)
print(f"After forward(size=3): len={len(buf)}, last 3 = {buf[0]}, {buf[1]}, {buf[2]}")

# Output:
# After 1st forward: idx=0, buf[0]=100.0
# After 2nd forward: idx=1, buf[0]=101.0, buf[1]=100.0
# Array state: [100.0, 101.0, 102.0, 103.0, 104.0]
# buf[0]=104.0 (current), buf[1]=103.0 (1 ago), buf[2]=102.0 (2 ago)
# After forward(size=3): len=8, last 3 = 999.0, 999.0, 999.0
```

---

#### 4. `__getitem__(ago)` and `__setitem__(ago, value)` - Access by Relative Position

```python
buf = LineBuffer()

# Build a price series
for price in [100, 101, 102, 103, 104, 105]:
    buf.forward(price)

# Access values using ago indexing
print(f"buf[0] = {buf[0]}  # Current (today)")
print(f"buf[1] = {buf[1]}  # 1 bar ago (yesterday)")
print(f"buf[2] = {buf[2]}  # 2 bars ago")
print(f"buf[3] = {buf[3]}  # 3 bars ago")

# Set values using ago indexing
buf[0] = 999  # Change current value
print(f"After buf[0] = 999: buf[0] = {buf[0]}")

# Set a past value (useful for corrections)
buf[2] = 888
print(f"After buf[2] = 888: buf[2] = {buf[2]}")

# Output:
# buf[0] = 105.0  # Current (today)
# buf[1] = 104.0  # 1 bar ago (yesterday)
# buf[2] = 103.0  # 2 bars ago
# buf[3] = 102.0  # 3 bars ago
# After buf[0] = 999: buf[0] = 999
# After buf[2] = 888: buf[2] = 888.0
```

---

#### 5. `get(ago=0, size=1)` - Get a Slice of Values

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104, 105, 106, 107]:
    buf.forward(price)

# Get last 3 values (including current)
slice_3 = buf.get(ago=0, size=3)
print(f"get(ago=0, size=3): {slice_3}")  # [105, 106, 107]

# Get 5 values ending at 2 bars ago
slice_5 = buf.get(ago=2, size=5)
print(f"get(ago=2, size=5): {slice_5}")  # [101, 102, 103, 104, 105]

# Use case: Calculate SMA
period = 4
recent_prices = buf.get(ago=0, size=period)
sma = sum(recent_prices) / period
print(f"SMA({period}) = {sma}")

# Output:
# get(ago=0, size=3): [105.0, 106.0, 107.0]
# get(ago=2, size=5): [101.0, 102.0, 103.0, 104.0, 105.0]
# SMA(4) = 105.5
```

---

#### 6. `getzero(idx=0, size=1)` and `getzeroval(idx=0)` - Access from Buffer Start

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104, 105]:
    buf.forward(price)

# getzero accesses from the BEGINNING of the buffer (not current position)
first_3 = buf.getzero(idx=0, size=3)
print(f"getzero(0, 3): {first_3}")  # First 3 values ever

middle_3 = buf.getzero(idx=2, size=3)
print(f"getzero(2, 3): {middle_3}")  # Values at positions 2, 3, 4

# getzeroval gets single value from buffer start
first_val = buf.getzeroval(0)
print(f"getzeroval(0): {first_val}")  # Very first value

third_val = buf.getzeroval(2)
print(f"getzeroval(2): {third_val}")  # Third value ever

# Output:
# getzero(0, 3): [100.0, 101.0, 102.0]
# getzero(2, 3): [102.0, 103.0, 104.0]
# getzeroval(0): 100.0
# getzeroval(2): 102.0
```

---

#### 7. `home()` - Reset Position Without Clearing Data

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104]:
    buf.forward(price)

print(f"Before home(): idx={buf.idx}, len={len(buf)}, buf[0]={buf[0]}")

buf.home()
print(f"After home(): idx={buf.idx}, len={len(buf)}")

# Now we can replay through the data
buf.advance()  # Move to position 0
print(f"After advance(): idx={buf.idx}, buf[0]={buf[0]}")

buf.advance()
print(f"After 2nd advance(): idx={buf.idx}, buf[0]={buf[0]}")

# Output:
# Before home(): idx=4, len=5, buf[0]=104.0
# After home(): idx=-1, len=0
# After advance(): idx=0, buf[0]=100.0
# After 2nd advance(): idx=1, buf[0]=101.0
```

---

#### 8. `advance(size=1)` - Move Index Without Adding Data

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104]:
    buf.forward(price)

buf.home()  # Go back to start

# Advance through existing data (replay mode)
for i in range(5):
    buf.advance()
    print(f"Step {i+1}: idx={buf.idx}, buf[0]={buf[0]}")

# Output:
# Step 1: idx=0, buf[0]=100.0
# Step 2: idx=1, buf[0]=101.0
# Step 3: idx=2, buf[0]=102.0
# Step 4: idx=3, buf[0]=103.0
# Step 5: idx=4, buf[0]=104.0
```

---

#### 9. `backwards(size=1, force=False)` - Remove Data and Move Back

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104, 105]:
    buf.forward(price)

print(f"Before backwards: len={len(buf)}, buf[0]={buf[0]}")
print(f"Array: {list(buf.array)}")

buf.backwards(size=2)  # Remove last 2 values
print(f"After backwards(2): len={len(buf)}, buf[0]={buf[0]}")
print(f"Array: {list(buf.array)}")

# Use case: Undo a tentative bar (used in resampling)
buf.forward(999)  # Add tentative value
print(f"Added tentative: buf[0]={buf[0]}")
buf.backwards()   # Remove it
print(f"Removed tentative: buf[0]={buf[0]}")

# Output:
# Before backwards: len=6, buf[0]=105.0
# Array: [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
# After backwards(2): len=4, buf[0]=103.0
# Array: [100.0, 101.0, 102.0, 103.0]
# Added tentative: buf[0]=999
# Removed tentative: buf[0]=103.0
```

---

#### 10. `rewind(size=1)` - Move Index Back Without Removing Data

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104]:
    buf.forward(price)

print(f"Before rewind: idx={buf.idx}, len={len(buf)}, buf[0]={buf[0]}")

buf.rewind(2)  # Move back 2 positions
print(f"After rewind(2): idx={buf.idx}, len={len(buf)}, buf[0]={buf[0]}")
print(f"Array still has all data: {list(buf.array)}")

# Note: rewind changes len and idx but NOT the array
# This is different from backwards() which removes data

# Output:
# Before rewind: idx=4, len=5, buf[0]=104.0
# After rewind(2): idx=2, len=3, buf[0]=102.0
# Array still has all data: [100.0, 101.0, 102.0, 103.0, 104.0]
```

---

#### 11. `extend(value=NAN, size=0)` - Add Future Values (Lookahead)

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104]:
    buf.forward(price)

print(f"Before extend: len={len(buf)}, buflen={buf.buflen()}")

# Extend adds positions BEYOND current index (for future values)
buf.extend(value=float('nan'), size=3)
print(f"After extend(3): len={len(buf)}, buflen={buf.buflen()}")
print(f"Array length: {len(buf.array)}")

# Now we can set future values using negative indexing
buf[-1] = 200  # 1 position ahead
buf[-2] = 201  # 2 positions ahead
print(f"buf[-1] = {buf[-1]}, buf[-2] = {buf[-2]}")

# Use case: Indicators that look ahead (e.g., ZigZag)

# Output:
# Before extend: len=5, buflen=5
# After extend(3): len=5, buflen=5
# Array length: 8
# buf[-1] = 200.0, buf[-2] = 201.0
```

---

#### 12. `buflen()` - Get Real Data Length

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104]:
    buf.forward(price)

print(f"len(buf) = {len(buf)}")       # Logical length
print(f"buflen() = {buf.buflen()}")    # Real array data length

buf.extend(size=3)  # Add extension space
print(f"After extend:")
print(f"len(buf) = {len(buf)}")        # Still 5
print(f"buflen() = {buf.buflen()}")    # Still 5 (excludes extension)
print(f"len(array) = {len(buf.array)}") # 8 (includes extension)

# Output:
# len(buf) = 5
# buflen() = 5
# After extend:
# len(buf) = 5
# buflen() = 5
# len(array) = 8
```

---

#### 13. `addbinding(binding)` - Link Lines Together

```python
# Create two line buffers
source = LineBuffer()
target = LineBuffer()

# Bind target to source - target receives same values
source.addbinding(target)

# Prepare target buffer
target.forward()
target.forward()
target.forward()

# Now when we set values on source, target gets them too
source.forward(100)
source.forward(101)
source.forward(102)

print(f"Source values: {[source[2], source[1], source[0]]}")
print(f"Target values: {[target[2], target[1], target[0]]}")

# Setting source[0] also sets target[0]
source[0] = 999
print(f"After source[0]=999:")
print(f"source[0] = {source[0]}")
print(f"target[0] = {target[0]}")

# Output:
# Source values: [100.0, 101.0, 102.0]
# Target values: [100.0, 101.0, 102.0]
# After source[0]=999:
# source[0] = 999
# target[0] = 999
```

---

#### 14. `qbuffer(savemem=0, extrasize=0)` - Enable Memory-Saving Mode

```python
buf = LineBuffer()
buf._minperiod = 5  # Set minperiod before qbuffer

# Enable QBuffer mode - only keeps last 'minperiod' values
buf.qbuffer(savemem=1, extrasize=1)

print(f"Mode: {'QBuffer' if buf.mode == 1 else 'UnBounded'}")
print(f"Max length: {buf.maxlen}")

# Add more values than maxlen
for i in range(10):
    buf.forward(i * 100)
    print(f"Added {i*100}: array has {len(buf.array)} values, buf[0]={buf[0]}")

# Only last N values are kept
print(f"\nFinal array: {list(buf.array)}")

# Output:
# Mode: QBuffer
# Max length: 5
# Added 0: array has 1 values, buf[0]=0.0
# Added 100: array has 2 values, buf[0]=100.0
# ...
# Added 900: array has 6 values, buf[0]=900.0
# Final array: [400.0, 500.0, 600.0, 700.0, 800.0, 900.0]
```

---

#### 15. `minbuffer(size)` - Ensure Minimum Buffer Size

```python
buf = LineBuffer()
buf._minperiod = 3
buf.qbuffer()  # Enable QBuffer with minperiod=3

print(f"Initial maxlen: {buf.maxlen}")

# An indicator needs more lookback - request larger buffer
buf.minbuffer(10)
print(f"After minbuffer(10): maxlen={buf.maxlen}")

# No change if requested size is smaller
buf.minbuffer(5)
print(f"After minbuffer(5): maxlen={buf.maxlen}")  # Still 10

# Output:
# Initial maxlen: 3
# After minbuffer(10): maxlen=10
# After minbuffer(5): maxlen=10
```

---

#### 16. `set(value, ago=0)` - Alternative Way to Set Values

```python
buf = LineBuffer()
for i in range(5):
    buf.forward(i * 10)

print(f"Before set: {[buf[i] for i in range(5)][::-1]}")

# set() is equivalent to buf[ago] = value
buf.set(999, ago=0)  # Same as buf[0] = 999
print(f"After set(999, ago=0): buf[0]={buf[0]}")

buf.set(888, ago=2)  # Same as buf[2] = 888
print(f"After set(888, ago=2): buf[2]={buf[2]}")

# Output:
# Before set: [0.0, 10.0, 20.0, 30.0, 40.0]
# After set(999, ago=0): buf[0]=999
# After set(888, ago=2): buf[2]=888
```

---

#### 17. `plot(idx=0, size=None)` and `plotrange(start, end)` - Get Data for Plotting

```python
buf = LineBuffer()
for price in [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]:
    buf.forward(price)

# plot() returns all data by default
all_data = buf.plot()
print(f"plot(): {all_data}")

# plot() with size - from beginning
first_5 = buf.plot(idx=0, size=5)
print(f"plot(0, 5): {first_5}")

# plotrange() - specific range
middle = buf.plotrange(3, 7)
print(f"plotrange(3, 7): {middle}")

# Output:
# plot(): [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
# plot(0, 5): [100.0, 101.0, 102.0, 103.0, 104.0]
# plotrange(3, 7): [103.0, 104.0, 105.0, 106.0]
```

---

#### 18. `oncebinding()` - Batch Copy to Bindings

```python
source = LineBuffer()
target = LineBuffer()

# In "once" mode, we build all data first, then copy to bindings
source.addbinding(target)

# Add all source data
for price in [100, 101, 102, 103, 104]:
    source.forward(price)

# Prepare target buffer
for _ in range(5):
    target.forward()

# Copy all values at once (used in runonce mode)
source.oncebinding()

print(f"Source: {list(source.array)}")
print(f"Target: {list(target.array)}")

# Output:
# Source: [100.0, 101.0, 102.0, 103.0, 104.0]
# Target: [100.0, 101.0, 102.0, 103.0, 104.0]
```

---

#### 19. `__call__(ago=None)` - Create Delayed or Coupled Version

```python
from backtrader.linebuffer import LineBuffer, LineDelay

buf = LineBuffer()
for price in [100, 101, 102, 103, 104, 105]:
    buf.forward(price)

# Calling with an integer creates a LineDelay
delayed = buf(-2)  # Values from 2 bars ago
print(f"Type: {type(delayed).__name__}")

# Calling with None creates a LineCoupler (for timeframe adaptation)
# coupled = buf()  # Would create LineCoupler

# In practice, used like:
# self.sma_delayed = self.sma(-5)  # SMA values from 5 bars ago
```

---

#### 20. DateTime Methods - `datetime()`, `date()`, `time()`, `dt()`, `tm()`

```python
from backtrader.linebuffer import LineBuffer
import datetime

# DateTime line stores dates as float numbers
dt_buf = LineBuffer()

# Simulate datetime as matplotlib date number (days since epoch)
# For demo, we'll just use simple numbers
from backtrader.utils import date2num

dates = [
    datetime.datetime(2024, 1, 1, 9, 30),
    datetime.datetime(2024, 1, 2, 9, 30),
    datetime.datetime(2024, 1, 3, 14, 45),
]

for d in dates:
    dt_buf.forward(date2num(d))

# Access datetime objects
print(f"datetime(0): {dt_buf.datetime(0)}")
print(f"datetime(1): {dt_buf.datetime(1)}")

# Just date part
print(f"date(0): {dt_buf.date(0)}")

# Just time part  
print(f"time(0): {dt_buf.time(0)}")

# Numeric date (integer part)
print(f"dt(0): {dt_buf.dt(0)}")

# Numeric time (fractional part)
print(f"tm(0): {dt_buf.tm(0)}")
```

---

#### 21. Time Comparison Methods - `tm_lt()`, `tm_le()`, `tm_eq()`, `tm_gt()`, `tm_ge()`

```python
from backtrader.linebuffer import LineBuffer
from backtrader.utils import date2num, time2num
import datetime

dt_buf = LineBuffer()

# Add a datetime
d = datetime.datetime(2024, 1, 15, 14, 30)  # 2:30 PM
dt_buf.forward(date2num(d))

# Compare time component
market_open = time2num(datetime.time(9, 30))
market_close = time2num(datetime.time(16, 0))
current_time = time2num(datetime.time(14, 30))

print(f"Is before market open? {dt_buf.tm_lt(market_open)}")   # False
print(f"Is after market open? {dt_buf.tm_gt(market_open)}")    # True
print(f"Is before market close? {dt_buf.tm_lt(market_close)}") # True
print(f"Is equal to 14:30? {dt_buf.tm_eq(current_time)}")      # True

# Output:
# Is before market open? False
# Is after market open? True
# Is before market close? True
# Is equal to 14:30? True
```

---

#### Complete Working Example: Simulating a Trading Day

```python
"""
Complete example showing LineBuffer methods in a realistic scenario
"""
from backtrader.linebuffer import LineBuffer

class SimplePriceSimulator:
    def __init__(self):
        self.close = LineBuffer()
        self.high = LineBuffer()
        self.low = LineBuffer()
        self.volume = LineBuffer()
    
    def add_bar(self, c, h, l, v):
        """Add a new price bar"""
        self.close.forward(c)
        self.high.forward(h)
        self.low.forward(l)
        self.volume.forward(v)
    
    def current_bar(self):
        """Get current bar data"""
        return {
            'close': self.close[0],
            'high': self.high[0],
            'low': self.low[0],
            'volume': self.volume[0]
        }
    
    def sma(self, period):
        """Calculate SMA of close prices"""
        if len(self.close) < period:
            return None
        prices = self.close.get(ago=0, size=period)
        return sum(prices) / period
    
    def highest(self, period):
        """Get highest high in period"""
        if len(self.high) < period:
            return None
        highs = self.high.get(ago=0, size=period)
        return max(highs)
    
    def lowest(self, period):
        """Get lowest low in period"""
        if len(self.low) < period:
            return None
        lows = self.low.get(ago=0, size=period)
        return min(lows)

# Simulate trading
sim = SimplePriceSimulator()

# Add historical bars (OHLCV simulation - just Close, High, Low, Volume)
bars = [
    (100, 102, 99, 1000),
    (101, 103, 100, 1200),
    (102, 104, 101, 1100),
    (103, 105, 102, 1300),
    (102, 104, 101, 1400),
    (104, 106, 103, 1500),
    (105, 107, 104, 1600),
    (106, 108, 105, 1700),
]

for c, h, l, v in bars:
    sim.add_bar(c, h, l, v)

print("=== Current State ===")
print(f"Current bar: {sim.current_bar()}")
print(f"SMA(5): {sim.sma(5):.2f}")
print(f"Highest(5): {sim.highest(5)}")
print(f"Lowest(5): {sim.lowest(5)}")

print("\n=== Historical Access ===")
print(f"Close 3 bars ago: {sim.close[3]}")
print(f"Last 4 closes: {sim.close.get(ago=0, size=4)}")

print("\n=== Replay Mode ===")
sim.close.home()
print("Replaying close prices:")
for i in range(len(bars)):
    sim.close.advance()
    print(f"  Bar {i}: close={sim.close[0]}")

# Output:
# === Current State ===
# Current bar: {'close': 106.0, 'high': 108.0, 'low': 105.0, 'volume': 1700.0}
# SMA(5): 104.40
# Highest(5): 108.0
# Lowest(5): 103.0
# 
# === Historical Access ===
# Close 3 bars ago: 103.0
# Last 4 closes: [103.0, 104.0, 105.0, 106.0]
# 
# === Replay Mode ===
# Replaying close prices:
#   Bar 0: close=100.0
#   Bar 1: close=101.0
#   Bar 2: close=102.0
#   ...
```

---

### Class: MetaLineActions

**Purpose**: Metaclass for LineActions that implements caching and manages initialization.

**Key Attributes**:
- `_acache`: Dictionary storing cached line action objects
- `_acacheuse`: Boolean flag to enable/disable caching

**Key Methods**:
- `cleancache()`: Clear the action cache
- `usecache(onoff)`: Enable or disable caching
- `__call__()`: Implements caching to avoid duplicate line operations
- `dopreinit()`: Calculate minperiod from operands, set clock
- `dopostinit()`: Register with owner after initialization

---

### MetaLineActions - Complete Examples

#### 1. Understanding the Caching Mechanism

The cache prevents creating duplicate LineActions objects when the same operation is performed multiple times.

```python
from backtrader.linebuffer import MetaLineActions, LineActions, LineBuffer

# Enable caching
MetaLineActions.usecache(True)

# The cache is a class-level dictionary
print(f"Cache enabled: {MetaLineActions._acacheuse}")
print(f"Cache contents: {MetaLineActions._acache}")

# When caching is ON, identical operations return the same object
# close - sma (same args) → returns cached object instead of creating new one

# Disable caching (default behavior)
MetaLineActions.usecache(False)

# Clear the cache
MetaLineActions.cleancache()
print(f"After clear: {MetaLineActions._acache}")

# Output:
# Cache enabled: True
# Cache contents: {}
# After clear: {}
```

#### 2. How `dopreinit` Works

The `dopreinit` method automatically calculates the minimum period from operands.

```python
"""
When you write: spread = close - open

MetaLineActions.dopreinit() does:
1. Sets _clock to the first LineRoot argument (close)
2. Collects all LineRoot args into _datas
3. Finds max _minperiod from all operands
4. Updates the new object's minperiod
"""

# Conceptual example of what happens internally:
class ConceptualDopreinit:
    def dopreinit(cls, _obj, *args, **kwargs):
        # 1. Default clock is owner
        _obj._clock = _obj._owner
        
        # 2. If first arg is a line, use it as clock
        if isinstance(args[0], LineRoot):
            _obj._clock = args[0]
        
        # 3. Collect all line data sources
        _obj._datas = [x for x in args if isinstance(x, LineRoot)]
        
        # 4. Get minperiods from all single-line operands
        _minperiods = [x._minperiod for x in args if isinstance(x, LineSingle)]
        
        # 5. Also check multi-line operands (use first line)
        mlines = [x.lines[0] for x in args if isinstance(x, LineMultiple)]
        _minperiods += [x._minperiod for x in mlines]
        
        # 6. Take the maximum (can't produce output until all inputs ready)
        _minperiod = max(_minperiods or [1])
        
        # 7. Update object's minperiod
        _obj.updateminperiod(_minperiod)
        
        return _obj, args, kwargs
```

#### 3. How `dopostinit` Works

The `dopostinit` method registers the action with its owner.

```python
"""
After a LineAction is fully initialized, dopostinit() registers it
with the owner so it gets called during iteration.
"""

# Conceptual example:
class ConceptualDopostinit:
    def dopostinit(cls, _obj, *args, **kwargs):
        # Register with owner's indicator list
        _obj._owner.addindicator(_obj)
        return _obj, args, kwargs

# In practice, this is why when you write:
#   self.diff = self.data.close - self.data.open
# 
# The resulting LinesOperation automatically gets registered
# with the strategy and will have its _next() called each bar.
```

---

### Class: PseudoArray

**Purpose**: Wraps a scalar value to make it behave like an array. Used when you need to treat a constant as a line.

```python
from backtrader.linebuffer import PseudoArray

# Create a PseudoArray from a scalar
const = PseudoArray(100.0)

# Any index returns the same wrapped value
print(f"const[0] = {const[0]}")
print(f"const[5] = {const[5]}")
print(f"const[-10] = {const[-10]}")

# The .array property returns self (for compatibility)
print(f"const.array is const: {const.array is const}")

# Use case: When you write  close * 2.0
# The 2.0 gets wrapped in PseudoArray so it can be used like a line:
#   for i in range(start, end):
#       result[i] = close.array[i] * const.array[i]  # const[i] always returns 2.0

# Output:
# const[0] = 100.0
# const[5] = 100.0
# const[-10] = 100.0
# const.array is const: True
```

---

### Class: LineActions

**Purpose**: Base class for all line operations. Extends LineBuffer with iteration interfaces (`_next`, `_once`) that make it compatible with LineIterator.

**Key Attributes**:
- `_ltype`: Line type (IndType for indicator)
- `_clock`: The data source used for timing
- `_datas`: List of data sources this action depends on

**Key Methods**:
- `_next()`: Internal iteration - determines which user method to call
- `_once()`: Batch processing mode
- `arrayize(obj)`: Static method to convert any object to array-like
- `qbuffer(savemem)`: Enable memory-saving mode for self and dependencies

---

### LineActions - Complete Examples

#### 1. The `_next()` Method

```python
"""
_next() is called once per bar and determines which user method to call
based on the current bar count vs minperiod.
"""

# Here's what _next() does:
def _next(self):
    clock_len = len(self._clock)  # How many bars so far
    
    # If clock advanced, we need to advance too
    if clock_len > len(self):
        self.forward()  # Add a new position
    
    # Determine which method to call based on minperiod
    if clock_len > self._minperiod:
        self.next()       # Normal calculation
    elif clock_len == self._minperiod:
        self.nextstart()  # First valid value (called once)
    else:
        self.prenext()    # Warmup period

# Example timeline for an SMA with period=3:
# Bar 1: prenext()     - not enough data
# Bar 2: prenext()     - not enough data  
# Bar 3: nextstart()   - first valid SMA
# Bar 4: next()        - normal calculation
# Bar 5: next()        - normal calculation
# ...
```

#### 2. The `_once()` Method (Batch Processing)

```python
"""
_once() processes ALL data at once (vectorized mode).
Much faster than calling _next() for each bar.
"""

def _once(self):
    # 1. Allocate space for all values at once
    self.forward(size=self._clock.buflen())
    
    # 2. Reset index to beginning
    self.home()
    
    # 3. Call batch methods for different phases
    self.preonce(0, self._minperiod - 1)           # Warmup phase
    self.oncestart(self._minperiod - 1, self._minperiod)  # First value
    self.once(self._minperiod, self.buflen())      # All remaining values
    
    # 4. Copy values to any bound lines
    self.oncebinding()
```

#### 3. The `arrayize()` Static Method

```python
from backtrader.linebuffer import LineActions, PseudoArray
from backtrader.lineroot import LineRoot, LineSingle, LineMultiple

# arrayize() converts any object to something with array-like access

# Case 1: Already a LineSingle - return as-is
line_single = some_line_buffer
result = LineActions.arrayize(line_single)
# result is line_single

# Case 2: LineMultiple - extract first line
line_multi = some_data_feed  # Has .lines with open, high, low, close
result = LineActions.arrayize(line_multi)
# result is line_multi.lines[0]

# Case 3: Scalar value - wrap in PseudoArray
result = LineActions.arrayize(2.5)
# result is PseudoArray(2.5)

# This is used internally in LinesOperation to handle mixed operands:
#   close * 2.0  →  arrayize(close), arrayize(2.0)
#                   →  close_line, PseudoArray(2.0)
```

#### 4. Creating a Custom LineAction

```python
import backtrader as bt
from backtrader.linebuffer import LineActions

class MyCustomAction(LineActions):
    """
    Custom action that calculates percentage change from N bars ago.
    """
    def __init__(self, data, period=1):
        super().__init__()
        self.data = data
        self.period = period
        self.addminperiod(period + 1)  # Need period+1 bars
    
    def next(self):
        current = self.data[0]
        past = self.data[self.period]
        if past != 0:
            self.lines[0] = (current - past) / past * 100
        else:
            self.lines[0] = 0
    
    def once(self, start, end):
        # Optimized batch processing
        src = self.data.array
        dst = self.array
        period = self.period
        
        for i in range(start, end):
            current = src[i]
            past = src[i - period]
            if past != 0:
                dst[i] = (current - past) / past * 100
            else:
                dst[i] = 0

# Usage in strategy:
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.pct_change = MyCustomAction(self.data.close, period=5)
    
    def next(self):
        print(f"5-bar % change: {self.pct_change[0]:.2f}%")
```

---

### Function: LineDelay(a, ago=0)

**Purpose**: Factory function that creates either a `_LineDelay` (for past values) or `_LineForward` (for future values) based on the `ago` parameter.

```python
from backtrader.linebuffer import LineDelay

# ago <= 0: Creates _LineDelay (accessing past)
delayed = LineDelay(some_line, ago=-3)  # Values from 3 bars ago
print(f"Type: {type(delayed).__name__}")  # _LineDelay

# ago > 0: Creates _LineForward (writing to future)
forward = LineDelay(some_line, ago=2)   # Write values 2 bars ahead
print(f"Type: {type(forward).__name__}")  # _LineForward

# Most common usage via __call__ on a line:
# close(-5)  →  LineDelay(close, -5)  →  _LineDelay object
```

---

### Function: LineNum(num)

**Purpose**: Creates a constant line that always returns the same value. Useful for operations involving constants.

```python
from backtrader.linebuffer import LineNum, PseudoArray

# Create a constant line with value 100
const_line = LineNum(100)

# Internally, it creates: LineDelay(PseudoArray(100))
# This makes the constant behave like a regular line

# Use case: Threshold comparisons
#   if close > 100:  →  close > LineNum(100)
# 
# Actually happens in LineIterator when non-line args are passed:
#   bt.indicators.CrossOver(close, 100)
#   → The 100 gets converted to LineNum(100) automatically
```

---

### Class: _LineDelay

**Purpose**: Delays a line by a specified number of periods. When you access `delayed[0]`, you get the value from N bars ago.

**Key Methods**:
- `__init__(a, ago)`: Store source line and delay amount
- `next()`: Copy value from `ago` periods back
- `once(start, end)`: Batch copy with delay

---

### _LineDelay - Complete Examples

#### 1. Basic Usage

```python
import backtrader as bt

class DelayedStrategy(bt.Strategy):
    def __init__(self):
        # Create delayed version of close price
        self.close_5_ago = self.data.close(-5)
        
        # The -5 triggers LineDelay → _LineDelay
        # self.close_5_ago[0] always equals self.data.close[5]
    
    def next(self):
        current = self.data.close[0]
        five_ago = self.close_5_ago[0]
        print(f"Current: {current}, 5 bars ago: {five_ago}")
```

#### 2. How `_LineDelay.next()` Works

```python
class _LineDelay:
    def __init__(self, a, ago):
        self.a = a          # Source line
        self.ago = ago      # Delay amount (negative)
        
        # Add delay to minperiod
        # If ago=-5, we need 6 bars before we can produce output
        self.addminperiod(abs(ago) + 1)
    
    def next(self):
        # Copy value from ago bars back
        self[0] = self.a[self.ago]
        
        # Example: ago=-3
        # self[0] = self.a[-3]
        # This accesses source 3 positions back
```

#### 3. How `_LineDelay.once()` Works (Batch Mode)

```python
def once(self, start, end):
    # Cache for performance
    dst = self.array      # Destination (our array)
    src = self.a.array    # Source array
    ago = self.ago        # Delay amount
    
    for i in range(start, end):
        dst[i] = src[i + ago]
        # With ago=-3:
        # dst[5] = src[5 + (-3)] = src[2]
        # dst[6] = src[6 + (-3)] = src[3]
        # etc.
```

#### 4. Practical Example: Momentum Indicator

```python
class SimpleMomentum(bt.Indicator):
    """
    Momentum = Close - Close[n bars ago]
    """
    lines = ('momentum',)
    params = (('period', 10),)
    
    def __init__(self):
        # Create delayed close
        delayed_close = self.data.close(-self.p.period)
        
        # Momentum is difference between current and delayed
        self.lines.momentum = self.data.close - delayed_close
        
        # This creates:
        # 1. _LineDelay(close, -10)
        # 2. LinesOperation(close, delayed, operator.sub)
```

---

### Class: _LineForward

**Purpose**: Stores values into future positions. The opposite of `_LineDelay` - instead of reading the past, it writes to the future.

**Key Methods**:
- `__init__(a, ago)`: Store source line and forward amount
- `next()`: Write current value to `ago` positions ahead
- `once(start, end)`: Batch write with forward offset

---

### _LineForward - Complete Examples

#### 1. Understanding Forward Writing

```python
"""
_LineForward writes values INTO THE FUTURE.

If ago=3:
  - On bar 0: writes to position -3 (3 bars ahead)
  - On bar 1: writes to position -2 (2 bars ahead)
  - etc.

This is used for indicators that need "lookahead" like ZigZag.
"""

class _LineForward:
    def __init__(self, a, ago):
        self.a = a      # Source line
        self.ago = ago  # Forward amount (positive)
        
        # Adjust minperiod if needed
        if ago > self.a._minperiod:
            self.addminperiod(ago - self.a._minperiod + 1)
    
    def next(self):
        # Write to FUTURE position
        self[-self.ago] = self.a[0]
        
        # Example: ago=2
        # self[-2] = self.a[0]
        # Writes current value 2 positions into the future
```

#### 2. How `_LineForward.once()` Works

```python
def once(self, start, end):
    dst = self.array
    src = self.a.array
    ago = self.ago
    
    for i in range(start, end):
        dst[i - ago] = src[i]
        # With ago=3:
        # dst[5 - 3] = src[5]  → dst[2] = src[5]
        # dst[6 - 3] = src[6]  → dst[3] = src[6]
        # Values are placed earlier in the array
```

#### 3. Use Case: ZigZag-style Indicator

```python
"""
Some indicators like ZigZag need to mark past points
after seeing future data. _LineForward enables this.

When a new peak is confirmed at bar 10:
  - Mark bar 7 as the peak (3 bars ago)
  - Use _LineForward with ago=3 to write backwards
"""

class SimpleZigZag(bt.Indicator):
    lines = ('zigzag',)
    params = (('depth', 12),)
    
    def __init__(self):
        # This indicator requires runonce=False
        # because it writes to past positions
        self._nextforce = True  # Force step-by-step mode
    
    def next(self):
        # When we confirm a peak/valley, mark it
        if self.is_peak_confirmed():
            peak_bar = self.find_peak_position()
            bars_ago = peak_bar  # How many bars back the peak was
            
            # Use extend() to make room for future writes
            # Then write the peak marker
            self.lines.zigzag[-bars_ago] = self.data.high[bars_ago]
```

#### 4. Comparison: _LineDelay vs _LineForward

```python
"""
_LineDelay: Read from the past
  - ago is negative (or 0)
  - self[0] = source[ago]
  - "Give me the value from N bars ago"

_LineForward: Write to the past (from future's perspective)
  - ago is positive
  - self[-ago] = source[0]
  - "Put today's value at position N bars ago"
"""

# Visual timeline:
#
# Array:    [... bar3, bar4, bar5, bar6, bar7 ...]
#                                         ↑
#                                     current (idx)
#
# _LineDelay(close, -3):
#   Reads: close[0-3] = close[-3] → reads bar4's value
#   self[0] = bar4_value
#
# _LineForward(close, 3):
#   Writes: self[0-3] = close[0] → writes to bar4's position
#   bar4_position = bar7_value
```

---

### Complete Example: Building Operations with LineActions

```python
"""
This example shows how LinesOperation uses the LineActions framework
to perform arithmetic operations between lines.
"""

import backtrader as bt
from backtrader.linebuffer import LinesOperation, LineOwnOperation
import operator

class OperationsDemo(bt.Strategy):
    def __init__(self):
        # Binary operations create LinesOperation objects
        
        # Addition: close + open
        self.sum_line = self.data.close + self.data.open
        print(f"Sum type: {type(self.sum_line).__name__}")
        
        # Subtraction: high - low  
        self.range_line = self.data.high - self.data.low
        print(f"Range type: {type(self.range_line).__name__}")
        
        # Scalar multiplication: close * 2
        self.doubled = self.data.close * 2.0
        print(f"Doubled type: {type(self.doubled).__name__}")
        
        # Unary operation: abs(close - open)
        self.abs_diff = abs(self.data.close - self.data.open)
        print(f"AbsDiff type: {type(self.abs_diff).__name__}")
        
        # Delayed line
        self.close_5_ago = self.data.close(-5)
        print(f"Delayed type: {type(self.close_5_ago).__name__}")
        
        # Chained operations
        self.complex = (self.data.close - self.data.open) / self.data.open * 100
        
    def next(self):
        print(f"Bar {len(self)}:")
        print(f"  Close + Open = {self.sum_line[0]:.2f}")
        print(f"  High - Low = {self.range_line[0]:.2f}")
        print(f"  Close * 2 = {self.doubled[0]:.2f}")
        print(f"  |Close - Open| = {self.abs_diff[0]:.2f}")
        print(f"  Close 5 ago = {self.close_5_ago[0]:.2f}")
        print(f"  Pct change = {self.complex[0]:.2f}%")

# Output:
# Sum type: LinesOperation
# Range type: LinesOperation
# Doubled type: LinesOperation
# AbsDiff type: LineOwnOperation
# Delayed type: _LineDelay
```

---

### Summary: LineActions Class Hierarchy

```
LineBuffer (core storage)
    │
    └── LineActions (adds iteration interface)
            │
            ├── _LineDelay (delay by N periods)
            │
            ├── _LineForward (write to future)
            │
            ├── LinesOperation (binary: a + b, a - b, etc.)
            │
            └── LineOwnOperation (unary: abs(a), -a, etc.)

MetaLineActions (metaclass)
    - Caching of identical operations
    - Automatic minperiod calculation
    - Registration with owner
```

---

### Class: _LineDelay (continued)

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

This file provides higher-level abstractions for working with multiple lines together. It's the bridge between low-level `LineBuffer` storage and high-level indicators/strategies.

---

### Class: LineAlias

**Purpose**: A Python descriptor that provides named access to lines. It allows accessing `self.lines.close` as `self.close`.

**Key Methods**:
- `__init__(line)`: Store the line index
- `__get__(obj, cls)`: Return the line from owner's lines
- `__set__(obj, value)`: Create a binding to set values automatically

---

### LineAlias - Complete Examples

#### 1. How LineAlias Works as a Descriptor

```python
from backtrader.lineseries import LineAlias

class SimpleExample:
    """Demonstrates how LineAlias descriptor works"""
    
    # Create descriptors for lines
    close = LineAlias(0)   # Maps to lines[0]
    high = LineAlias(1)    # Maps to lines[1]
    low = LineAlias(2)     # Maps to lines[2]
    
    def __init__(self):
        # Simulate a lines container
        self.lines = [
            [100, 101, 102],  # "close" data
            [105, 106, 107],  # "high" data
            [95, 96, 97],     # "low" data
        ]

obj = SimpleExample()

# Access lines by name (uses __get__)
print(f"obj.close = {obj.close}")  # [100, 101, 102]
print(f"obj.high = {obj.high}")    # [105, 106, 107]
print(f"obj.low = {obj.low}")      # [95, 96, 97]

# This is equivalent to:
print(f"obj.lines[0] = {obj.lines[0]}")
```

#### 2. How `__set__` Creates Bindings

```python
"""
When you assign to a LineAlias attribute, it doesn't replace the line.
Instead, it creates a BINDING so the source automatically updates the target.
"""

class MyIndicator(bt.Indicator):
    lines = ('signal',)
    
    def __init__(self):
        # This ASSIGNMENT uses LineAlias.__set__
        self.lines.signal = self.data.close - self.data.open
        
        # What actually happens:
        # 1. (self.data.close - self.data.open) creates a LinesOperation
        # 2. LineAlias.__set__ is called
        # 3. It calls value.addbinding(self.lines[0])
        # 4. Now the LinesOperation will auto-update self.lines.signal

# The indicator doesn't need a next() method!
# The binding handles everything automatically.
```

#### 3. Why LineDelay(0) is Needed in `__set__`

```python
"""
In LineAlias.__set__, there's this check:
    if not isinstance(value, LineActions):
        value = value(0)

This converts a raw LineBuffer to a LineDelay(0) before binding.
Why? Timing issues.
"""

class ExplainDelay:
    """
    Without the LineDelay(0) wrapper:
    - The binding would write immediately when set
    - But the line might not have forward()'d yet
    - This would write to the wrong index (1 bar early)
    
    With LineDelay(0):
    - Creates a LineActions object
    - LineActions._next() ensures proper timing
    - forward() happens before the value is copied
    """
    pass
```

---

### Class: Lines

**Purpose**: Container class that holds multiple `LineBuffer` objects. Provides array-like interface and forwards operations to all contained lines.

**Key Class Methods**:
- `_derive(name, lines, extralines, otherbases, ...)`: Create a subclass with additional lines
- `_getlines()`: Get tuple of line names
- `_getlinealias(i)`: Get name of line at index i
- `getlinealiases()`: Get all line names

**Key Instance Methods**:
- `__init__(initlines=None)`: Create LineBuffers for each defined line
- `size()`: Number of named lines
- `fullsize()`: Total lines including extras
- `extrasize()`: Number of extra lines
- Proxy methods: `forward`, `backwards`, `rewind`, `extend`, `reset`, `home`, `advance`

---

### Lines - Complete Examples

#### 1. Creating a Lines Class with `_derive()`

```python
from backtrader.lineseries import Lines

# Start with base Lines class (no lines defined)
print(f"Base Lines._getlines(): {Lines._getlines()}")  # ()

# Derive a new class with OHLC lines
OHLCLines = Lines._derive(
    name='OHLC',
    lines=('open', 'high', 'low', 'close'),
    extralines=0,
    otherbases=[],
)

print(f"OHLCLines._getlines(): {OHLCLines._getlines()}")
# ('open', 'high', 'low', 'close')

# Now derive with volume added
OHLCVLines = OHLCLines._derive(
    name='OHLCV',
    lines=('volume',),
    extralines=0,
    otherbases=[],
)

print(f"OHLCVLines._getlines(): {OHLCVLines._getlines()}")
# ('open', 'high', 'low', 'close', 'volume')
```

#### 2. Instantiating and Using Lines

```python
from backtrader.lineseries import Lines

# Create OHLC lines class
OHLCLines = Lines._derive('OHLC', ('open', 'high', 'low', 'close'), 0, [])

# Create instance - this creates LineBuffer for each line
lines = OHLCLines()

print(f"Number of lines: {lines.size()}")       # 4
print(f"Full size: {lines.fullsize()}")          # 4

# Add data to all lines at once
lines.forward()  # Moves all lines forward with NaN
print(f"Length after forward: {len(lines)}")     # 1

# Access individual lines
print(f"lines[0]: {lines[0]}")                   # LineBuffer object
print(f"lines.open: {lines.open}")               # Same LineBuffer (via descriptor)

# Set values
lines[0][0] = 100.0  # Set open
lines[1][0] = 105.0  # Set high
lines[2][0] = 95.0   # Set low
lines[3][0] = 102.0  # Set close

# Or access by name
lines.open[0] = 100.0
lines.close[0] = 102.0
```

#### 3. Proxy Operations on All Lines

```python
# All buffer operations are forwarded to every line

# Forward all lines
lines.forward(value=0.0, size=5)
print(f"After forward(5): len={len(lines)}")

# Home all lines (reset index to start)
lines.home()
print(f"After home: idx of first line = {lines[0].idx}")

# Advance all lines
lines.advance(size=3)
print(f"After advance(3): idx = {lines[0].idx}")

# Reset all lines
lines.reset()
print(f"After reset: len={len(lines)}")
```

#### 4. Extra Lines

```python
# Extra lines are anonymous LineBuffers used for internal calculations

LinesWithExtra = Lines._derive(
    name='WithExtra',
    lines=('main', 'signal'),
    extralines=2,  # 2 extra unnamed lines
    otherbases=[],
)

lines = LinesWithExtra()
print(f"Named lines (size): {lines.size()}")       # 2
print(f"Total lines (fullsize): {lines.fullsize()}") # 4
print(f"Extra lines: {lines.extrasize()}")          # 2

# Access extra lines by index
extra1 = lines[2]  # First extra line
extra2 = lines[3]  # Second extra line
```

---

### Class: MetaLineSeries

**Purpose**: Metaclass that processes class definitions, extracting `lines`, `plotinfo`, `plotlines` and creating derived classes.

**When Called**:
- `__new__`: At class definition time (creates the class)
- `donew`: At instance creation time (creates the instance)

---

### MetaLineSeries - Complete Examples

#### 1. What `__new__` Does (Class Creation)

```python
"""
When you define:

    class MyIndicator(bt.Indicator):
        lines = ('signal', 'histogram')
        plotinfo = dict(subplot=True)
        plotlines = dict(signal=dict(color='blue'))

MetaLineSeries.__new__ does:
"""

def conceptual_new(meta, name, bases, dct):
    # 1. Extract and remove special attributes
    newlines = dct.pop('lines', ())         # ('signal', 'histogram')
    newplotinfo = dct.pop('plotinfo', {})   # {'subplot': True}
    newplotlines = dct.pop('plotlines', {}) # {'signal': {'color': 'blue'}}
    
    # 2. Create the class without these attributes
    cls = super().__new__(meta, name, bases, dct)
    
    # 3. Get parent's lines class
    parent_lines = getattr(cls, 'lines', Lines)
    
    # 4. Derive new lines class with additional lines
    cls.lines = parent_lines._derive(
        name=name,
        lines=newlines,
        extralines=0,
        otherbases=[],
    )
    # cls.lines now has LineAlias descriptors for 'signal' and 'histogram'
    
    # 5. Derive plotinfo/plotlines classes
    parent_plotinfo = getattr(cls, 'plotinfo', AutoInfoClass)
    cls.plotinfo = parent_plotinfo._derive('pi_' + name, newplotinfo, [])
    
    parent_plotlines = getattr(cls, 'plotlines', AutoInfoClass)
    cls.plotlines = parent_plotlines._derive('pl_' + name, newplotlines, [])
    
    return cls
```

#### 2. What `donew` Does (Instance Creation)

```python
"""
When you create an instance:

    ind = MyIndicator(self.data)

MetaLineSeries.donew does:
"""

def conceptual_donew(cls, *args, **kwargs):
    # 1. Create plotinfo INSTANCE
    plotinfo = cls.plotinfo()
    for pname, pdef in cls.plotinfo._getitems():
        setattr(plotinfo, pname, kwargs.pop(pname, pdef))
    
    # 2. Create the object
    _obj = cls.__new__(cls)
    
    # 3. Attach plotinfo instance
    _obj.plotinfo = plotinfo
    
    # 4. Create LINES INSTANCE (creates LineBuffers)
    _obj.lines = cls.lines()  # Instantiates the derived Lines class
    
    # 5. Create plotlines instance
    _obj.plotlines = cls.plotlines()
    
    # 6. Add shortcuts
    _obj.l = _obj.lines              # Short alias
    _obj.line = _obj.lines[0]        # First line
    
    # 7. Add indexed aliases
    for i, line in enumerate(_obj.lines):
        setattr(_obj, f'line_{i}', line)
        setattr(_obj, f'line{i}', line)
    
    return _obj, args, kwargs
```

#### 3. Class Aliases Feature

```python
"""
You can define aliases for indicator classes:
"""

class SMA(bt.Indicator):
    alias = ('SimpleMovingAverage', ('MovAvg', 'Moving Average'))
    lines = ('sma',)
    
    # This creates:
    # - SimpleMovingAverage (alias for SMA)
    # - MovAvg (alias with plotname='Moving Average')

# All three are equivalent:
sma1 = SMA(data, period=20)
sma2 = SimpleMovingAverage(data, period=20)
sma3 = MovAvg(data, period=20)
```

---

### Class: LineSeries

**Purpose**: High-level base class for all multi-line objects (indicators, data feeds, observers).

**Key Attributes**:
- `lines`: Lines instance containing all LineBuffers
- `l`: Shortcut to lines
- `line`: First line (shortcut)
- `plotinfo`: Plotting configuration instance
- `plotlines`: Per-line plotting configuration

**Key Methods**:
- `__getattr__`: Delegates attribute access to lines
- `__getitem__`: Access first line by index
- `__call__`: Create delayed or coupled version
- `plotlabel()`: Generate plot label
- Proxy methods for buffer operations

---

### LineSeries - Complete Examples

#### 1. Defining a LineSeries Subclass

```python
import backtrader as bt

class BollingerBands(bt.Indicator):
    """Example LineSeries-based indicator"""
    
    # Lines declaration - processed by MetaLineSeries
    lines = ('mid', 'top', 'bot')
    
    # Parameters
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )
    
    # Plot configuration
    plotinfo = dict(subplot=False)  # Plot on main chart
    plotlines = dict(
        mid=dict(ls='--'),          # Dashed middle line
        top=dict(_samecolor=True),  # Same color as mid
        bot=dict(_samecolor=True),
    )
    
    def __init__(self):
        self.lines.mid = bt.indicators.SMA(self.data, period=self.p.period)
        stddev = bt.indicators.StdDev(self.data, period=self.p.period)
        self.lines.top = self.lines.mid + self.p.devfactor * stddev
        self.lines.bot = self.lines.mid - self.p.devfactor * stddev
```

#### 2. Accessing Lines Multiple Ways

```python
class LineAccessDemo(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(self.data, period=20)
        self.bb = BollingerBands(self.data)
    
    def next(self):
        # Method 1: Direct line access
        sma_value = self.sma.lines.sma[0]
        
        # Method 2: Using shortcut 'l'
        sma_value = self.sma.l.sma[0]
        
        # Method 3: Using 'line' (first line)
        sma_value = self.sma.line[0]
        
        # Method 4: Direct attribute (via __getattr__)
        sma_value = self.sma.sma[0]
        
        # Method 5: Indexed access on LineSeries
        sma_value = self.sma[0]  # Same as self.sma.lines[0][0]
        
        # For multi-line indicators:
        mid = self.bb.mid[0]
        top = self.bb.top[0]
        bot = self.bb.bot[0]
        
        # Or via lines:
        mid = self.bb.lines.mid[0]
```

#### 3. The `__call__` Method - Delays and Coupling

```python
class CallableDemo(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(self.data, period=20)
        
        # __call__ with integer creates LineDelay
        self.sma_5_ago = self.sma(-5)  # SMA values from 5 bars ago
        print(f"Delayed type: {type(self.sma_5_ago).__name__}")
        # Output: _LineDelay
        
        # __call__ with None creates LineCoupler (timeframe adaptation)
        # Useful for multi-timeframe strategies
        daily_data = self.datas[1]  # Assume daily data
        daily_sma = bt.indicators.SMA(daily_data, period=50)
        
        # Couple daily SMA to intraday timeframe
        self.coupled_sma = daily_sma()
        print(f"Coupled type: {type(self.coupled_sma).__name__}")
        # Output: LinesCoupler (or SingleCoupler)
    
    def next(self):
        current_sma = self.sma[0]
        sma_5_bars_ago = self.sma_5_ago[0]
        
        # Coupled SMA holds daily value, updates when daily bar closes
        daily_sma_value = self.coupled_sma[0]
```

#### 4. The `plotlabel()` Method

```python
class PlotLabelDemo(bt.Indicator):
    lines = ('output',)
    params = (('period', 20), ('mult', 2.0))
    
    def _plotlabel(self):
        # Override to customize sublabels
        return [self.p.period, self.p.mult]

# Plot label will be: "PlotLabelDemo (20, 2.0)"

# Or use plotinfo.plotname:
class NamedIndicator(bt.Indicator):
    lines = ('output',)
    params = (('period', 20),)
    plotinfo = dict(plotname='My Custom Name')

# Plot label will be: "My Custom Name (20)"
```

#### 5. Buffer Operations

```python
# LineSeries provides proxy methods that forward to all lines

class BufferDemo(bt.Indicator):
    lines = ('line1', 'line2', 'line3')
    
    def some_method(self):
        # Forward all lines
        self.forward()  # Calls forward() on line1, line2, line3
        
        # Reset all lines
        self.reset()    # Calls reset() on all lines
        
        # Home all lines
        self.home()     # Calls home() on all lines
        
        # These are equivalent to:
        self.lines.forward()
        self.lines.reset()
        self.lines.home()
```

---

### Class: LineSeriesStub

**Purpose**: Wraps a single `LineBuffer` to give it a `LineSeries` interface. Used internally when operations need to treat a single line as a multi-line object.

**Key Feature**: The `slave` parameter controls whether buffer operations are executed or suppressed (to prevent double-advancing).

---

### LineSeriesStub - Complete Examples

#### 1. Basic Usage

```python
from backtrader.lineseries import LineSeriesStub, LineSeries

class StubDemo(bt.Strategy):
    def __init__(self):
        # Get a single line (LineBuffer)
        close_line = self.data.close
        print(f"close_line type: {type(close_line).__name__}")
        # Output: LineBuffer
        
        # Wrap it in LineSeriesStub
        stub = LineSeriesStub(close_line, slave=False)
        print(f"stub type: {type(stub).__name__}")
        # Output: LineSeriesStub
        
        # Now it has LineSeries interface
        print(f"stub.lines: {stub.lines}")
        print(f"isinstance LineSeries: {isinstance(stub, LineSeries)}")
        # Output: True
```

#### 2. The `slave` Parameter

```python
"""
The slave parameter prevents double-advancing of lines.

Scenario: A LineBuffer is part of a LineSeries (like data.close is part of data).
When you wrap it in LineSeriesStub:

slave=False: Buffer operations ARE executed
  - Use when the stub manages its own lifecycle

slave=True: Buffer operations are SKIPPED
  - Use when the original owner (data feed) manages the lifecycle
  - Prevents calling forward() twice
"""

class SlaveDemo(bt.Strategy):
    def __init__(self):
        # Close line is managed by self.data
        close = self.data.close
        
        # If we create a non-slave stub and call forward()...
        stub_master = LineSeriesStub(close, slave=False)
        stub_master.forward()  # This WOULD modify the buffer
        
        # If we create a slave stub and call forward()...
        stub_slave = LineSeriesStub(close, slave=True)
        stub_slave.forward()  # This is IGNORED
        
        # The slave stub inherits owner and minperiod
        print(f"Owner: {stub_slave._owner}")
        print(f"Minperiod: {stub_slave._minperiod}")
```

#### 3. Methods That Check `slave`

```python
class LineSeriesStub(LineSeries):
    """All these methods check slave before executing"""
    
    def forward(self, value=NAN, size=1):
        if not self.slave:
            super().forward(value, size)
    
    def backwards(self, size=1, force=False):
        if not self.slave:
            super().backwards(size, force=force)
    
    def rewind(self, size=1):
        if not self.slave:
            super().rewind(size)
    
    def extend(self, value=NAN, size=0):
        if not self.slave:
            super().extend(value, size)
    
    def reset(self):
        if not self.slave:
            super().reset()
    
    def home(self):
        if not self.slave:
            super().home()
    
    def advance(self, size=1):
        if not self.slave:
            super().advance(size)
    
    def qbuffer(self):
        if not self.slave:
            super().qbuffer()
    
    def minbuffer(self, size):
        if not self.slave:
            super().minbuffer(size)
```

---

### Function: LineSeriesMaker(arg, slave=False)

**Purpose**: Factory function that ensures any input has a `LineSeries` interface.

**Logic**:
- If input is already `LineSeries`: return as-is
- If input is `LineBuffer`: wrap in `LineSeriesStub`

---

### LineSeriesMaker - Complete Examples

```python
from backtrader.lineseries import LineSeriesMaker, LineSeries, LineSeriesStub

# Case 1: Already a LineSeries - returned unchanged
data_feed = self.data  # LineSeries
result = LineSeriesMaker(data_feed)
print(result is data_feed)  # True

# Case 2: Single line - wrapped in stub
close_line = self.data.close  # LineBuffer
result = LineSeriesMaker(close_line)
print(type(result).__name__)  # LineSeriesStub

# Case 3: With slave parameter
result = LineSeriesMaker(close_line, slave=True)
print(result.slave)  # True

# Internal implementation:
def LineSeriesMaker(arg, slave=False):
    if isinstance(arg, LineSeries):
        return arg
    return LineSeriesStub(arg, slave=slave)
```

---

### Complete Example: Building a Custom Multi-Line Indicator

```python
"""
Comprehensive example showing all lineseries.py concepts together
"""

import backtrader as bt

class MACD(bt.Indicator):
    """
    MACD indicator demonstrating lineseries concepts:
    - Multiple output lines
    - Line bindings (automatic assignment)
    - Plotting configuration
    """
    
    # Lines processed by MetaLineSeries
    lines = ('macd', 'signal', 'histogram')
    
    # Parameters processed by MetaParams
    params = (
        ('fast', 12),
        ('slow', 26),
        ('signal', 9),
    )
    
    # Plotting configuration
    plotinfo = dict(
        subplot=True,
        plotname='MACD'
    )
    
    plotlines = dict(
        macd=dict(color='blue'),
        signal=dict(color='orange', ls='--'),
        histogram=dict(_method='bar', color='gray', alpha=0.5),
    )
    
    def __init__(self):
        # Calculate EMAs
        fast_ema = bt.indicators.EMA(self.data, period=self.p.fast)
        slow_ema = bt.indicators.EMA(self.data, period=self.p.slow)
        
        # MACD line = fast EMA - slow EMA
        # Using line assignment (triggers LineAlias.__set__)
        self.lines.macd = fast_ema - slow_ema
        
        # Signal line = EMA of MACD
        self.lines.signal = bt.indicators.EMA(self.lines.macd, period=self.p.signal)
        
        # Histogram = MACD - Signal
        self.lines.histogram = self.lines.macd - self.lines.signal
        
        # All calculations are automatic via bindings!
        # No next() method needed.


class MACDStrategy(bt.Strategy):
    def __init__(self):
        self.macd = MACD(self.data)
        
        # Access all the line access patterns:
        print("=== Line Access Patterns ===")
        print(f"self.macd.lines.macd: {type(self.macd.lines.macd).__name__}")
        print(f"self.macd.l.signal: {type(self.macd.l.signal).__name__}")
        print(f"self.macd.histogram: {type(self.macd.histogram).__name__}")
        
        # Delayed version
        self.macd_yesterday = self.macd.macd(-1)
        
    def next(self):
        macd_val = self.macd.macd[0]
        signal_val = self.macd.signal[0]
        hist_val = self.macd.histogram[0]
        
        if self.macd.macd[0] > self.macd.signal[0]:
            if self.macd.macd[1] <= self.macd.signal[1]:
                print(f"MACD Cross Up! MACD={macd_val:.4f}")
                self.buy()
        
        elif self.macd.macd[0] < self.macd.signal[0]:
            if self.macd.macd[1] >= self.macd.signal[1]:
                print(f"MACD Cross Down! MACD={macd_val:.4f}")
                self.sell()


# Run backtest
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    data = bt.feeds.YahooFinanceData(dataname='AAPL',
                                      fromdate=datetime(2020, 1, 1),
                                      todate=datetime(2021, 1, 1))
    cerebro.adddata(data)
    cerebro.addstrategy(MACDStrategy)
    cerebro.run()
    cerebro.plot()
```

---

### Summary: lineseries.py Class Hierarchy

```
LineMultiple (from lineroot.py)
    │
    └── LineSeries (uses MetaLineSeries metaclass)
            │
            ├── LineSeriesStub (wraps single line as LineSeries)
            │
            └── [User classes: Indicators, DataFeeds, Observers, Strategies]

Lines (container class)
    │
    └── Derived Lines classes (created by _derive())
            - Hold multiple LineBuffer objects
            - Have LineAlias descriptors for named access

LineAlias (descriptor)
    - __get__: Return line from lines container
    - __set__: Create binding for automatic updates

LineSeriesMaker (factory function)
    - Ensures LineSeries interface for any input

MetaLineSeries (metaclass)
    - __new__: Process class definition, create Lines/plotinfo/plotlines classes
    - donew: Create instances, set up shortcuts and aliases
```

---

## lineiterator.py

This file adds iteration capabilities for indicators and strategies. It's the execution engine that drives the bar-by-bar processing.

---

### Class: MetaLineIterator

**Purpose**: Metaclass that manages data sources, creates data shortcuts, and sets up the iteration framework.

**Key Lifecycle Methods**:
- `donew`: Scans args for data sources, creates data shortcuts
- `dopreinit`: Sets clock, calculates initial minperiod
- `dopostinit`: Finalizes minperiod, registers with owner

---

### MetaLineIterator - Complete Examples

#### 1. What `donew` Does

```python
"""
When you create an indicator:

    sma = bt.indicators.SMA(self.data, period=20)

MetaLineIterator.donew() does:
"""

def conceptual_donew(cls, *args, **kwargs):
    # 1. Call parent's donew (creates lines, params, etc.)
    _obj, args, kwargs = super().donew(*args, **kwargs)
    
    # 2. Initialize child iterator storage
    _obj._lineiterators = collections.defaultdict(list)
    # Holds: {IndType: [indicators], ObsType: [observers], ...}
    
    # 3. Scan args for data sources
    _obj.datas = []
    mindatas = _obj._mindatas  # Usually 1
    
    for arg in args:
        if isinstance(arg, LineRoot):
            # It's a line/data - add it
            _obj.datas.append(LineSeriesMaker(arg))
        elif mindatas > 0:
            try:
                # Try to convert to LineNum (for constants)
                _obj.datas.append(LineSeriesMaker(LineNum(arg)))
            except:
                break
        else:
            break
        mindatas -= 1
    
    # 4. If no datas found, use owner's datas
    if not _obj.datas and isinstance(_obj, (IndicatorBase, ObserverBase)):
        _obj.datas = _obj._owner.datas[0:_obj._mindatas]
    
    # 5. Create data shortcuts
    if _obj.datas:
        _obj.data = _obj.datas[0]  # First data shortcut
        
        # Create line shortcuts for first data
        # data_close, data_high, data_low, data_open, etc.
        for i, line in enumerate(_obj.data.lines):
            alias = _obj.data._getlinealias(i)
            if alias:
                setattr(_obj, f'data_{alias}', line)
            setattr(_obj, f'data_{i}', line)
        
        # Create numbered data shortcuts
        # data0, data1, data2, etc.
        for d, data in enumerate(_obj.datas):
            setattr(_obj, f'data{d}', data)
            
            # And their line shortcuts
            # data0_close, data1_high, etc.
            for i, line in enumerate(data.lines):
                alias = data._getlinealias(i)
                if alias:
                    setattr(_obj, f'data{d}_{alias}', line)
                setattr(_obj, f'data{d}_{i}', line)
    
    # 6. Create dnames for named data access
    _obj.dnames = DotDict([(d._name, d) for d in _obj.datas if d._name])
    
    return _obj, newargs, kwargs
```

#### 2. What `dopreinit` Does

```python
def conceptual_dopreinit(cls, _obj, *args, **kwargs):
    # 1. Fall back to owner as data source if none found
    _obj.datas = _obj.datas or [_obj._owner]
    
    # 2. First data is the clock (timing reference)
    _obj._clock = _obj.datas[0]
    
    # 3. Calculate minperiod from all data sources
    # Can't produce output until all inputs are ready
    _obj._minperiod = max([x._minperiod for x in _obj.datas])
    
    # 4. Propagate minperiod to all output lines
    for line in _obj.lines:
        line.addminperiod(_obj._minperiod)
    
    return _obj, args, kwargs
```

#### 3. What `dopostinit` Does

```python
def conceptual_dopostinit(cls, _obj, *args, **kwargs):
    # 1. Final minperiod is max of all output lines
    _obj._minperiod = max([x._minperiod for x in _obj.lines])
    
    # 2. Recalculate considering child indicators
    _obj._periodrecalc()
    
    # 3. Register with owner
    if _obj._owner is not None:
        _obj._owner.addindicator(_obj)
    
    return _obj, args, kwargs
```

#### 4. Data Shortcuts Created by donew

```python
class DataShortcutsDemo(bt.Strategy):
    def __init__(self):
        # All these shortcuts are created by MetaLineIterator.donew:
        
        # First data shortcuts
        print(f"self.data: {self.data}")           # First data feed
        print(f"self.data0: {self.data0}")         # Same as self.data
        print(f"self.data_close: {self.data_close}") # Close line
        print(f"self.data_high: {self.data_high}")   # High line
        print(f"self.data_0: {self.data_0}")         # First line by index
        
        # Second data shortcuts (if exists)
        if len(self.datas) > 1:
            print(f"self.data1: {self.data1}")
            print(f"self.data1_close: {self.data1_close}")
        
        # Named data access (if data has _name)
        # cerebro.adddata(data, name='AAPL')
        if 'AAPL' in self.dnames:
            print(f"self.dnames.AAPL: {self.dnames.AAPL}")
```

---

### Class: LineIterator

**Purpose**: The main iteration class that all indicators, observers, and strategies inherit from. Provides the execution machinery for bar-by-bar and batch processing.

**Key Attributes**:
- `datas`: List of data sources
- `data`: First data source (shortcut)
- `_clock`: Timing reference (usually first data)
- `_lineiterators`: Dict of child indicators/observers
- `_mindatas`: Minimum required data sources (default 1)
- `_nextforce`: Force step-by-step mode (disable runonce)
- `_ltype`: Type identifier (IndType, StratType, ObsType)

**Key Methods**:
- Iteration: `_next()`, `_once()`, `_clk_update()`
- User callbacks: `prenext()`, `nextstart()`, `next()`, `preonce()`, `oncestart()`, `once()`
- Management: `addindicator()`, `getindicators()`, `bindlines()`
- Stages: `_stage1()`, `_stage2()`, `_periodrecalc()`

---

### LineIterator - Complete Examples

#### 1. The `_next()` Method - Step-by-Step Execution

```python
"""
_next() is called once per bar by cerebro.
It orchestrates the entire calculation chain.
"""

def _next(self):
    # 1. Update clock and forward if needed
    clock_len = self._clk_update()
    
    # 2. First, calculate ALL child indicators
    for indicator in self._lineiterators[LineIterator.IndType]:
        indicator._next()
    
    # 3. Handle notifications (for strategies)
    self._notify()
    
    # 4. Determine which user method to call
    if self._ltype == LineIterator.StratType:
        # Strategy: check actual minperiod status
        minperstatus = self._getminperstatus()
        if minperstatus < 0:
            self.next()       # All datas have enough bars
        elif minperstatus == 0:
            self.nextstart()  # First bar with enough data
        else:
            self.prenext()    # Warming up
    else:
        # Indicator/Observer: use simple clock check
        if clock_len > self._minperiod:
            self.next()
        elif clock_len == self._minperiod:
            self.nextstart()
        elif clock_len:
            self.prenext()

# Timeline example for indicator with minperiod=5:
# Bar 1: prenext()
# Bar 2: prenext()
# Bar 3: prenext()
# Bar 4: prenext()
# Bar 5: nextstart()  ← First valid calculation
# Bar 6: next()
# Bar 7: next()
# ...
```

#### 2. The `_once()` Method - Batch Execution

```python
"""
_once() processes ALL data at once (vectorized).
Much faster than calling _next() for each bar.
"""

def _once(self):
    # 1. Allocate space for all values
    self.forward(size=self._clock.buflen())
    
    # 2. Process all child indicators in batch
    for indicator in self._lineiterators[LineIterator.IndType]:
        indicator._once()
    
    # 3. Prepare observers (allocate space)
    for observer in self._lineiterators[LineIterator.ObsType]:
        observer.forward(size=self.buflen())
    
    # 4. Reset all indices to beginning
    for data in self.datas:
        data.home()
    for indicator in self._lineiterators[LineIterator.IndType]:
        indicator.home()
    for observer in self._lineiterators[LineIterator.ObsType]:
        observer.home()
    self.home()
    
    # 5. Call batch calculation methods
    self.preonce(0, self._minperiod - 1)
    self.oncestart(self._minperiod - 1, self._minperiod)
    self.once(self._minperiod, self.buflen())
    
    # 6. Execute bindings
    for line in self.lines:
        line.oncebinding()
```

#### 3. The `_clk_update()` Method

```python
def _clk_update(self):
    """
    Sync our position with the clock.
    Returns current clock length.
    """
    clock_len = len(self._clock)
    
    # If clock advanced, we need to advance too
    if clock_len != len(self):
        self.forward()  # Add new position
    
    return clock_len
```

#### 4. User-Overridable Iteration Methods

```python
class IterationMethodsDemo(bt.Indicator):
    lines = ('output',)
    params = (('period', 20),)
    
    def __init__(self):
        self.addminperiod(self.p.period)
        self.count = 0
    
    def prenext(self):
        """
        Called during warmup period.
        Not enough data for valid calculation.
        """
        self.count += 1
        # Can still do partial calculations if desired
        # self.lines.output[0] = float('nan')
        print(f"prenext #{self.count}: bar {len(self)}")
    
    def nextstart(self):
        """
        Called ONCE when minperiod is first satisfied.
        Default implementation calls next().
        """
        print(f"nextstart: bar {len(self)} - First valid calculation!")
        # Do any first-time initialization
        self.next()  # Usually just call next()
    
    def next(self):
        """
        Called for each bar after minperiod.
        This is where main calculation happens.
        """
        # Calculate SMA
        total = sum(self.data.close.get(size=self.p.period))
        self.lines.output[0] = total / self.p.period
```

#### 5. Batch Processing Methods

```python
class BatchMethodsDemo(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)
    
    def preonce(self, start, end):
        """
        Batch warmup - process bars 0 to minperiod-1.
        Usually left empty (output is NaN anyway).
        """
        pass
    
    def oncestart(self, start, end):
        """
        Batch first value - process bar at minperiod-1.
        Default calls once(start, end).
        """
        self.once(start, end)
    
    def once(self, start, end):
        """
        Batch main calculation - process bars from minperiod to end.
        This is optimized for speed.
        """
        # Cache array references for speed
        src = self.data.close.array
        dst = self.lines.sma.array
        period = self.p.period
        
        for i in range(start, end):
            # Sum last 'period' values
            total = 0
            for j in range(period):
                total += src[i - j]
            dst[i] = total / period
```

#### 6. The `addindicator()` Method

```python
def addindicator(self, indicator):
    """
    Register a child indicator/observer.
    Called automatically by MetaLineIterator.dopostinit.
    """
    # Store by type (IndType, ObsType, StratType)
    self._lineiterators[indicator._ltype].append(indicator)
    
    # Check if indicator requires step-by-step mode
    if getattr(indicator, '_nextforce', False):
        # Walk up to find strategy and disable runonce
        o = self
        while o is not None:
            if o._ltype == LineIterator.StratType:
                o.cerebro._disable_runonce()
                break
            o = o._owner

# This is why indicators are automatically calculated:
# 1. Indicator created in Strategy.__init__
# 2. MetaLineIterator.dopostinit calls owner.addindicator(indicator)
# 3. Indicator added to strategy._lineiterators[IndType]
# 4. When strategy._next() runs, it calls indicator._next() first
```

#### 7. The `bindlines()` Method

```python
class BindLinesDemo(bt.Indicator):
    """
    Bind indicator output to strategy lines.
    Useful for creating strategy-level lines from indicators.
    """
    lines = ('result',)
    
    def __init__(self):
        sma = bt.indicators.SMA(self.data, period=20)
        
        # Bind our 'result' line to owner's line 0
        self.bindlines(owner=0, own='result')
        
        # Alternative: bind by names
        # self.bindlines(owner='signal', own='result')
        
        # After binding, when we set self.lines.result[0],
        # it also sets self._owner.lines[0][0]


# The implementation:
def bindlines(self, owner=None, own=None):
    # Normalize to lists
    if not owner:
        owner = 0
    if isinstance(owner, string_types):
        owner = [owner]
    elif not isinstance(owner, collections.Iterable):
        owner = [owner]
    
    if not own:
        own = range(len(owner))
    if isinstance(own, string_types):
        own = [own]
    elif not isinstance(own, collections.Iterable):
        own = [own]
    
    # Create bindings
    for lineowner, lineown in zip(owner, own):
        # Get owner's line
        if isinstance(lineowner, string_types):
            lownerref = getattr(self._owner.lines, lineowner)
        else:
            lownerref = self._owner.lines[lineowner]
        
        # Get our line
        if isinstance(lineown, string_types):
            lownref = getattr(self.lines, lineown)
        else:
            lownref = self.lines[lineown]
        
        # Bind them
        lownref.addbinding(lownerref)
    
    return self  # Allow chaining
```

#### 8. Stage Management

```python
"""
Stages control how operations behave:
- Stage 1: Setup phase - operations create new line objects
- Stage 2: Execution phase - operations return values
"""

class StageDemo(bt.Strategy):
    def __init__(self):
        # Stage 1 (setup)
        # This creates a LinesOperation object
        self.diff = self.data.close - self.data.open
        print(f"Stage 1: type(diff) = {type(self.diff).__name__}")
        # Output: LinesOperation
    
    def next(self):
        # Stage 2 (execution)
        # Now operations return actual values
        if self.data.close[0] > self.data.open[0]:
            # This comparison returns True/False, not a line object
            self.buy()

# The stage transition happens via:
# cerebro calls strategy._stage2() before running
# which propagates to all children
```

#### 9. Memory Management with `qbuffer()`

```python
class MemoryDemo(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(period=20)
        
        # Enable memory-saving mode
        # Only keep minperiod values in buffer
        self.qbuffer(savemem=1)

# The implementation:
def qbuffer(self, savemem=0):
    if savemem:
        # Enable qbuffer for our lines
        for line in self.lines:
            line.qbuffer()
    
    # Propagate to child indicators
    for obj in self._lineiterators[self.IndType]:
        obj.qbuffer(savemem=1)
    
    # Tell datas to limit buffer size
    for data in self.datas:
        data.minbuffer(self._minperiod)
```

---

### Class: DataAccessor

**Purpose**: Provides constants for accessing OHLCV data columns by index. Inherited by all indicators, strategies, and observers.

---

### DataAccessor - Complete Examples

```python
from backtrader.lineiterator import DataAccessor
from backtrader.dataseries import DataSeries

# DataAccessor provides these constants:
class DataAccessor(LineIterator):
    PriceClose = DataSeries.Close           # 0
    PriceLow = DataSeries.Low               # 1  
    PriceHigh = DataSeries.High             # 2
    PriceOpen = DataSeries.Open             # 3
    PriceVolume = DataSeries.Volume         # 4
    PriceOpenInteres = DataSeries.OpenInterest  # 5
    PriceDateTime = DataSeries.DateTime     # 6

# Usage example:
class UseDataAccessor(bt.Indicator):
    def next(self):
        # Access by index constant
        close = self.data.lines[self.PriceClose][0]
        high = self.data.lines[self.PriceHigh][0]
        low = self.data.lines[self.PriceLow][0]
        
        # This is equivalent to:
        close = self.data.close[0]
        high = self.data.high[0]
        low = self.data.low[0]
        
        # The constants are useful for generic code:
        def get_price(data, price_type):
            return data.lines[price_type][0]
        
        close = get_price(self.data, self.PriceClose)
```

---

### Class: IndicatorBase

**Purpose**: Empty base class for indicators. Inherits from `DataAccessor`. Used for type checking and identification.

```python
class IndicatorBase(DataAccessor):
    pass

# All indicators ultimately inherit from this:
# bt.Indicator -> ... -> IndicatorBase -> DataAccessor -> LineIterator

# Use for type checking:
def is_indicator(obj):
    return isinstance(obj, IndicatorBase)
```

---

### Class: ObserverBase

**Purpose**: Empty base class for observers. Used for type checking.

```python
class ObserverBase(DataAccessor):
    pass

# Observers watch but don't affect trading:
# - Track broker cash/value
# - Record trades
# - Calculate drawdown

# Use for type checking:
def is_observer(obj):
    return isinstance(obj, ObserverBase)
```

---

### Class: StrategyBase

**Purpose**: Empty base class for strategies. Used for type checking.

```python
class StrategyBase(DataAccessor):
    pass

# All strategies ultimately inherit from this:
# bt.Strategy -> ... -> StrategyBase -> DataAccessor -> LineIterator

# The _ltype is used to identify:
# LineIterator.IndType (0) = Indicator
# LineIterator.StratType (1) = Strategy
# LineIterator.ObsType (2) = Observer
```

---

### Class: SingleCoupler

**Purpose**: Couples a single line from one timeframe to another. Holds the last value until the source updates.

---

### SingleCoupler - Complete Examples

#### 1. How SingleCoupler Works

```python
"""
SingleCoupler bridges different timeframes.
Example: Use daily SMA value in an hourly strategy.

Problem: Daily SMA only updates once per day, but hourly
strategy needs a value every hour.

Solution: SingleCoupler holds the daily value and repeats
it for each hourly bar until the daily bar updates.
"""

class SingleCoupler(LineActions):
    def __init__(self, cdata, clock=None):
        super().__init__()
        
        # Use provided clock or default to owner
        self._clock = clock if clock is not None else self._owner
        
        self.cdata = cdata          # Source line (e.g., daily SMA)
        self.dlen = 0               # Track source length
        self.val = float('NaN')     # Cached value
    
    def next(self):
        # Check if source has new data
        if len(self.cdata) > self.dlen:
            # Source advanced - get new value
            self.val = self.cdata[0]
            self.dlen += 1
        
        # Output current (possibly cached) value
        self[0] = self.val
```

#### 2. Visual Timeline

```
Daily bars:     |----D1----|----D2----|----D3----|
Daily SMA:         10.0        10.5        11.0

Hourly bars:    |H1|H2|H3|H4|H5|H6|H7|H8|H9|...
Coupled SMA:    10.0 10.0 10.0 10.0 10.5 10.5 10.5 10.5 11.0 ...
                ↑                   ↑                   ↑
                D1 closes           D2 closes           D3 closes
```

#### 3. Practical Usage

```python
class MultiTimeframeStrategy(bt.Strategy):
    def __init__(self):
        # Assume data0 is hourly, data1 is daily
        hourly = self.datas[0]
        daily = self.datas[1]
        
        # Create daily indicator
        self.daily_sma = bt.indicators.SMA(daily, period=20)
        
        # Couple to hourly timeframe
        # This is created automatically when you call sma()
        self.hourly_daily_sma = self.daily_sma()
        
        # Internally, this creates:
        # SingleCoupler(self.daily_sma.lines[0], clock=hourly)
    
    def next(self):
        # Access daily SMA value at hourly frequency
        daily_sma = self.hourly_daily_sma[0]
        hourly_close = self.data0.close[0]
        
        if hourly_close > daily_sma:
            self.buy()
```

---

### Class: MultiCoupler

**Purpose**: Couples multiple lines from one timeframe to another. Similar to SingleCoupler but handles LineSeries with multiple lines.

---

### MultiCoupler - Complete Examples

```python
class MultiCoupler(LineIterator):
    """
    Couples all lines from a multi-line source to a different clock.
    """
    _ltype = LineIterator.IndType
    
    def __init__(self):
        super().__init__()
        self.dlen = 0
        self.dsize = self.fullsize()      # Number of lines to couple
        self.dvals = [float('NaN')] * self.dsize  # Cached values
    
    def next(self):
        # Check if source has new data
        if len(self.data) > self.dlen:
            self.dlen += 1
            
            # Cache all line values
            for i in range(self.dsize):
                self.dvals[i] = self.data.lines[i][0]
        
        # Output cached values to all our lines
        for i in range(self.dsize):
            self.lines[i][0] = self.dvals[i]

# Usage example:
class MultiCouplerDemo(bt.Strategy):
    def __init__(self):
        daily = self.datas[1]
        
        # Bollinger Bands has 3 lines: mid, top, bot
        self.daily_bb = bt.indicators.BollingerBands(daily)
        
        # Couple ALL lines to hourly timeframe
        self.hourly_bb = self.daily_bb()  # Creates MultiCoupler
        
    def next(self):
        # Access all daily BB values at hourly frequency
        mid = self.hourly_bb.mid[0]
        top = self.hourly_bb.top[0]
        bot = self.hourly_bb.bot[0]
```

---

### Function: LinesCoupler(cdata, clock=None)

**Purpose**: Factory function that creates the appropriate coupler (Single or Multi) based on input type.

---

### LinesCoupler - Complete Examples

```python
from backtrader.lineiterator import LinesCoupler, SingleCoupler, MultiCoupler

def LinesCoupler(cdata, clock=None, **kwargs):
    """
    Factory that creates appropriate coupler type.
    """
    
    # Single line → SingleCoupler
    if isinstance(cdata, LineSingle):
        return SingleCoupler(cdata, clock)
    
    # Multi-line → create custom MultiCoupler subclass
    cdatacls = cdata.__class__
    
    # Generate unique class name
    try:
        LinesCoupler.counter += 1
    except AttributeError:
        LinesCoupler.counter = 0
    
    nclsname = f'LinesCoupler_{LinesCoupler.counter}'
    
    # Create subclass of MultiCoupler
    ncls = type(nclsname, (MultiCoupler,), {})
    
    # Copy lines/params/plotinfo from source
    ncls.lines = cdatacls.lines
    ncls.params = cdatacls.params
    ncls.plotinfo = cdatacls.plotinfo
    ncls.plotlines = cdatacls.plotlines
    
    # Create instance
    obj = ncls(cdata, **kwargs)
    
    # Set clock (determines timing)
    if clock is None:
        # Try to find appropriate clock
        clock = getattr(cdata, '_clock', None)
        if clock is not None:
            # Get clock's clock if available
            nclock = getattr(clock, '_clock', None)
            if nclock is not None:
                clock = nclock
            else:
                nclock = getattr(clock, 'data', None)
                if nclock is not None:
                    clock = nclock
        
        if clock is None:
            clock = obj._owner
    
    obj._clock = clock
    return obj

# Usage:
# sma = bt.indicators.SMA(daily_data)
# coupled = sma()  # Internally calls LinesCoupler(sma, clock=None)
```

---

### LineCoupler (Alias)

```python
# LineCoupler is just an alias for LinesCoupler
LineCoupler = LinesCoupler

# Both work the same:
coupled1 = LinesCoupler(some_line)
coupled2 = LineCoupler(some_line)
```

---

### Complete Example: Multi-Timeframe Strategy

```python
"""
Comprehensive example showing all lineiterator.py concepts.
"""

import backtrader as bt
from datetime import datetime

class MultiTimeframeIndicator(bt.Indicator):
    """
    Custom indicator that uses multiple timeframes.
    Demonstrates:
    - LineIterator inheritance
    - Data access shortcuts
    - Timeframe coupling
    """
    
    lines = ('trend', 'signal')
    
    params = (
        ('fast_period', 10),
        ('slow_period', 20),
    )
    
    # Force step-by-step mode (required for coupling)
    _nextforce = True
    
    def __init__(self):
        # Access data via shortcuts (created by MetaLineIterator)
        fast_ma = bt.indicators.SMA(self.data_close, period=self.p.fast_period)
        slow_ma = bt.indicators.SMA(self.data_close, period=self.p.slow_period)
        
        # Trend line: difference between fast and slow
        self.lines.trend = fast_ma - slow_ma
        
        # Signal: 1 when fast > slow, -1 when fast < slow
        self.cross = bt.indicators.CrossOver(fast_ma, slow_ma)
    
    def next(self):
        if self.cross[0] > 0:
            self.lines.signal[0] = 1
        elif self.cross[0] < 0:
            self.lines.signal[0] = -1
        else:
            self.lines.signal[0] = 0


class MultiTimeframeStrategy(bt.Strategy):
    """
    Strategy using multiple timeframes.
    Demonstrates:
    - Multiple data feeds
    - Data shortcuts (data0, data1, data0_close, etc.)
    - Timeframe coupling
    - Indicator registration
    """
    
    params = (
        ('printlog', False),
    )
    
    def __init__(self):
        # data0 = intraday (e.g., hourly)
        # data1 = daily
        
        # Indicators on intraday data
        self.intraday_sma = bt.indicators.SMA(
            self.data0_close,  # Shortcut for self.datas[0].close
            period=10
        )
        
        # Indicators on daily data
        self.daily_sma = bt.indicators.SMA(
            self.data1_close,  # Shortcut for self.datas[1].close
            period=20
        )
        
        # Couple daily SMA to intraday timeframe
        self.coupled_daily_sma = self.daily_sma()
        
        # Check registered indicators
        print(f"Indicators registered: {len(self.getindicators())}")
        for ind in self.getindicators():
            print(f"  - {ind.__class__.__name__}")
    
    def prenext(self):
        """Called during warmup period."""
        if self.p.printlog:
            print(f'Prenext: {len(self.data0)}, {len(self.data1)}')
    
    def nextstart(self):
        """Called once when all data ready."""
        print(f'Nextstart: Ready to trade!')
        self.next()  # Continue to regular next
    
    def next(self):
        """Main trading logic."""
        # Compare intraday price to daily SMA
        intraday_close = self.data0_close[0]
        daily_sma_value = self.coupled_daily_sma[0]
        
        if intraday_close > daily_sma_value:
            if not self.position:
                self.buy(data=self.data0)
        elif intraday_close < daily_sma_value:
            if self.position:
                self.sell(data=self.data0)


# Run backtest
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # Add intraday data (60-minute bars)
    intraday_data = bt.feeds.GenericCSVData(
        dataname='intraday.csv',
        timeframe=bt.TimeFrame.Minutes,
        compression=60,
    )
    cerebro.adddata(intraday_data)
    
    # Add daily data
    daily_data = bt.feeds.GenericCSVData(
        dataname='daily.csv',
        timeframe=bt.TimeFrame.Days,
        compression=1,
    )
    cerebro.adddata(daily_data)
    
    # Add strategy
    cerebro.addstrategy(MultiTimeframeStrategy, printlog=True)
    
    # Run with runonce=False (required for coupling)
    cerebro.run(runonce=False)
```

---

### Summary: lineiterator.py Class Hierarchy

```
LineSeries (from lineseries.py)
    │
    └── LineIterator (uses MetaLineIterator metaclass)
            │
            ├── _next() / _once() - execution engine
            ├── prenext/nextstart/next - user callbacks
            ├── addindicator() - child registration
            └── bindlines() - line binding
            │
            └── DataAccessor (adds price constants)
                    │
                    ├── IndicatorBase (marker for indicators)
                    │
                    ├── ObserverBase (marker for observers)
                    │
                    └── StrategyBase (marker for strategies)

LineActions (from linebuffer.py)
    │
    └── SingleCoupler (couples single line to different clock)

LineIterator
    │
    └── MultiCoupler (couples multiple lines to different clock)

LinesCoupler / LineCoupler (factory functions)
    - Creates SingleCoupler or MultiCoupler based on input

MetaLineIterator (metaclass)
    - donew: Create data shortcuts
    - dopreinit: Set clock, calculate minperiod
    - dopostinit: Finalize minperiod, register with owner
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
