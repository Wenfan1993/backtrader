# Backtrader Line System - Complete Architecture Guide

This document provides a comprehensive explanation of backtrader's line-based architecture, covering all core classes, their relationships, and how they work together.

---

## Table of Contents

1. [Overview & Class Hierarchy](#overview--class-hierarchy)
2. [The Foundation: metabase.py](#the-foundation-metabasepy)
3. [Metaclass Lifecycle](#metaclass-lifecycle)
4. [Core Classes Explained](#core-classes-explained)
5. [Key Mechanisms](#key-mechanisms)
6. [Complete Examples](#complete-examples)
7. [Execution Flow](#execution-flow)

---

## Overview & Class Hierarchy

### The Complete Inheritance Chain

```
object
│
├── MetaBase (metaclass) ─────────────────────────────────────────────────┐
│       │                                                                  │
│       └── MetaParams ──► MetaLineRoot ──► MetaLineSeries ──► MetaLineIterator
│                                │                                         │
│                                ▼                                         │
├── LineRoot ◄───────────────────┘                                         │
│       │                                                                  │
│       ├── LineSingle                                                     │
│       │       │                                                          │
│       │       └── LineBuffer ──► LineActions ──► LinesOperation          │
│       │                                      └── LineOwnOperation        │
│       │                                      └── _LineDelay              │
│       │                                                                  │
│       └── LineMultiple                                                   │
│               │                                                          │
│               └── LineSeries (uses MetaLineSeries) ◄─────────────────────┘
│                       │
│                       └── LineIterator (uses MetaLineIterator)
│                               │
│                               ├── IndicatorBase ──► Indicator
│                               ├── StrategyBase ──► Strategy
│                               └── ObserverBase ──► Observer
│
└── Lines (container for LineBuffer objects)
        │
        └── Lines_<ClassName> (dynamically created subclasses)
```

### Purpose of Each Layer

| Layer | Purpose |
|-------|---------|
| `LineRoot` | Base interface: minperiod, operations, comparisons |
| `LineSingle` | Single line (one data series) |
| `LineMultiple` | Multiple lines (container) |
| `LineBuffer` | Actual data storage (array + index management) |
| `Lines` | Collection of LineBuffers with proxy operations |
| `LineSeries` | Named lines with descriptors and plotting |
| `LineIterator` | Iteration logic for backtesting |
| `Indicator/Strategy/Observer` | User-facing classes |

---

## The Foundation: metabase.py

The `metabase.py` file is the **foundation of backtrader's entire metaclass system**. It provides the base metaclass, helper functions, parameter handling, and utility classes that all other components build upon.

### File Structure Overview

```
metabase.py
├── Helper Functions
│   ├── findbases()     - Find all base classes in hierarchy
│   └── findowner()     - Walk call stack to find owner object
│
├── Core Metaclass
│   └── MetaBase        - 5-phase object creation lifecycle
│
├── Auto-Info System
│   └── AutoInfoClass   - Dynamic class derivation for params/plotinfo
│
├── Parameter System
│   ├── MetaParams      - Metaclass for parameter handling
│   └── ParamsBase      - Base class with MetaParams
│
└── Utility Classes
    └── ItemCollection  - Named collection with index/name access
```

---

### Helper Functions

#### `findbases(kls, topclass)` - Find Base Classes

Recursively finds all base classes that inherit from a specific top class.

```python
def findbases(kls, topclass):
    """
    Recursively find all bases of 'kls' that are subclasses of 'topclass'.
    Returns them in order from most distant ancestor to immediate parent.
    """
    retval = list()
    for base in kls.__bases__:
        if issubclass(base, topclass):
            retval.extend(findbases(base, topclass))  # Recurse first
            retval.append(base)                        # Then add this base
    return retval
```

**Example:**
```python
class A(LineRoot): pass
class B(A): pass
class C(B): pass

findbases(C, LineRoot)
# Returns: [LineRoot, A, B] - ancestors in order
```

**Used for:** Collecting inherited parameters, lines, and plotinfo from all ancestors.

---

#### `findowner(owned, cls, startlevel=2, skip=None)` - Ownership Discovery

**This is one of the most important functions in backtrader.** It walks the Python call stack to automatically discover the "owner" of an object.

```python
def findowner(owned, cls, startlevel=2, skip=None):
    """
    Walk the call stack to find an object of type 'cls' that can be the owner.
    
    Args:
        owned: The object looking for its owner
        cls: The class type the owner must be
        startlevel: Stack frame to start at (2 = skip this func and caller)
        skip: Object to skip (avoid self-referencing)
    """
    for framelevel in itertools.count(startlevel):
        try:
            frame = sys._getframe(framelevel)
        except ValueError:
            # Frame depth exceeded ... no owner
            break

        # Check 'self' in regular code (inside methods)
        self_ = frame.f_locals.get('self', None)
        if skip is not self_:
            if self_ is not owned and isinstance(self_, cls):
                return self_

        # Check '_obj' in metaclasses (during object creation)
        obj_ = frame.f_locals.get('_obj', None)
        if skip is not obj_:
            if obj_ is not owned and isinstance(obj_, cls):
                return obj_

    return None
```

**How it works - Visual Example:**

```python
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(period=20)
```

When `SMA()` is called, the call stack looks like:

```
Frame 0: findowner() itself
Frame 1: MetaLineRoot.donew() - has '_obj' = sma instance
Frame 2: MetaBase.__call__()
Frame 3: SMA.__init__() - but SMA isn't created yet
Frame 4: MetaLineIterator.doinit()
Frame 5: MetaBase.__call__()
Frame 6: MyStrategy.__init__() - has 'self' = strategy instance ✓
```

The function finds `self` at frame 6, which is the Strategy instance, and returns it as the owner.

**Result:** `sma._owner = strategy` - automatically set without explicit passing!

---

### MetaBase - The Core Metaclass

`MetaBase` defines the **5-phase object creation lifecycle** that all backtrader metaclasses use.

```python
class MetaBase(type):
    def doprenew(cls, *args, **kwargs):
        """Phase 1: Before object creation - can modify class or args"""
        return cls, args, kwargs

    def donew(cls, *args, **kwargs):
        """Phase 2: Object creation - create the instance"""
        _obj = cls.__new__(cls, *args, **kwargs)
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        """Phase 3: Before __init__ - setup before user code"""
        return _obj, args, kwargs

    def doinit(cls, _obj, *args, **kwargs):
        """Phase 4: Call __init__ - run user's initialization"""
        _obj.__init__(*args, **kwargs)
        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        """Phase 5: After __init__ - cleanup and registration"""
        return _obj, args, kwargs

    def __call__(cls, *args, **kwargs):
        """Orchestrates the 5-phase lifecycle"""
        cls, args, kwargs = cls.doprenew(*args, **kwargs)
        _obj, args, kwargs = cls.donew(*args, **kwargs)
        _obj, args, kwargs = cls.dopreinit(_obj, *args, **kwargs)
        _obj, args, kwargs = cls.doinit(_obj, *args, **kwargs)
        _obj, args, kwargs = cls.dopostinit(_obj, *args, **kwargs)
        return _obj
```

**Why 5 phases?**

| Phase | Purpose | Example Use |
|-------|---------|-------------|
| `doprenew` | Modify class before creation | Cache lookup, class transformation |
| `donew` | Create object, consume args | Extract datas, create lines instance |
| `dopreinit` | Setup before user's `__init__` | Set clock, initial minperiod |
| `doinit` | Run user's `__init__` | User defines indicators |
| `dopostinit` | Finalize after user code | Calculate final minperiod, register |

**Key insight:** Each phase can modify `args` and `kwargs`, consuming parameters before passing to the next phase. This enables automatic parameter extraction.

---

### AutoInfoClass - Dynamic Class Derivation

`AutoInfoClass` is a base for dynamically-derived info classes like `params`, `plotinfo`, and `plotlines`.

```python
class AutoInfoClass(object):
    _getpairsbase = classmethod(lambda cls: OrderedDict())
    _getpairs = classmethod(lambda cls: OrderedDict())
    _getrecurse = classmethod(lambda cls: False)
```

#### The `_derive()` Method

This is the core mechanism for creating subclasses with merged attributes:

```python
@classmethod
def _derive(cls, name, info, otherbases, recurse=False):
    """
    Create a new subclass with merged info from:
    1. This class's existing pairs (baseinfo)
    2. Other base classes (obasesinfo)  
    3. New info being added (info)
    """
    # Collect existing info
    baseinfo = cls._getpairs().copy()
    
    # Collect from other bases
    obasesinfo = OrderedDict()
    for obase in otherbases:
        if isinstance(obase, (tuple, dict)):
            obasesinfo.update(obase)
        else:
            obasesinfo.update(obase._getpairs())
    
    # Merge: base + otherbases + new
    baseinfo.update(obasesinfo)
    clsinfo = baseinfo.copy()
    clsinfo.update(info)
    
    # Create unique class name
    newclsname = str(cls.__name__ + '_' + name)
    namecounter = 1
    while hasattr(clsmodule, newclsname):
        newclsname += str(namecounter)
        namecounter += 1
    
    # Create the new class
    newcls = type(newclsname, (cls,), {})
    
    # Set class methods to return the merged info
    setattr(newcls, '_getpairsbase', classmethod(lambda cls: baseinfo.copy()))
    setattr(newcls, '_getpairs', classmethod(lambda cls: clsinfo.copy()))
    
    # If recursive, derive nested items too
    if recurse:
        for infoname, infoval in info.items():
            recursecls = getattr(newcls, infoname, AutoInfoClass)
            infoval = recursecls._derive(name + '_' + infoname, infoval, [])
            setattr(newcls, infoname, infoval)
    
    return newcls
```

**Example: How params are derived:**

```python
class BaseIndicator(Indicator):
    params = (('period', 10),)

class SMA(BaseIndicator):
    params = (('period', 20), ('plotname', 'SMA'))
```

**Derivation process:**
```
1. BaseIndicator.params._derive('SMA', (('period', 20), ('plotname', 'SMA')), [])

2. baseinfo = {'period': 10}  (from BaseIndicator)
3. obasesinfo = {}            (no other bases)
4. clsinfo = {'period': 20, 'plotname': 'SMA'}  (merged, period overwritten)

5. Creates: AutoInfoClass_SMA with _getpairs() returning:
   OrderedDict([('period', 20), ('plotname', 'SMA')])
```

#### Instance Methods

```python
def isdefault(self, pname):
    """Check if parameter still has default value"""
    return self._get(pname) == self._getkwargsdefault()[pname]

def notdefault(self, pname):
    """Check if parameter was modified from default"""
    return self._get(pname) != self._getkwargsdefault()[pname]

def _getkwargs(self, skip_=False):
    """Get all parameters as OrderedDict"""
    return OrderedDict([
        (x, getattr(self, x))
        for x in self._getkeys() 
        if not skip_ or not x.startswith('_')
    ])

def _getvalues(self):
    """Get just the values (used for plot labels)"""
    return [getattr(self, x) for x in self._getkeys()]
```

---

### MetaParams - Parameter Handling Metaclass

`MetaParams` extends `MetaBase` to handle the `params` class attribute.

#### Class Creation (`__new__`)

```python
class MetaParams(MetaBase):
    def __new__(meta, name, bases, dct):
        # Extract params from class definition
        newparams = dct.pop('params', ())  # Remove to avoid repetition
        
        # Also handle packages for imports
        newpackages = tuple(dct.pop('packages', ()))
        fnewpackages = tuple(dct.pop('frompackages', ()))
        
        # Create the class
        cls = super(MetaParams, meta).__new__(meta, name, bases, dct)
        
        # Get parent's params class
        params = getattr(cls, 'params', AutoInfoClass)
        
        # Collect params from other base classes (multiple inheritance)
        morebasesparams = [x.params for x in bases[1:] if hasattr(x, 'params')]
        
        # Derive new params class with merged params
        cls.params = params._derive(name, newparams, morebasesparams)
        
        return cls
```

**Example:**
```python
class MyIndicator(bt.Indicator):
    params = (
        ('period', 20),
        ('factor', 1.5),
    )
```

After metaclass processing:
```python
MyIndicator.params  # AutoInfoClass_MyIndicator
MyIndicator.params._getpairs()  # OrderedDict([('period', 20), ('factor', 1.5)])
```

#### Instance Creation (`donew`)

```python
def donew(cls, *args, **kwargs):
    # Handle package imports (for talib, etc.)
    for p in cls.packages:
        pmod = __import__(p)
        setattr(clsmod, palias, pmod)
    
    # Create params instance
    params = cls.params()
    
    # Set values from kwargs, removing them from kwargs
    for pname, pdef in cls.params._getitems():
        setattr(params, pname, kwargs.pop(pname, pdef))
    
    # Create the object
    _obj, args, kwargs = super(MetaParams, cls).donew(*args, **kwargs)
    
    # Attach params to object
    _obj.params = params
    _obj.p = params  # Short alias
    
    return _obj, args, kwargs
```

**Example:**
```python
sma = bt.indicators.SMA(self.data, period=50)

# What happens:
# 1. kwargs = {'period': 50}
# 2. params = AutoInfoClass_SMA()
# 3. params.period = kwargs.pop('period', 20) = 50
# 4. sma.params = params
# 5. sma.p = params  (shortcut)

# Result:
sma.p.period  # 50
sma.params.period  # 50
```

---

### ParamsBase - Convenience Base Class

```python
class ParamsBase(with_metaclass(MetaParams, object)):
    pass  # Stub to allow easy subclassing without metaclasses
```

Use this when you want parameter handling without the full line system.

---

### ItemCollection - Named Collection Utility

A utility class for managing collections with both index and name access.

```python
class ItemCollection(object):
    """
    Holds a collection of items accessible by:
      - Index: collection[0]
      - Name: collection.myitem
    """
    def __init__(self):
        self._items = list()
        self._names = list()

    def __len__(self):
        return len(self._items)

    def append(self, item, name=None):
        setattr(self, name, item)  # Add as attribute
        self._items.append(item)
        if name:
            self._names.append(name)

    def __getitem__(self, key):
        return self._items[key]

    def getnames(self):
        return self._names

    def getitems(self):
        return zip(self._names, self._items)

    def getbyname(self, name):
        idx = self._names.index(name)
        return self._items[idx]
```

**Example:**
```python
collection = ItemCollection()
collection.append(data1, name='AAPL')
collection.append(data2, name='GOOGL')

collection[0]        # data1
collection.AAPL      # data1
collection.getnames()  # ['AAPL', 'GOOGL']
```

---

### How metabase.py Connects to the Line System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        metabase.py in the System                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MetaBase                                                                   │
│  ────────                                                                   │
│  └─► MetaParams (adds params handling)                                      │
│       └─► MetaLineRoot (adds ownership via findowner)                       │
│            └─► MetaLineSeries (adds lines, plotinfo)                        │
│                 └─► MetaLineIterator (adds data handling, registration)     │
│                                                                             │
│  AutoInfoClass                                                              │
│  ─────────────                                                              │
│  └─► Used for: params, plotinfo, plotlines, linealias                      │
│       Each uses _derive() to create inherited subclasses                    │
│                                                                             │
│  findowner()                                                                │
│  ───────────                                                                │
│  └─► Called by MetaLineRoot.donew() to auto-discover parent                │
│       Enables: sma = SMA(period=20) without passing owner                   │
│                                                                             │
│  findbases()                                                                │
│  ───────────                                                                │
│  └─► Used to collect inherited definitions from class hierarchy            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Metaclass Lifecycle

Backtrader uses a sophisticated metaclass system with a 5-phase lifecycle:

```python
class MetaBase(type):
    def __call__(cls, *args, **kwargs):
        # Phase 1: Pre-new (before object creation)
        cls, args, kwargs = cls.doprenew(*args, **kwargs)
        
        # Phase 2: New (object creation)
        _obj, args, kwargs = cls.donew(*args, **kwargs)
        
        # Phase 3: Pre-init (before __init__)
        _obj, args, kwargs = cls.dopreinit(_obj, *args, **kwargs)
        
        # Phase 4: Init (call __init__)
        _obj, args, kwargs = cls.doinit(_obj, *args, **kwargs)
        
        # Phase 5: Post-init (after __init__)
        _obj, args, kwargs = cls.dopostinit(_obj, *args, **kwargs)
        
        return _obj
```

### What Each Metaclass Does

#### MetaLineRoot
- Finds and sets the `_owner` by walking the call stack

#### MetaLineSeries  
- `__new__`: Creates `Lines`, `plotinfo`, `plotlines` subclasses from class attributes
- `donew`: Instantiates lines, creates convenience aliases (`l`, `line`, `line0`)

#### MetaLineIterator
- `donew`: Scans args for data sources, creates data aliases (`data_close`, `data0_close`)
- `dopreinit`: Sets clock, calculates initial minperiod
- `dopostinit`: Finalizes minperiod, registers with owner

---

## Core Classes Explained

### 1. LineBuffer (`linebuffer.py`)

The fundamental data container - stores values in an array with index management.

```python
class LineBuffer(LineSingle):
    """
    Key Attributes:
    - array: The actual data (array.array or deque)
    - idx: Current position index
    - _minperiod: Minimum bars needed
    - mode: UnBounded (keep all) or QBuffer (rolling window)
    - extension: Extra "future" positions
    """
    
    def __getitem__(self, ago):
        """Access value at offset from current position"""
        return self.array[self.idx + ago]
    
    def __setitem__(self, ago, value):
        """Set value at offset"""
        self.array[self.idx + ago] = value
    
    def forward(self, value=NAN, size=1):
        """Advance by adding new position(s)"""
        self.idx += size
        self.array.append(value)
    
    def __call__(self, ago):
        """Create delayed version: line(-1) = previous value"""
        return LineDelay(self, ago)
```

**Key Insight:** `line[0]` is always the current value, `line[-1]` is the previous.

### 2. Lines (`lineseries.py`)

Container that holds multiple `LineBuffer` objects and proxies operations to all of them.

```python
class Lines:
    """
    Manages a collection of LineBuffers.
    
    Key Methods:
    - _derive(): Creates subclass with new lines (used by metaclass)
    - forward/backwards/reset/home(): Applied to ALL lines
    """
    
    def __init__(self):
        self.lines = []
        for linealias in self._getlines():
            self.lines.append(LineBuffer())
    
    def forward(self, value=NAN, size=1):
        for line in self.lines:
            line.forward(value, size)
```

### 3. LineAlias (`lineseries.py`)

Descriptor that provides named access to lines.

```python
class LineAlias:
    def __init__(self, line):
        self.line = line  # Integer index!
    
    def __get__(self, obj, cls=None):
        return obj.lines[self.line]  # Return LineBuffer
    
    def __set__(self, obj, value):
        # Create binding instead of replacing
        value.addbinding(obj.lines[self.line])
```

### 4. LineSeries (`lineseries.py`)

Combines Lines with metadata (plotinfo, plotlines) and provides attribute access.

```python
class LineSeries(LineMultiple):
    def __getattr__(self, name):
        # Fallback: look in self.lines
        return getattr(self.lines, name)
    
    def __getitem__(self, key):
        # Index access goes to first line
        return self.lines[0][key]
    
    def __call__(self, ago=None, line=-1):
        # Create delayed or coupled version
        if isinstance(ago, int):
            return LineDelay(self._getline(line), ago)
        else:
            return LinesCoupler(self, ago)
```

### 5. LineIterator (`lineiterator.py`)

The execution engine - handles iteration during backtesting.

```python
class LineIterator(LineSeries):
    def _next(self):
        """Called each bar in bar-by-bar mode"""
        # 1. Sync with clock
        clock_len = self._clk_update()
        
        # 2. Update all child indicators
        for indicator in self._lineiterators[IndType]:
            indicator._next()
        
        # 3. Process notifications
        self._notify()
        
        # 4. Call appropriate method
        if clock_len > self._minperiod:
            self.next()
        elif clock_len == self._minperiod:
            self.nextstart()
        else:
            self.prenext()
    
    def _once(self):
        """Called once in vectorized mode"""
        # Process all bars at once
        self.once(self._minperiod, self.buflen())
```

---

## Key Mechanisms

### 1. Ownership Discovery

Backtrader automatically finds the "owner" of each object by walking the call stack:

```python
def findowner(owned, cls, startlevel=2, skip=None):
    """Walk call stack to find owner"""
    for framelevel in itertools.count(startlevel):
        frame = sys._getframe(framelevel)
        
        # Check 'self' in regular code
        self_ = frame.f_locals.get('self', None)
        if self_ is not owned and isinstance(self_, cls):
            return self_
        
        # Check '_obj' in metaclasses
        obj_ = frame.f_locals.get('_obj', None)
        if obj_ is not owned and isinstance(obj_, cls):
            return obj_
    
    return None
```

**Example:**
```python
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(period=20)
        # findowner() walks the stack and finds MyStrategy instance
        # sma._owner = self (the strategy)
```

### 2. Minperiod Calculation

Minperiod is calculated through a chain of operations:

```python
# 1. Base minperiod from data sources
_obj._minperiod = max([x._minperiod for x in _obj.datas])

# 2. Added during __init__ via addminperiod
class SMA(Indicator):
    def __init__(self):
        self.addminperiod(self.p.period)  # Adds period to minperiod

# 3. Propagated from operations
line_a = data.close  # minperiod = 1
line_b = bt.indicators.SMA(period=20)  # minperiod = 20
result = line_a + line_b  # minperiod = max(1, 20) = 20

# 4. Finalized after __init__
_obj._minperiod = max([x._minperiod for x in _obj.lines])
```

### 3. Registration & Iteration

When an indicator is created, it registers itself with its owner:

```python
# In MetaLineIterator.dopostinit:
if _obj._owner is not None:
    _obj._owner.addindicator(_obj)

# In LineIterator.addindicator:
def addindicator(self, indicator):
    self._lineiterators[indicator._ltype].append(indicator)
```

During iteration, the owner calls all registered children:

```python
def _next(self):
    # Children first (bottom-up calculation)
    for indicator in self._lineiterators[IndType]:
        indicator._next()
    
    # Then self
    self.next()
```

### 4. Line Operations (Lazy Evaluation)

Operations on lines create new line objects rather than computing immediately:

```python
# During __init__ (Stage 1):
self.diff = self.data.close - self.data.open
# This creates a LinesOperation object, NOT a number!

class LinesOperation(LineActions):
    def __init__(self, a, b, operation):
        self.a = a
        self.b = b
        self.operation = operation
    
    def next(self):
        # Computed during backtest
        self[0] = self.operation(self.a[0], self.b[0])
```

### 5. Bindings

Bindings allow one line to automatically copy values to another:

```python
# Creating a binding
source_line.addbinding(target_line)

# When source_line is written:
def __setitem__(self, ago, value):
    self.array[self.idx + ago] = value
    for binding in self.bindings:
        binding[ago] = value  # Automatically propagates!
```

---

## Complete Examples

### Example 1: Simple Moving Average

```python
class SMA(bt.Indicator):
    lines = ('sma',)
    params = (('period', 20),)
    
    def __init__(self):
        self.lines.sma = bt.indicators.Average(self.data, period=self.p.period)
```

**What happens during creation:**

```
1. MetaLineSeries.__new__():
   - Creates Lines_SMA with 'sma' line
   - Creates plotinfo_SMA, plotlines_SMA

2. MetaLineIterator.donew():
   - Scans args (no explicit data provided)
   - Uses owner's data: sma.datas = [strategy.data]
   - Creates aliases: sma.data, sma.data_close, etc.

3. MetaLineIterator.dopreinit():
   - Sets clock: sma._clock = strategy.data
   - Initial minperiod: sma._minperiod = 1

4. SMA.__init__() executes:
   - Creates Average indicator (sub-indicator)
   - LineAlias.__set__ creates binding from Average to sma line

5. MetaLineIterator.dopostinit():
   - Recalculates minperiod: sma._minperiod = 20
   - Registers: strategy._lineiterators[0].append(sma)
```

### Example 2: MACD Indicator

```python
class MACD(bt.Indicator):
    lines = ('macd', 'signal', 'histo')
    params = (
        ('fast', 12),
        ('slow', 26),
        ('signal', 9),
    )
    
    def __init__(self):
        ema_fast = bt.indicators.EMA(self.data, period=self.p.fast)
        ema_slow = bt.indicators.EMA(self.data, period=self.p.slow)
        
        self.l.macd = ema_fast - ema_slow
        self.l.signal = bt.indicators.EMA(self.l.macd, period=self.p.signal)
        self.l.histo = self.l.macd - self.l.signal
```

**Ownership chain:**
```
Strategy (owner)
    └── MACD (owned by Strategy)
            ├── EMA_fast (owned by MACD)
            ├── EMA_slow (owned by MACD)
            ├── LinesOperation (macd = fast - slow, owned by MACD)
            ├── EMA_signal (owned by MACD)
            └── LinesOperation (histo = macd - signal, owned by MACD)
```

**Minperiod calculation:**
```
EMA_fast:  minperiod = 12
EMA_slow:  minperiod = 26
macd:      minperiod = max(12, 26) = 26
signal:    minperiod = 26 + 9 - 1 = 34
histo:     minperiod = max(26, 34) = 34
MACD:      minperiod = 34
```

### Example 3: Custom Indicator with Manual next()

```python
class MyRSI(bt.Indicator):
    lines = ('rsi', 'overbought', 'oversold')
    params = (
        ('period', 14),
        ('upper', 70),
        ('lower', 30),
    )
    
    def __init__(self):
        self.addminperiod(self.p.period)
        
        # Pre-calculate change
        self.change = self.data - self.data(-1)
    
    def next(self):
        # Get last 'period' changes
        changes = [self.change[-i] for i in range(self.p.period)]
        
        gains = sum(c for c in changes if c > 0)
        losses = abs(sum(c for c in changes if c < 0))
        
        if losses == 0:
            rs = 100
        else:
            rs = gains / losses
        
        self.l.rsi[0] = 100 - (100 / (1 + rs))
        self.l.overbought[0] = self.p.upper
        self.l.oversold[0] = self.p.lower
```

### Example 4: Strategy Using All Concepts

```python
class MyStrategy(bt.Strategy):
    params = (
        ('sma_period', 20),
        ('rsi_period', 14),
    )
    
    def __init__(self):
        # Simple indicator
        self.sma = bt.indicators.SMA(self.data, period=self.p.sma_period)
        
        # Indicator of indicator
        self.sma_slope = self.sma - self.sma(-1)
        
        # Multiple data access
        self.rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)
        
        # Cross detection
        self.cross = bt.indicators.CrossOver(self.data.close, self.sma)
    
    def prenext(self):
        # Called during warmup (before minperiod met)
        print(f'Warming up: bar {len(self)}')
    
    def nextstart(self):
        # Called once when minperiod is met
        print(f'Starting: bar {len(self)}, SMA ready at {self.sma[0]:.2f}')
        self.next()
    
    def next(self):
        # Normal execution
        if self.cross[0] > 0:  # Bullish cross
            if self.rsi[0] < 70:  # Not overbought
                self.buy()
        elif self.cross[0] < 0:  # Bearish cross
            if self.rsi[0] > 30:  # Not oversold
                self.sell()
```

**Resulting structure:**
```
Strategy
│
├── _lineiterators[IndType] = [sma, sma_slope, rsi, cross]
│
├── datas = [data_feed]
│
├── Aliases:
│   ├── data = datas[0]
│   ├── data_close = datas[0].lines.close
│   ├── data0 = datas[0]
│   └── data0_close = datas[0].lines.close
│
└── Minperiod = max(20, 21, 14, 21) = 21
```

---

## Execution Flow

### Bar-by-Bar Mode (runonce=False)

```
For each bar:
┌─────────────────────────────────────────────────────────────────────────┐
│  1. Data feed advances (forward)                                        │
│                                                                         │
│  2. Cerebro calls strategy._next()                                      │
│     │                                                                   │
│     ├─► strategy._clk_update()  → Sync with data                       │
│     │                                                                   │
│     ├─► for each indicator:                                            │
│     │       indicator._next()                                          │
│     │       │                                                          │
│     │       ├─► indicator._clk_update()                               │
│     │       ├─► for each sub-indicator:                               │
│     │       │       sub_indicator._next()  (recursive)                │
│     │       └─► indicator.next()  (calculate value)                   │
│     │                                                                   │
│     ├─► strategy._notify()  → Process orders, trades                   │
│     │                                                                   │
│     └─► strategy.next()  → Execute trading logic                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Vectorized Mode (runonce=True, default)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. All data loaded into arrays                                         │
│                                                                         │
│  2. strategy._once() called once:                                       │
│     │                                                                   │
│     ├─► forward(size=all_bars)  → Allocate all space                   │
│     │                                                                   │
│     ├─► for each indicator:                                            │
│     │       indicator._once()                                          │
│     │       └─► indicator.once(start, end)  (vectorized calc)          │
│     │                                                                   │
│     ├─► home()  → Reset all indices to start                           │
│     │                                                                   │
│     └─► Iterate through bars calling strategy.next()                   │
│         (strategy still needs bar-by-bar for orders)                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Timeline of a Single Indicator Creation

```
Time ──────────────────────────────────────────────────────────────────►

│ Class Definition                    │ Object Instantiation
│ (import time)                       │ (strategy.__init__)
│                                     │
├─────────────────────────────────────┼─────────────────────────────────────
│                                     │
│ MetaLineSeries.__new__()            │ MetaLineIterator.donew()
│ ├─ Extract lines=('sma',)           │ ├─ Create _lineiterators dict
│ ├─ Create Lines_SMA class           │ ├─ Scan args for datas
│ ├─ Add LineAlias descriptors        │ ├─ Create data aliases
│ └─ Create plotinfo, plotlines       │ └─ Create dnames dict
│                                     │
│                                     │ MetaLineIterator.dopreinit()
│                                     │ ├─ Set _clock = data[0]
│                                     │ └─ Initial _minperiod from datas
│                                     │
│                                     │ SMA.__init__()
│                                     │ ├─ Create sub-indicators
│                                     │ ├─ Set up bindings
│                                     │ └─ Minperiod propagated
│                                     │
│                                     │ MetaLineIterator.dopostinit()
│                                     │ ├─ Final _minperiod calculation
│                                     │ ├─ _periodrecalc()
│                                     │ └─ Register with owner
│                                     │
│                                     ▼
│                                     SMA object ready
```

---

## Summary: How Everything Connects

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BACKTRADER LINE SYSTEM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DATA STORAGE                                                               │
│  ────────────                                                               │
│  LineBuffer: array + idx → line[0] = current, line[-1] = previous          │
│                                                                             │
│  CONTAINER                                                                  │
│  ─────────                                                                  │
│  Lines: [LineBuffer, LineBuffer, ...] → proxy operations to all            │
│                                                                             │
│  NAMED ACCESS                                                               │
│  ────────────                                                               │
│  LineAlias: descriptor → self.lines.close returns LineBuffer               │
│                                                                             │
│  METADATA                                                                   │
│  ────────                                                                   │
│  LineSeries: combines Lines + plotinfo + plotlines                         │
│                                                                             │
│  EXECUTION                                                                  │
│  ─────────                                                                  │
│  LineIterator: _next()/_once() → prenext()/nextstart()/next()              │
│                                                                             │
│  LAZY OPERATIONS                                                            │
│  ───────────────                                                            │
│  LinesOperation: holds operands → computes during _next()                  │
│                                                                             │
│  OWNERSHIP                                                                  │
│  ─────────                                                                  │
│  findowner(): walks call stack → auto-discovers parent                     │
│                                                                             │
│  REGISTRATION                                                               │
│  ────────────                                                               │
│  addindicator(): adds to owner._lineiterators[type]                        │
│                                                                             │
│  MINPERIOD                                                                  │
│  ─────────                                                                  │
│  Propagated: data → indicators → lines → final value                       │
│                                                                             │
│  BINDINGS                                                                   │
│  ────────                                                                   │
│  addbinding(): source writes → target automatically updated                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

This architecture enables backtrader's elegant API where:
- `self.data.close` gives you a line you can operate on
- `self.data.close[0]` gives you the current value
- `self.data.close - self.data.open` creates a new line automatically
- Indicators register themselves and get called automatically
- Minperiods are calculated and enforced automatically
