# Walkthrough: analyzer-annualreturn.py

This document provides a comprehensive trace of what happens at **compile time** (class creation) and **runtime** (execution) when running `samples/analyzer-annualreturn/analyzer-annualreturn.py`.

---

## Table of Contents

1. [Overview](#overview)
2. [Phase 1: Import Time (Module Loading)](#phase-1-import-time-module-loading)
3. [Phase 2: Class Definition (Compile Time)](#phase-2-class-definition-compile-time)
4. [Phase 3: Cerebro Setup](#phase-3-cerebro-setup)
5. [Phase 4: Strategy Instantiation](#phase-4-strategy-instantiation)
6. [Phase 5: cerebro.run() Execution](#phase-5-cerebrorun-execution)
7. [Phase 6: Bar-by-Bar Iteration](#phase-6-bar-by-bar-iteration)
8. [Phase 7: Shutdown](#phase-7-shutdown)
9. [Complete Call Flow Diagram](#complete-call-flow-diagram)
10. [Data Flow Diagram](#data-flow-diagram)

---

## Overview

The sample file creates a `LongShortStrategy` that:
1. Creates an SMA indicator on the data
2. Creates a CrossOver signal between close price and SMA
3. Buys on upward crossover, sells on downward crossover
4. Uses multiple analyzers (SQN, AnnualReturn/TimeReturn, SharpeRatio, TradeAnalyzer)

### The Sample Code Structure

```python
# Key components:
class LongShortStrategy(bt.Strategy):
    params = dict(period=15, stake=1, ...)
    
    def __init__(self):
        sma = btind.MovAv.SMA(self.data, period=self.p.period)
        self.signal = btind.CrossOver(self.data.close, sma)
    
    def next(self):
        if self.signal > 0.0:
            self.buy(size=self.p.stake)
        elif self.signal < 0.0:
            self.sell(size=self.p.stake)

def runstrategy():
    cerebro = bt.Cerebro()
    data = btfeeds.BacktraderCSVData(dataname=args.data, ...)
    cerebro.adddata(data)
    cerebro.addstrategy(LongShortStrategy, period=args.period, ...)
    cerebro.addanalyzer(SQN)
    cerebro.run()
```

---

## Phase 1: Import Time (Module Loading)

When Python loads the script, these imports trigger class creation via metaclasses.

### 1.1 Import Chain

```
import backtrader as bt
    └── backtrader/__init__.py
        ├── from .cerebro import Cerebro
        ├── from .strategy import Strategy
        ├── from .indicator import Indicator
        └── from .linebuffer import LineBuffer, ...
```

### 1.2 What Happens During Import

```
┌─────────────────────────────────────────────────────────────────┐
│ IMPORT TIME: backtrader module loads                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. MetaBase class is defined (backtrader/metabase.py)         │
│     └── Provides: doprenew, donew, dopreinit, doinit, dopostinit│
│                                                                 │
│  2. MetaParams class is defined (inherits MetaBase)            │
│     └── Provides: params inheritance system                    │
│                                                                 │
│  3. MetaLineRoot is defined (backtrader/lineroot.py)           │
│     └── Provides: minperiod, operator overloading              │
│                                                                 │
│  4. MetaLineSeries is defined (backtrader/lineseries.py)       │
│     └── Provides: lines, plotinfo, plotlines                   │
│                                                                 │
│  5. MetaLineIterator is defined (backtrader/lineiterator.py)   │
│     └── Provides: data scanning, clock setup                   │
│                                                                 │
│  6. MetaStrategy is defined (backtrader/strategy.py)           │
│     └── Provides: cerebro link, broker, orders, trades         │
│                                                                 │
│  7. Strategy base class is created using MetaStrategy          │
│     └── type('Strategy', (StrategyBase,), {...})               │
│                                                                 │
│  8. Indicator base class is created using MetaIndicator        │
│     └── All built-in indicators are defined                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Class Definition (Compile Time)

When Python encounters `class LongShortStrategy(bt.Strategy):`, the metaclass machinery activates.

### 2.1 Class Hierarchy

```
LongShortStrategy
    └── bt.Strategy
        └── StrategyBase (via MetaStrategy metaclass)
            └── DataAccessor
                └── LineIterator (via MetaLineIterator metaclass)
                    └── LineSeries (via MetaLineSeries metaclass)
                        └── LineMultiple (via MetaLineRoot metaclass)
                            └── LineRoot
                                └── object
```

### 2.2 Metaclass Call Chain for Class Creation

When `class LongShortStrategy(bt.Strategy):` is encountered:

```python
# Python calls: MetaStrategy.__new__(meta, 'LongShortStrategy', (bt.Strategy,), dct)

# Step 1: MetaStrategy.__new__
def __new__(meta, name, bases, dct):
    # Handle backward compatibility
    if 'notify' in dct:
        dct['notify_order'] = dct.pop('notify')
    
    # Call parent __new__ (MetaLineIterator.__new__)
    return super(MetaStrategy, meta).__new__(meta, name, bases, dct)

# Step 2: MetaLineIterator.__new__ (inherited from LineSeries.__class__)
#    -> MetaLineSeries.__new__
def __new__(meta, name, bases, dct):
    # Process 'lines' declaration
    # lines = ('datetime',) from Strategy
    
    # Process 'plotinfo' declaration
    # Process 'plotlines' declaration
    
    # Call parent __new__
    return super(MetaLineSeries, meta).__new__(meta, name, bases, dct)

# Step 3: MetaLineRoot.__new__
def __new__(meta, name, bases, dct):
    # Setup operator overloading
    # Return actual class object
    return super(MetaLineRoot, meta).__new__(meta, name, bases, dct)

# Step 4: MetaParams.__new__
def __new__(meta, name, bases, dct):
    # Build params from class hierarchy
    # params = dict(period=15, stake=1, ...)
    
    # Create AutoInfoClass for params
    cls.params = AutoInfoClass.from_dict(params_dict)
    
    return super(MetaParams, meta).__new__(meta, name, bases, dct)

# Step 5: MetaBase.__new__
def __new__(meta, name, bases, dct):
    # Final class creation
    cls = super(MetaBase, meta).__new__(meta, name, bases, dct)
    return cls
```

### 2.3 MetaStrategy.__init__ (Class Registration)

```python
# After __new__ returns, __init__ is called
def __init__(cls, name, bases, dct):
    super(MetaStrategy, cls).__init__(name, bases, dct)
    
    # Register class (unless private or aliased)
    if not cls.aliased and name != 'Strategy' and not name.startswith('_'):
        cls._indcol[name] = cls
        # Now: MetaStrategy._indcol['LongShortStrategy'] = <class LongShortStrategy>
```

### 2.4 What LongShortStrategy Class Contains After Definition

```python
LongShortStrategy = {
    # From MetaParams
    'params': AutoInfoClass with:
        - period = 15
        - stake = 1
        - printout = False
        - onlylong = False
        - csvcross = False
    
    # From MetaLineSeries
    'lines': Lines class with:
        - datetime (inherited from Strategy)
    
    'plotinfo': AutoInfoClass with:
        - plot = True
        - subplot = True
        - ...
    
    'plotlines': AutoInfoClass (empty)
    
    # From LineIterator
    '_ltype': LineIterator.StratType (1)
    '_mindatas': 1
    '_nextforce': False
    
    # User-defined methods
    '__init__': <function>
    'next': <function>
    'notify_order': <function>
    'notify_trade': <function>
    'start': <function>
    'stop': <function>
    'log': <function>
}
```

---

## Phase 3: Cerebro Setup

### 3.1 `bt.Cerebro()` Creation

```python
cerebro = bt.Cerebro()
```

**Call Flow:**

```
bt.Cerebro()
    └── MetaParams.__call__(Cerebro)
        └── MetaParams.donew(Cerebro)
            └── Cerebro.__new__(Cerebro)
                └── object.__new__(Cerebro)
                    # Returns: Cerebro (uninitialized instance)
            └── Create params instance
                # _obj.params: AutoInfoClass (with preload, runonce, stdstats, etc.)
                # _obj.p: AutoInfoClass (alias for params)
            └── Return (_obj, args, kwargs)
        └── MetaParams.dopreinit(_obj)
            # (No additional setup for Cerebro at this stage)
        └── Cerebro.__init__(self)  # User's __init__
            │
            │   # Initialize storage
            │   self._dolive: bool = False
            │   self._doreplay: bool = False
            │   self._dooptimize: bool = False
            │   self.stores: list[Store] = list()
            │   self.feeds: list[Feed] = list()
            │   self.datas: list[DataBase] = list()
            │   self.datasbyname: OrderedDict[str, DataBase] = OrderedDict()
            │   self.strats: list[list[tuple[type, tuple, dict]]] = list()
            │   self.optcbs: list[Callable] = list()
            │   self.observers: list[tuple[bool, type, tuple, dict]] = list()
            │   self.analyzers: list[tuple[type, tuple, dict]] = list()
            │   self.indicators: list[tuple[type, tuple, dict]] = list()
            │   self.sizers: dict[int|None, tuple[type, tuple, dict]] = dict()
            │   self.writers: list[tuple[type, tuple, dict]] = list()
            │   self.storecbs: list[Callable] = list()
            │   self.datacbs: list[Callable] = list()
            │   self.signals: list[tuple[int, type, tuple, dict]] = list()
            │   self._signal_strat: tuple[type|None, tuple|None, dict|None] = (None, None, None)
            │   self._dataid: itertools.count = itertools.count(1)
            │   
            │   # Create default broker
            │   self._broker: BackBroker = BackBroker()
            │   self._broker.cerebro: Cerebro = self
            │   
            │   self._tradingcal: TradingCalendar|None = None
            │   self._pretimers: list[Timer] = list()
            │   self._ohistory: list[tuple] = list()
            │   self._fhistory: Iterable|None = None
            │
            └── Return
        └── MetaParams.dopostinit(_obj)
            # (No additional setup for Cerebro at this stage)
        └── Return cerebro instance
            # Type: Cerebro (fully initialized)
```

### 3.2 Data Feed Creation

```python
data = btfeeds.BacktraderCSVData(
    dataname='../../datas/2005-2006-day-001.txt',
    fromdate=datetime.datetime(2005, 1, 1),
    todate=datetime.datetime(2006, 12, 31)
)
```

**Call Flow:**

```
BacktraderCSVData(...)
    └── MetaLineSeries.__call__(BacktraderCSVData, ...)
        └── MetaLineSeries.donew(cls, *args, **kwargs)
            │
            │   # Inherited from MetaLineRoot.donew:
            │   _obj = cls.__new__(cls)
            │   _obj._minperiod = 1
            │   _obj._minperiods = []
            │   
            │   # From MetaLineSeries.donew:
            │   # Create Lines instance for OHLCV data
            │   _obj.lines = _obj.lines()  # Lines with: datetime, open, high, low, close, volume, openinterest
            │   _obj.plotinfo = _obj.plotinfo()
            │   _obj.plotlines = _obj.plotlines()
            │   
            │   # From MetaLineIterator.donew:
            │   _obj._lineiterators = defaultdict(list)
            │   _obj.datas = []  # No input datas for data feed
            │   
            └── Return (_obj, args, kwargs)
        
        └── MetaLineSeries.dopreinit(_obj)
            │   _obj._clock = _obj  # Data is its own clock
            │   _obj._minperiod = 1
            └── Return
        
        └── BacktraderCSVData.__init__(self, ...)
            │   # Store dataname, fromdate, todate
            │   self._dataname = dataname
            │   self.fromdate = fromdate
            │   self.todate = todate
            └── Return
        
        └── dopostinit(_obj)
        └── Return data instance
```

### 3.3 Adding Data to Cerebro

```python
cerebro.adddata(data)
```

```python
def adddata(self, data, name=None):
    if name is not None:
        data._name = name
    
    data._id = next(self._dataid)  # Assign unique ID
    data.setenvironment(self)      # Link to cerebro
    
    self.datas.append(data)        # Add to datas list
    self.datasbyname[data._name] = data
    
    feed = data.getfeed()
    if feed and feed not in self.feeds:
        self.feeds.append(feed)
    
    if data.islive():
        self._dolive = True
    
    return data

# After this:
# cerebro.datas = [data]
# cerebro.datasbyname = {'2005-2006-day-001': data}
```

### 3.4 Adding Strategy to Cerebro

```python
cerebro.addstrategy(LongShortStrategy, period=15, onlylong=False, ...)
```

```python
def addstrategy(self, strategy, *args, **kwargs):
    # Store as tuple, NOT instantiated yet
    self.strats.append([(strategy, args, kwargs)])
    return len(self.strats) - 1

# After this:
# cerebro.strats = [[(LongShortStrategy, (), {'period': 15, ...})]]
```

### 3.5 Adding Analyzers

```python
cerebro.addanalyzer(SQN)
cerebro.addanalyzer(AnnualReturn)
cerebro.addanalyzer(SharpeRatio, legacyannual=True)
cerebro.addanalyzer(TradeAnalyzer)
```

```python
def addanalyzer(self, ancls, *args, **kwargs):
    self.analyzers.append((ancls, args, kwargs))

# After this:
# cerebro.analyzers = [
#     (SQN, (), {}),
#     (AnnualReturn, (), {}),
#     (SharpeRatio, (), {'legacyannual': True}),
#     (TradeAnalyzer, (), {})
# ]
```

---

## Phase 4: Strategy Instantiation

This happens inside `cerebro.run()` when `runstrategies()` is called.

### 4.1 High-Level run() Flow

```python
cerebro.run()
    └── run(self, **kwargs)
        │   # Early setup
        │   self._dorunonce = self.p.runonce  # True
        │   self._dopreload = self.p.preload  # True
        │   
        │   # Create writers
        │   for wrcls, wrargs, wrkwargs in self.writers:
        │       wr = wrcls(*wrargs, **wrkwargs)
        │       self.runwriters.append(wr)
        │   
        │   # Build strategy combinations
        │   iterstrats = itertools.product(*self.strats)
        │   
        │   # Run each strategy combination
        │   for iterstrat in iterstrats:
        │       runstrat = self.runstrategies(iterstrat)
        │       self.runstrats.append(runstrat)
        │   
        └── return self.runstrats[0]
```

### 4.2 runstrategies() - Data Initialization

```python
def runstrategies(self, iterstrat, predata=False):
    self._init_stcount()
    self.runningstrats = runstrats = list()
    
    # Start broker
    self._broker.start()
    
    # Initialize and preload data feeds
    for data in self.datas:
        data.reset()          # Reset buffer indices
        data.extend(size=0)   # Extend buffer if needed
        data._start()         # Start data feed
        if self._dopreload:
            data.preload()    # Load ALL data into memory
    
    # Now: data.lines.close.array = [100.1, 100.5, 99.8, ...]
    # All historical data is loaded
```

### 4.3 Strategy Instantiation - The Critical Part

```python
for stratcls, sargs, skwargs in iterstrat:
    # Prepend datas to args
    sargs = self.datas + list(sargs)  # [data] + []
    
    # THIS IS WHERE STRATEGY IS CREATED
    strat = stratcls(*sargs, **skwargs)
    # stratcls = LongShortStrategy
    # sargs = [data]
    # skwargs = {'period': 15, 'onlylong': False, ...}
    
    runstrats.append(strat)
```

### 4.4 Metaclass Chain for Strategy Instance Creation

```
LongShortStrategy(data, period=15, ...)
    │
    └── MetaStrategy.__call__(cls, data, period=15, ...)
        │
        ├── [1] MetaStrategy.donew(cls, data, period=15, ...)
        │       │
        │       │   # Call parent chain
        │       └── MetaLineIterator.donew(cls, data, ...)
        │           │
        │           │   # Create _lineiterators storage
        │           │   _obj._lineiterators = defaultdict(list)
        │           │   # Type: collections.defaultdict[int, list]
        │           │   
        │           │   # Scan args for data sources
        │           │   for arg in args:
        │           │       if isinstance(arg, LineRoot):
        │           │           _obj.datas.append(LineSeriesMaker(arg))
        │           │   # Result: _obj.datas = [data]
        │           │   # Type: list[BacktraderCSVData]
        │           │   
        │           │   # Create data shortcuts
        │           │   _obj.data = data                    # Type: BacktraderCSVData
        │           │   _obj.data0 = data                   # Type: BacktraderCSVData
        │           │   _obj.data_close = data.lines.close  # Type: LineBuffer
        │           │   _obj.data_high = data.lines.high    # Type: LineBuffer
        │           │   _obj.data_0 = data.lines[0]         # Type: LineBuffer (datetime)
        │           │   ...
        │           │   
        │           │   # Create dnames dict
        │           │   _obj.dnames = DotDict(...)          # Type: DotDict
        │           │   
        │           └── MetaLineSeries.donew(...)
        │               │   # Create lines instance
        │               │   _obj.lines = _obj.lines()
        │               │   # Type: Lines (subclass with 'datetime' attribute)
        │               │   # For Strategy: just 'datetime' line
        │               │   
        │               │   _obj.plotinfo = _obj.plotinfo()
        │               │   # Type: AutoInfoClass (subclass)
        │               │   _obj.plotlines = _obj.plotlines()
        │               │   # Type: AutoInfoClass (subclass)
        │               │   
        │               └── MetaLineRoot.donew(...)
        │                   │   _obj = cls.__new__(cls)
        │                   │   # Type: LongShortStrategy (uninitialized)
        │                   │   _obj._minperiod = 1          # Type: int
        │                   │   _obj._minperiods = []        # Type: list[int]
        │                   │   _obj._opstage = 1            # Type: int (Stage 1 = setup)
        │                   │   
        │                   └── MetaParams.donew(...)
        │                       │   # Create params instance with overrides
        │                       │   _obj.params = cls.params(**kwargs)
        │                       │   # Type: AutoInfoClass (subclass with period, stake, etc.)
        │                       │   # params.period = 15
        │                       │   # params.stake = 1
        │                       │   _obj.p = _obj.params    # Type: same AutoInfoClass (alias)
        │                       │   
        │                       └── MetaBase.donew(...)
        │                           │   _obj = cls.__new__(cls)
        │                           │   # Type: LongShortStrategy (bare instance)
        │                           └── Return (_obj, args, kwargs)
        │       │
        │       │   # MetaStrategy.donew continues:
        │       │   _obj.env = _obj.cerebro = findowner(_obj, bt.Cerebro)
        │       │   # Type: Cerebro
        │       │   # Walks call stack to find Cerebro instance
        │       │   _obj._id = cerebro._next_stid()  # 0
        │       │   # Type: int
        │       │   
        │       └── Return (_obj, args, kwargs)
        │
        ├── [2] MetaStrategy.dopreinit(cls, _obj, ...)
        │       │
        │       └── MetaLineIterator.dopreinit(...)
        │           │   # Set clock
        │           │   _obj.datas = _obj.datas or [_obj._owner]
        │           │   _obj._clock = _obj.datas[0]  # = data
        │           │   # Type: BacktraderCSVData
        │           │   
        │           │   # Calculate initial minperiod
        │           │   _obj._minperiod = max([x._minperiod for x in _obj.datas])
        │           │   # Type: int (= 1, data's minperiod)
        │           │   
        │           │   # Add minperiod to lines
        │           │   for line in _obj.lines:
        │           │       line.addminperiod(_obj._minperiod)
        │           │       # line Type: LineBuffer
        │           │   
        │           └── MetaLineSeries.dopreinit(...)
        │               └── MetaLineRoot.dopreinit(...)
        │                   └── MetaParams.dopreinit(...)
        │                       └── MetaBase.dopreinit(...)
        │       │
        │       │   # MetaStrategy.dopreinit continues:
        │       │   _obj.broker = _obj.env.broker
        │       │   # Type: BackBroker
        │       │   _obj._sizer = bt.sizers.FixedSize()
        │       │   # Type: FixedSize (Sizer subclass)
        │       │   _obj._orders = list()
        │       │   # Type: list[Order]
        │       │   _obj._orderspending = list()
        │       │   # Type: list[Order]
        │       │   _obj._trades = defaultdict(AutoDictList)
        │       │   # Type: defaultdict[data, AutoDictList[tradeid, list[Trade]]]
        │       │   _obj._tradespending = list()
        │       │   # Type: list[Trade]
        │       │   _obj.stats = _obj.observers = ItemCollection()
        │       │   # Type: ItemCollection
        │       │   _obj.analyzers = ItemCollection()
        │       │   # Type: ItemCollection
        │       │   
        │       └── Return (_obj, args, kwargs)
        │
        ├── [3] LongShortStrategy.__init__(self)  ← USER CODE RUNS HERE
        │       │
        │       │   # User's __init__ code:
        │       │   self.orderid = None
        │       │   # Type: NoneType (will be Order when set)
        │       │   
        │       │   # Create SMA indicator
        │       │   sma = btind.MovAv.SMA(self.data, period=self.p.period)
        │       │   # Type: SMA (MovingAverageSimple)
        │       │   │
        │       │   │   # This triggers indicator creation:
        │       │   │   └── MetaIndicator.__call__(SMA, self.data, period=15)
        │       │   │       └── SMA.donew, dopreinit, __init__, dopostinit
        │       │   │           │   # In SMA.__init__:
        │       │   │           │   self.lines.sma = Average(self.data, period=15)
        │       │   │           │   # self.lines.sma Type: LineBuffer
        │       │   │           │   self._minperiod = 15  # Type: int
        │       │   │           │
        │       │   │           └── SMA registered with strategy via:
        │       │   │               _obj._owner.addindicator(sma)
        │       │   │               # _obj._owner Type: LongShortStrategy
        │       │   │
        │       │   │   # Now: self._lineiterators[IndType] = [sma]
        │       │   │   # Type: list[SMA]
        │       │   
        │       │   # Create CrossOver indicator
        │       │   self.signal = btind.CrossOver(self.data.close, sma)
        │       │   # Type: CrossOver
        │       │   │
        │       │   │   # CrossOver internally creates:
        │       │   │   # - CrossUp(data1, data2)    Type: CrossUp
        │       │   │   # - CrossDown(data1, data2)  Type: CrossDown
        │       │   │   # CrossOver._minperiod = sma._minperiod + 1 = 16
        │       │   │
        │       │   │   # Registered with strategy:
        │       │   │   # self._lineiterators[IndType] = [sma, signal]
        │       │   │   # Type: list[SMA, CrossOver]
        │       │   
        │       │   self.signal.csv = self.p.csvcross
        │       │   # Type: bool
        │       │   
        │       └── Return
        │
        ├── [4] MetaStrategy.dopostinit(cls, _obj, ...)
        │       │
        │       └── MetaLineIterator.dopostinit(...)
        │           │   # Calculate final minperiod from lines
        │           │   _obj._minperiod = max([x._minperiod for x in _obj.lines])
        │           │   # Type: int
        │           │   
        │           │   # Recalculate from child indicators
        │           │   _obj._periodrecalc()
        │           │   # Finds max of [sma._minperiod, signal._minperiod]
        │           │   # = max(15, 16) = 16
        │           │   
        │           │   # Register with owner (but strategy has no owner)
        │           │   if _obj._owner is not None:
        │           │       _obj._owner.addindicator(_obj)
        │           │   # _obj._owner Type: NoneType (strategy has no owner)
        │           │   
        │           └── Return
        │       │
        │       │   # MetaStrategy.dopostinit:
        │       │   _obj._sizer.set(_obj, _obj.broker)
        │       │   # Links sizer to strategy and broker
        │       │   
        │       └── Return (_obj, args, kwargs)
        │
        └── Return strat  # Type: LongShortStrategy (fully initialized)
```

### 4.5 After Strategy Creation - Object Graph

```
strategy: LongShortStrategy
    │
    ├── .cerebro: Cerebro
    ├── .broker: BackBroker
    ├── ._id: int = 0
    │
    ├── .datas: list[BacktraderCSVData] = [data]
    ├── .data: BacktraderCSVData (shortcut to datas[0])
    ├── .data0: BacktraderCSVData (same as .data)
    ├── .data_close: LineBuffer (data.lines.close)
    ├── .data_high: LineBuffer (data.lines.high)
    ├── .data_low: LineBuffer
    ├── .data_open: LineBuffer
    ├── .data_volume: LineBuffer
    ├── .dnames: DotDict
    │
    ├── .lines: Lines (subclass with 'datetime')
    │   └── .datetime: LineBuffer
    │
    ├── .params: AutoInfoClass (subclass)
    │   ├── .period: int = 15
    │   ├── .stake: int = 1
    │   ├── .printout: bool = False
    │   ├── .onlylong: bool = False
    │   └── .csvcross: bool = False
    ├── .p: AutoInfoClass (alias for .params)
    │
    ├── ._lineiterators: defaultdict[int, list]
    │   ├── [IndType=0]: list[SMA, CrossOver]
    │   ├── [ObsType=2]: list[] (empty, observers added later)
    │   └── [StratType=1]: list[] (empty)
    │
    ├── .signal: CrossOver
    │   ├── .datas: list[LineSeriesStub, SMA] (close line wrapped, sma)
    │   ├── .lines: Lines (subclass with 'crossover')
    │   │   └── .crossover: LineBuffer
    │   ├── ._minperiod: int = 16
    │   ├── ._owner: LongShortStrategy
    │   └── ._clock: BacktraderCSVData
    │
    ├── sma (local variable in __init__, but registered in _lineiterators)
    │   │   Type: SMA (MovingAverageSimple)
    │   ├── .datas: list[BacktraderCSVData]
    │   ├── .lines: Lines (subclass with 'sma')
    │   │   └── .sma: LineBuffer
    │   ├── ._minperiod: int = 15
    │   ├── ._owner: LongShortStrategy
    │   └── ._clock: BacktraderCSVData
    │
    ├── ._minperiod: int = 16
    ├── ._clock: BacktraderCSVData
    ├── ._opstage: int = 1 (Stage 1 until _start() switches to Stage 2)
    │
    ├── ._orders: list[Order] = []
    ├── ._orderspending: list[Order] = []
    ├── ._trades: defaultdict[data, AutoDictList] = {}
    ├── ._tradespending: list[Trade] = []
    │
    ├── ._sizer: FixedSize
    ├── .observers: ItemCollection (alias for .stats)
    ├── .stats: ItemCollection
    ├── .analyzers: ItemCollection
    │
    └── .orderid: NoneType = None (user attribute)
```

---

## Phase 4.6: How Data, Lines, and Bindings Connect

This section explains how the strategy's data, the SMA's data/lines, and the CrossOver's data/lines are wired together — and how values flow through bindings at runtime.

### The Wiring Overview

```
                          ┌──────────────────────────────────────┐
                          │       BacktraderCSVData (data)        │
                          │                                      │
                          │  .lines.datetime: LineBuffer  [0]    │
                          │  .lines.close:    LineBuffer  [1]    │
                          │  .lines.low:      LineBuffer  [2]    │
                          │  .lines.high:     LineBuffer  [3]    │
                          │  .lines.open:     LineBuffer  [4]    │
                          │  .lines.volume:   LineBuffer  [5]    │
                          │  .lines.openinterest: LineBuffer [6] │
                          └────┬──────────────────────┬──────────┘
                               │                      │
           ┌───────────────────┘                      └───────────────┐
           │ (data passed as arg)                    (data.close passed│
           ▼                                           as arg)        ▼
┌─────────────────────────┐                   ┌───────────────────────────┐
│  SMA Indicator          │                   │  CrossOver Indicator      │
│                         │                   │                           │
│  .datas[0] = data       │                   │  .datas[0] = data.close   │
│   (BacktraderCSVData)   │                   │   (wrapped as             │
│                         │                   │    LineSeriesStub)        │
│  .data = .datas[0]      │                   │                           │
│   (shortcut)            │                   │  .datas[1] = sma          │
│                         │                   │   (SMA indicator)         │
│  ._owner = strategy     │                   │                           │
│  ._clock = data         │                   │  .data  = .datas[0]       │
│                         │                   │  .data1 = .datas[1]       │
│  .lines.sma: LineBuffer │                   │                           │
│       ▲                 │                   │  ._owner = strategy       │
│       │ binding         │                   │  ._clock = data           │
│       │                 │                   │                           │
│  Average indicator      │                   │  .lines.crossover:        │
│   (sub-indicator)       │                   │       LineBuffer          │
│   .lines.av: LineBuffer │                   │       ▲                   │
│       │                 │                   │       │ binding            │
│       │ binding ────────┼───► sma.lines.sma │       │                   │
│       │                 │                   │  (upcross - downcross)    │
│       │                 │                   │       : LinesOperation    │
└───────┼─────────────────┘                   │       .lines[0]:          │
        │                                     │         LineBuffer        │
        │                                     │                           │
        │                                     │  upcross: CrossUp         │
        │                                     │  downcross: CrossDown     │
        │                                     │  (sub-indicators)         │
        │                                     └───────────────────────────┘
        │
        │
        ▼
  LongShortStrategy
    .data = data (BacktraderCSVData)
    .data_close = data.lines.close (LineBuffer)
    .signal = CrossOver
    ._lineiterators[IndType] = [sma, signal]
```

### How Each Indicator Gets Its Data

#### SMA: Single Data Source

In the user's `__init__`:

```python
sma = btind.MovAv.SMA(self.data, period=self.p.period)
# self.data is BacktraderCSVData (the strategy's first data feed)
```

`MetaLineIterator.donew` scans the constructor args:

```python
# args = (self.data,)  where self.data is a BacktraderCSVData (which IS a LineRoot)
for arg in args:
    if isinstance(arg, LineRoot):             # True
        _obj.datas.append(LineSeriesMaker(arg))

# Result: sma.datas = [data]
# sma.data = data (shortcut to datas[0])
```

When `sma.data` is used inside the SMA's computation (e.g. `self.data.get(size=period)`),
it reads from the **close** line of BacktraderCSVData by default (line index 0 in OHLC
convention maps to close for indicators via `data.lines[0]`).

#### CrossOver: Two Data Sources

```python
self.signal = btind.CrossOver(self.data.close, sma)
# arg1: self.data.close is a LineBuffer (a single line, not a LineSeries)
# arg2: sma is an SMA indicator (a LineSeries)
```

`MetaLineIterator.donew` scans the constructor args:

```python
# args = (self.data.close, sma)

# Iteration 1: self.data.close
if isinstance(arg, LineRoot):                 # True (LineBuffer IS a LineRoot)
    _obj.datas.append(LineSeriesMaker(arg))
    # LineSeriesMaker wraps the LineBuffer in a LineSeriesStub
    # so it behaves like a full LineSeries with .lines, etc.

# Iteration 2: sma
if isinstance(arg, LineRoot):                 # True (SMA IS a LineRoot)
    _obj.datas.append(LineSeriesMaker(arg))
    # SMA is already a LineSeries, returned as-is

# Result:
# signal.datas = [LineSeriesStub(data.close), sma]
# signal.data  = signal.datas[0] = LineSeriesStub(data.close)
# signal.data1 = signal.datas[1] = sma
```

### How Line Bindings Work

#### The Binding Mechanism

A **binding** means: "when a value is written to line A, also write it to line B."

```python
# In LineBuffer:
class LineBuffer:
    def __init__(self):
        self.bindings = []    # list[LineBuffer]
    
    def addbinding(self, binding):
        self.bindings.append(binding)
        binding.updateminperiod(self._minperiod)
    
    def __setitem__(self, ago, value):
        # Write to self
        self.array[self.idx + ago] = value
        # Propagate to all bindings
        for binding in self.bindings:
            binding[ago] = value
    
    def oncebinding(self):
        # Batch copy for "once" mode
        larray = self.array
        blen = self.buflen()
        for binding in self.bindings:
            binding.array[0:blen] = larray[0:blen]
```

#### How `self.lines.sma = Average(...)` Creates a Binding

Inside SMA's `__init__`:

```python
class MovingAverageSimple(MovingAverageBase):
    lines = ('sma',)
    
    def __init__(self):
        self.lines[0] = Average(self.data, period=self.p.period)
```

`self.lines[0] = ...` triggers `Lines.__setitem__`, which calls `setattr(self, alias, value)`,
which triggers the `LineAlias` descriptor's `__set__`:

```python
class LineAlias(object):
    def __set__(self, obj, value):
        # value = Average indicator (a LineMultiple)
        
        # Step 1: Extract the first line from multi-line objects
        if isinstance(value, LineMultiple):
            value = value.lines[0]
        # Now value = Average.lines.av (a LineBuffer)
        
        # Step 2: Wrap non-LineActions in a zero-delay wrapper
        if not isinstance(value, LineActions):
            value = value(0)    # Creates _LineDelay(value, 0)
        # This ensures proper timing during next() mode
        
        # Step 3: Create the binding
        value.addbinding(obj.lines[self.line])
        # Translation: Average.lines.av.addbinding(SMA.lines.sma)
        #
        # Now when Average writes to its .av line,
        # the value is automatically copied to SMA's .sma line
```

**Result:** `Average.lines.av` → binding → `SMA.lines.sma`

#### How `self.lines.crossover = upcross - downcross` Creates a Binding

Inside CrossOver's `__init__`:

```python
class CrossOver(Indicator):
    lines = ('crossover',)
    
    def __init__(self):
        upcross = CrossUp(self.data, self.data1)       # Type: CrossUp indicator
        downcross = CrossDown(self.data, self.data1)    # Type: CrossDown indicator
        
        self.lines.crossover = upcross - downcross
```

Step by step:

```python
# Step 1: upcross - downcross
# upcross is a CrossUp indicator (LineMultiple)
# In Stage 1, __sub__ calls _operation_stage1:
#   other = downcross.lines[0]   (extract first line)
#   self  = upcross.lines[0]     (called on first line)
#   return LinesOperation(self, other, operator.__sub__)
#
# Result: LinesOperation instance
# Type: LinesOperation (inherits LineActions → LineBuffer → LineSingle)
# It has .lines[0] which is the LinesOperation itself (it IS a line)

# Step 2: Assignment to self.lines.crossover
# Triggers LineAlias.__set__:
#   value = LinesOperation (a LineMultiple)
#   value = value.lines[0]     → the LinesOperation itself (a LineActions)
#   isinstance(value, LineActions) → True, no wrapping needed
#   value.addbinding(obj.lines[self.line])
#
# Translation: LinesOperation.addbinding(CrossOver.lines.crossover)
```

**Result:** `LinesOperation(upcross.line - downcross.line)` → binding → `CrossOver.lines.crossover`

### Complete Binding Chain

```
                         COMPUTATION                          BINDING TARGET
                         ──────────                           ──────────────

data.lines.close ─────► Average.next():                      
                           dst[i] = fsum(src) / period        
                           writes to Average.lines.av ──────► SMA.lines.sma
                                                              (via addbinding)

data.lines.close ──┐
                   ├──► CrossUp._once():
SMA.lines.sma  ───┘      computes cross signal
                          writes to CrossUp.lines.cross

data.lines.close ──┐
                   ├──► CrossDown._once():
SMA.lines.sma  ───┘      computes cross signal
                          writes to CrossDown.lines.cross

CrossUp.lines.cross ──┐
                      ├──► LinesOperation._once():
CrossDown.lines.cross ─┘     dst[i] = upcross[i] - downcross[i]
                              writes to LinesOperation.lines[0] ──► CrossOver.lines.crossover
                                                                    (via addbinding)
```

### Runtime Value Flow: Step-by-Step for One Bar

In `_once()` (batch) mode, the order of execution for bar `i`:

```
1. data.preload()
   └── CSV file → data.lines.close.array[i] = 100.50
                  data.lines.high.array[i]  = 101.20
                  ... (all OHLCV loaded)

2. strat._once() calls indicator._once() for each indicator:

   a. SMA._once()
      └── Average._once()
          └── Average.once(start=15, end=500):
              for i in range(15, 500):
                  Average.lines.av.array[i] = fsum(data.close[i-14:i+1]) / 15
          └── Average.oncebinding():
              SMA.lines.sma.array[0:500] = Average.lines.av.array[0:500]
              # Binding copies all values at once

   b. CrossOver._once()
      └── CrossUp._once()
          └── NonZeroDifference._once()  → computes diff between close and sma
          └── And._once() → computes (prev_diff < 0) AND (close > sma)
          └── CrossUp.oncebinding()
      └── CrossDown._once()
          └── (similar chain)
      └── LinesOperation._once()  → dst[i] = upcross[i] - downcross[i]
      └── LinesOperation.oncebinding():
          CrossOver.lines.crossover.array[0:500] = LinesOperation.array[0:500]
          # Binding copies all values at once

3. For each bar i, strat._oncepost(dt):
   └── strategy.next():
       self.signal > 0.0
       # self.signal is the CrossOver indicator
       # In Stage 2: CrossOver.__gt__(0.0) returns bool
       #   reads CrossOver.lines.crossover[0] (current value)
       #   compares with 0.0
       # Result: True if upward crossover happened
```

### Runtime Value Flow: Step-by-Step in `_next()` Mode

In `_next()` (event-by-event) mode, bindings fire immediately via `__setitem__`:

```
For each bar:

1. data.next()
   └── data.lines.close[0] = 100.50   (new bar loaded)

2. strat._next() calls indicator._next() for each:

   a. SMA._next()
      └── Average._next()
          └── Average.next():
              self.line[0] = fsum(self.data.get(size=15)) / 15
              # self.line[0] = ... triggers __setitem__:
              #   Average.lines.av.array[idx] = value
              #   for binding in self.bindings:
              #       binding[0] = value
              #   → SMA.lines.sma[0] = value (IMMEDIATE propagation)

   b. CrossOver._next()
      └── CrossUp._next(), CrossDown._next() compute values
      └── LinesOperation._next():
              self[0] = upcross[0] - downcross[0]
              # Triggers __setitem__:
              #   LinesOperation.array[idx] = value
              #   for binding in self.bindings:
              #       binding[0] = value
              #   → CrossOver.lines.crossover[0] = value (IMMEDIATE)

3. strategy.next():
   self.signal > 0.0  → reads CrossOver.lines.crossover[0]
```

### Key Insight: Bindings vs Direct Ownership

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  The SMA indicator does NOT compute values into its own .lines.sma.     │
│  Instead:                                                                │
│                                                                          │
│  1. SMA creates a sub-indicator: Average                                 │
│  2. Average computes into Average.lines.av                               │
│  3. A BINDING copies Average.lines.av → SMA.lines.sma                  │
│                                                                          │
│  Similarly, CrossOver does NOT compute into .lines.crossover directly.  │
│  Instead:                                                                │
│                                                                          │
│  1. CrossOver creates: CrossUp, CrossDown                                │
│  2. Creates LinesOperation = CrossUp.line - CrossDown.line              │
│  3. A BINDING copies LinesOperation → CrossOver.lines.crossover        │
│                                                                          │
│  This is the "declarative" style: indicators wire up a computation      │
│  graph in __init__, and bindings propagate results to the named lines.  │
│                                                                          │
│  When a user writes: self.lines.sma = SomeExpression                    │
│  The LineAlias descriptor intercepts this and creates a binding from    │
│  SomeExpression's output line → self.lines.sma                          │
│                                                                          │
│  Values never flow "backwards". The expression produces values, and     │
│  bindings push them into the named output line.                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Who Owns Whom: The `_owner` Chain

```
LongShortStrategy (strategy)
    │
    ├── owns SMA (sma._owner = strategy)
    │       │
    │       └── owns Average (average._owner = sma)
    │               Average registered in sma._lineiterators[IndType]
    │
    └── owns CrossOver (signal._owner = strategy)
            │
            ├── owns CrossUp (crossup._owner = crossover)
            │       │
            │       ├── owns NonZeroDifference (nzd._owner = crossup)
            │       └── owns And (and._owner = crossup)
            │
            ├── owns CrossDown (crossdown._owner = crossover)
            │       │
            │       ├── owns NonZeroDifference (nzd._owner = crossdown)
            │       └── owns And (and._owner = crossdown)
            │
            └── owns LinesOperation (linesop._owner = crossover)
                    (upcross.line - downcross.line)

All ownership is established automatically by findowner() walking the
call stack during each indicator's donew().
```

---

## Phase 5: cerebro.run() Execution

After strategy instantiation, `runstrategies()` continues.

### 5.1 Add Standard Observers

```python
if self.p.stdstats:
    strat._addobserver(False, observers.Broker)
    strat._addobserver(True, observers.BuySell, barplot=True)
    strat._addobserver(False, observers.Trades)

# Now: strat.observers = [Broker, [BuySell], Trades]
```

### 5.2 Add User Analyzers

```python
for ancls, anargs, ankwargs in self.analyzers:
    strat._addanalyzer(ancls, *anargs, **ankwargs)

# Internally:
def _addanalyzer(self, ancls, *anargs, **ankwargs):
    anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
    analyzer = ancls(*anargs, **ankwargs)  # Instantiate
    self.analyzers.append(analyzer, anname)

# Now: strat.analyzers = [sqn, annualreturn, sharperatio, tradeanalyzer]
```

### 5.3 Start Strategy

```python
strat._start()
```

**Call Flow:**

```python
def _start(self):
    # Calculate per-data minperiods
    self._periodset()
    # self._minperiods = [16]  # One data, needs 16 bars
    
    # Start analyzers
    for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        analyzer._start()
    
    # Start observers
    for obs in self.observers:
        if not isinstance(obs, list):
            obs = [obs]
        for o in obs:
            o._start()
    
    # SWITCH TO STAGE 2 (execution mode)
    self._stage2()
    # Now operators return values instead of creating line objects
    
    # Track data lengths
    self._dlens = [len(data) for data in self.datas]
    
    # Start in prenext mode
    self._minperstatus = MAXINT
    
    # Call user's start()
    self.start()  # User's empty start()
```

### 5.4 Choose Execution Mode

```python
if self._dopreload and self._dorunonce:
    if self.p.oldsync:
        self._runonce_old(runstrats)
    else:
        self._runonce(runstrats)  # ← Usually this path
else:
    self._runnext(runstrats)
```

---

## Phase 6: Bar-by-Bar Iteration

### 6.1 `_runonce()` Method (Vectorized Mode)

```python
def _runonce(self, runstrats):
    # First: process all indicators in batch
    for strat in runstrats:
        strat._once()
    
    # Then: iterate bar by bar
    data0 = self.datas[0]
    for i in range(data0.buflen()):
        data0.advance()
        for data in self.datas[1:]:
            data.advance()
        
        self._brokernotify()
        
        for strat in runstrats:
            strat._oncepost(data0.datetime[0])
```

### 6.2 Strategy._once() - Batch Processing

```python
def _once(self):
    # Allocate space for all bars
    self.forward(size=self._clock.buflen())
    
    # Process all child indicators in batch
    for indicator in self._lineiterators[LineIterator.IndType]:
        indicator._once()  # Calls SMA._once(), CrossOver._once()
    
    # Prepare observers
    for observer in self._lineiterators[LineIterator.ObsType]:
        observer.forward(size=self.buflen())
    
    # Reset all indices to start
    for data in self.datas:
        data.home()
    for indicator in self._lineiterators[LineIterator.IndType]:
        indicator.home()
    for observer in self._lineiterators[LineIterator.ObsType]:
        observer.home()
    self.home()
    
    # Note: preonce/oncestart/once are not used for Strategy
    # Strategy uses _oncepost instead
    
    # Execute bindings
    for line in self.lines:
        line.oncebinding()
```

### 6.3 Indicator._once() - SMA Example

```python
# For SMA indicator:
def once(self, start, end):
    # Optimized batch calculation
    src = self.data.array  # Source close prices
    dst = self.lines.sma.array  # Output array
    period = self.p.period
    
    for i in range(start, end):
        dst[i] = sum(src[i-period+1:i+1]) / period

# Called as: sma.once(15, 500)  # Start at minperiod, go to end
```

### 6.4 Strategy._oncepost() - Per-Bar Processing

```python
def _oncepost(self, dt):
    # Advance indicators if needed
    for indicator in self._lineiterators[LineIterator.IndType]:
        if len(indicator._clock) > len(indicator):
            indicator.advance()
    
    # Advance strategy
    self.forward()
    
    # Set strategy datetime
    self.lines.datetime[0] = dt
    
    # Process pending orders and trades
    self._notify()
    
    # Check minperiod status
    minperstatus = self._getminperstatus()
    # Returns: len(data) - minperiod[0]
    # Bar 1: 1 - 16 = -15 (prenext)
    # Bar 16: 16 - 16 = 0 (nextstart)
    # Bar 17: 17 - 16 = 1 (next)
    
    if minperstatus < 0:
        self.next()       # Normal operation
    elif minperstatus == 0:
        self.nextstart()  # First valid bar
    else:
        self.prenext()    # Warming up
    
    # Process analyzers and observers
    self._next_analyzers(minperstatus, once=True)
    self._next_observers(minperstatus, once=True)
    
    self.clear()  # Clear pending notifications
```

### 6.5 User's next() Method Execution

```python
def next(self):
    if self.orderid:
        return  # Skip if order pending
    
    # At this point, Stage 2 is active
    # self.signal > 0.0 returns True/False, not a LinesOperation
    
    if self.signal > 0.0:  # Upward cross
        if self.position:
            self.log('CLOSE SHORT , %.2f' % self.data.close[0])
            self.close()
        
        self.log('BUY CREATE , %.2f' % self.data.close[0])
        self.buy(size=self.p.stake)
        │
        └── Strategy.buy(size=1)
            │
            │   data = self.datas[0]
            │   size = 1  # From params
            │   
            └── self.broker.buy(self, data, size=1, ...)
                │
                │   # Creates Order object
                │   order = Order(...)
                │   order.submit(broker)
                │   
                └── Returns order
    
    elif self.signal < 0.0:  # Downward cross
        if self.position:
            self.close()
        
        if not self.p.onlylong:
            self.sell(size=self.p.stake)
```

### 6.6 Broker Processing

```python
# In cerebro._brokernotify():
def _brokernotify(self):
    self._broker.next()  # Process pending orders
    
    while True:
        order = self._broker.get_notification()
        if order is None:
            break
        
        owner = order.owner
        owner._addnotification(order, quicknotify=self.p.quicknotify)
        # This calls strategy.notify_order(order) via _notify()
```

### 6.7 Analyzer Processing

```python
def _next_analyzers(self, minperstatus, once=False):
    for analyzer in self.analyzers:
        if minperstatus < 0:
            analyzer._next()      # Normal
        elif minperstatus == 0:
            analyzer._nextstart() # First bar
        else:
            analyzer._prenext()   # Warming up

# Each analyzer tracks trades, returns, etc.
```

### 6.8 Timeline: What Happens Each Bar

```
┌─────────────────────────────────────────────────────────────────────────┐
│ BAR 1-15: Warmup Period (minperstatus > 0)                              │
├─────────────────────────────────────────────────────────────────────────┤
│ • Indicators calculating but not fully valid                           │
│ • strategy.prenext() called (does nothing in this strategy)            │
│ • analyzer._prenext() called                                            │
│ • No trading allowed                                                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ BAR 16: First Valid Bar (minperstatus == 0)                             │
├─────────────────────────────────────────────────────────────────────────┤
│ • strategy.nextstart() called                                           │
│   └── Defaults to calling next()                                       │
│ • First potential trading opportunity                                   │
│ • SMA has 15 bars of history, CrossOver has full data                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ BAR 17+: Normal Operation (minperstatus < 0)                            │
├─────────────────────────────────────────────────────────────────────────┤
│ • strategy.next() called                                               │
│ • Check self.signal[0] for crossover                                   │
│ • Issue buy/sell orders based on signal                                │
│ • Broker processes orders from previous bar                            │
│ • Notifications delivered                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 7: Shutdown

### 7.1 Strategy Stop

```python
for strat in runstrats:
    strat._stop()

def _stop(self):
    self.stop()  # User's stop() method
    
    # Stop all analyzers
    for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        analyzer._stop()
        # Analyzers finalize calculations here
        # e.g., SharpeRatio computes final ratio
    
    # Switch back to Stage 1
    self._stage1()
```

### 7.2 Broker and Data Stop

```python
self._broker.stop()

for data in self.datas:
    data.stop()

for feed in self.feeds:
    feed.stop()
```

### 7.3 Writer Output

```python
self.stop_writers(runstrats)

def stop_writers(self, runstrats):
    # Collect all info
    cerebroinfo = OrderedDict()
    cerebroinfo['Datas'] = {data info}
    cerebroinfo['Strategies'] = {strategy info, analyzer results}
    
    for writer in self.runwriters:
        writer.writedict(dict(Cerebro=cerebroinfo))
        writer.stop()
```

---

## Complete Call Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            COMPILE TIME                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  class LongShortStrategy(bt.Strategy):                                      │
│      │                                                                      │
│      └── MetaStrategy.__new__() ─┬─→ MetaLineIterator.__new__()            │
│          MetaStrategy.__init__()  │   MetaLineSeries.__new__()              │
│                                   │   MetaLineRoot.__new__()                │
│                                   │   MetaParams.__new__()                  │
│                                   └─→ MetaBase.__new__()                    │
│                                                                             │
│  Result: LongShortStrategy class with params, lines, plotinfo              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RUNTIME: SETUP                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  cerebro = bt.Cerebro()                                                     │
│      └── Cerebro.__init__(): datas=[], strats=[], broker=BackBroker()      │
│                                                                             │
│  data = BacktraderCSVData(...)                                              │
│      └── Data feed created with lines: datetime, OHLCV                     │
│                                                                             │
│  cerebro.adddata(data)                                                      │
│      └── cerebro.datas = [data]                                             │
│                                                                             │
│  cerebro.addstrategy(LongShortStrategy, period=15)                          │
│      └── cerebro.strats = [[(LongShortStrategy, (), {period:15})]]         │
│                                                                             │
│  cerebro.addanalyzer(SQN), addanalyzer(...)                                 │
│      └── cerebro.analyzers = [(SQN,...), (AnnualReturn,...), ...]          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RUNTIME: cerebro.run()                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  cerebro.run()                                                              │
│      │                                                                      │
│      ├── runstrategies(iterstrat)                                           │
│      │   │                                                                  │
│      │   ├── broker.start()                                                 │
│      │   │                                                                  │
│      │   ├── for data in datas:                                             │
│      │   │       data.reset()                                               │
│      │   │       data._start()                                              │
│      │   │       data.preload()  ← Load all CSV data into memory           │
│      │   │                                                                  │
│      │   ├── strat = LongShortStrategy(data, period=15)                     │
│      │   │   │                                                              │
│      │   │   ├── [1] donew chain: Create instance, lines, params           │
│      │   │   ├── [2] dopreinit chain: Set clock, initial minperiod         │
│      │   │   ├── [3] __init__: User code, create SMA, CrossOver            │
│      │   │   │       └── Indicators register with strategy                 │
│      │   │   └── [4] dopostinit chain: Final minperiod, register           │
│      │   │                                                                  │
│      │   ├── Add observers (Broker, BuySell, Trades)                        │
│      │   ├── Add analyzers (SQN, AnnualReturn, SharpeRatio, Trade)         │
│      │   │                                                                  │
│      │   ├── strat._start()                                                 │
│      │   │   ├── _periodset()  ← Calculate per-data minperiods             │
│      │   │   ├── analyzer._start() for each                                │
│      │   │   ├── observer._start() for each                                │
│      │   │   ├── _stage2()  ← Switch to execution mode                     │
│      │   │   └── start()  ← User's start() method                          │
│      │   │                                                                  │
│      │   └── _runonce(runstrats)  ← Main execution loop                    │
│      │                                                                      │
│      └── return runstrats                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RUNTIME: _runonce() Loop                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  _runonce(runstrats):                                                       │
│      │                                                                      │
│      ├── for strat in runstrats:                                            │
│      │       strat._once()  ← Batch process all indicators                 │
│      │       │                                                              │
│      │       ├── forward(size=buflen)  ← Allocate all lines                │
│      │       ├── for indicator in indicators:                              │
│      │       │       indicator._once()  ← SMA.once(), CrossOver.once()     │
│      │       ├── home()  ← Reset all indices to 0                          │
│      │       └── oncebinding()  ← Execute line bindings                    │
│      │                                                                      │
│      └── for i in range(data.buflen()):  ← For each bar                    │
│              │                                                              │
│              ├── data.advance()  ← Move to next bar                        │
│              │                                                              │
│              ├── _brokernotify()                                            │
│              │   ├── broker.next()  ← Process pending orders               │
│              │   └── Deliver order notifications                           │
│              │                                                              │
│              └── for strat in runstrats:                                    │
│                      strat._oncepost(dt)                                    │
│                      │                                                      │
│                      ├── forward()  ← Add new position                     │
│                      ├── self.lines.datetime[0] = dt                       │
│                      ├── _notify()  ← notify_order(), notify_trade()       │
│                      │                                                      │
│                      ├── minperstatus = _getminperstatus()                  │
│                      │   if minperstatus > 0: prenext()   ← Warmup         │
│                      │   if minperstatus == 0: nextstart() ← First valid   │
│                      │   if minperstatus < 0: next()      ← Normal         │
│                      │                                                      │
│                      ├── _next_analyzers()                                  │
│                      ├── _next_observers()                                  │
│                      └── clear()                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RUNTIME: Shutdown                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  for strat in runstrats:                                                    │
│      strat._stop()                                                          │
│      ├── stop()  ← User's stop() method                                    │
│      ├── analyzer._stop() for each  ← Finalize calculations               │
│      └── _stage1()  ← Return to setup mode                                 │
│                                                                             │
│  broker.stop()                                                              │
│  data.stop() for each                                                       │
│  stop_writers()  ← Output final results                                    │
│                                                                             │
│  return runstrats                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW                                        │
└──────────────────────────────────────────────────────────────────────────────┘

                    CSV File
                       │
                       ▼
              ┌────────────────┐
              │ BacktraderCSV  │
              │    Data Feed   │
              │    .preload()  │
              └───────┬────────┘
                      │
                      │ lines.datetime, lines.open, lines.high,
                      │ lines.low, lines.close, lines.volume
                      ▼
        ┌─────────────────────────────┐
        │        Data Buffer          │
        │  [100.1, 100.5, 99.8, ...]  │
        └─────────────┬───────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│   SMA Indicator │       │     Strategy    │
│                 │       │                 │
│  .data = close  │       │ .data = feed    │
│  .lines.sma     │       │ .data_close     │
│                 │       │ .data_high      │
└────────┬────────┘       └────────┬────────┘
         │                         │
         │ .lines.sma              │ self.signal[0]
         ▼                         │
┌─────────────────┐                │
│    CrossOver    │                │
│                 │                │
│ .data = close   │                │
│ .data1 = sma    │                │
│ .lines.crossover│                │
└────────┬────────┘                │
         │                         │
         └────────────┬────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Strategy.next │
              │               │
              │ if signal > 0 │
              │   buy()       │
              │ if signal < 0 │
              │   sell()      │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │    Broker     │
              │               │
              │ Execute Order │
              │ Update Cash   │
              │ Track Position│
              └───────┬───────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
  ┌───────────────┐       ┌───────────────┐
  │   Observers   │       │   Analyzers   │
  │               │       │               │
  │ Cash, Value   │       │ SQN           │
  │ BuySell marks │       │ AnnualReturn  │
  │ Trade markers │       │ SharpeRatio   │
  └───────────────┘       │ TradeAnalyzer │
                          └───────────────┘
```

---

## Memory Management Across the Lifecycle

This section explains how backtrader manages the memory behind every `LineBuffer` — from
initial creation through preloading, execution, and how the `exactbars` / QBuffer system
changes everything.

### Default Mode: UnBounded (`array.array`)

By default every `LineBuffer` uses an **unbounded** `array.array('d')` (C-level doubles).
The array grows by one element for each bar and **never shrinks**.

```
LineBuffer.__init__():
    self.mode = self.UnBounded   # = 0
    self.reset()

LineBuffer.reset():
    # mode == UnBounded
    self.array = array.array('d')   # empty, growable C array
    self.useislice = False           # direct slicing OK
    self.lencount = 0
    self.idx = -1                    # no current position yet
```

#### Memory layout during the lifecycle

```
                     bar 0     bar 1     bar 2    ...    bar 499
                    ┌─────────┬─────────┬─────────┬─────┬─────────┐
  data.lines.close: │  100.50 │  101.20 │   99.80 │ ... │  105.30 │  array.array('d')
                    └─────────┴─────────┴─────────┴─────┴─────────┘
                                                          ▲
                                                          │
                                                        idx = 499

  Every bar that was ever loaded stays in memory.
  After 500 bars:  len(array) = 500  →  500 × 8 bytes = 4 KB per line
  After 1M bars:   len(array) = 1,000,000  →  ~8 MB per line
  With 7 OHLCV lines × N data feeds × M indicator lines = lots of memory
```

### Lifecycle Stage 1: Object Construction (before `run()`)

At this point nothing is loaded — arrays are empty:

```python
# After strategy creation (Phase 4), before cerebro.run():

data.lines.close.array   # array.array('d') — empty, 0 elements
data.lines.close.idx     # -1
data.lines.close.mode    # UnBounded (0)

sma.lines.sma.array      # array.array('d') — empty, 0 elements
signal.lines.crossover.array  # array.array('d') — empty, 0 elements
```

### Lifecycle Stage 2: Preloading (`data._start()` + `data.preload()`)

In the default `runonce` mode, Cerebro preloads all data before any indicator runs:

```python
# cerebro._runonce():
for data in self.datas:
    data.reset()
    if self._exactbars < 1:             # True for default (exactbars=0)
        data.extend(size=self.params.lookahead)  # extend for lookahead
    data._start()
    data.preload()                       # load ALL bars from CSV into arrays
```

After preloading 500 bars of CSV data:

```
data.lines.close.array:
  ┌──────────────────────────────────────────────────────────────┐
  │ 100.50 │ 101.20 │ 99.80 │ 102.10 │ ... │ 105.30 │          │
  └──────────────────────────────────────────────────────────────┘
  index:  0       1       2       3     ...     499
  
  len(array) = 500        (all bars in memory)
  idx        = 499        (pointing at last loaded bar)
  buflen()   = 500

  Same for all 7 OHLCV lines: datetime, open, high, low, close, volume, openinterest
  Total memory for data feed: 500 × 7 × 8 bytes = 28 KB
```

### Lifecycle Stage 3: Indicator Batch Computation (`_once()`)

After preloading, indicators compute all values at once:

```python
# strat._once() → calls each indicator's _once()

# SMA._once():
#   Average._once() runs:
#     self.forward(size=500)      # grow output array to 500 NaN slots
#     self.home()                  # reset idx to -1
#     self.once(15, 500)          # compute from minperiod to end
#
#   for i in range(15, 500):
#       Average.lines.av.array[i] = fsum(data.close[i-14:i+1]) / 15
#
#   Average.oncebinding()         # copy av → sma
```

After indicator computation:

```
sma.lines.sma.array:
  ┌──────────────────────────────────────────────────────────────┐
  │  NaN  │  NaN  │ ... │  NaN  │ 100.95 │ 101.02 │ ... │104.88│
  └──────────────────────────────────────────────────────────────┘
  index: 0     1    ...   13      14       15       ...   499
                          ▲ minperiod-1    ▲ first valid value
  
  len(array) = 500  (same size as data — one slot per bar)
  Bars 0-13: NaN (not enough data for 15-period average)
  Bars 14-499: valid SMA values
```

### Lifecycle Stage 4: Bar-by-Bar Strategy Processing (`_oncepost()`)

After all indicators have computed, the strategy iterates bar-by-bar.
The arrays are already full — `_oncepost()` only advances the logical index:

```python
# For each bar i from 0 to 499:
data0.advance()                    # data0.idx += 1
for data in self.datas[1:]:
    data.advance()

dt0 = data0.datetime.datetime()

for strat in runstrats:
    strat._oncepost(dt0)
    # Inside _oncepost:
    #   for each line in lines: line.advance()   # just idx += 1
    #   strategy.next() called                    # reads values at line[0]
```

Key point: In `_once` mode, **no new memory is allocated** during the bar-by-bar loop.
All arrays were pre-filled. `advance()` just increments `idx`.

```
During bar i=200:

data.lines.close:  [..., 99.80, 102.10, ..., 105.30]
                              ▲
                            idx=200, close[0] returns array[200]

sma.lines.sma:     [..., NaN, 100.95, ..., 104.88]
                              ▲
                            idx=200, sma[0] returns array[200]

signal.lines.crossover: [..., 0.0, 1.0, ..., -1.0]
                              ▲
                            idx=200, crossover[0] returns array[200]
```

### Lifecycle Stage 5: After `run()` Completes

With default settings, **all data remains in memory**:

```python
results = cerebro.run()
strat = results[0]

# Everything is still accessible:
strat.data.close[0]         # last bar's close (idx still at end)
len(strat.data.close)       # 500

# Can plot because all history is available:
cerebro.plot()              # reads all array values for matplotlib
```

---

### QBuffer Mode: Memory-Saving with `exactbars`

When `cerebro = bt.Cerebro(exactbars=True)` (or `exactbars=1`), the entire memory
model changes. Instead of growing `array.array` objects, each `LineBuffer` uses a
fixed-size `collections.deque` that only keeps the minimum number of bars needed.

#### How `exactbars` Propagates

```
cerebro.run()
    │
    ├── self._exactbars = int(self.p.exactbars)  # e.g. 1
    │
    ├── self._dorunonce = False   # QBuffer forces step-by-step mode
    │   # (because indicators need to compute before old values are discarded)
    │
    ├── self._dopreload = False   # (for exactbars >= 1)
    │   # (cannot preload everything if we're saving memory)
    │
    │   ... strategy created, observers/analyzers added ...
    │
    └── strat.qbuffer(self._exactbars, replaying=self._doreplay)
        │
        │   # Strategy.qbuffer(savemem=1):
        │
        ├── for data in self.datas:
        │       data.qbuffer(replaying=False)
        │       # → for each of data's 7 lines:
        │       #     line.qbuffer(savemem=0, extrasize=0)
        │       #     line.mode = QBuffer
        │       #     line.maxlen = line._minperiod  (= 1 for data lines)
        │       #     line.array = deque(maxlen=1)
        │
        ├── for line in self.lines:
        │       line.qbuffer(savemem=1)
        │       # strategy's datetime line → deque(maxlen=1)
        │
        └── for itcls in self._lineiterators:
                for it in self._lineiterators[itcls]:
                    it.qbuffer(savemem=1)
                    │
                    │   # LineIterator.qbuffer(savemem=1):
                    │   # For each indicator (SMA, CrossOver, etc.):
                    │
                    ├── for line in self.lines:
                    │       line.qbuffer()
                    │       # sma.lines.sma → deque(maxlen=15)
                    │       # signal.lines.crossover → deque(maxlen=16)
                    │
                    ├── for obj in self._lineiterators[IndType]:
                    │       obj.qbuffer(savemem=1)
                    │       # Sub-indicators also switch to QBuffer
                    │
                    └── for data in self.datas:
                            data.minbuffer(self._minperiod)
                            # Ensures data deque is large enough
                            # for this indicator's needs
```

#### The `minbuffer()` Negotiation

Different indicators need different amounts of history. A 15-period SMA needs
at least 15 bars of data. The `minbuffer()` call ensures each data line's deque
is large enough:

```python
# LineBuffer.minbuffer(size):
def minbuffer(self, size):
    if self.mode != self.QBuffer or self.maxlen >= size:
        return              # already big enough, skip
    
    self.maxlen = size      # enlarge
    self.lenmark = self.maxlen - (not self.extrasize)
    self.reset()            # recreate deque with new maxlen

# Example negotiation for our sample:
#
# Initial: data.lines.close.maxlen = 1  (data's own minperiod)
#
# SMA calls: data.lines.close.minbuffer(15)
#   → maxlen becomes 15
#
# CrossOver calls: data.lines.close.minbuffer(16)
#   → maxlen becomes 16
#
# Final: data.lines.close = deque(maxlen=16)
#   Only the last 16 close values are kept!
```

#### QBuffer Memory Layout

```
After 200 bars with QBuffer (maxlen=16 for data.close):

data.lines.close:
  collections.deque(maxlen=16):
  ┌────────┬────────┬────────┬─────┬────────┐
  │ 101.30 │ 100.80 │ 102.50 │ ... │ 103.70 │   ← only 16 values!
  └────────┴────────┴────────┴─────┴────────┘
  positions: 0(=bar185)  1(=bar186) ...  15(=bar200)
  
  idx = 15 (clamped at lenmark, doesn't grow beyond maxlen-1)
  
  Bars 0-184: GONE (automatically discarded by deque)
  
  Memory: 16 × 8 = 128 bytes (vs 1600 bytes in UnBounded mode)

sma.lines.sma:
  collections.deque(maxlen=15):
  ┌────────┬────────┬─────┬────────┐
  │ 101.10 │ 101.25 │ ... │ 102.88 │   ← only 15 values
  └────────┴────────┴─────┴────────┘
  
  Memory: 15 × 8 = 120 bytes
```

#### How `deque` Auto-Discards Old Values

The key mechanism is Python's `collections.deque(maxlen=N)`:

```python
from collections import deque

# Create a deque that holds at most 3 items
d = deque(maxlen=3)

d.append(100)    # d = [100]
d.append(200)    # d = [100, 200]
d.append(300)    # d = [100, 200, 300]  ← full
d.append(400)    # d = [200, 300, 400]  ← 100 auto-discarded!
d.append(500)    # d = [300, 400, 500]  ← 200 auto-discarded!

# This is exactly what happens when LineBuffer.forward() appends:
# def forward(self, value=NAN, size=1):
#     self.idx += size
#     self.lencount += size
#     for i in range(size):
#         self.array.append(value)    # deque auto-discards oldest
```

#### QBuffer Changes Data Access: `useislice`

In QBuffer mode, direct array slicing doesn't work because `deque` doesn't support
Python slice notation efficiently. The `get()` method switches to `itertools.islice`:

```python
# LineBuffer.get() — called by e.g. Average to fetch last N values:

def get(self, ago=0, size=1):
    if self.useislice:    # True when mode == QBuffer
        start = self.idx + ago - size + 1
        end = self.idx + ago + 1
        return list(islice(self.array, start, end))
        # islice works on any iterable, including deque
    
    # UnBounded mode: direct slice (faster)
    return self.array[self.idx + ago - size + 1:self.idx + ago + 1]

# Example:
# In QBuffer mode, SMA computing 15-period average:
#   self.data.get(size=15)
#   → list(islice(deque, start, end))
#   → returns list of the last 15 values in the deque
```

#### QBuffer Changes Index Behavior: `set_idx`

The idx property setter prevents the index from growing past the deque size:

```python
def set_idx(self, idx, force=False):
    if self.mode == self.QBuffer:
        if force or self._idx < self.lenmark:
            self._idx = idx
        # else: idx stays clamped at lenmark
        # This means idx stops growing once the deque is full
    else:
        self._idx = idx    # unbounded: always updates

# Example timeline (maxlen=3, lenmark=2):
#
# Bar 0: forward() → idx=0, deque=[NaN]
# Bar 1: forward() → idx=1, deque=[NaN, NaN]
# Bar 2: forward() → idx=2, deque=[NaN, NaN, NaN]  ← idx reaches lenmark
# Bar 3: forward() → idx stays 2, deque=[NaN, NaN, NaN]  ← oldest pushed out
#         idx is clamped! self[0] always reads deque[2] = last element
```

#### Execution Mode Changes with QBuffer

QBuffer forces `_runnext()` (step-by-step) instead of `_runonce()` (batch):

```python
# In cerebro.run():
self._exactbars = int(self.p.exactbars)

if self._exactbars:
    self._dorunonce = False    # CANNOT batch-process with rolling buffers
    self._dopreload = self._dopreload and self._exactbars < 1
    # For exactbars >= 1: _dopreload = False

# Why? Because in _runonce() mode:
#   1. All data is preloaded into full arrays
#   2. All indicators compute in one pass via _once()
#   3. Then bar-by-bar iteration just advances idx
#
# With QBuffer this is impossible because:
#   1. Data can't be fully preloaded (deque discards old values)
#   2. Indicators must compute step-by-step so that values are
#      consumed before being discarded
#
# So execution falls through to _runnext():
if self._dopreload and self._dorunonce:
    self._runonce(runstrats)     # ← NOT taken with QBuffer
else:
    self._runnext(runstrats)     # ← QBuffer uses this path
```

Step-by-step execution with QBuffer:

```
For each bar:

1. data._next()
   └── data.lines.close.forward(value=100.50)
       # deque.append(100.50) → oldest auto-discarded if full

2. strat._next()
   └── for each indicator: indicator._next()
       │
       ├── sma._next()
       │   └── Average._next()
       │       └── Average.next():
       │           self.line[0] = fsum(self.data.get(size=15)) / 15
       │           # Reads last 15 from deque via islice
       │           # Writes result → triggers binding → sma.lines.sma[0] = value
       │           # The deque for sma.lines.sma.append(value)
       │           #   oldest SMA value auto-discarded if deque full
       │
       └── signal._next()
           └── CrossOver._next() → ... → crossover[0] = value

3. strat.next()
   └── reads crossover[0]  (latest value in deque)
       if self.signal > 0: self.buy()
```

### Negative `exactbars`: Partial Memory Saving for Plotting

```
exactbars value │ Behavior
────────────────┼──────────────────────────────────────────────────────
      0 (False) │ Default. All values kept. Plotting works. runonce works.
                │ array.array('d') for everything.
────────────────┼──────────────────────────────────────────────────────
      1 (True)  │ Maximum saving. Everything uses QBuffer (deque).
                │ No preloading. No runonce. No plotting.
────────────────┼──────────────────────────────────────────────────────
     -1         │ Indicators at strategy level + observers keep full data.
                │ Sub-indicators (inside other indicators) use QBuffer.
                │ Data feeds keep full data (preload works).
                │ Plotting works for strategy-level indicators.
────────────────┼──────────────────────────────────────────────────────
     -2         │ Same as -1, plus: indicators with plotinfo.plot=False
                │ also use QBuffer (since they won't be plotted anyway).
                │ Slightly more memory saved than -1.
```

How the strategy's `qbuffer()` implements negative values:

```python
def qbuffer(self, savemem=0, replaying=False):
    if savemem < 0:
        # Only save memory for sub-indicators, not strategy-level ones
        for ind in self._lineiterators[self.IndType]:
            subsave = isinstance(ind, (LineSingle,))
            # LineSingle = line operations (always safe to save)
            
            if not subsave and savemem < -1:   # exactbars == -2
                subsave = not ind.plotinfo.plot
                # Also save if indicator is not plotted
            
            ind.qbuffer(savemem=subsave)
            # subsave=False (0) → indicator keeps full data
            # subsave=True (1) → indicator uses QBuffer

    elif savemem > 0:
        # Save everything
        for data in self.datas:
            data.qbuffer(replaying=replaying)
        for line in self.lines:
            line.qbuffer(savemem=1)
        for itcls in self._lineiterators:
            for it in self._lineiterators[itcls]:
                it.qbuffer(savemem=1)
```

### Concrete Example: Memory Comparison for the Sample

For the analyzer-annualreturn sample with ~500 bars of OHLCV data:

```
Component                  │ Lines │ UnBounded (default)  │ QBuffer (exactbars=1)
───────────────────────────┼───────┼──────────────────────┼──────────────────────
BacktraderCSVData          │   7   │ 500 × 7 = 3,500     │ 16 × 7 = 112
  (datetime,O,H,L,C,V,OI) │       │ doubles              │ doubles
                           │       │                      │ (maxlen=16, negotiated)
───────────────────────────┼───────┼──────────────────────┼──────────────────────
SMA (period=15)            │   1   │ 500 × 1 = 500       │ 15 × 1 = 15
  .lines.sma               │       │                      │ (maxlen=15)
───────────────────────────┼───────┼──────────────────────┼──────────────────────
Average (inside SMA)       │   1   │ 500 × 1 = 500       │ 15 × 1 = 15
  .lines.av                │       │                      │
───────────────────────────┼───────┼──────────────────────┼──────────────────────
CrossOver                  │   1   │ 500 × 1 = 500       │ 16 × 1 = 16
  .lines.crossover         │       │                      │ (maxlen=16)
───────────────────────────┼───────┼──────────────────────┼──────────────────────
CrossUp                    │   1   │ 500 × 1 = 500       │ 2 × 1 = 2
  .lines.cross             │       │                      │
───────────────────────────┼───────┼──────────────────────┼──────────────────────
CrossDown                  │   1   │ 500 × 1 = 500       │ 2 × 1 = 2
  .lines.cross             │       │                      │
───────────────────────────┼───────┼──────────────────────┼──────────────────────
NonZeroDiff (×2)           │   2   │ 500 × 2 = 1,000     │ ~2 × 2 = 4
───────────────────────────┼───────┼──────────────────────┼──────────────────────
LinesOperation (×several)  │  ~5   │ 500 × 5 = 2,500     │ ~2 × 5 = 10
  (subtraction, And, etc.) │       │                      │
───────────────────────────┼───────┼──────────────────────┼──────────────────────
Strategy                   │   1   │ 500 × 1 = 500       │ 1 × 1 = 1
  .lines.datetime          │       │                      │
───────────────────────────┼───────┼──────────────────────┼──────────────────────
Observers (Broker, etc.)   │  ~5   │ 500 × 5 = 2,500     │ ~1 × 5 = 5
───────────────────────────┼───────┼──────────────────────┼──────────────────────
TOTAL doubles              │ ~25   │ ~12,500              │ ~182
TOTAL bytes (×8)           │       │ ~100 KB              │ ~1.5 KB
───────────────────────────┼───────┼──────────────────────┼──────────────────────
Can plot?                  │       │ Yes                  │ No
Can use _runonce()?        │       │ Yes                  │ No
```

With 500 bars the difference is small, but with 10 million bars of tick data:

```
UnBounded: 10,000,000 × 25 × 8 = ~2 GB
QBuffer:   182 × 8             = ~1.5 KB   (same regardless of bar count!)
```

### Visual Timeline: Memory States

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     UNBOUNDED MODE (default)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Construction    Preload          _once()          _oncepost()    plot()    │
│  ┌─────┐        ┌──────────┐    ┌──────────┐    ┌──────────┐  ┌────────┐  │
│  │empty│───────►│load 500  │───►│compute   │───►│advance   │─►│read    │  │
│  │array│        │bars into │    │all ind   │    │idx only  │  │all     │  │
│  │     │        │array     │    │values    │    │no alloc  │  │values  │  │
│  └─────┘        └──────────┘    └──────────┘    └──────────┘  └────────┘  │
│  0 bytes         4 KB/line       +4 KB/ind       same          same       │
│                  (growing)       (growing)       (no growth)   (read-only)│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                     QBUFFER MODE (exactbars=1)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Construction    qbuffer()        _runnext() per bar                        │
│  ┌─────┐        ┌──────────┐    ┌──────────────────────────────┐            │
│  │empty│───────►│switch to │───►│ for each bar:                │            │
│  │array│        │deque     │    │   data.forward() → append    │            │
│  │     │        │maxlen=N  │    │   (oldest auto-discarded)    │            │
│  └─────┘        └──────────┘    │   ind._next() → compute 1   │            │
│  0 bytes         128 bytes      │   strat.next() → trade      │   NO PLOT  │
│                  (fixed!)       │   memory stays constant!     │            │
│                                 └──────────────────────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Example: Enabling QBuffer in the Sample

```python
# Original sample (default — all data kept):
cerebro = bt.Cerebro()

# Modified for memory saving:
cerebro = bt.Cerebro(exactbars=True)   # or exactbars=1

# What changes:
# 1. cerebro._dorunonce = False        (no batch mode)
# 2. cerebro._dopreload = False        (no full preload)
# 3. strat.qbuffer(1) called           (all lines → deque)
# 4. cerebro._runnext() used           (step-by-step)
# 5. cerebro.plot() disabled           (no history to plot)
#
# Trade-off: much less memory, but slower execution
# (step-by-step is ~2-5x slower than batch _runonce)
```

```python
# Compromise: save some memory but keep plotting:
cerebro = bt.Cerebro(exactbars=-1)

# What changes:
# 1. Data feeds keep ALL bars (can preload)
# 2. Strategy-level indicators (SMA, CrossOver) keep ALL values
# 3. Sub-indicators (Average inside SMA, NonZeroDiff inside CrossOver) use QBuffer
# 4. Can still plot strategy-level indicators
# 5. Still forces _runnext() (step-by-step, no batch mode)
```

```python
# Even more aggressive partial saving:
cerebro = bt.Cerebro(exactbars=-2)

# Same as -1, plus:
# Any indicator with plotinfo.plot = False also uses QBuffer
# Useful when you have many indicators but only plot a few
```

### The `minbuffer()` Negotiation in Detail

When QBuffer is active, a critical negotiation happens to ensure no indicator
loses data it needs. Here's the exact sequence for our sample:

```
1. Strategy.qbuffer(savemem=1) called by Cerebro

2. Data lines initially set to minperiod:
   data.lines.close.qbuffer()  → deque(maxlen=1)
   data.lines.high.qbuffer()   → deque(maxlen=1)
   ... (all 7 lines: maxlen=1)

3. SMA.qbuffer(savemem=1) called:
   │
   ├── sma.lines.sma.qbuffer()  → deque(maxlen=15)
   │
   ├── Average.qbuffer(savemem=1)  (sub-indicator)
   │   └── Average.lines.av.qbuffer()  → deque(maxlen=15)
   │
   └── for data in self.datas:
           data.minbuffer(self._minperiod)
           # data.lines.close.minbuffer(15)
           # maxlen was 1, now 15 < 15? No, 15 >= 15 → OK (becomes 15)
           # Actually 1 < 15, so maxlen → 15, deque recreated

4. CrossOver.qbuffer(savemem=1) called:
   │
   ├── signal.lines.crossover.qbuffer()  → deque(maxlen=16)
   │
   ├── CrossUp.qbuffer(savemem=1)
   │   └── CrossUp needs data.close.minbuffer(16)
   │       # maxlen was 15, 15 < 16 → enlarge to 16!
   │
   ├── CrossDown.qbuffer(savemem=1)
   │   └── CrossDown also calls data.close.minbuffer(16)
   │       # maxlen is already 16 >= 16 → skip
   │
   └── signal calls data.minbuffer(16)
       # Already 16, skip

5. Final deque sizes:
   data.lines.close:         deque(maxlen=16)    ← negotiated up from 1
   data.lines.high:          deque(maxlen=1)     ← nobody needed more
   data.lines.open:          deque(maxlen=1)
   sma.lines.sma:            deque(maxlen=15)
   signal.lines.crossover:   deque(maxlen=16)
```

---

## Key Takeaways

1. **Metaclass Chain**: Class creation flows through 6+ metaclasses, each adding functionality
2. **Two-Phase Execution**: Stage 1 (setup) creates line objects; Stage 2 (execution) returns values
3. **findowner()**: Automatically links child objects (indicators) to parents (strategy) via call stack
4. **Minperiod Propagation**: Each component calculates required warmup bars; max is used
5. **Batch Processing**: `_once()` calculates all indicator values at once; `_oncepost()` iterates bar-by-bar
6. **Order Flow**: buy() → broker → notification → notify_order()
7. **Analyzer Integration**: Analyzers receive same lifecycle calls as strategy (prenext, next, stop)
8. **Memory Management**: Default mode keeps all values in `array.array`; QBuffer mode uses fixed-size `deque` for constant memory usage regardless of bar count
9. **Memory Trade-offs**: `exactbars=1` saves maximum memory but disables plotting and batch mode; negative values (`-1`, `-2`) offer a compromise preserving plottable data
