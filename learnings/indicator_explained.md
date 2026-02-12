# Backtrader Indicator System Explained

This document provides a comprehensive walkthrough of `backtrader/indicator.py`, explaining each class with detailed examples.

---

## Overview

The `indicator.py` file defines the base classes for all indicators in Backtrader:

| Class | Purpose |
|-------|---------|
| `MetaIndicator` | Metaclass that handles caching and automatic method wiring |
| `Indicator` | Base class for all indicators |
| `MtLinePlotterIndicator` | Metaclass for line plotting indicators |
| `LinePlotterIndicator` | Special indicator for plotting arbitrary lines |

---

## Class: MetaIndicator

**Purpose**: Metaclass for `Indicator` that provides:
1. **Indicator Registry**: Automatically registers indicator classes by name
2. **Instance Caching**: Optional caching to reuse identical indicator instances
3. **Automatic Method Wiring**: Auto-generates `once()` from `next()` if not overridden

**Inherits from**: `IndicatorBase.__class__` (which is `MetaLineIterator`)

---

### MetaIndicator - Complete Examples

#### 1. Class Attributes

```python
class MetaIndicator(IndicatorBase.__class__):
    _refname = '_indcol'    # Name of the registry attribute
    _indcol = dict()        # Registry: {'SMA': <class SMA>, 'EMA': <class EMA>, ...}
    
    _icache = dict()        # Instance cache: {(cls, args, kwargs): instance}
    _icacheuse = False      # Whether caching is enabled (default: off)
```

#### 2. The Indicator Registry

```python
"""
When you define an indicator, it's automatically registered in _indcol.
"""

class SMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        self.lines.sma = bt.indicators.SimpleMovingAverage(
            self.data, period=self.p.period
        )

# After class creation, MetaIndicator.__init__ registers it:
# MetaIndicator._indcol['SMA'] = <class SMA>

# You can access all registered indicators:
print(MetaIndicator._indcol.keys())
# dict_keys(['SMA', 'EMA', 'RSI', 'MACD', ...])

# Look up an indicator by name:
indicator_class = MetaIndicator._indcol['SMA']
```

#### 3. The `__init__` Method - Class Registration

```python
def __init__(cls, name, bases, dct):
    """
    Called when a new Indicator class is defined.
    Registers the class and wires once() if needed.
    """
    # Call parent metaclass __init__
    super(MetaIndicator, cls).__init__(name, bases, dct)
    
    # Register in collection (unless aliased or private)
    if not cls.aliased and \
       name != 'Indicator' and not name.startswith('_'):
        refattr = getattr(cls, cls._refname)  # _indcol dict
        refattr[name] = cls
    
    # Check if next() is overridden but once() is not
    next_over = cls.next != IndicatorBase.next
    once_over = cls.once != IndicatorBase.once
    
    if next_over and not once_over:
        # Auto-generate once() from next()
        cls.once = cls.once_via_next
        cls.preonce = cls.preonce_via_prenext
        cls.oncestart = cls.oncestart_via_nextstart

# What this means for you:
# If you only override next(), the metaclass automatically creates
# once() that calls next() for each bar. This is slightly slower
# than a native once() but works correctly.
```

#### 4. Aliased Indicators (Skip Registration)

```python
class MyIndicator(bt.Indicator):
    """Primary indicator class - gets registered."""
    lines = ('output',)
    
    def next(self):
        self.lines.output[0] = self.data.close[0] * 2

# Create an alias that points to the same class
# but doesn't get registered separately
class MyInd(MyIndicator):
    """Alias - shorter name for same indicator."""
    aliased = True  # Prevents duplicate registration

# Only 'MyIndicator' is in the registry, not 'MyInd'
# Both names work:
ind1 = MyIndicator(data)
ind2 = MyInd(data)  # Same behavior
```

#### 5. Instance Caching

```python
"""
Instance caching allows reusing identical indicators.
DISABLED by default (since 2016-08-17) due to minperiod issues.
"""

# Enable caching (use with caution!)
bt.Indicator.usecache(True)

class MyStrategy(bt.Strategy):
    def __init__(self):
        # With caching enabled, identical indicators return same instance
        sma1 = bt.indicators.SMA(self.data, period=20)
        sma2 = bt.indicators.SMA(self.data, period=20)
        
        # If caching enabled:
        print(sma1 is sma2)  # True - same instance!
        
        # If caching disabled (default):
        print(sma1 is sma2)  # False - different instances

# Disable caching
bt.Indicator.usecache(False)

# Clear the cache
bt.Indicator.cleancache()
```

#### 6. The `__call__` Method - Instance Creation with Caching

```python
def __call__(cls, *args, **kwargs):
    """
    Called when creating an indicator instance: SMA(data, period=20)
    """
    # If caching disabled, just create normally
    if not cls._icacheuse:
        return super(MetaIndicator, cls).__call__(*args, **kwargs)
    
    # Create cache key from class and arguments
    ckey = (cls, tuple(args), tuple(kwargs.items()))
    
    try:
        # Try to return cached instance
        return cls._icache[ckey]
    except TypeError:
        # Arguments not hashable (e.g., contain lists)
        return super(MetaIndicator, cls).__call__(*args, **kwargs)
    except KeyError:
        pass  # Not in cache, create new
    
    # Create new instance and cache it
    _obj = super(MetaIndicator, cls).__call__(*args, **kwargs)
    return cls._icache.setdefault(ckey, _obj)
```

#### 7. Automatic once() Wiring

```python
"""
The metaclass automatically creates once() if you only define next().
"""

class ManualSMA(bt.Indicator):
    """Only defines next() - once() is auto-generated."""
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        self.addminperiod(self.p.period)
    
    def next(self):
        # Called for each bar
        datasum = sum(self.data.get(size=self.p.period))
        self.lines.sma[0] = datasum / self.p.period
    
    # No once() defined!
    # MetaIndicator automatically sets:
    # cls.once = cls.once_via_next
    # cls.preonce = cls.preonce_via_prenext
    # cls.oncestart = cls.oncestart_via_nextstart


class OptimizedSMA(bt.Indicator):
    """Defines both next() and once() - uses native once()."""
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        self.addminperiod(self.p.period)
    
    def next(self):
        datasum = sum(self.data.get(size=self.p.period))
        self.lines.sma[0] = datasum / self.p.period
    
    def once(self, start, end):
        # Optimized batch processing
        src = self.data.array
        dst = self.lines.sma.array
        period = self.p.period
        
        for i in range(start, end):
            dst[i] = sum(src[i-period+1:i+1]) / period

# Performance comparison:
# - ManualSMA: once_via_next calls next() for each bar (slower)
# - OptimizedSMA: native once() with array access (faster)
```

---

## Class: Indicator

**Purpose**: The base class that all indicators inherit from. Provides:
1. Identification as indicator type (`_ltype = IndType`)
2. Support for different data lengths (timeframes)
3. Fallback methods to simulate `once()` from `next()`

**Inherits from**: `IndicatorBase` (via `MetaIndicator` metaclass)

---

### Indicator - Complete Examples

#### 1. Class Attributes

```python
class Indicator(with_metaclass(MetaIndicator, IndicatorBase)):
    _ltype = LineIterator.IndType  # Identifies as indicator (value: 0)
    csv = False  # Don't export to CSV by default
```

#### 2. The `advance()` Method

```python
def advance(self, size=1):
    """
    Move the index pointer forward.
    Handles different data lengths (multi-timeframe).
    """
    # Only advance if we're behind the clock
    if len(self) < len(self._clock):
        self.lines.advance(size=size)

# Why this matters:
# In multi-timeframe scenarios, the indicator might be on
# a slower timeframe than its clock. This prevents advancing
# past the available data.

# Example: Daily indicator on hourly clock
# Clock (hourly): has 100 bars
# Indicator (daily): only has 10 bars
# Without this check, indicator would try to advance beyond its data
```

#### 3. The `once_via_next()` Method

```python
def once_via_next(self, start, end):
    """
    Simulate once() by calling next() for each bar.
    Auto-assigned when only next() is overridden.
    """
    for i in range(start, end):
        # Advance all data sources
        for data in self.datas:
            data.advance()
        
        # Advance all child indicators
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator.advance()
        
        # Advance self and call next()
        self.advance()
        self.next()

# This method is slower than a native once() because:
# 1. It has loop overhead
# 2. It calls advance() for every data/indicator each bar
# 3. next() uses line[0] indexing instead of array[i]
#
# But it's convenient - you only need to write next()!
```

#### 4. The `preonce_via_prenext()` Method

```python
def preonce_via_prenext(self, start, end):
    """
    Simulate preonce() by calling prenext() for each bar.
    Used during warmup period.
    """
    for i in range(start, end):
        for data in self.datas:
            data.advance()
        
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator.advance()
        
        self.advance()
        self.prenext()  # Warmup method
```

#### 5. The `oncestart_via_nextstart()` Method

```python
def oncestart_via_nextstart(self, start, end):
    """
    Simulate oncestart() by calling nextstart() for each bar.
    Called once when minperiod is first satisfied.
    """
    for i in range(start, end):
        for data in self.datas:
            data.advance()
        
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator.advance()
        
        self.advance()
        self.nextstart()  # First valid bar method
```

#### 6. Complete Indicator Example

```python
import backtrader as bt

class MyRSI(bt.Indicator):
    """
    Custom RSI implementation demonstrating all methods.
    """
    
    lines = ('rsi', 'overbought', 'oversold')
    
    params = (
        ('period', 14),
        ('upperband', 70.0),
        ('lowerband', 30.0),
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='My RSI',
    )
    
    plotlines = dict(
        overbought=dict(_plotskip=True),  # Don't plot this line
        oversold=dict(_plotskip=True),
    )
    
    def __init__(self):
        # Calculate price changes
        self.change = self.data.close - self.data.close(-1)
        
        # Separate gains and losses
        self.gain = bt.Max(self.change, 0.0)
        self.loss = bt.Max(-self.change, 0.0)
        
        # Average gains and losses
        self.avg_gain = bt.indicators.SmoothedMovingAverage(
            self.gain, period=self.p.period
        )
        self.avg_loss = bt.indicators.SmoothedMovingAverage(
            self.loss, period=self.p.period
        )
    
    def prenext(self):
        """Called during warmup - output NaN."""
        self.lines.rsi[0] = float('nan')
        self.lines.overbought[0] = self.p.upperband
        self.lines.oversold[0] = self.p.lowerband
    
    def nextstart(self):
        """First valid bar - same as next()."""
        self.next()
    
    def next(self):
        """Calculate RSI for each bar."""
        avg_gain = self.avg_gain[0]
        avg_loss = self.avg_loss[0]
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        
        self.lines.rsi[0] = rsi
        self.lines.overbought[0] = self.p.upperband
        self.lines.oversold[0] = self.p.lowerband


# Usage in strategy:
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.rsi = MyRSI(self.data, period=14)
    
    def next(self):
        if self.rsi.rsi[0] < 30:  # Oversold
            self.buy()
        elif self.rsi.rsi[0] > 70:  # Overbought
            self.sell()
```

#### 7. Optimized Indicator with Native once()

```python
class OptimizedRSI(bt.Indicator):
    """
    RSI with optimized once() for faster backtesting.
    """
    
    lines = ('rsi',)
    params = (('period', 14),)
    
    def __init__(self):
        self.change = self.data.close - self.data.close(-1)
        self.addminperiod(self.p.period + 1)
    
    def next(self):
        """Step-by-step calculation."""
        changes = list(self.change.get(size=self.p.period))
        gains = [max(c, 0) for c in changes]
        losses = [max(-c, 0) for c in changes]
        
        avg_gain = sum(gains) / self.p.period
        avg_loss = sum(losses) / self.p.period
        
        if avg_loss == 0:
            self.lines.rsi[0] = 100.0
        else:
            rs = avg_gain / avg_loss
            self.lines.rsi[0] = 100.0 - (100.0 / (1.0 + rs))
    
    def once(self, start, end):
        """Batch calculation - much faster!"""
        close = self.data.close.array
        rsi_arr = self.lines.rsi.array
        period = self.p.period
        
        for i in range(start, end):
            # Calculate changes for this window
            gains = 0.0
            losses = 0.0
            
            for j in range(period):
                idx = i - j
                change = close[idx] - close[idx - 1]
                if change > 0:
                    gains += change
                else:
                    losses -= change
            
            avg_gain = gains / period
            avg_loss = losses / period
            
            if avg_loss == 0:
                rsi_arr[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_arr[i] = 100.0 - (100.0 / (1.0 + rs))
```

#### 8. Declarative vs Imperative Indicators

```python
"""
Backtrader supports two indicator styles:
1. Declarative: Operations in __init__ create line graphs
2. Imperative: Calculations in next() set values directly
"""

# Style 1: Declarative (preferred for simple indicators)
class DeclarativeSMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        # This creates a line graph - no next() needed!
        self.lines.sma = bt.indicators.Average(
            self.data.close, period=self.p.period
        )
    
    # No next() or once() - handled by the line graph


# Style 2: Imperative (for complex logic)
class ImperativeSMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        self.addminperiod(self.p.period)
    
    def next(self):
        # Manual calculation each bar
        total = sum(self.data.close.get(size=self.p.period))
        self.lines.sma[0] = total / self.p.period


# Style 3: Hybrid (declarative setup, imperative logic)
class HybridIndicator(bt.Indicator):
    lines = ('signal',)
    params = (('fast', 10), ('slow', 20))
    
    def __init__(self):
        # Declarative: create sub-indicators
        self.fast_ma = bt.indicators.SMA(period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow)
    
    def next(self):
        # Imperative: custom logic using sub-indicators
        if self.fast_ma[0] > self.slow_ma[0]:
            self.lines.signal[0] = 1
        else:
            self.lines.signal[0] = -1
```

---

## Class: MtLinePlotterIndicator

**Purpose**: Metaclass for `LinePlotterIndicator`. Dynamically creates lines and plotlines based on the `name` parameter.

**Inherits from**: `Indicator.__class__` (which is `MetaIndicator`)

---

### MtLinePlotterIndicator - Complete Examples

#### 1. The `donew()` Method

```python
class MtLinePlotterIndicator(Indicator.__class__):
    def donew(cls, *args, **kwargs):
        """
        Create a single-line indicator with dynamic name.
        """
        # Extract the line name from kwargs
        lname = kwargs.pop('name')
        name = cls.__name__
        
        # Dynamically create lines tuple with the given name
        lines = getattr(cls, 'lines', Lines)
        cls.lines = lines._derive(name, (lname,), 0, [])
        
        # Dynamically create plotlines with the given name
        plotlines = AutoInfoClass
        newplotlines = dict()
        newplotlines.setdefault(lname, dict())
        cls.plotlines = plotlines._derive(name, newplotlines, [], recurse=True)
        
        # Call parent donew
        _obj, args, kwargs = \
            super(MtLinePlotterIndicator, cls).donew(*args, **kwargs)
        
        # Set up the binding
        _obj.owner = _obj.data.owner._clock
        _obj.data.lines[0].addbinding(_obj.lines[0])
        
        return _obj, args, kwargs
```

#### 2. Understanding the Line Binding

```python
"""
LinePlotterIndicator creates a binding from input to output.
This allows plotting a line from one object on another's subplot.
"""

# The key line:
# _obj.data.lines[0].addbinding(_obj.lines[0])

# This means:
# When input data updates -> our output line also updates
# The indicator acts as a "pass-through" for plotting purposes
```

---

## Class: LinePlotterIndicator

**Purpose**: A special indicator for plotting lines that belong to other objects (like strategies or other indicators) in a separate subplot.

**Inherits from**: `Indicator` (via `MtLinePlotterIndicator` metaclass)

---

### LinePlotterIndicator - Complete Examples

#### 1. Basic Usage

```python
class LinePlotterIndicator(with_metaclass(MtLinePlotterIndicator, Indicator)):
    """
    Empty class - all work done by metaclass.
    """
    pass

# Usage:
# LinePlotterIndicator(some_line, name='my_line')
# Creates an indicator that plots 'some_line' with label 'my_line'
```

#### 2. Practical Example: Plotting Strategy Lines

```python
class MyStrategy(bt.Strategy):
    """
    Strategy that creates lines and plots them.
    """
    
    lines = ('buy_signal', 'sell_signal')
    
    def __init__(self):
        self.sma_fast = bt.indicators.SMA(period=10)
        self.sma_slow = bt.indicators.SMA(period=30)
        
        # Create plot indicators for our strategy lines
        # This puts them in a visible subplot
        bt.LinePlotterIndicator(
            self.lines.buy_signal, 
            name='Buy Signal'
        )
        bt.LinePlotterIndicator(
            self.lines.sell_signal,
            name='Sell Signal'
        )
    
    def next(self):
        # Set signal values
        if self.sma_fast[0] > self.sma_slow[0]:
            self.lines.buy_signal[0] = 1
            self.lines.sell_signal[0] = 0
        else:
            self.lines.buy_signal[0] = 0
            self.lines.sell_signal[0] = 1
```

#### 3. Plotting Computed Values

```python
class VolatilityStrategy(bt.Strategy):
    """
    Plot custom computed values as separate indicator.
    """
    
    lines = ('volatility',)
    
    def __init__(self):
        # Make our volatility line visible
        bt.LinePlotterIndicator(
            self.lines.volatility,
            name='Custom Volatility'
        )
    
    def next(self):
        # Calculate custom volatility
        if len(self) >= 20:
            closes = list(self.data.close.get(size=20))
            mean = sum(closes) / 20
            variance = sum((c - mean) ** 2 for c in closes) / 20
            self.lines.volatility[0] = variance ** 0.5
        else:
            self.lines.volatility[0] = 0
```

---

## Complete Example: Building a Custom Indicator

```python
import backtrader as bt
import math

class KeltnerChannel(bt.Indicator):
    """
    Complete custom indicator example.
    
    Keltner Channel:
    - Middle: EMA of close
    - Upper: Middle + (multiplier * ATR)
    - Lower: Middle - (multiplier * ATR)
    """
    
    # Define output lines
    lines = ('mid', 'top', 'bot')
    
    # Define parameters
    params = (
        ('period', 20),
        ('devfactor', 2.0),
        ('movav', bt.indicators.EMA),  # Configurable MA type
    )
    
    # Plotting configuration
    plotinfo = dict(
        subplot=False,  # Plot on main chart
        plotname='Keltner Channel',
    )
    
    plotlines = dict(
        mid=dict(ls='--', color='blue'),
        top=dict(color='green'),
        bot=dict(color='red'),
    )
    
    def __init__(self):
        # Calculate middle line (EMA)
        self.lines.mid = self.p.movav(self.data.close, period=self.p.period)
        
        # Calculate ATR
        self.atr = bt.indicators.ATR(self.data, period=self.p.period)
        
        # Calculate bands
        self.lines.top = self.lines.mid + (self.atr * self.p.devfactor)
        self.lines.bot = self.lines.mid - (self.atr * self.p.devfactor)
    
    # No next() needed - fully declarative!


class KeltnerStrategy(bt.Strategy):
    """
    Strategy using the Keltner Channel indicator.
    """
    
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )
    
    def __init__(self):
        self.kc = KeltnerChannel(
            self.data,
            period=self.p.period,
            devfactor=self.p.devfactor
        )
        
        # Track position
        self.order = None
    
    def next(self):
        if self.order:
            return
        
        close = self.data.close[0]
        
        if not self.position:
            # Buy when price touches lower band
            if close <= self.kc.bot[0]:
                self.order = self.buy()
        else:
            # Sell when price touches upper band
            if close >= self.kc.top[0]:
                self.order = self.sell()
    
    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Rejected]:
            self.order = None


# Run backtest
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # Add data
    data = bt.feeds.GenericCSVData(
        dataname='data.csv',
        dtformat='%Y-%m-%d',
    )
    cerebro.adddata(data)
    
    # Add strategy
    cerebro.addstrategy(KeltnerStrategy)
    
    # Run
    cerebro.run()
    cerebro.plot()
```

---

## Summary: Indicator Class Hierarchy

```
IndicatorBase (from lineiterator.py)
    │
    └── Indicator (uses MetaIndicator metaclass)
            │
            ├── _ltype = IndType (identifies as indicator)
            ├── csv = False (no CSV export by default)
            │
            ├── advance() - handle multi-timeframe
            ├── once_via_next() - simulate once from next
            ├── preonce_via_prenext() - simulate preonce from prenext
            └── oncestart_via_nextstart() - simulate oncestart from nextstart
            │
            └── LinePlotterIndicator (uses MtLinePlotterIndicator metaclass)
                    - For plotting lines from other objects

MetaIndicator (metaclass)
    │
    ├── _indcol - indicator registry
    ├── _icache - instance cache
    ├── __call__() - instance creation with optional caching
    ├── __init__() - class registration and once() wiring
    ├── cleancache() - clear instance cache
    └── usecache() - enable/disable caching

MtLinePlotterIndicator (metaclass)
    │
    └── donew() - dynamic line/plotline creation
```

---

## Key Takeaways

1. **Declarative is preferred**: Define line operations in `__init__()` when possible
2. **Automatic once() wiring**: If you only write `next()`, `once()` is auto-generated
3. **Caching is disabled by default**: Due to minperiod propagation issues
4. **Indicators auto-register**: Accessible via `MetaIndicator._indcol`
5. **LinePlotterIndicator**: Use for plotting custom lines in subplots
6. **Multi-timeframe support**: `advance()` handles different data lengths
