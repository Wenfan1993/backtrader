# Backtrader Architecture Overview

## Executive Summary

Backtrader is a sophisticated Python backtesting framework built on a powerful **metaprogramming foundation**. The architecture centers around **Lines** - time-series data containers that flow through the system, processed by a hierarchy of iterators including data feeds, indicators, strategies, and observers.

---

## 1. Core Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CEREBRO (Orchestrator)                           │
│   - Registers strategies, data feeds, brokers, observers, analyzers         │
│   - Controls execution mode (runonce vs next, preload vs live)              │
│   - Manages multiprocessing optimization                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
       ▼                               ▼                               ▼
┌──────────────┐              ┌────────────────┐              ┌──────────────┐
│  DATA FEEDS  │              │    STRATEGY    │              │    BROKER    │
│  - Lines     │──────────────│  - Lines       │──────────────│  - Orders    │
│  - OHLCV     │              │  - Indicators  │              │  - Trades    │
│  - DateTime  │              │  - Observers   │              │  - Positions │
└──────────────┘              │  - Analyzers   │              │  - Cash      │
       │                      └────────────────┘              └──────────────┘
       │                               │
       └───────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │       LINE ITERATOR         │
        │  - _next() / _once()        │
        │  - prenext/nextstart/next   │
        │  - Minperiod management     │
        └─────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │        LINE BUFFER          │
        │  - Circular array storage   │
        │  - Index 0 = current bar    │
        │  - Bindings between lines   │
        └─────────────────────────────┘
```

---

## 2. The Metaclass Foundation

The framework uses a sophisticated metaclass hierarchy that provides automatic parameter handling, object lifecycle management, and component registration.

### 2.1 MetaBase - The Object Creation Chain

**File:** `backtrader/metabase.py:66-90`

```python
class MetaBase(type):
    def doprenew(cls, *args, **kwargs):
        return cls, args, kwargs

    def donew(cls, *args, **kwargs):
        _obj = cls.__new__(cls, *args, **kwargs)
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        return _obj, args, kwargs

    def doinit(cls, _obj, *args, **kwargs):
        _obj.__init__(*args, **kwargs)
        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        return _obj, args, kwargs

    def __call__(cls, *args, **kwargs):
        cls, args, kwargs = cls.doprenew(*args, **kwargs)
        _obj, args, kwargs = cls.donew(*args, **kwargs)
        _obj, args, kwargs = cls.dopreinit(_obj, *args, **kwargs)
        _obj, args, kwargs = cls.doinit(_obj, *args, **kwargs)
        _obj, args, kwargs = cls.dopostinit(_obj, *args, **kwargs)
        return _obj
```

**Design Pattern:** This implements a **Template Method** pattern at the metaclass level, allowing subclasses to hook into any stage of object creation without modifying the core flow.

### 2.2 MetaParams - Automatic Parameter Inheritance

**File:** `backtrader/metabase.py:203-294`

```python
class MetaParams(MetaBase):
    def __new__(meta, name, bases, dct):
        # Extract params from class definition
        newparams = dct.pop('params', ())
        cls = super(MetaParams, meta).__new__(meta, name, bases, dct)

        # Get parent params and merge
        params = getattr(cls, 'params', AutoInfoClass)
        morebasesparams = [x.params for x in bases[1:] if hasattr(x, 'params')]

        # Create derived params class
        cls.params = params._derive(name, newparams, morebasesparams)
        return cls

    def donew(cls, *args, **kwargs):
        # Create params instance with user-provided or default values
        params = cls.params()
        for pname, pdef in cls.params._getitems():
            setattr(params, pname, kwargs.pop(pname, pdef))

        _obj, args, kwargs = super(MetaParams, cls).donew(*args, **kwargs)
        _obj.params = params
        _obj.p = params  # shorter alias
        return _obj, args, kwargs
```

**Key Design:** Parameters defined as tuples are automatically:
- Inherited from parent classes
- Merged with multiple inheritance
- Instantiated with defaults or user overrides
- Accessible via `self.params` or `self.p`

### 2.3 AutoInfoClass - Dynamic Class Derivation

**File:** `backtrader/metabase.py:93-201`

This creates unique subclasses at runtime to hold configuration, avoiding name collisions in multiprocessing scenarios.

### 2.4 Owner Discovery via Stack Frame Inspection

**File:** `backtrader/metabase.py:42-63`

```python
def findowner(owned, cls, startlevel=2, skip=None):
    for framelevel in itertools.count(startlevel):
        try:
            frame = sys._getframe(framelevel)
        except ValueError:
            break

        self_ = frame.f_locals.get('self', None)
        if skip is not self_:
            if self_ is not owned and isinstance(self_, cls):
                return self_
    return None
```

**Design Pattern:** This enables **implicit dependency injection** - when you create an indicator inside a strategy's `__init__`, the indicator automatically discovers its owner without explicit passing.

---

## 3. The Lines System - Core Data Structure

### 3.1 LineBuffer - The Foundation

**File:** `backtrader/linebuffer.py:50-330`

```python
class LineBuffer(LineSingle):
    '''
    Index 0 = current bar (active for input/output)
    Positive indices = past values (left)
    Negative indices = future values (right, if extended)
    '''
    UnBounded, QBuffer = (0, 1)

    def __init__(self):
        self.lines = [self]
        self.mode = self.UnBounded
        self.bindings = list()
        self.reset()

    def reset(self):
        if self.mode == self.QBuffer:
            # Memory-efficient circular buffer
            self.array = collections.deque(maxlen=self.maxlen + self.extrasize)
        else:
            # Unbounded array for full history
            self.array = array.array(str('d'))

    def __getitem__(self, ago):
        return self.array[self.idx + ago]  # idx + ago gives relative access

    def __setitem__(self, ago, value):
        self.array[self.idx + ago] = value
        for binding in self.bindings:
            binding[ago] = value  # Propagate to bound lines
```

**Key Design Principles:**

1. **Zero-Indexed Current Bar:** `self.data.close[0]` always returns the current close price
2. **Positive for Past:** `self.data.close[1]` returns yesterday's close
3. **Bindings for Data Flow:** When you assign to one line, bound lines update automatically
4. **Memory Modes:**
   - `UnBounded`: Keep all history (for plotting/analysis)
   - `QBuffer`: Circular buffer keeping only `minperiod` bars (memory saving)

### 3.2 Line Operations - Mathematical DSL

**File:** `backtrader/linebuffer.py:705-830`

```python
class LinesOperation(LineActions):
    '''Holds binary operations like: close - open, sma * 2'''

    def __init__(self, a, b, operation, r=False):
        self.operation = operation
        self.a = a  # always a LineBuffer
        self.b = b  # can be LineBuffer or scalar
        self.bline = isinstance(b, LineBuffer)

    def next(self):
        if self.bline:
            self[0] = self.operation(self.a[0], self.b[0])
        else:
            self[0] = self.operation(self.a[0], self.b)

    def once(self, start, end):
        # Vectorized operation for runonce mode
        for i in range(start, end):
            dst[i] = op(srca[i], srcb[i])
```

This enables the elegant syntax:
```python
# This creates a LinesOperation under the hood
spread = self.data.high - self.data.low
```

---

## 4. LineIterator - The Execution Engine

**File:** `backtrader/lineiterator.py:148-377`

### 4.1 The Iteration Lifecycle

```python
class LineIterator(LineSeries):
    def _next(self):
        clock_len = self._clk_update()  # Advance position

        # Process all child indicators first
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator._next()

        self._notify()  # Handle notifications

        # Call appropriate lifecycle method
        if clock_len > self._minperiod:
            self.next()
        elif clock_len == self._minperiod:
            self.nextstart()  # Called exactly once
        elif clock_len:
            self.prenext()

    def _once(self):
        # Vectorized mode - process all bars at once
        self.forward(size=self._clock.buflen())

        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator._once()

        self.home()  # Reset to beginning

        # Process in phases
        self.preonce(0, self._minperiod - 1)
        self.oncestart(self._minperiod - 1, self._minperiod)
        self.once(self._minperiod, self.buflen())
```

### 4.2 Minperiod - Automatic Warm-up Calculation

The framework automatically calculates how many bars are needed before indicators can produce valid values:

```python
# In MetaLineIterator.dopreinit
_obj._minperiod = max([x._minperiod for x in _obj.datas] or [_obj._minperiod])

# In MetaLineIterator.dopostinit
_obj._minperiod = max([x._minperiod for x in _obj.lines])
```

**Example:**
- SMA(20) needs 20 bars before producing a value
- EMA(20) of SMA(20) needs ~40 bars total
- The framework tracks this automatically

### 4.3 Type Classification

```python
class LineIterator:
    # Type constants for routing
    IndType = 0   # Indicators
    ObsType = 1   # Observers
    StratType = 2 # Strategies
```

---

## 5. Strategy - User Trading Logic

**File:** `backtrader/strategy.py:107-400`

### 5.1 Strategy Lifecycle

```python
class Strategy(StrategyBase):
    _ltype = LineIterator.StratType
    lines = ('datetime',)  # Strategy tracks latest datetime

    def _start(self):
        self._periodset()  # Calculate minperiods per data
        for analyzer in self.analyzers:
            analyzer._start()

    def prenext(self):
        '''Called during warm-up period'''
        pass

    def nextstart(self):
        '''Called once when all data is ready'''
        self.next()

    def next(self):
        '''Called for each bar - implement your logic here'''
        pass

    def notify_order(self, order):
        '''Called when order status changes'''
        pass

    def notify_trade(self, trade):
        '''Called when trade opens/closes'''
        pass
```

### 5.2 MetaStrategy - Automatic Wiring

**File:** `backtrader/strategy.py:43-105`

```python
class MetaStrategy(StrategyBase.__class__):
    def donew(cls, *args, **kwargs):
        _obj, args, kwargs = super().donew(*args, **kwargs)
        # Auto-discover Cerebro from call stack
        _obj.env = _obj.cerebro = cerebro = findowner(_obj, bt.Cerebro)
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        _obj.broker = _obj.env.broker
        _obj._sizer = bt.sizers.FixedSize()
        _obj._orders = list()
        _obj.stats = _obj.observers = ItemCollection()
        _obj.analyzers = ItemCollection()
        return _obj, args, kwargs
```

---

## 6. Cerebro - The Orchestrator

**File:** `backtrader/cerebro.py:60-294`

### 6.1 Configuration Parameters

```python
class Cerebro(MetaParams):
    params = (
        ('preload', True),      # Load all data before running
        ('runonce', True),      # Use vectorized indicator calculation
        ('live', False),        # Live trading mode
        ('maxcpus', None),      # CPUs for optimization
        ('stdstats', True),     # Add default observers
        ('exactbars', False),   # Memory saving mode
        ('optdatas', True),     # Shared data in optimization
        ('optreturn', True),    # Lightweight optimization results
        ('cheat_on_open', False), # Execute orders at open
    )
```

### 6.2 Execution Flow

```
cerebro.run()
    │
    ├─► _runonce() if runonce=True and not live
    │       │
    │       ├─► Preload all data feeds
    │       ├─► All indicators._once() [vectorized]
    │       └─► Loop: strategy._oncepost() for each bar
    │
    └─► _runnext() if runonce=False or live
            │
            └─► Loop: for each bar
                    ├─► data._load() [get next bar]
                    ├─► All indicators._next()
                    ├─► broker.next() [process orders]
                    └─► strategy._next()
```

### 6.3 Two Execution Modes

| Mode | `runonce=True` | `runonce=False` |
|------|----------------|-----------------|
| **Speed** | Fast (vectorized) | Slower (event-driven) |
| **Indicators** | Use `once()` method | Use `next()` method |
| **Use Case** | Backtesting | Live trading, complex logic |
| **Memory** | Higher (preloaded) | Lower (streaming) |

---

## 7. Broker System

**File:** `backtrader/brokers/bbroker.py:36-300`

### 7.1 BackBroker - The Simulation Engine

```python
class BackBroker(BrokerBase):
    params = (
        ('cash', 10000.0),
        ('checksubmit', True),  # Validate orders before submission
        ('slip_perc', 0.0),     # Slippage percentage
        ('slip_fixed', 0.0),    # Fixed slippage
        ('coc', False),         # Cheat-on-close
        ('coo', False),         # Cheat-on-open
        ('shortcash', True),    # Add cash on shorts
    )

    def init(self):
        self.startingcash = self.cash = self.p.cash
        self.orders = list()
        self.pending = collections.deque()
        self.positions = collections.defaultdict(Position)
```

### 7.2 Order Types

**File:** `backtrader/order.py:222-250`

```python
class OrderBase:
    # Execution Types
    (Market, Close, Limit, Stop, StopLimit,
     StopTrail, StopTrailLimit, Historical) = range(8)

    # Order States
    (Created, Submitted, Accepted, Partial, Completed,
     Canceled, Expired, Margin, Rejected) = range(9)

    # Order Direction
    Buy, Sell = range(2)
```

### 7.3 Order Execution Tracking

**File:** `backtrader/order.py:35-86`

```python
class OrderExecutionBit:
    '''Represents one execution piece of an order'''
    def __init__(self, dt, size, price,
                 closed, closedvalue, closedcomm,
                 opened, openedvalue, openedcomm, pnl,
                 psize, pprice):
        self.dt = dt
        self.size = size
        self.price = price
        self.closed = closed   # How much closed existing position
        self.opened = opened   # How much opened new position
        self.pnl = pnl        # PnL from this execution
```

---

## 8. Indicator System

**File:** `backtrader/indicators/sma.py`

### 8.1 Simple Indicator Example

```python
class MovingAverageSimple(MovingAverageBase):
    '''
    Formula: movav = Sum(data, period) / period
    '''
    alias = ('SMA', 'SimpleMovingAverage',)
    lines = ('sma',)  # Output line name

    def __init__(self):
        # Declarative: Average calculates and assigns to line 0
        self.lines[0] = Average(self.data, period=self.p.period)
        super(MovingAverageSimple, self).__init__()
```

### 8.2 Indicator with Custom Calculation

```python
class MyIndicator(bt.Indicator):
    lines = ('signal',)
    params = (('period', 14),)

    def __init__(self):
        self.addminperiod(self.p.period)  # Declare warm-up requirement

    def next(self):
        # Called each bar after minperiod
        values = self.data.get(size=self.p.period)
        self.lines.signal[0] = sum(values) / self.p.period

    def once(self, start, end):
        # Vectorized version for runonce mode
        for i in range(start, end):
            self.lines.signal[i] = ...
```

### 8.3 Indicator Hierarchy

```
Indicator (indicator.py)
├── MovingAverageBase
│   ├── SMA, EMA, WMA, DEMA, TEMA
│   ├── KAMA, HMA, ZLEMA
│   └── Ichimoku
├── OscillatorBase
│   ├── RSI, Stochastic, MACD
│   └── CCI, Williams
└── VolatilityBase
    ├── ATR, Bollinger
    └── StandardDeviation
```

---

## 9. Data Feed System

**File:** `backtrader/feed.py:40-250`

### 9.1 Data Feed Architecture

```python
class AbstractDataBase(OHLCDateTime):
    params = (
        ('dataname', None),       # Source (filename, symbol, etc.)
        ('compression', 1),       # Bar compression
        ('timeframe', TimeFrame.Days),
        ('fromdate', None),       # Start date filter
        ('todate', None),         # End date filter
        ('sessionstart', None),   # Trading session start
        ('sessionend', None),     # Trading session end
        ('filters', []),          # Data filters (Renko, etc.)
        ('tz', None),             # Timezone
    )

    # Standard Lines (inherited from OHLCDateTime)
    lines = ('datetime', 'open', 'high', 'low', 'close',
             'volume', 'openinterest')
```

### 9.2 Data Feed Implementations

| Feed | File | Use Case |
|------|------|----------|
| `GenericCSVData` | feeds/csvgeneric.py | Custom CSV files |
| `PandasData` | feeds/pandafeed.py | Pandas DataFrames |
| `YahooFinanceData` | feeds/yahoo.py | Yahoo Finance |
| `IBData` | feeds/ibdata.py | Interactive Brokers |
| `OandaData` | feeds/oandadata.py | OANDA forex |

### 9.3 Resampling and Replaying

**File:** `backtrader/resamplerfilter.py`

```python
# Resample 1-minute data to 5-minute
cerebro.resampledata(data, timeframe=bt.TimeFrame.Minutes, compression=5)

# Replay (delivers tick-by-tick within bars)
cerebro.replaydata(data, timeframe=bt.TimeFrame.Days)
```

---

## 10. Observer and Analyzer System

### 10.1 Observers

**File:** `backtrader/observer.py`

```python
class Observer(ObserverBase):
    _ltype = LineIterator.ObsType

    def __init__(self):
        # Observers always observe, even during prenext
        self.plotinfo.plot = False  # Hidden by default
```

**Built-in Observers:**
- `Broker`: Cash and portfolio value
- `BuySell`: Buy/sell markers on chart
- `Trades`: Trade entry/exit markers
- `DrawDown`: Drawdown tracking

### 10.2 Analyzers

**File:** `backtrader/analyzer.py`

```python
class Analyzer:
    def start(self):
        '''Called at strategy start'''
        pass

    def prenext(self):
        '''Called during warm-up'''
        pass

    def next(self):
        '''Called each bar'''
        pass

    def stop(self):
        '''Called at end - generate results'''
        pass

    def get_analysis(self):
        '''Return analysis results'''
        return self.rets
```

**Built-in Analyzers:**
- `TradeAnalyzer`: Win/loss statistics
- `SharpeRatio`: Risk-adjusted returns
- `DrawDown`: Maximum drawdown
- `Returns`: Cumulative/annual returns
- `SQN`: System Quality Number
- `PyFolio`: PyFolio integration

---

## 11. Complete Example Walkthrough

### 11.1 Basic Backtest

```python
import backtrader as bt

class SmaCross(bt.Strategy):
    params = (('fast', 10), ('slow', 30),)

    def __init__(self):
        # Indicators are created and auto-registered
        sma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        sma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(sma_fast, sma_slow)

    def next(self):
        if self.crossover > 0:  # Fast crossed above slow
            self.buy()
        elif self.crossover < 0:  # Fast crossed below slow
            self.sell()

# Setup and run
cerebro = bt.Cerebro()
cerebro.addstrategy(SmaCross)
cerebro.adddata(bt.feeds.YahooFinanceData(dataname='AAPL', fromdate=...))
cerebro.broker.setcash(100000)
results = cerebro.run()
cerebro.plot()
```

### 11.2 Execution Flow Walkthrough

```
1. cerebro.addstrategy(SmaCross)
   └─► Strategy class stored (not instantiated yet)

2. cerebro.adddata(data)
   └─► Data feed stored in cerebro.datas

3. cerebro.run()
   │
   ├─► Data preloaded (if preload=True)
   │   └─► data._load() called repeatedly until exhausted
   │
   ├─► Strategy instantiated
   │   │
   │   ├─► MetaStrategy.donew():
   │   │   └─► Auto-discovers cerebro via findowner()
   │   │   └─► Sets _obj.broker = cerebro.broker
   │   │
   │   ├─► Strategy.__init__():
   │   │   ├─► SMA(fast) created
   │   │   │   └─► Auto-registers with strategy._lineiterators
   │   │   │   └─► minperiod = 10
   │   │   │
   │   │   ├─► SMA(slow) created
   │   │   │   └─► minperiod = 30
   │   │   │
   │   │   └─► CrossOver created
   │   │       └─► minperiod = max(10, 30) + 1 = 31
   │   │
   │   └─► MetaLineIterator.dopostinit():
   │       └─► Strategy._minperiod = 31
   │
   ├─► Indicators._once() if runonce=True
   │   └─► SMA and CrossOver calculate all values vectorized
   │
   └─► Main loop: for each bar
       │
       ├─► Bars 1-30: strategy.prenext()
       │   └─► Waiting for minperiod
       │
       ├─► Bar 31: strategy.nextstart()
       │   └─► First valid bar, calls next()
       │
       └─► Bars 32+: strategy.next()
           │
           ├─► self.crossover > 0 checked
           │   └─► Accesses CrossOver.lines[0][0]
           │
           ├─► self.buy() called
           │   └─► Creates Market order
           │   └─► Submits to broker.submit()
           │
           └─► broker.next()
               └─► Processes pending orders
               └─► Executes at next bar's open
               └─► Notifies strategy via notify_order()
```

### 11.3 How Indicators Auto-Register

```python
# In strategy.__init__:
sma_fast = bt.indicators.SMA(self.data.close, period=10)

# What happens internally:
# 1. MetaLineIterator.donew() scans args for LineRoot instances
#    - Finds self.data.close (a LineBuffer)
#    - Stores in _obj.datas

# 2. MetaLineIterator.dopreinit():
#    - _obj._clock = self.data.close (first data)
#    - _obj._minperiod = max([10]) = 10

# 3. MetaLineActions.dopostinit():
#    - _obj._owner.addindicator(_obj)
#    - This adds SMA to strategy._lineiterators[IndType]
```

---

## 12. Key Design Patterns Summary

| Pattern | Usage | Location |
|---------|-------|----------|
| **Template Method** | Object creation lifecycle | `backtrader/metabase.py:84-90` |
| **Observer** | Observers, Analyzers | `backtrader/observer.py` |
| **Descriptor** | LineAlias property access | `backtrader/lineseries.py` |
| **Builder** | Cerebro configuration | `backtrader/cerebro.py` |
| **Iterator** | Line buffer traversal | `backtrader/linebuffer.py` |
| **Cache** | Indicator object reuse | `backtrader/linebuffer.py:509-534` |
| **Adapter** | Multiple broker/feed impls | `backtrader/brokers/` |
| **Command** | Order objects | `backtrader/order.py` |
| **Singleton** | Store class | `backtrader/store.py` |
| **Implicit Injection** | findowner() | `backtrader/metabase.py:42-63` |

---

## 13. Memory Management

### 13.1 exactbars Modes

| Value | Behavior | Use Case |
|-------|----------|----------|
| `False` | Keep all history | Default, needed for plotting |
| `True/1` | Circular buffer = minperiod | Maximum memory saving |
| `-1` | Strategy-level keeps all | Plotting + some memory saving |
| `-2` | Only declared attrs keep all | More aggressive saving |

### 13.2 QBuffer Implementation

```python
def qbuffer(self, savemem=0, extrasize=0):
    self.mode = self.QBuffer
    self.maxlen = self._minperiod
    self.array = collections.deque(maxlen=self.maxlen + self.extrasize)
```

---

## 14. Live vs Backtesting Mode

| Aspect | Backtesting | Live Trading |
|--------|-------------|--------------|
| `preload` | True | False (auto) |
| `runonce` | True | False (auto) |
| Data loading | All upfront | Real-time streaming |
| Indicator calc | Vectorized `once()` | Event-driven `next()` |
| Broker | `BackBroker` simulation | `IBBroker`, `OandaBroker` |
| Order execution | Next bar open | Real market |

---

## 15. File Structure Overview

```
backtrader/
├── __init__.py          # Package entry, imports all components
├── metabase.py          # Metaclass foundation (MetaBase, MetaParams)
├── lineroot.py          # Base line classes (LineRoot, LineSingle)
├── lineseries.py        # Lines container and descriptors
├── linebuffer.py        # LineBuffer implementation
├── lineiterator.py      # Execution engine (LineIterator)
├── dataseries.py        # TimeFrame, OHLC structures
├── feed.py              # Data feed base classes
├── cerebro.py           # Main orchestrator
├── strategy.py          # Strategy base class
├── broker.py            # Broker interface
├── order.py             # Order types and execution
├── trade.py             # Trade tracking
├── position.py          # Position management
├── comminfo.py          # Commission calculation
├── indicator.py         # Indicator base class
├── observer.py          # Observer base class
├── analyzer.py          # Analyzer base class
├── sizer.py             # Position sizing
├── writer.py            # Output writers
├── brokers/             # Broker implementations
│   ├── bbroker.py       # BackBroker (simulation)
│   ├── ibbroker.py      # Interactive Brokers
│   └── oandabroker.py   # OANDA
├── feeds/               # Data feed implementations
│   ├── csvgeneric.py    # Generic CSV
│   ├── pandafeed.py     # Pandas DataFrame
│   ├── yahoo.py         # Yahoo Finance
│   └── ibdata.py        # Interactive Brokers
├── indicators/          # 80+ built-in indicators
│   ├── sma.py           # Simple Moving Average
│   ├── ema.py           # Exponential Moving Average
│   ├── rsi.py           # Relative Strength Index
│   └── ...
├── analyzers/           # 15+ built-in analyzers
│   ├── returns.py       # Returns analysis
│   ├── sharpe.py        # Sharpe ratio
│   ├── drawdown.py      # Drawdown analysis
│   └── ...
├── observers/           # Built-in observers
│   ├── broker.py        # Cash/value tracking
│   ├── buysell.py       # Buy/sell markers
│   └── trades.py        # Trade markers
├── sizers/              # Position sizing
│   └── fixedsize.py     # Fixed size sizer
└── filters/             # Data filters
    ├── heikinashi.py    # Heikin-Ashi
    └── renko.py         # Renko
```

---

## 16. Summary

Backtrader's architecture enables:

- **Declarative**: Indicators defined in `__init__` auto-register and calculate
- **Efficient**: Vectorized operations when possible via `runonce` mode
- **Flexible**: Same code works for backtesting and live trading
- **Extensible**: Clean metaclass hooks for customization
- **Memory-efficient**: QBuffer mode for large datasets
- **Pythonic**: Natural syntax like `self.data.close[0]` for current price

The key insight is that everything flows through **Lines** - the time-series containers that unify data feeds, indicators, and strategy signals into a coherent data flow model.
