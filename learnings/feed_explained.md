# backtrader/feed.py — Data Feeds Explained

This document walks through every class and method in `backtrader/feed.py`,
the module responsible for loading, filtering, and delivering price data bars
into the backtrader system.

---

## Inheritance Hierarchy

```
object
  └── LineSeries (from lineseries.py)
        └── DataSeries (from dataseries.py)
              │   lines: close, low, high, open, volume, openinterest
              └── OHLC
                    └── OHLCDateTime
                          │   lines: datetime
                          └── AbstractDataBase  (metaclass: MetaAbstractDataBase)
                                │   Core data feed logic
                                ├── DataBase (empty, exists for naming)
                                │     ├── CSVDataBase (metaclass: MetaCSVDataBase)
                                │     │     └── BacktraderCSVData (in feeds/btcsv.py)
                                │     └── (other feed classes: PandasData, IBData, etc.)
                                └── DataClone (shares another data feed's bars)

object
  └── FeedBase (metaclass: MetaParams)
        └── CSVFeedBase
              └── BacktraderCSV (in feeds/btcsv.py)
```

---

## Class: MetaAbstractDataBase

**File:** `backtrader/feed.py:41-119`
**Inherits from:** `OHLCDateTime.__class__` (which is `MetaLineSeries`)

The metaclass for all data feed classes. It handles:
1. Registering data feed subclasses in a global registry
2. Setting up feed/notification infrastructure during instance creation
3. Processing date/time/session parameters and filters

### Class Attribute

```python
_indcol = dict()   # Registry: maps class names to class objects
                    # e.g. {'BacktraderCSVData': <class BacktraderCSVData>}
```

### Method: `__init__(cls, name, bases, dct)`

Called when a new data feed **class** is defined (class creation time, not instance creation).
Registers the class in `_indcol` unless it's the base `DataBase` or starts with `_`.

```python
class MetaAbstractDataBase(dataseries.OHLCDateTime.__class__):
    _indcol = dict()

    def __init__(cls, name, bases, dct):
        super(MetaAbstractDataBase, cls).__init__(name, bases, dct)
        if not cls.aliased and name != 'DataBase' and not name.startswith('_'):
            cls._indcol[name] = cls
```

**Example:**

```python
# When Python encounters this class definition:
class BacktraderCSVData(CSVDataBase):
    ...

# MetaAbstractDataBase.__init__ is called:
#   name = 'BacktraderCSVData'
#   cls.aliased = False
#   → _indcol['BacktraderCSVData'] = <class BacktraderCSVData>
#
# This allows looking up data classes by name:
feed_cls = MetaAbstractDataBase._indcol['BacktraderCSVData']
```

### Method: `dopreinit(cls, _obj, *args, **kwargs)`

Called during instance creation, before `__init__`. Sets up:
- `_feed`: finds the owning `FeedBase` (if any) via `findowner`
- `notifs`: notification deque for Cerebro
- `_dataname` and `_name`: data identification

```python
def dopreinit(cls, _obj, *args, **kwargs):
    _obj, args, kwargs = super().dopreinit(_obj, *args, **kwargs)

    _obj._feed = metabase.findowner(_obj, FeedBase)  # find owning FeedBase
    _obj.notifs = collections.deque()                 # notification queue
    _obj._dataname = _obj.p.dataname                  # e.g. 'data/orcl.csv'
    _obj._name = ''                                   # name set in dopostinit
    return _obj, args, kwargs
```

**Example:**

```python
# When creating a data feed inside a FeedBase:
class MyFeed(FeedBase):
    DataCls = BacktraderCSVData
    
    def getdata(self, dataname, ...):
        data = self.DataCls(dataname=dataname)
        # During data creation:
        #   _obj._feed = findowner(_obj, FeedBase)  → finds MyFeed instance
        #   _obj.notifs = deque()
        #   _obj._dataname = 'data/orcl.csv'

# When creating standalone (no FeedBase):
data = bt.feeds.BacktraderCSVData(dataname='data/orcl.csv')
#   _obj._feed = findowner(...)  → None (no FeedBase on call stack)
```

### Method: `dopostinit(cls, _obj, *args, **kwargs)`

Called after `__init__`. Finalizes:
- Name resolution (from `_name`, `p.name`, or `p.dataname`)
- Compression/timeframe settings
- Session start/end normalization
- Filter setup from `params.filters`
- Bar stack/stash initialization

```python
def dopostinit(cls, _obj, *args, **kwargs):
    _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs)

    # Name resolution
    _obj._name = _obj._name or _obj.p.name
    if not _obj._name and isinstance(_obj.p.dataname, string_types):
        _obj._name = _obj.p.dataname

    # Timeframe
    _obj._compression = _obj.p.compression
    _obj._timeframe = _obj.p.timeframe

    # Session normalization
    if isinstance(_obj.p.sessionstart, datetime.datetime):
        _obj.p.sessionstart = _obj.p.sessionstart.time()
    elif _obj.p.sessionstart is None:
        _obj.p.sessionstart = datetime.time.min

    if isinstance(_obj.p.sessionend, datetime.datetime):
        _obj.p.sessionend = _obj.p.sessionend.time()
    elif _obj.p.sessionend is None:
        _obj.p.sessionend = datetime.time(23, 59, 59, 999990)

    # Date range normalization
    if isinstance(_obj.p.fromdate, datetime.date):
        if not hasattr(_obj.p.fromdate, 'hour'):  # date, not datetime
            _obj.p.fromdate = datetime.datetime.combine(
                _obj.p.fromdate, _obj.p.sessionstart)

    # Similar for todate ...

    # Filter/bar stack setup
    _obj._barstack = collections.deque()   # for filter operations
    _obj._barstash = collections.deque()   # for filter operations
    _obj._filters = list()
    _obj._ffilters = list()                # filters with .last() method
    for fp in _obj.p.filters:
        if inspect.isclass(fp):
            fp = fp(_obj)
            if hasattr(fp, 'last'):
                _obj._ffilters.append((fp, [], {}))
        _obj._filters.append((fp, [], {}))

    return _obj, args, kwargs
```

**Example:**

```python
import datetime

data = bt.feeds.BacktraderCSVData(
    dataname='datas/orcl-2014.txt',
    fromdate=datetime.date(2014, 1, 1),
    todate=datetime.date(2014, 12, 31),
    timeframe=bt.TimeFrame.Days,
    compression=1,
)

# After dopostinit:
# data._name = 'datas/orcl-2014.txt'   (from p.dataname since p.name is '')
# data._compression = 1
# data._timeframe = TimeFrame.Days (5)
# data.p.sessionstart = datetime.time(0, 0)       (from time.min)
# data.p.sessionend = datetime.time(23, 59, 59, 999990)
# data.p.fromdate = datetime.datetime(2014, 1, 1, 0, 0)  (combined with sessionstart)
# data.p.todate = datetime.datetime(2014, 12, 31, 23, 59, 59, 999990)
# data._barstack = deque()
# data._barstash = deque()
# data._filters = []
# data._ffilters = []
```

---

## Class: AbstractDataBase

**File:** `backtrader/feed.py:122-597`
**Inherits from:** `OHLCDateTime` (via metaclass `MetaAbstractDataBase`)

The core data feed class. Every data feed in backtrader inherits from this.
It provides the full lifecycle: start, load, filter, preload, advance, stop.

### Parameters

```python
params = (
    ('dataname', None),          # File path, URL, ticker, or file-like object
    ('name', ''),                # Human-readable name (for plotting/logging)
    ('compression', 1),          # Bar compression (e.g. 5 for 5-minute bars)
    ('timeframe', TimeFrame.Days),  # TimeFrame.Minutes, .Days, .Weeks, etc.
    ('fromdate', None),          # Start date filter (datetime.date or datetime.datetime)
    ('todate', None),            # End date filter
    ('sessionstart', None),      # Session start time (for intraday)
    ('sessionend', None),        # Session end time
    ('filters', []),             # List of filter callables/classes
    ('tz', None),                # Output timezone (pytz or string)
    ('tzinput', None),           # Input timezone
    ('qcheck', 0.0),            # Timeout for live data queue check
    ('calendar', None),          # Trading calendar (for session end detection)
)
```

### Class-Level Constants: Notification Status

```python
(CONNECTED, DISCONNECTED, CONNBROKEN, DELAYED,
 LIVE, NOTSUBSCRIBED, NOTSUPPORTED_TF, UNKNOWN) = range(8)

_NOTIFNAMES = [
    'CONNECTED', 'DISCONNECTED', 'CONNBROKEN', 'DELAYED',
    'LIVE', 'NOTSUBSCRIBED', 'NOTSUPPORTED_TIMEFRAME', 'UNKNOWN'
]
```

**Example:**

```python
# Live data feeds use these to report status changes:
class MyLiveData(bt.feeds.DataBase):
    def start(self):
        super().start()
        self.put_notification(self.CONNECTED)
    
    def _load(self):
        if connection_lost:
            self.put_notification(self.CONNBROKEN)
            return None  # None = no bar but not done
        
        if new_bar_available:
            self.put_notification(self.LIVE)
            # ... load bar data ...
            return True
        
        return False  # done

# In a strategy, you receive these:
class MyStrategy(bt.Strategy):
    def notify_data(self, data, status, *args, **kwargs):
        print(f'Data status: {data._getstatusname(status)}')
        # Prints: 'Data status: CONNECTED'
        # Later:  'Data status: LIVE'
```

### Class-Level Attributes

```python
_compensate = None     # Another data this one compensates (for position netting)
_feed = None           # Owning FeedBase instance (set in dopreinit)
_store = None          # Owning Store instance (for broker-connected feeds)
_clone = False         # True for DataClone instances
_qcheck = 0.0          # Live data queue check timeout
_tmoffset = datetime.timedelta()  # Time offset for live feeds
resampling = 0         # Non-zero if this data is being resampled
replaying = 0          # Non-zero if this data is being replayed
_started = False       # Whether _start_finish has been called
```

### Method: `_start_finish(self)`

Performs late-stage timezone and date setup. Called from `_start()` after `start()`.
This is late because live feeds may discover timezone info during `start()`.

```python
def _start_finish(self):
    # Get output timezone
    self._tz = self._gettz()
    self.lines.datetime._settz(self._tz)

    # Get input timezone converter
    self._tzinput = bt.utils.date.Localizer(self._gettzinput())

    # Convert from/to dates to numeric
    if self.p.fromdate is None:
        self.fromdate = float('-inf')
    else:
        self.fromdate = self.date2num(self.p.fromdate)

    if self.p.todate is None:
        self.todate = float('inf')
    else:
        self.todate = self.date2num(self.p.todate)

    # Session times to numeric
    self.sessionstart = time2num(self.p.sessionstart)
    self.sessionend = time2num(self.p.sessionend)

    # Calendar setup
    self._calendar = cal = self.p.calendar
    if cal is None:
        self._calendar = self._env._tradingcal
    elif isinstance(cal, string_types):
        self._calendar = PandasMarketCalendar(calendar=cal)

    self._started = True
```

**Example:**

```python
data = bt.feeds.BacktraderCSVData(
    dataname='datas/orcl-2014.txt',
    fromdate=datetime.datetime(2014, 1, 1),
    todate=datetime.datetime(2014, 12, 31),
    tz='US/Eastern',
)

# After _start_finish():
# data._tz = <pytz US/Eastern>
# data.lines.datetime._tz = <pytz US/Eastern>
# data._tzinput = None (no tzinput specified)
# data.fromdate = 735234.0  (numeric date)
# data.todate = 735598.999...  (numeric date)
# data._calendar = None or cerebro's trading calendar
# data._started = True
```

### Method: `_start(self)`

The internal start method called by Cerebro. Calls `start()` then `_start_finish()`.

```python
def _start(self):
    self.start()               # subclass hook (e.g. open file)
    if not self._started:
        self._start_finish()   # timezone/date setup
```

### Method: `start(self)`

User-overridable startup hook. Base implementation resets bar stacks and status.

```python
def start(self):
    self._barstack = collections.deque()
    self._barstash = collections.deque()
    self._laststatus = self.CONNECTED
```

**Example:**

```python
class MyCustomData(bt.feeds.DataBase):
    def start(self):
        super().start()                      # reset stacks + status
        self.connection = connect_to_api()   # custom setup
        print('Data feed started')
```

### Method: `stop(self)`

User-overridable cleanup hook. Base implementation does nothing.

```python
def stop(self):
    pass

# Example: CSVDataBase overrides this to close the file:
# def stop(self):
#     super().stop()
#     if self.f is not None:
#         self.f.close()
#         self.f = None
```

### Method: `preload(self)`

Loads **all** bars at once. Used in `runonce` mode (the default).
After preloading, `home()` resets the index so iteration can start from bar 0.

```python
def preload(self):
    while self.load():       # load every bar
        pass

    self._last()             # give filters a chance to finalize
    self.home()              # reset idx to -1 for iteration
```

**Example:**

```python
data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')
cerebro.adddata(data)

# During cerebro.run() in runonce mode:
#   data._start()
#   data.preload()
#     → while self.load(): pass
#     → Loads all ~252 trading days into arrays
#     → self._last()        # filter finalization
#     → self.home()         # idx = -1, ready for iteration
#
# After preload:
#   data.lines.close.buflen() = 252
#   data.lines.close.idx = -1
#   All bars are in memory
```

### Method: `load(self)` — The Core Loading Engine

The main bar-loading loop. Returns:
- `True`: a bar was successfully loaded and passed all filters
- `False`: no more bars (data feed is exhausted)
- `None`: no bar available right now, but feed is not done (live feeds)

```python
def load(self):
    while True:
        # 1. Move pointer forward for new bar slot
        self.forward()

        # 2. Try to get a bar from the stack (put there by filters)
        if self._fromstack():
            return True

        # 3. Try the stash, then the actual data source
        if not self._fromstack(stash=True):
            _loadret = self._load()
            if not _loadret:
                self.backwards(force=True)   # undo the forward
                return _loadret              # False or None

        # 4. Timezone conversion if input tz specified
        dt = self.lines.datetime[0]
        if self._tzinput:
            dtime = num2date(dt)
            dtime = self._tzinput.localize(dtime)
            self.lines.datetime[0] = dt = date2num(dtime)

        # 5. Date range filtering
        if dt < self.fromdate:
            self.backwards()                 # discard, too early
            continue
        if dt > self.todate:
            self.backwards(force=True)       # past end, stop
            break

        # ────────────────────────────────────────────────────────────
        # What does backwards() do?
        #
        # backwards() is the OPPOSITE of forward(). While forward()
        # appends a slot to the array and advances idx, backwards()
        # pops the last slot and moves idx back. It ERASES the bar.
        #
        # See the detailed "backwards() Deep Dive" section below.
        # ────────────────────────────────────────────────────────────

        # 6. Pass through user filters
        retff = False
        for ff, fargs, fkwargs in self._filters:
            if self._barstack:
                for i in range(len(self._barstack)):
                    self._fromstack(forward=True)
                    retff = ff(self, *fargs, **fkwargs)
            else:
                retff = ff(self, *fargs, **fkwargs)
            if retff:
                break

        if retff:
            continue                         # bar filtered out, get next

        # 7. Bar passed all checks
        return True

    return False                             # past todate
```

**Detailed Flow Diagram:**

```
load() called
    │
    ├── forward()                    ← allocate slot for new bar
    │
    ├── _fromstack()?  ─── Yes ───► return True (bar from filter stack)
    │       │
    │      No
    │       │
    ├── _fromstack(stash=True)?
    │       │
    │      No
    │       │
    ├── _load()                      ← read from actual source (CSV, API, etc.)
    │       │
    │    False/None ──────────────► backwards(force=True), return False/None
    │       │
    │    True (bar loaded into lines[0])
    │       │
    ├── timezone conversion (if _tzinput)
    │       │
    ├── dt < fromdate? ── Yes ────► backwards(), continue (skip bar)
    │       │
    ├── dt > todate? ──── Yes ────► backwards(force=True), break → return False
    │       │
    ├── pass through filters
    │       │
    │    retff True ──────────────► continue (bar removed by filter)
    │       │
    │    retff False
    │       │
    └── return True                  ← bar delivered
```

**Example: How a bar moves through load():**

```python
# Given CSV line: "2014-01-02,38.01,38.06,37.77,37.92,10892000,0"
# and fromdate=2014-01-01, todate=2014-12-31

# Step 1: forward()
#   data.lines.close.array.append(NaN)
#   data.lines.close.idx += 1
#   (same for all 7 lines)

# Step 2: _fromstack() → False (stack empty)

# Step 3: _fromstack(stash=True) → False (stash empty)

# Step 4: _load() → CSVDataBase._load() reads line, calls _loadline()
#   BacktraderCSVData._loadline() parses CSV:
#     self.lines.datetime[0] = date2num(datetime(2014, 1, 2))
#     self.lines.open[0] = 38.01
#     self.lines.high[0] = 38.06
#     self.lines.low[0] = 37.77
#     self.lines.close[0] = 37.92
#     self.lines.volume[0] = 10892000.0
#     self.lines.openinterest[0] = 0.0
#   Returns True

# Step 5: dt = 735235.xxx
#   dt < fromdate (735234.0)? No
#   dt > todate (735598.xxx)? No

# Step 6: No filters → retff = False

# Step 7: return True ← bar 2014-01-02 delivered!
```

### `backwards()` Deep Dive

`backwards()` is the **undo operation** for `forward()`. Together they form a
matched pair that manages the data buffer:

| Method | idx | lencount | array |
|---|---|---|---|
| `forward()` | `idx += 1` | `lencount += 1` | `array.append(NaN)` — **grows** |
| `backwards()` | `idx -= 1` | `lencount -= 1` | `array.pop()` — **shrinks** |
| `rewind()` | `idx -= 1` | `lencount -= 1` | array **unchanged** |

**Key difference between `backwards()` and `rewind()`:** `backwards()` removes
the last element from the array (destructive). `rewind()` only moves the pointer
back without touching the array (non-destructive, used for multi-timeframe sync).

#### Implementation in LineBuffer

```python
# backtrader/linebuffer.py

def forward(self, value=NAN, size=1):
    '''Grow buffer and advance pointer'''
    self.idx += size
    self.lencount += size
    for i in range(size):
        self.array.append(value)       # APPEND to array

def backwards(self, size=1, force=False):
    '''Shrink buffer and retreat pointer'''
    self.set_idx(self._idx - size, force=force)   # move idx back
    self.lencount -= size
    for i in range(size):
        self.array.pop()               # POP from array (remove last)

def rewind(self, size=1):
    '''Move pointer back WITHOUT touching array'''
    self.idx -= size
    self.lencount -= size
    # array is NOT modified
```

When called on a data feed (which is a `LineSeries`), `backwards()` propagates
to **every line**:

```python
# backtrader/lineseries.py — Lines container:
def backwards(self, size=1, force=False):
    for line in self.lines:
        line.backwards(size, force=force)
    # Pops from: close, low, high, open, volume, openinterest, datetime
    # All 7 lines shrink by 1 simultaneously

# backtrader/lineseries.py — LineSeries:
def backwards(self, size=1, force=False):
    self.lines.backwards(size, force=force)
```

#### The `force` Parameter and QBuffer

In QBuffer mode (memory-saving deque), the `idx` setter normally **clamps** the
index once the deque is full — it refuses to move below `lenmark`. The `force`
parameter bypasses this restriction:

```python
def set_idx(self, idx, force=False):
    if self.mode == self.QBuffer:
        if force or self._idx < self.lenmark:
            self._idx = idx       # only move if not clamped, OR force
        # else: idx stays put (clamped)
    else:
        self._idx = idx           # UnBounded: always moves

# Why force matters:
#
# In QBuffer mode with maxlen=16, after 100 bars:
#   idx is clamped at 15 (lenmark)
#
# backwards(force=False):
#   set_idx(15 - 1 = 14, force=False)
#   _idx (15) >= lenmark (15) → REFUSED, idx stays at 15
#   array.pop() still removes the last element though!
#   → idx and array are now INCONSISTENT
#
# backwards(force=True):
#   set_idx(15 - 1 = 14, force=True)
#   → idx = 14 (forced through)
#   array.pop() removes last element
#   → idx and array are CONSISTENT
#
# This is why replay mode needs force=True:
# The replayer must move the pointer backwards to overwrite
# the previous bar with updated values.
```

#### Visual Example: forward() + backwards() in load()

```
The load() loop calls forward() at the start to make room for a new bar,
then backwards() if the bar should be discarded.

BEFORE load():
  array: [100.5, 101.2, 99.8]      idx=2, lencount=3
                            ▲
                           idx

STEP 1: forward() — make room
  array: [100.5, 101.2, 99.8, NaN]  idx=3, lencount=4
                                ▲
                               idx

STEP 2: _load() fills the slot
  array: [100.5, 101.2, 99.8, 38.01] idx=3, lencount=4
                                ▲
                               idx
         lines.close[0] = array[3] = 38.01

STEP 3a: Bar passes all checks → return True
  array: [100.5, 101.2, 99.8, 38.01] idx=3, lencount=4
  ✓ Bar stays in the buffer

STEP 3b: Bar is before fromdate → backwards()
  array: [100.5, 101.2, 99.8]        idx=2, lencount=3
                            ▲
                           idx
  ✗ 38.01 is ERASED — as if it was never loaded
  → continue (loop back to load next bar)

STEP 3c: _load() returns False → backwards(force=True)
  array: [100.5, 101.2, 99.8]        idx=2, lencount=3
  ✗ The NaN slot is removed — buffer is back to its previous state
  → return False (no more data)
```

#### All Places Where backwards() Is Called

**1. `load()` — Date range filtering (in `feed.py`):**

```python
# Bar too early — erase and try the next one:
if dt < self.fromdate:
    self.backwards()            # erase bar, no force needed
    continue                    # (UnBounded mode, idx not clamped)

# Bar too late — erase and stop:
if dt > self.todate:
    self.backwards(force=True)  # force: might be in QBuffer mode
    break                       # at the boundary, must force

# _load() returned False/None — undo the forward():
self.backwards(force=True)      # force: always clean up properly
return _loadret
```

**2. `SimpleFilterWrapper` — Simple bar removal (in `dataseries.py`):**

```python
class SimpleFilterWrapper:
    def __call__(self, data):
        if self.ffilter(data, *self.args, **self.kwargs):
            data.backwards()    # filter says remove → erase bar
            return True
        return False

# Example:
def skip_zero_volume(data):
    return data.volume[0] == 0.0    # True = remove this bar

data.addfilter_simple(skip_zero_volume)
# When a zero-volume bar is loaded:
#   forward() → _load() fills bar → volume is 0
#   SimpleFilterWrapper calls data.backwards() → bar erased
#   load() loops back to try the next bar
```

**3. Resampler — Consuming input bars (in `resamplerfilter.py`):**

```python
# The Resampler reads lower-timeframe bars and accumulates them
# into higher-timeframe bars. Each input bar is CONSUMED:

# Input bar arrives (e.g. 1-minute bar):
self.bar.bupdate(data)   # accumulate into the resampled bar
data.backwards()          # ERASE the input bar from the stream
#                          The resampled bar will be delivered later
#                          via _add2stack / _fromstack

# Example flow for 1-min → 5-min resampling:
#   Bar 10:01 → bupdate, backwards() — consumed
#   Bar 10:02 → bupdate, backwards() — consumed
#   Bar 10:03 → bupdate, backwards() — consumed
#   Bar 10:04 → bupdate, backwards() — consumed
#   Bar 10:05 → bupdate, backwards() — consumed, bar complete!
#   → 5-min bar [10:01-10:05] added to _barstack
#   → _fromstack delivers the completed 5-min bar
```

**4. Replayer — Replacing bars (in `resamplerfilter.py`):**

```python
# The Replayer is like the Resampler but it delivers PARTIAL bars
# as they build up. Each tick replaces the previous partial bar:

data.backwards(force=True)                        # remove old partial bar
data._updatebar(self.bar.lvalues(), forward=False, ago=0)  # write updated bar
# force=True because in QBuffer mode the idx is clamped and
# the replayer needs to actually move the pointer back

# Example for replaying ticks → 1-min bar:
#   Tick 10:00:05 → partial bar written: O=100 H=100 L=100 C=100
#   Tick 10:00:15 → backwards(force=True), write: O=100 H=101 L=100 C=101
#   Tick 10:00:30 → backwards(force=True), write: O=100 H=101 L=99  C=99.5
#   10:01:00      → bar finalized, advance to next bar
```

**5. Session/Renko/DaySteps filters:**

```python
# Session filter — remove bars outside trading hours:
class SessionFilter:
    def __call__(self, data):
        dt = data.datetime.datetime(0)
        if dt.time() < time(9, 30) or dt.time() >= time(16, 0):
            data.backwards()     # bar outside session → erase
            return True
        return False

# Renko filter — remove bars that don't form a new brick:
class RenkoFilter:
    def __call__(self, data):
        if not self._is_new_brick(data):
            data.backwards()     # not a brick → erase
            return True
        return False

# DaySteps filter — split a daily bar into open/close sub-bars:
class DayStepsFilter:
    def __call__(self, data):
        newbar = [data.lines[i][0] for i in range(data.size())]
        data.backwards()          # remove original bar
        # ... then add modified bars to _barstack
```

**6. `_save2stack(erase=True)` — Save bar then erase from stream:**

```python
def _save2stack(self, erase=False, force=False, stash=False):
    bar = [line[0] for line in self.itersize()]   # snapshot current values
    self._barstack.append(bar)                    # save to stack

    if erase:
        self.backwards(force=force)               # erase from lines
    
# This is used when a filter wants to MOVE a bar from the line buffer
# to the stack for later delivery:
#   1. Copy current bar values to a list
#   2. Push list onto _barstack
#   3. backwards() erases the bar from lines
#   4. Later, _fromstack() pops from _barstack back into lines
```

#### Complete Example: Date Filtering in Action

```python
# Data with fromdate=2014-03-01, todate=2014-03-05
# CSV contains:
#   2014-02-28, 37.50, 38.00, 37.00, 37.80, 5000000, 0
#   2014-03-01, 38.00, 38.50, 37.90, 38.20, 6000000, 0
#   2014-03-03, 38.20, 39.00, 38.10, 38.90, 7000000, 0
#   2014-03-05, 38.90, 39.50, 38.80, 39.20, 5500000, 0
#   2014-03-06, 39.20, 39.80, 39.00, 39.50, 6200000, 0

# --- Iteration 1: 2014-02-28 ---
#
# forward():
#   close.array = [NaN]    idx=0
#
# _load() → _loadline() fills:
#   close.array = [37.80]  idx=0
#   datetime[0] = date2num(2014-02-28)
#
# Date check: 2014-02-28 < fromdate (2014-03-01) → TOO EARLY
#   backwards():
#     close.array = []     idx=-1   ← bar erased!
#   continue → loop back

# --- Iteration 2: 2014-03-01 ---
#
# forward():
#   close.array = [NaN]    idx=0
#
# _load() → fills:
#   close.array = [38.20]  idx=0
#
# Date check: 2014-03-01 >= fromdate → OK
# Date check: 2014-03-01 <= todate → OK
# Filters: none
# return True ← first bar delivered!

# --- Iteration 3: 2014-03-03 ---
#
# forward():
#   close.array = [38.20, NaN]   idx=1
#
# _load() → fills:
#   close.array = [38.20, 38.90] idx=1
#
# Date check: OK
# return True ← second bar delivered!

# --- Iteration 4: 2014-03-05 ---
#
# forward():
#   close.array = [38.20, 38.90, NaN]   idx=2
#
# _load() → fills:
#   close.array = [38.20, 38.90, 39.20] idx=2
#
# Date check: OK
# return True ← third bar delivered!

# --- Iteration 5: 2014-03-06 ---
#
# forward():
#   close.array = [38.20, 38.90, 39.20, NaN]   idx=3
#
# _load() → fills:
#   close.array = [38.20, 38.90, 39.20, 39.50] idx=3
#   datetime[0] = date2num(2014-03-06)
#
# Date check: 2014-03-06 > todate (2014-03-05) → PAST END
#   backwards(force=True):
#     close.array = [38.20, 38.90, 39.20]      idx=2   ← bar erased!
#   break → return False
#
# Final state:
#   close.array = [38.20, 38.90, 39.20]   (3 bars: Mar 1, 3, 5)
#   Only bars within [fromdate, todate] survived
```

### Method: `_load(self)`

The actual data loading hook. Subclasses **must** override this.
Returns `True` if a bar was loaded, `False` if done, `None` if no data yet (live).

```python
def _load(self):
    return False    # base implementation: no data

# CSVDataBase overrides:
def _load(self):
    if self.f is None:
        return False
    line = self.f.readline()
    if not line:
        return False
    line = line.rstrip('\n')
    linetokens = line.split(self.separator)
    return self._loadline(linetokens)
```

**Example — Custom Data Feed:**

```python
class MyAPIData(bt.feeds.DataBase):
    """Load data from a REST API."""

    params = (
        ('dataname', 'AAPL'),
        ('api_key', ''),
    )

    def start(self):
        super().start()
        self.api = connect_api(self.p.api_key)
        self.bars = self.api.get_bars(self.p.dataname)
        self.bar_idx = 0

    def _load(self):
        if self.bar_idx >= len(self.bars):
            return False

        bar = self.bars[self.bar_idx]
        self.bar_idx += 1

        self.lines.datetime[0] = bt.date2num(bar['datetime'])
        self.lines.open[0] = bar['open']
        self.lines.high[0] = bar['high']
        self.lines.low[0] = bar['low']
        self.lines.close[0] = bar['close']
        self.lines.volume[0] = bar['volume']
        self.lines.openinterest[0] = 0.0

        return True
```

### Method: `next(self, datamaster=None, ticks=True)`

Step-by-step bar delivery. Used in `_runnext()` mode (non-preloaded, live, or QBuffer).
Called by Cerebro on each iteration.

```python
def next(self, datamaster=None, ticks=True):
    if len(self) >= self.buflen():
        # Not preloaded — need to load a new bar
        if ticks:
            self._tick_nullify()

        ret = self.load()
        if not ret:
            return ret              # False or None

        if datamaster is None:
            if ticks:
                self._tick_fill()
            return ret
    else:
        # Preloaded — just advance the pointer
        self.advance(ticks=ticks)

    # Datamaster synchronization
    if datamaster is not None:
        if self.lines.datetime[0] > datamaster.lines.datetime[0]:
            self.rewind()           # too far ahead, go back
            return False
        else:
            if ticks:
                self._tick_fill()

    return True
```

**Example:**

```python
# In step-by-step mode (live or exactbars):
# Cerebro calls data.next() for each bar:

# Bar 1:
#   len(data) = 0, buflen() = 0  → needs loading
#   data.load() → reads CSV line → returns True
#   data.lines.close[0] = 37.92
#   return True

# Bar 2:
#   len(data) = 1, buflen() = 1  → needs loading
#   data.load() → reads next CSV line → returns True
#   data.lines.close[0] = 38.10
#   return True

# In preloaded mode (after preload()):
#   len(data) = 0, buflen() = 252  → 0 < 252, use advance
#   data.advance()  → idx moves from -1 to 0
#   data.lines.close[0] now returns first bar's close
```

### Method: `advance(self, size=1, datamaster=None, ticks=True)`

Moves the logical pointer forward without loading new data.
Handles synchronization with a datamaster for multi-timeframe setups.

```python
def advance(self, size=1, datamaster=None, ticks=True):
    if ticks:
        self._tick_nullify()

    self.lines.advance(size)        # advance all lines' idx

    if datamaster is not None:
        if len(self) > self.buflen():
            self.rewind()           # past end, fill empty bar
            self.lines.forward()
            return

        if self.lines.datetime[0] > datamaster.lines.datetime[0]:
            self.lines.rewind()     # too far ahead
        else:
            if ticks:
                self._tick_fill()
    elif len(self) < self.buflen():
        if ticks:
            self._tick_fill()
```

**Example — Multi-Timeframe:**

```python
# Daily data (master) and weekly data (slave):
# cerebro.adddata(daily_data)     # data0, master
# cerebro.adddata(weekly_data)    # data1

# When iterating, daily advances normally:
#   daily_data.advance()  → idx += 1

# Weekly data advances with master sync:
#   weekly_data.advance(datamaster=daily_data)
#   if weekly_data.datetime[0] > daily_data.datetime[0]:
#       weekly_data.lines.rewind()  # not time yet for new weekly bar
```

### Method: `advance_peek(self)`

Returns the datetime of the **next** bar without advancing.
Used by Cerebro to determine synchronization order.

```python
def advance_peek(self):
    if len(self) < self.buflen():
        return self.lines.datetime[1]    # peek at future (preloaded)
    return float('inf')                  # no more data
```

**Example:**

```python
# After preloading, data has 252 bars, currently at bar 100 (idx=100):
data.advance_peek()
# → data.lines.datetime[1]
# → returns the numeric datetime of bar 101
# (datetime[1] means 1 position into the past in backtrader's convention,
#  but here idx hasn't been advanced yet, so [1] looks at the next slot)

# At the last bar (idx=251):
data.advance_peek()
# → len(self)=252 >= buflen()=252
# → returns float('inf')  (no more bars)
```

### Method: `_getnexteos(self)`

Returns the next **End-Of-Session** (EOS) datetime and its matplotlib numeric
equivalent as a tuple `(nexteos, nextdteos)`. This method answers the question:
*"Given the current bar's datetime, when does the current trading session end?"*

It is used by two consumers internally:

1. **Resampler** (`resamplerfilter.py`) — to decide when a higher-timeframe bar
   is complete. For example, when resampling 1-minute bars into daily bars, the
   resampler needs to know the session close time (e.g., 16:00) to finalize
   the daily bar.

2. **Timer** (`timer.py`) — to manage timer callbacks relative to session
   boundaries. A timer scheduled at "15 minutes before session close" needs
   to know when the session ends.

**Full implementation:**

```python
def _getnexteos(self):
    '''Returns the next eos using a trading calendar if available'''
    # Clones delegate to the source data
    if self._clone:
        return self.data._getnexteos()

    # No bars yet — return minimum date
    if not len(self):
        return datetime.datetime.min, 0.0

    # Get the current bar's datetime
    dt = self.lines.datetime[0]
    dtime = num2date(dt)

    if self._calendar is None:
        # No trading calendar — use sessionend parameter
        # Combine today's date with the session end time
        nexteos = datetime.datetime.combine(dtime, self.p.sessionend)
        nextdteos = self.date2num(nexteos)    # localize → UTC-like numeric
        nexteos = num2date(nextdteos)         # back to datetime in UTC

        # If current time is PAST session end (e.g. after-hours bar),
        # advance to the next day's session end
        while dtime > nexteos:
            nexteos += datetime.timedelta(days=1)

        nextdteos = date2num(nexteos)         # final numeric value

    else:
        # Trading calendar provides exact session boundaries
        # (handles holidays, half-days, different exchange schedules)
        _, nexteos = self._calendar.schedule(dtime, self._tz)
        nextdteos = date2num(nexteos)         # already in UTC

    return nexteos, nextdteos
```

**Example 1 — Default behavior (no trading calendar):**

```python
# Data feed with default session parameters:
data = bt.feeds.BacktraderCSVData(
    dataname='datas/orcl-2014.txt',
    # sessionend defaults to time(23, 59, 59, 999990)
)

# Current bar: 2014-03-15 10:30:00
# _getnexteos() computes:
#   dtime = datetime(2014, 3, 15, 10, 30, 0)
#   nexteos = datetime.combine(dtime, time(23, 59, 59, 999990))
#           = datetime(2014, 3, 15, 23, 59, 59, 999990)
#   dtime (10:30) < nexteos (23:59) → no advancing needed
#   Returns: (datetime(2014, 3, 15, 23, 59, 59, 999990), 735279.999...)
```

**Example 2 — Custom session end time:**

```python
import datetime

data = bt.feeds.GenericCSVData(
    dataname='intraday_data.csv',
    timeframe=bt.TimeFrame.Minutes,
    compression=1,
    sessionend=datetime.time(16, 0, 0),   # market closes at 4 PM
)

# Current bar: 2014-03-15 14:35:00
# _getnexteos() computes:
#   nexteos = datetime.combine(2014-03-15, time(16, 0, 0))
#           = datetime(2014, 3, 15, 16, 0, 0)
#   14:35 < 16:00 → session ends today at 16:00
#   Returns: (datetime(2014, 3, 15, 16, 0, 0), 735279.666...)
#
# Current bar: 2014-03-15 16:30:00  (after-hours bar)
# _getnexteos() computes:
#   nexteos = datetime(2014, 3, 15, 16, 0, 0)
#   16:30 > 16:00 → advance!
#   nexteos += timedelta(days=1) → datetime(2014, 3, 16, 16, 0, 0)
#   16:30 > 16:00 on the 16th? No, 2014-03-15 16:30 vs 2014-03-16 16:00
#   → loop ends
#   Returns: (datetime(2014, 3, 16, 16, 0, 0), ...)
#   This means: next session end is tomorrow at 4 PM
```

**Example 3 — How the Resampler uses it:**

```python
# Resampling 1-minute bars into daily bars:
data = bt.feeds.GenericCSVData(
    dataname='aapl_1min.csv',
    timeframe=bt.TimeFrame.Minutes,
    sessionend=datetime.time(16, 0, 0),
)
data.resample(timeframe=bt.TimeFrame.Days)

# Inside the Resampler filter:
#
# class _BaseResampler:
#     def _eosset(self):
#         if self._nexteos is None:
#             self._nexteos, self._nextdteos = self.data._getnexteos()
#
#     def _eoscheck(self, data, seteos=True, exact=False):
#         if seteos:
#             self._eosset()
#
#         # Is the current bar AT or PAST session end?
#         equal = data.datetime[0] == self._nextdteos
#         grter = data.datetime[0] > self._nextdteos
#         # If so → the daily bar is complete, deliver it
#
# Flow:
#   Bar 09:30 → _nextdteos = 16:00 → 09:30 < 16:00 → accumulate
#   Bar 09:31 → 09:31 < 16:00 → accumulate (update high/low/close/volume)
#   ...
#   Bar 15:59 → 15:59 < 16:00 → accumulate
#   Bar 16:00 → 16:00 == 16:00 → BAR COMPLETE! Deliver the daily bar.
#   Next bar 09:30 (next day) → _getnexteos() returns tomorrow's 16:00
```

**Example 4 — With a trading calendar:**

```python
# A trading calendar knows about holidays and half-days:
cerebro = bt.Cerebro()
data = bt.feeds.GenericCSVData(
    dataname='spy_1min.csv',
    timeframe=bt.TimeFrame.Minutes,
    calendar='NYSE',   # uses PandasMarketCalendar
)

# On a normal day (2014-03-15):
#   _getnexteos() → calendar.schedule(2014-03-15, tz)
#   Returns: (datetime(2014, 3, 15, 16, 0, 0, tzinfo=UTC), ...)
#
# On Christmas Eve (2014-12-24, NYSE closes at 1 PM):
#   _getnexteos() → calendar.schedule(2014-12-24, tz)
#   Returns: (datetime(2014, 12, 24, 13, 0, 0, tzinfo=UTC), ...)
#   The resampler correctly finalizes the daily bar at 1 PM!
#
# On Christmas Day (2014-12-25, market closed):
#   No bars are loaded, so _getnexteos() is never called
```

**Example 5 — Timer using session end:**

```python
class MyStrat(bt.Strategy):
    def __init__(self):
        # Fire timer 15 minutes before session close
        self.add_timer(
            bt.timer.SESSION_END,        # relative to session end
            offset=datetime.timedelta(minutes=-15),
        )

    def notify_timer(self, timer, when, *args, **kwargs):
        print(f'Timer fired at {when} — 15 min before close')
        self.close()   # flatten all positions before close

# Internally, the Timer calls data._getnexteos() to find when
# the session ends, then subtracts 15 minutes to determine
# when to fire the callback.
```

### Method: `_last(self, datamaster=None)`

Gives filters a final chance to deliver bars. Called after all `_load()` returns `False`.

```python
def _last(self, datamaster=None):
    ret = 0
    for ff, fargs, fkwargs in self._ffilters:
        ret += ff.last(self, *fargs, **fkwargs)    # filters with .last()

    while self._fromstack(forward=True):
        pass    # consume any bars produced by last()

    return bool(ret)
```

**Example:**

```python
# A resampler filter might have a partial bar still buffered:
# When _last() is called after all data is loaded,
# the resampler's .last() method delivers the final incomplete bar
# onto the _barstack, which _fromstack then loads into the lines.
```

### Method: `_check(self, forcedata=None)`

Calls `check()` on filters that implement it. Used for live data synchronization.

### Methods: `date2num(self, dt)` and `num2date(self, dt=None, tz=None, naive=True)`

Convert between `datetime` objects and matplotlib numeric dates, applying
the data feed's timezone if configured.

```python
def date2num(self, dt):
    if self._tz is not None:
        return date2num(self._tz.localize(dt))
    return date2num(dt)

def num2date(self, dt=None, tz=None, naive=True):
    if dt is None:
        return num2date(self.lines.datetime[0], tz or self._tz, naive)
    return num2date(dt, tz or self._tz, naive)
```

**Example:**

```python
# Inside a strategy:
current_date = self.data.num2date()  # datetime of current bar
print(f"Current bar: {current_date}")
# Output: Current bar: 2014-03-15 23:59:59.999990
```

### Methods: `haslivedata(self)` and `islive(self)`

```python
def haslivedata(self):
    return False       # override for live feeds

def islive(self):
    '''If True, Cerebro deactivates preload and runonce'''
    return False       # override for live feeds
```

**Example:**

```python
class IBData(bt.feeds.DataBase):
    def islive(self):
        return True    # tells Cerebro to use step-by-step mode

    def haslivedata(self):
        return not self._queue.empty()  # pending real-time ticks
```

### Methods: `put_notification(self, status, *args, **kwargs)` and `get_notifications(self)`

Notification system for data feed status changes.

```python
def put_notification(self, status, *args, **kwargs):
    if self._laststatus != status:           # avoid duplicates
        self.notifs.append((status, args, kwargs))
        self._laststatus = status

def get_notifications(self):
    self.notifs.append(None)                 # sentinel mark
    notifs = list()
    while True:
        notif = self.notifs.popleft()
        if notif is None:
            break
        notifs.append(notif)
    return notifs
```

**Example:**

```python
# Live data feed:
class MyLiveFeed(bt.feeds.DataBase):
    def _load(self):
        try:
            bar = self.api.get_next_bar(timeout=self.p.qcheck)
        except ConnectionError:
            self.put_notification(self.CONNBROKEN)
            return None

        if bar is not None:
            self.put_notification(self.LIVE)
            self._fill_bar(bar)
            return True

        return None   # no bar yet, but not done

# Cerebro reads notifications on each iteration:
# for data in self.datas:
#     for notif in data.get_notifications():
#         status, args, kwargs = notif
#         strat.notify_data(data, status, *args, **kwargs)
```

### Methods: `do_qcheck(self, onoff, qlapse)`

Controls live data queue checking timeout.

```python
def do_qcheck(self, onoff, qlapse):
    qwait = self.p.qcheck if onoff else 0.0
    qwait = max(0.0, qwait - qlapse)
    self._qcheck = qwait
```

### Method: `clone(self, **kwargs)` and `copyas(self, _dataname, **kwargs)`

Create data clones — lightweight copies that share the original's bars.

```python
def clone(self, **kwargs):
    return DataClone(dataname=self, **kwargs)

def copyas(self, _dataname, **kwargs):
    d = DataClone(dataname=self, **kwargs)
    d._dataname = _dataname
    d._name = _dataname
    return d
```

**Example:**

```python
data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')
cerebro.adddata(data)

# Create a clone with different name:
data_clone = data.copyas('ORCL_CLONE')
cerebro.adddata(data_clone)

# data_clone shares data's bars, but can have independent indicators
# and be used as a separate "data feed" in the strategy
```

### Method: `setenvironment(self, env)` and `getenvironment(self)`

```python
def setenvironment(self, env):
    '''Keep a reference to the Cerebro environment'''
    self._env = env

def getenvironment(self):
    return self._env
```

Called by `cerebro.adddata()` to link the data feed to Cerebro.

### Method: `compensate(self, other)`

```python
def compensate(self, other):
    '''Tell the broker that actions on this asset compensate
    open positions in another'''
    self._compensate = other
```

**Example:**

```python
# If trading a futures contract and its continuation:
data_front = bt.feeds.GenericCSVData(dataname='ES_front.csv')
data_back = bt.feeds.GenericCSVData(dataname='ES_back.csv')
data_front.compensate(data_back)
# Now: buying data_front can offset positions in data_back
```

### Methods: `addfilter(self, p, *args, **kwargs)` and `addfilter_simple(self, f, *args, **kwargs)`

Add filters to the data loading pipeline. Filters can modify, remove, or
create bars during loading.

```python
def addfilter(self, p, *args, **kwargs):
    if inspect.isclass(p):
        pobj = p(self, *args, **kwargs)         # instantiate filter class
        self._filters.append((pobj, [], {}))
        if hasattr(pobj, 'last'):
            self._ffilters.append((pobj, [], {}))
    else:
        self._filters.append((p, args, kwargs)) # callable filter

def addfilter_simple(self, f, *args, **kwargs):
    fp = SimpleFilterWrapper(self, f, *args, **kwargs)
    self._filters.append((fp, fp.args, fp.kwargs))
```

**Example:**

```python
# Simple filter: skip bars with zero volume
def skip_zero_volume(data):
    if data.volume[0] == 0.0:
        return True     # True = remove this bar
    return False        # False = keep this bar

data = bt.feeds.BacktraderCSVData(dataname='data.csv')
data.addfilter_simple(skip_zero_volume)

# Class-based filter with state:
class SessionFilter(object):
    def __init__(self, data):
        self.data = data

    def __call__(self, data):
        '''Called for each bar during load()'''
        dt = data.datetime.datetime(0)
        if dt.hour < 9 or dt.hour >= 16:
            data.backwards()    # remove pre/post market bar
            return True
        return False

    def last(self, data):
        '''Called after all data loaded — deliver pending bars'''
        return 0

data.addfilter(SessionFilter)
```

### Method: `resample(self, **kwargs)` and `replay(self, **kwargs)`

Convenience methods to add Resampler/Replayer filters.

```python
def resample(self, **kwargs):
    self.addfilter(Resampler, **kwargs)

def replay(self, **kwargs):
    self.addfilter(Replayer, **kwargs)
```

**Example:**

```python
# Resample 1-minute data to 5-minute bars:
data = bt.feeds.GenericCSVData(
    dataname='AAPL_1min.csv',
    timeframe=bt.TimeFrame.Minutes,
    compression=1,
)
data.resample(timeframe=bt.TimeFrame.Minutes, compression=5)
cerebro.adddata(data)
# Now data delivers 5-minute bars constructed from 1-minute input
```

#### Resampling: Full Code Flow and Call Chain

Let's trace exactly what happens when you call `data.resample(...)` and then
run the backtest.

**Phase 1: Setup — `data.resample()` Call Chain**

```
data.resample(timeframe=bt.TimeFrame.Minutes, compression=5)
    │
    └── self.addfilter(Resampler, timeframe=Minutes, compression=5)
        │
        │   # Resampler is a CLASS (inspect.isclass → True):
        ├── pobj = Resampler(self, timeframe=Minutes, compression=5)
        │   │
        │   │   # Resampler inherits _BaseResampler
        │   │   # _BaseResampler.__init__(self, data):
        │   │
        │   ├── self.subdays = True
        │   │   # Ticks(1) < Minutes(4) < Days(5) → True
        │   │   # "subdays" means the target timeframe is intra-day
        │   │
        │   ├── self.componly = False
        │   │   # componly would be True if input and output timeframe
        │   │   # are the SAME (e.g. 1-min → 5-min same Minutes frame
        │   │   # AND 5 % 1 == 0). For 1-min → 5-min:
        │   │   #   data._timeframe (Minutes) == self.p.timeframe (Minutes)
        │   │   #   and not (5 % 1) → not 0 → not False → True?
        │   │   # Actually: 5 % 1 == 0, not 0 == True → componly = True
        │   │   # (When timeframes match, it's "compression only" mode)
        │   │
        │   ├── self.bar = _Bar(maxdate=True)
        │   │   # _Bar is an accumulator dict:
        │   │   #   bar.close = NaN, bar.low = inf, bar.high = -inf
        │   │   #   bar.open = NaN, bar.volume = 0, bar.datetime = MAXDATE
        │   │
        │   ├── self.compcount = 0
        │   │   # Counts input bars consumed, used with compression
        │   │
        │   ├── data.resampling = 1        ← marks data as being resampled
        │   ├── data.replaying = 0         ← Resampler.replaying = False
        │   ├── data._timeframe = Minutes  ← OUTPUT timeframe
        │   └── data._compression = 5      ← OUTPUT compression
        │
        ├── self._filters.append((pobj, [], {}))
        │   # The Resampler instance is now in the filter pipeline
        │
        └── pobj has .last() → self._ffilters.append((pobj, [], {}))
            # Also registered as a "final filter" for end-of-data
```

**Phase 2: Runtime — How Each Bar Flows Through the Resampler**

During `cerebro.run()`, every bar loaded from CSV passes through the
Resampler filter in the `load()` loop:

```
load() loop iteration:
    │
    ├── forward()                   ← allocate slot in line arrays
    ├── _load()                     ← read 1 CSV line (1-minute bar)
    │   fills: close[0]=100.50, high[0]=100.80, low[0]=100.20,
    │          open[0]=100.30, volume[0]=5000, datetime[0]=10:01
    │
    ├── date range checks           ← pass
    │
    └── filter pipeline:
        retff = Resampler.__call__(data)
```

**The Resampler `__call__` method is the heart of resampling.** It is called
for every 1-minute input bar. Here's the detailed flow for the `componly=True`
case (same timeframe, different compression):

```python
def __call__(self, data, fromcheck=False, forcedata=None):
    consumed = False
    onedge = False
    docheckover = True

    if not fromcheck:
        # componly=True for 1-min → 5-min (same Minutes timeframe)
        if self.componly:
            _, self._lastdteos = self.data._getnexteos()  # session end ref
            consumed = True

    if consumed:
        self.bar.bupdate(data)    # accumulate input bar into _Bar
        data.backwards()          # ERASE input bar from line arrays

    # Check if resampled bar is complete:
    cond = self.bar.isopen()      # is there accumulated data?
    if cond:
        if docheckover:
            cond = self._checkbarover(data, ...)

    if cond:    # bar boundary crossed
        # DELIVER the completed resampled bar:
        data._add2stack(self.bar.lvalues())
        self.bar.bstart(maxdate=True)   # reset accumulator

    if not consumed:
        self.bar.bupdate(data)    # accumulate
        data.backwards()          # erase input bar

    return True    # always returns True (bar was handled by filter)
```

**The `_Bar.bupdate()` accumulation logic:**

```python
def bupdate(self, data, reopen=False):
    self.datetime = data.datetime[0]         # latest datetime

    self.high = max(self.high, data.high[0]) # running maximum
    self.low = min(self.low, data.low[0])    # running minimum
    self.close = data.close[0]               # latest close

    self.volume += data.volume[0]            # sum volumes
    self.openinterest = data.openinterest[0] # latest OI

    o = self.open
    if not o == o:                           # NaN check (first update)
        self.open = data.open[0]             # set open from first bar
        return True
    return False
```

**The `_checkbarover()` boundary detection:**

```python
def _checkbarover(self, data, fromcheck=False, forcedata=None):
    if not self.componly and not self._barover(chkdata):
        return False

    # For componly mode: count input bars
    self.compcount += 1
    if not (self.compcount % self.p.compression):
        # e.g. compression=5: fires when compcount is 5, 10, 15, ...
        return True    # boundary reached!

    return False
```

**Phase 3: Step-by-Step Trace — Five 1-Minute Bars → One 5-Minute Bar**

```
CSV input (1-minute bars):
  10:01  O=100.00 H=100.50 L=99.80  C=100.30 V=5000
  10:02  O=100.30 H=100.80 L=100.10 C=100.60 V=4000
  10:03  O=100.60 H=101.00 L=100.40 C=100.80 V=6000
  10:04  O=100.80 H=101.20 L=100.50 C=100.90 V=3000
  10:05  O=100.90 H=101.50 L=100.70 C=101.30 V=7000

─── Bar 1: 10:01 ──────────────────────────────────────────

load():
  forward()         → close.array = [..., NaN]
  _load()           → close.array = [..., 100.30], datetime = 10:01

Resampler.__call__():
  consumed = True (componly)
  bar.bupdate(data):
    bar.open = 100.00  (first update, was NaN)
    bar.high = 100.50
    bar.low  = 99.80
    bar.close = 100.30
    bar.volume = 5000
    bar.datetime = 10:01
  data.backwards()   → 100.30 ERASED from close.array

  bar.isopen() → True (open is 100.00, not NaN)
  _checkbarover():
    compcount = 1
    1 % 5 = 1 → NOT zero → return False

  return True        → load() loops back (bar consumed by filter)

─── Bar 2: 10:02 ──────────────────────────────────────────

Resampler.__call__():
  bar.bupdate(data):
    bar.high = max(100.50, 100.80) = 100.80  ← updated
    bar.low  = min(99.80, 100.10)  = 99.80   ← unchanged
    bar.close = 100.60                        ← updated
    bar.volume = 5000 + 4000 = 9000          ← accumulated
  data.backwards()

  compcount = 2, 2 % 5 = 2 → NOT zero → not delivered

─── Bar 3: 10:03 ──────────────────────────────────────────

  bar.bupdate: high=101.00, close=100.80, volume=15000
  compcount = 3, 3 % 5 = 3 → not delivered

─── Bar 4: 10:04 ──────────────────────────────────────────

  bar.bupdate: high=101.20, close=100.90, volume=18000
  compcount = 4, 4 % 5 = 4 → not delivered

─── Bar 5: 10:05 ──────────────────────────────────────────

Resampler.__call__():
  bar.bupdate(data):
    bar.high = max(101.20, 101.50) = 101.50
    bar.low  = min(99.80, 100.70)  = 99.80
    bar.close = 101.30
    bar.volume = 18000 + 7000 = 25000
  data.backwards()

  compcount = 5, 5 % 5 = 0 → YES! Bar is complete!

  DELIVER:
    data._add2stack(self.bar.lvalues())
    # bar.lvalues() returns the accumulated values as a list:
    # [101.30, 99.80, 101.50, 100.00, 25000, 0.0, <datetime 10:05>]
    # (order: close, low, high, open, volume, OI, datetime)
    #
    # This list is pushed onto data._barstack

    self.bar.bstart(maxdate=True)
    # Reset accumulator: open=NaN, high=-inf, low=inf, ...

  return True → load() loops back

─── Next load() iteration ─────────────────────────────────

load():
  forward()           → allocate new slot
  _fromstack()        → POP from _barstack → fill lines[0]:
    close[0]    = 101.30
    low[0]      = 99.80
    high[0]     = 101.50
    open[0]     = 100.00
    volume[0]   = 25000
    datetime[0] = 10:05
  return True         → 5-MINUTE BAR DELIVERED!
```

**Summary of the data flow:**

```
CSV file                    Resampler filter               Line arrays
─────────                   ────────────────               ───────────
1-min bar 10:01 ──load()──► bupdate → backwards()         (erased)
1-min bar 10:02 ──load()──► bupdate → backwards()         (erased)
1-min bar 10:03 ──load()──► bupdate → backwards()         (erased)
1-min bar 10:04 ──load()──► bupdate → backwards()         (erased)
1-min bar 10:05 ──load()──► bupdate → backwards()         (erased)
                            │
                            ├── compcount=5 → DELIVER!
                            └── _add2stack(bar) ──────────► _fromstack()
                                                            │
                                                            ▼
                                                 5-min bar in lines:
                                                 O=100.00 H=101.50
                                                 L=99.80  C=101.30
                                                 V=25000  dt=10:05
                                                            │
                                                            ▼
                                                 return True
                                                 (strategy sees this bar)
```

**Phase 4: End of Data — `Resampler.last()`**

When all CSV lines are exhausted, `load()` calls `_last()`, which calls
`Resampler.last()`. If there's a partially accumulated bar (e.g., only 3 of 5
minutes arrived before the data ended), it delivers that partial bar:

```python
def last(self, data):
    if self.bar.isopen():                    # partial bar exists?
        if self.doadjusttime:
            self._adjusttime()               # adjust bar timestamp

        data._add2stack(self.bar.lvalues())  # deliver partial bar
        self.bar.bstart(maxdate=True)        # reset
        return True

    return False
```

```
Example: CSV ends after 10:03 (only 3 of 5 minutes):

  10:01 → bupdate (compcount=1)
  10:02 → bupdate (compcount=2)
  10:03 → bupdate (compcount=3)
  _load() → False (EOF)

  _last() → Resampler.last():
    bar.isopen() → True (has accumulated data)
    _add2stack([100.80, 99.80, 101.00, 100.00, 15000, 0, 10:03])
    → partial 3-minute bar delivered

  Without .last(), those 3 minutes of data would be lost!
```

**Phase 5: Cerebro-Level Resampling (Alternative API)**

Instead of calling `data.resample()` directly, you can also use Cerebro's API.
This does the same thing but through a different entry point:

```python
# Direct method (what we traced above):
data = bt.feeds.GenericCSVData(dataname='1min.csv', timeframe=bt.TimeFrame.Minutes)
data.resample(timeframe=bt.TimeFrame.Minutes, compression=5)
cerebro.adddata(data)

# Cerebro method (equivalent, creates a DataClone):
data = bt.feeds.GenericCSVData(dataname='1min.csv', timeframe=bt.TimeFrame.Minutes)
cerebro.adddata(data)                     # add original 1-min data
cerebro.resampledata(data, timeframe=bt.TimeFrame.Minutes, compression=5)
# cerebro.resampledata() internally does:
#   clone = data.clone()             → DataClone pointing at data
#   clone.resample(timeframe=Minutes, compression=5)
#   cerebro.adddata(clone)
#   return clone
#
# Now the strategy sees TWO data feeds:
#   self.data0 = original 1-min data
#   self.data1 = resampled 5-min data (DataClone + Resampler)
```

### Method: `qbuffer(self, savemem=0, replaying=False)`

Switches all lines to QBuffer (memory-saving deque) mode.

```python
def qbuffer(self, savemem=0, replaying=False):
    extrasize = self.resampling or replaying
    for line in self.lines:
        line.qbuffer(savemem=savemem, extrasize=extrasize)
```

**Example:**

```python
# Called by Cerebro when exactbars > 0:
# cerebro = bt.Cerebro(exactbars=True)
#   → data.qbuffer(savemem=0, replaying=False)
#   → for each of data's 7 lines:
#       line.qbuffer()
#       line.array = collections.deque(maxlen=line._minperiod)
#       line.mode = QBuffer
```

### Methods: `_tick_nullify(self)` and `_tick_fill(self, force=False)`

These two methods manage a set of **instance attributes** (`tick_close`, `tick_open`,
`tick_high`, `tick_low`, `tick_volume`, `tick_openinterest`, `tick_last`) that
shadow the data feed's line values. They exist to solve a specific problem:

**The Problem:** In replay mode or live data, a bar can be **updated multiple times**
before it is finalized. The bar's `lines` (close, high, low, etc.) are updated
in-place at `line[0]`, but the broker needs to know the **current sub-bar prices**
for order execution — even when the bar hasn't "advanced" yet (i.e., `len(data)`
hasn't changed). The `tick_*` attributes provide this intermediate state.

**The Key Consumer:** The broker's `_try_exec()` method reads these attributes
to get the most current prices for order matching:

```python
# backtrader/brokers/bbroker.py — _try_exec():
def _try_exec(self, order):
    data = order.data

    popen = getattr(data, 'tick_open', None)
    if popen is None:
        popen = data.open[0]           # fallback to bar value

    phigh = getattr(data, 'tick_high', None)
    if phigh is None:
        phigh = data.high[0]

    plow = getattr(data, 'tick_low', None)
    if plow is None:
        plow = data.low[0]

    pclose = getattr(data, 'tick_close', None)
    if pclose is None:
        pclose = data.close[0]

    # Use these prices for order execution:
    if order.exectype == Order.Market:
        self._try_exec_market(order, popen, phigh, plow)
    elif order.exectype == Order.Limit:
        self._try_exec_limit(order, popen, phigh, plow, pcreated)
    # ... etc.
```

#### `_tick_nullify(self)` — Reset All Tick Attributes to None

Called at the **start** of a new bar (when `advance()` or `next()` begins processing).
It signals "we don't have tick data for this bar yet."

```python
def _tick_nullify(self):
    # These are the updating prices in case the new bar is "updated"
    # and the length doesn't change like if a replay is happening or
    # a real-time data feed is in use and 1 minutes bars are being
    # constructed with 5 seconds updates
    for lalias in self.getlinealiases():
        if lalias != 'datetime':
            setattr(self, 'tick_' + lalias, None)
            # Sets: self.tick_close = None
            #       self.tick_low = None
            #       self.tick_high = None
            #       self.tick_open = None
            #       self.tick_volume = None
            #       self.tick_openinterest = None

    self.tick_last = None
```

#### `_tick_fill(self, force=False)` — Populate Tick Attributes from Current Bar

Called **after** a bar has been loaded or advanced to. Copies the current
`lines[0]` values into the `tick_*` attributes.

```python
def _tick_fill(self, force=False):
    # alias0 = the first line alias = 'close' (index 0 in OHLC declaration)
    alias0 = self._getlinealias(0)

    # Only fill if tick_close is still None (hasn't been set by a
    # live feed or replay), OR if force=True
    if force or getattr(self, 'tick_' + alias0, None) is None:
        for lalias in self.getlinealiases():
            if lalias != 'datetime':
                setattr(self, 'tick_' + lalias,
                        getattr(self.lines, lalias)[0])
                # Sets: self.tick_close = self.lines.close[0]
                #       self.tick_high  = self.lines.high[0]
                #       self.tick_low   = self.lines.low[0]
                #       self.tick_open  = self.lines.open[0]
                #       etc.

        self.tick_last = getattr(self.lines, alias0)[0]
        # self.tick_last = self.lines.close[0]
```

**The `force` parameter:** When `force=False` (default), `_tick_fill` only fills
if `tick_close` is still `None` — meaning nothing else has set tick data yet.
When `force=True`, it overwrites unconditionally. The resampler and Cerebro's
multi-data synchronization use `force=True` to ensure tick data is always current.

#### Where They Are Called

```
advance(ticks=True):
    │
    ├── _tick_nullify()           ← RESET: new bar starting
    ├── lines.advance(size)       ← move pointer
    └── _tick_fill()              ← FILL: populate from bar values

next(ticks=True):
    │
    ├── _tick_nullify()           ← RESET: about to load new bar
    ├── load()                    ← load from source
    └── _tick_fill()              ← FILL: populate from loaded bar

Resampler.__call__():
    │
    └── data._tick_fill(force=True)  ← FORCE FILL after each sub-bar update

Cerebro._runnext() multi-data sync:
    │
    └── di._tick_fill(force=True)    ← FORCE FILL for synchronized data
```

#### Example 1 — Normal Daily Bar (No Replay)

In the simplest case (preloaded daily bars), tick attributes simply mirror the bar:

```python
# During _oncepost iteration over preloaded daily data:

# advance() called:
#   _tick_nullify() → tick_close=None, tick_open=None, ...
#   lines.advance()  → idx moves to next bar
#   _tick_fill()     → tick_close = lines.close[0] = 38.01
#                       tick_open  = lines.open[0]  = 37.77
#                       tick_high  = lines.high[0]  = 38.06
#                       tick_low   = lines.low[0]   = 37.50
#                       tick_last  = lines.close[0] = 38.01

# In broker._try_exec():
#   popen = data.tick_open   → 37.77  (same as data.open[0])
#   phigh = data.tick_high   → 38.06  (same as data.high[0])
#   pclose = data.tick_close → 38.01  (same as data.close[0])
# No difference from bar values — tick_* is just a copy
```

#### Example 2 — Replay Mode (Bar Updated Multiple Times)

This is where tick attributes become essential. In replay mode, a higher-timeframe
bar is "replayed" by receiving multiple updates as sub-bars arrive:

```python
# Replaying 5-second ticks into 1-minute bars:
data = bt.feeds.GenericCSVData(
    dataname='ticks.csv',
    timeframe=bt.TimeFrame.Ticks,
)
data.replay(timeframe=bt.TimeFrame.Minutes, compression=1)

# The 10:00 1-minute bar is built from multiple ticks:

# ─── Tick 1: 10:00:05 ──────────────────────────────────
#   Replayer updates the bar in-place:
#     data.lines.open[0]   = 100.00
#     data.lines.high[0]   = 100.00
#     data.lines.low[0]    = 100.00
#     data.lines.close[0]  = 100.00
#     data.lines.volume[0] = 50
#
#   data._tick_fill(force=True) called by Replayer:
#     data.tick_open   = 100.00
#     data.tick_high   = 100.00
#     data.tick_low    = 100.00
#     data.tick_close  = 100.00
#     data.tick_volume = 50
#     data.tick_last   = 100.00
#
#   strategy.next() called (len(data) = 1, same bar):
#     # Broker checks pending orders using tick_* prices
#     # Limit buy at 99.90? tick_low=100.00 > 99.90 → NOT filled

# ─── Tick 2: 10:00:15 ──────────────────────────────────
#   Replayer updates the SAME bar (len doesn't change):
#     data.lines.high[0]   = 100.50  (new high)
#     data.lines.close[0]  = 100.50
#     data.lines.volume[0] = 120     (accumulated)
#
#   data._tick_fill(force=True):
#     data.tick_high   = 100.50     ← UPDATED
#     data.tick_close  = 100.50     ← UPDATED
#     data.tick_volume = 120        ← UPDATED
#
#   strategy.next() called AGAIN (same len(data) = 1):
#     # Broker: tick_low still 100.00, limit buy at 99.90 → NOT filled

# ─── Tick 3: 10:00:45 ──────────────────────────────────
#   Replayer updates the SAME bar:
#     data.lines.low[0]    = 99.80  (new low!)
#     data.lines.close[0]  = 99.85
#     data.lines.volume[0] = 200
#
#   data._tick_fill(force=True):
#     data.tick_low    = 99.80      ← UPDATED
#     data.tick_close  = 99.85      ← UPDATED
#
#   strategy.next() called AGAIN (same len(data) = 1):
#     # Broker: tick_low=99.80 < 99.90 → LIMIT BUY FILLED at 99.90!
#     # Without tick_*, the broker would only see the final bar values
#     # and might miss intra-bar order triggers.

# ─── Bar complete at 10:01:00 ──────────────────────────
#   advance() → _tick_nullify() → all tick_* = None
#   New bar starts, cycle repeats
```

#### Example 3 — Live Data Feed (Incremental Bar Construction)

```python
class MyLiveFeed(bt.feeds.DataBase):
    """Builds 1-minute bars from streaming ticks."""

    def islive(self):
        return True

    def _load(self):
        tick = self.api.get_next_tick(timeout=self._qcheck)
        if tick is None:
            return None  # no tick yet

        # Update the current bar in-place
        self.lines.datetime[0] = bt.date2num(tick['time'])
        self.lines.close[0] = tick['price']
        self.lines.volume[0] += tick['size']

        if tick['price'] > self.lines.high[0] or self.lines.high[0] != self.lines.high[0]:
            self.lines.high[0] = tick['price']
        if tick['price'] < self.lines.low[0] or self.lines.low[0] != self.lines.low[0]:
            self.lines.low[0] = tick['price']

        # Manually set tick attributes for the broker:
        self.tick_close = tick['price']
        self.tick_high = self.lines.high[0]
        self.tick_low = self.lines.low[0]
        self.tick_open = self.lines.open[0]
        self.tick_volume = self.lines.volume[0]
        self.tick_last = tick['price']

        return True

# Now the broker can match orders against the latest tick price,
# even though the bar hasn't been finalized yet.
```

#### Example 4 — Multi-Data Synchronization in Cerebro

When multiple data feeds with different timeframes are used, Cerebro forces
`_tick_fill` to keep tick data consistent:

```python
# Daily data + Weekly data:
# On Monday, the weekly bar hasn't completed yet.
# Cerebro syncs the weekly data's tick_* to the current daily values:

# In cerebro._runnext():
for i, dti in enumerate(dts):
    if dti is not None:
        di = datas[i]
        if dti > dt0:
            di.rewind()                      # not time for this data yet
        elif not di.replaying:
            di._tick_fill(force=True)        # force-sync tick attributes

# This ensures:
#   weekly_data.tick_close = latest daily close
#   weekly_data.tick_high  = week-to-date high
# So orders placed against weekly data use current prices
```

#### Example 5 — Why `force=False` Matters

```python
# In normal advance() flow:
#   _tick_nullify()        → tick_close = None
#   lines.advance()        → idx += 1, close[0] now has bar value
#   _tick_fill(force=False) → tick_close is None, so fill it
#
# tick_close = lines.close[0] = 38.01  ← filled because was None

# But if a live feed or replay has ALREADY set tick_close before
# _tick_fill is called:
#   self.tick_close = 38.05   (set by live feed with latest tick)
#   _tick_fill(force=False)   → tick_close is 38.05, NOT None → SKIP
#
# The live feed's more current price is preserved!
# The bar's close[0] might be 38.01 (previous tick), but tick_close
# is 38.05 (latest tick) — the broker correctly uses 38.05.

# When force=True (resampler, cerebro sync):
#   _tick_fill(force=True)  → always overwrites, regardless of current value
#   Ensures tick_* matches the current lines[0] values exactly
```

#### Summary: The Nullify/Fill Lifecycle

```
┌────────────────────────────────────────────────────────────────────────┐
│                    TICK ATTRIBUTE LIFECYCLE                             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │  nullify()  │───►│  load/adv   │───►│   fill()    │                │
│  │             │    │             │    │             │                │
│  │ tick_close  │    │ lines get   │    │ tick_close  │                │
│  │  = None     │    │ new values  │    │  = close[0] │                │
│  │ tick_high   │    │             │    │ tick_high   │                │
│  │  = None     │    │ (or replay  │    │  = high[0]  │                │
│  │ tick_low    │    │  updates    │    │ tick_low    │                │
│  │  = None     │    │  in-place)  │    │  = low[0]   │                │
│  │ tick_last   │    │             │    │ tick_last   │                │
│  │  = None     │    │             │    │  = close[0] │                │
│  └─────────────┘    └─────────────┘    └──────┬──────┘                │
│                                               │                        │
│                                               ▼                        │
│                                        ┌─────────────┐                │
│                                        │   broker     │                │
│                                        │ _try_exec()  │                │
│                                        │             │                │
│                                        │ reads:      │                │
│                                        │ tick_open   │                │
│                                        │ tick_high   │                │
│                                        │ tick_low    │                │
│                                        │ tick_close  │                │
│                                        │             │                │
│                                        │ falls back  │                │
│                                        │ to line[0]  │                │
│                                        │ if None     │                │
│                                        └─────────────┘                │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Bar Stack Methods: `_add2stack`, `_save2stack`, `_updatebar`, `_fromstack`

These methods manage an internal bar stack used by filters to buffer,
rearrange, or inject bars.

```python
def _add2stack(self, bar, stash=False):
    '''Save a bar (list of values) to the stack for later retrieval'''
    if not stash:
        self._barstack.append(bar)
    else:
        self._barstash.append(bar)

def _save2stack(self, erase=False, force=False, stash=False):
    '''Save the CURRENT bar to the stack'''
    bar = [line[0] for line in self.itersize()]  # snapshot current bar
    if not stash:
        self._barstack.append(bar)
    else:
        self._barstash.append(bar)
    if erase:
        self.backwards(force=force)              # remove from lines

def _updatebar(self, bar, forward=False, ago=0):
    '''Write a bar's values into the lines'''
    if forward:
        self.forward()
    for line, val in zip(self.itersize(), bar):
        line[0 + ago] = val

def _fromstack(self, forward=False, stash=False):
    '''Pop a bar from the stack into the lines'''
    coll = self._barstack if not stash else self._barstash
    if coll:
        if forward:
            self.forward()
        for line, val in zip(self.itersize(), coll.popleft()):
            line[0] = val
        return True
    return False
```

#### Stack vs Stash: Two Separate Queues

The data feed has **two** deques for buffering bars:

```python
self._barstack = collections.deque()   # "stack" — deliver THIS load() cycle
self._barstash = collections.deque()   # "stash" — deliver NEXT load() cycle
```

The critical difference is **when** bars in each queue get delivered. Look
at the priority order inside `load()`:

```python
def load(self):
    while True:
        self.forward()                          # 1. make room

        if self._fromstack():                   # 2. FIRST: check stack
            return True                         #    → deliver immediately

        if not self._fromstack(stash=True):     # 3. SECOND: check stash
            _loadret = self._load()             # 4. THIRD: read from source
            if not _loadret:
                self.backwards(force=True)
                return _loadret

        # ... date filtering, user filters ...
```

**The stack (`_barstack`)** is checked first. Any bar placed on the stack
during a filter's `__call__` will be popped and delivered in the **current**
`load()` iteration (or the very next one if the filter returns `True`).

**The stash (`_barstash`)** is checked only if the stack is empty. Bars
placed on the stash will be delivered in the **next** `load()` call, after
all stack bars are consumed. This creates a **one-cycle delay**.

```
┌────────────────────────────────────────────────────────────────────┐
│                    DELIVERY PRIORITY                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   load() called                                                    │
│       │                                                            │
│       ├── 1. _barstack has bars? ──── YES → deliver → return True  │
│       │       │                                                    │
│       │      NO                                                    │
│       │       │                                                    │
│       ├── 2. _barstash has bars? ──── YES → pop into lines[0]      │
│       │       │                        (treated as if _load() did)  │
│       │       │                        → continue to date/filter    │
│       │      NO                        checks                      │
│       │       │                                                    │
│       └── 3. _load() from source ──── read CSV/API                 │
│                                                                    │
│   Stack  = "deliver NOW"     (skips date/filter checks)            │
│   Stash  = "deliver NEXT"    (goes through date/filter checks)     │
│   Source = "read new data"   (goes through date/filter checks)     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Important subtlety:** Bars from the stack bypass date and filter checks
(the `_fromstack()` call is before the filter loop). Bars from the stash
go through the full pipeline (date checks, filters), because they're loaded
into `lines[0]` and execution continues to the filter loop below.

#### When To Use Stack vs Stash

| Use case | Queue | Why |
|---|---|---|
| Filter produces a completed bar to deliver immediately | **Stack** | Skip further processing, deliver now |
| Filter splits one bar into two; first part is for now | **Stack** | Deliver first part this cycle |
| Filter splits one bar into two; second part is for later | **Stash** | Deliver second part next cycle |
| Filter fills calendar gaps with synthetic bars | **Stack** | Inject bars before the real bar |
| Filter saves the real bar for delivery after injected bars | **Stack** (via `_save2stack`) | Queue behind the gap-fill bars |
| Resampler delivers a completed higher-timeframe bar | **Stack** | Deliver the resampled bar immediately |

#### Example 1: Resampler — Stack Only

The Resampler only uses `_barstack`. When 5 input bars have been accumulated
into a 5-minute bar, it delivers the result:

```python
# Inside Resampler.__call__() when bar is complete:
data._add2stack(self.bar.lvalues())     # → _barstack.append(bar_values)
self.bar.bstart(maxdate=True)           # reset accumulator

# Then Resampler returns True (bar consumed)
# load() loops back:
#   forward()
#   _fromstack() → pops from _barstack → fills lines[0] → return True
#   → 5-minute bar delivered to strategy
```

```
Timeline:
  load() #1: _load()=10:01 → filter: bupdate, backwards, return True → loop
  load() #2: _load()=10:02 → filter: bupdate, backwards, return True → loop
  ...
  load() #5: _load()=10:05 → filter: bupdate, backwards, _add2stack → return True → loop
  load() #6: forward, _fromstack() → POP 5-min bar → return True → DELIVERED
  load() #7: _load()=10:06 → next cycle begins...
```

#### Example 2: CalendarDays — Stack for Gap-Filling

The `CalendarDays` filter detects gaps in the calendar (weekends, holidays)
and injects synthetic bars. It uses the stack to inject bars **before** the
real bar that triggered the gap:

```python
# backtrader/filters/calendardays.py:

def __call__(self, data):
    dt = data.datetime.date()
    if (dt - self.lastdt) > self.ONEDAY:    # gap detected!
        self._fillbars(data, dt, self.lastdt)
    self.lastdt = dt
    return False   # bar is NOT removed (return False)

def _fillbars(self, data, dt, lastdt):
    while lastdt < dt:
        lastdt += self.ONEDAY
        bar = [float('Nan')] * data.size()
        bar[data.DateTime] = data.date2num(datetime.combine(lastdt, tm))
        # fill price, volume, etc.
        data._add2stack(bar)           # synthetic bar → STACK

    data._save2stack(erase=True)       # real bar → STACK (after synthetics)
```

**Trace: Friday → Monday gap fill:**

```
Input CSV has: Friday 2014-03-07, Monday 2014-03-10 (gap: Sat + Sun)

load() iteration for Monday bar:
  forward()
  _fromstack() → empty
  _load() → reads Monday 2014-03-10 bar → fills lines[0]
  date checks → pass
  filter: CalendarDays.__call__(data):
    dt = 2014-03-10
    lastdt = 2014-03-07
    gap = 3 days > 1 day → _fillbars!
    │
    ├── lastdt += 1 → 2014-03-08 (Saturday)
    │   bar = [NaN, NaN, ..., Sat datetime, fill_price, ...]
    │   data._add2stack(bar)              ← Stack: [Sat]
    │
    ├── lastdt += 1 → 2014-03-09 (Sunday)
    │   bar = [NaN, NaN, ..., Sun datetime, fill_price, ...]
    │   data._add2stack(bar)              ← Stack: [Sat, Sun]
    │
    └── data._save2stack(erase=True)
        # Snapshot Monday's values from lines[0] into a list
        # Append to stack
        # backwards() erases Monday from lines
        # Stack: [Sat, Sun, Mon]

    return False (bar not "removed" by this filter's return code,
                  but it was erased+re-stacked by _save2stack)

  Back in load()'s filter loop:
    retff = False → the filter "didn't remove" the bar
    But the stack now has 3 bars!

  Next load() iterations:
    load() → forward, _fromstack() → pops Saturday bar → return True
    load() → forward, _fromstack() → pops Sunday bar  → return True
    load() → forward, _fromstack() → pops Monday bar  → return True

  Strategy sees: ..., Friday, Saturday, Sunday, Monday, ...
  (gaps filled with synthetic bars)
```

#### Example 3: DaySplitter_Close — Stack + Stash Together

This is the canonical example of using **both** queues. The `DaySplitter_Close`
filter splits each daily bar into two ticks for replay:
- **First tick (OHL):** open/high/low with a synthetic close, timestamped at session open
- **Second tick (Close):** close price only, timestamped at session close

The first tick should be delivered **now** (stack), the second tick should be
delivered in the **next** `load()` call (stash):

```python
# backtrader/filters/bsplitter.py:

def __call__(self, data):
    # Snapshot and split the daily bar:
    ohlbar = [data.lines[i][0] for i in range(data.size())]
    closebar = ohlbar[:]

    # ohlbar: Open, High, Low, synthetic close, session-start time
    ohlbar[data.Close] = (ohlbar[data.Open] + ohlbar[data.High]
                          + ohlbar[data.Low]) / 3.0
    dt = datetime.combine(datadt, data.p.sessionstart)
    ohlbar[data.DateTime] = data.date2num(dt)

    # closebar: Close price for all OHLC, session-end time
    closebar[data.Open] = closebar[data.Close]
    closebar[data.High] = closebar[data.Close]
    closebar[data.Low] = closebar[data.Close]
    dt = datetime.combine(datadt, data.p.sessionend)
    closebar[data.DateTime] = data.date2num(dt)

    data.backwards(force=True)              # remove original daily bar

    data._add2stack(ohlbar)                 # OHL tick → STACK (deliver NOW)
    data._add2stack(closebar, stash=True)   # Close tick → STASH (deliver NEXT)

    return False  # don't skip further processing
```

**Trace:**

```
load() #1: Daily bar for 2014-03-10

  forward()
  _fromstack() → empty
  _load() → reads daily bar: O=100, H=105, L=98, C=103, V=50000
  filter: DaySplitter_Close.__call__():
    │
    ├── ohlbar  = [103, 98, 105, 100, 50000, 0, <10:00>]  (close replaced with avg)
    │              close  low high  open  vol   OI  datetime
    │   ohlbar[Close] = (100+105+98)/3 = 101.0
    │   ohlbar[DateTime] = 09:30 (session start)
    │   ohlbar[Volume] = 25000 (50% of original)
    │
    ├── closebar = [103, 103, 103, 103, 25000, 0, <16:00>]
    │               close low  high open  vol   OI  datetime
    │   closebar[DateTime] = 16:00 (session end)
    │
    ├── data.backwards(force=True)     ← erase original daily bar
    ├── data._add2stack(ohlbar)        ← _barstack = [ohlbar]
    └── data._add2stack(closebar, stash=True)  ← _barstash = [closebar]

  return False → load() continues filter processing
  But _barstack now has ohlbar!

  Next part of load() filter loop:
    _barstack is not empty:
      _fromstack(forward=True) → pop ohlbar into lines[0]
      pass through remaining filters (if any)

  ... date checks pass, return True
  → OHL tick delivered to strategy (09:30, O=100 H=105 L=98 C=101)

load() #2: Next call to load()

  forward()
  _fromstack() → _barstack is empty
  _fromstack(stash=True) → _barstash has closebar!
    → pop closebar into lines[0]
    → execution continues to date/filter checks (normal processing)

  ... date checks pass, filters pass, return True
  → Close tick delivered to strategy (16:00, O=103 H=103 L=103 C=103)

Strategy sees two bars for the same day:
  Bar 1 (09:30): O=100 H=105 L=98  C=101 V=25000  ← "market opens"
  Bar 2 (16:00): O=103 H=103 L=103 C=103 V=25000  ← "market closes"
```

**Why the stash is necessary here:** If both bars were put on the stack,
they would both be delivered in the same `load()` cycle. But in replay mode,
the Replayer needs to see them as **separate events** — first the open tick
triggers strategy processing, then the close tick arrives as a new event.
The stash delays the close tick to the next `load()` call, creating the
two-step simulation.

#### Example 4: Session Filter — Stack for Bar Rearrangement

```python
# backtrader/filters/session.py:
# Fills missing intraday bars during a session

def _fillbars(self, data, ...):
    while time_start < current_time:
        time_start += self._tdunit

        bar = [data.lines[i][0] for i in range(data.size())]
        bar[data.DateTime] = data.date2num(datetime.combine(dt, time_start))
        data._add2stack(bar)             # synthetic bar → stack

    if dirty and tostack:
        data._save2stack(erase=True)     # real bar → stack (after fills)
```

#### Summary: Stack vs Stash Decision Flowchart

```
"Should I use stack or stash?"

 Does the bar need to be delivered        ┌─────────┐
 in the CURRENT load() cycle?  ── YES ──► │  STACK  │
       │                                   │ _add2stack(bar)
      NO                                   │ or _save2stack()
       │                                   └─────────┘
       ▼
 Does the bar need to go through           ┌─────────┐
 date/filter checks when delivered? ─ YES ─► │  STASH  │
       │                                   │ _add2stack(bar, stash=True)
      NO                                   │ or _save2stack(stash=True)
       │                                   └─────────┘
       ▼
 ┌─────────┐
 │  STACK  │  (default — delivers immediately, skips checks)
 └─────────┘

 Common patterns:
   • Inject bars BEFORE the real bar   → stack (gap fill, rearrange)
   • Split 1 bar into 2 parts         → stack for part 1, stash for part 2
   • Produce a completed resampled bar → stack
   • Delay delivery to next cycle      → stash
```

---

## Class: DataBase

**File:** `backtrader/feed.py:599-600`

An empty class that exists purely for naming clarity. All concrete data feeds
inherit from this (or `CSVDataBase`) rather than `AbstractDataBase`.

```python
class DataBase(AbstractDataBase):
    pass
```

The metaclass `MetaAbstractDataBase.__init__` specifically excludes `DataBase`
from the registry (`name != 'DataBase'`), so only its subclasses get registered.

---

## Class: FeedBase

**File:** `backtrader/feed.py:603-635`
**Inherits from:** `object` (via `MetaParams`)

A container/factory for creating multiple related data feeds. Not commonly
used directly — most users create individual data feed objects. But it's
useful for multi-asset feeds from a single source.

```python
class FeedBase(with_metaclass(metabase.MetaParams, object)):
    params = () + DataBase.params._gettuple()
    # Inherits ALL of DataBase's params: dataname, name, timeframe, etc.

    def __init__(self):
        self.datas = list()

    def start(self):
        for data in self.datas:
            data.start()

    def stop(self):
        for data in self.datas:
            data.stop()

    def getdata(self, dataname, name=None, **kwargs):
        # Propagate feed-level params as defaults
        for pname, pvalue in self.p._getitems():
            kwargs.setdefault(pname, getattr(self.p, pname))
        kwargs['dataname'] = dataname
        data = self._getdata(**kwargs)
        data._name = name
        self.datas.append(data)
        return data

    def _getdata(self, dataname, **kwargs):
        for pname, pvalue in self.p._getitems():
            kwargs.setdefault(pname, getattr(self.p, pname))
        kwargs['dataname'] = dataname
        return self.DataCls(**kwargs)
```

**Example:**

```python
class MyMultiFeed(bt.feeds.FeedBase):
    """Load multiple tickers from the same data directory."""
    DataCls = bt.feeds.BacktraderCSVData

    def __init__(self, basepath=''):
        super().__init__()
        self.basepath = basepath

# Usage:
feed = MyMultiFeed(timeframe=bt.TimeFrame.Days)

# Create multiple data feeds with shared parameters:
orcl = feed.getdata(dataname='datas/orcl-2014.txt', name='ORCL')
yhoo = feed.getdata(dataname='datas/yhoo-2014.txt', name='YHOO')

# Both inherit timeframe=Days from the feed
# feed.datas = [orcl, yhoo]

cerebro = bt.Cerebro()
for data in feed.datas:
    cerebro.adddata(data)

feed.start()   # calls start() on both orcl and yhoo
# ... run ...
feed.stop()    # calls stop() on both
```

---

## Class: MetaCSVDataBase

**File:** `backtrader/feed.py:637-646`
**Inherits from:** `DataBase.__class__` (which is `MetaAbstractDataBase`)

Metaclass for CSV-based data feeds. Adds automatic name extraction from
the filename.

```python
class MetaCSVDataBase(DataBase.__class__):
    def dopostinit(cls, _obj, *args, **kwargs):
        # Extract name from filename BEFORE parent dopostinit
        if not _obj.p.name and not _obj._name:
            _obj._name, _ = os.path.splitext(
                os.path.basename(_obj.p.dataname))

        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs)
        return _obj, args, kwargs
```

**Example:**

```python
data = bt.feeds.BacktraderCSVData(
    dataname='/path/to/data/orcl-2014.txt'
)

# MetaCSVDataBase.dopostinit:
#   _obj.p.name = ''  and _obj._name = ''
#   os.path.basename('/path/to/data/orcl-2014.txt') = 'orcl-2014.txt'
#   os.path.splitext('orcl-2014.txt') = ('orcl-2014', '.txt')
#   _obj._name = 'orcl-2014'
#
# data._name = 'orcl-2014'  (used in plots, writer output, etc.)
```

---

## Class: CSVDataBase

**File:** `backtrader/feed.py:649-725`
**Inherits from:** `DataBase` (via metaclass `MetaCSVDataBase`)

Base class for CSV file data feeds. Handles file opening, line reading,
and tokenization. Subclasses only need to override `_loadline(tokens)`.

### Parameters

```python
params = (
    ('headers', True),       # Whether CSV has a header row to skip
    ('separator', ','),      # Column separator
)
# Plus all inherited params from DataBase
```

### Class Attribute

```python
f = None    # File handle (set during start())
```

### Method: `start(self)`

Opens the CSV file and skips headers.

```python
def start(self):
    super(CSVDataBase, self).start()

    if self.f is None:
        if hasattr(self.p.dataname, 'readline'):
            self.f = self.p.dataname          # already a file-like object
        else:
            self.f = io.open(self.p.dataname, 'r')  # open file by path

    if self.p.headers:
        self.f.readline()                     # skip header row

    self.separator = self.p.separator
```

**Example:**

```python
# From a file path:
data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')
# start() opens 'datas/orcl-2014.txt', skips header

# From a file-like object:
import io
csv_content = "Date,Open,High,Low,Close,Volume,OI\n2014-01-02,38.01,..."
f = io.StringIO(csv_content)
data = bt.feeds.BacktraderCSVData(dataname=f)
# start() uses the StringIO directly (it has .readline)
```

### Method: `stop(self)`

Closes the file handle.

```python
def stop(self):
    super(CSVDataBase, self).stop()
    if self.f is not None:
        self.f.close()
        self.f = None
```

### Method: `preload(self)`

Overrides `AbstractDataBase.preload()` to close the file early after loading.

```python
def preload(self):
    while self.load():
        pass

    self._last()
    self.home()

    # Close file after preloading — no need to keep it open
    # (Also avoids issues with multiprocessing in Python 3.x)
    self.f.close()
    self.f = None
```

### Method: `_load(self)`

Reads one line from the CSV, tokenizes it, and delegates to `_loadline()`.

```python
def _load(self):
    if self.f is None:
        return False

    line = self.f.readline()
    if not line:
        return False

    line = line.rstrip('\n')
    linetokens = line.split(self.separator)
    return self._loadline(linetokens)
```

**Example:**

```python
# CSV line: "2014-01-02,38.01,38.06,37.77,37.92,10892000,0"
# After split(','):
# linetokens = ['2014-01-02', '38.01', '38.06', '37.77', '37.92', '10892000', '0']
# → self._loadline(linetokens)
# Subclass parses tokens into self.lines.datetime[0], .open[0], etc.
```

### Method: `_loadline(self, linetokens)`

**Not defined in CSVDataBase** — subclasses must implement this.
Returns `True` if the line was successfully parsed.

**Example — BacktraderCSVData's Implementation:**

```python
class BacktraderCSVData(CSVDataBase):
    def _loadline(self, linetokens):
        itoken = iter(linetokens)

        dttxt = next(itoken)  # '2014-01-02'
        dt = date(int(dttxt[0:4]), int(dttxt[5:7]), int(dttxt[8:10]))

        if len(linetokens) == 8:  # has time column
            tmtxt = next(itoken)
            tm = time(int(tmtxt[0:2]), int(tmtxt[3:5]), int(tmtxt[6:8]))
        else:
            tm = self.p.sessionend

        self.lines.datetime[0] = date2num(datetime.combine(dt, tm))
        self.lines.open[0] = float(next(itoken))
        self.lines.high[0] = float(next(itoken))
        self.lines.low[0] = float(next(itoken))
        self.lines.close[0] = float(next(itoken))
        self.lines.volume[0] = float(next(itoken))
        self.lines.openinterest[0] = float(next(itoken))

        return True
```

### Method: `_getnextline(self)`

Utility to read and tokenize the next CSV line without loading into lines.
Returns the token list or `None` if no more data.

```python
def _getnextline(self):
    if self.f is None:
        return None

    line = self.f.readline()
    if not line:
        return None

    line = line.rstrip('\n')
    linetokens = line.split(self.separator)
    return linetokens
```

**Example:**

```python
# Used internally when a filter or resampler needs to peek ahead
# without committing the bar to the data lines:
tokens = data._getnextline()
if tokens:
    next_date = tokens[0]  # peek at date
    # decide whether to load or skip
```

---

## Class: CSVFeedBase

**File:** `backtrader/feed.py:728-733`
**Inherits from:** `FeedBase`

A `FeedBase` specialization for CSV feeds. Adds a `basepath` parameter
and constructs full file paths.

```python
class CSVFeedBase(FeedBase):
    params = (('basepath', ''),) + CSVDataBase.params._gettuple()

    def _getdata(self, dataname, **kwargs):
        return self.DataCls(
            dataname=self.p.basepath + dataname,
            **self.p._getkwargs()
        )
```

**Example:**

```python
class BacktraderCSV(CSVFeedBase):
    DataCls = BacktraderCSVData

# Usage:
feed = bt.feeds.BacktraderCSV(basepath='datas/')

orcl = feed.getdata(dataname='orcl-2014.txt', name='ORCL')
# Internally: BacktraderCSVData(dataname='datas/orcl-2014.txt', ...)

yhoo = feed.getdata(dataname='yhoo-2014.txt', name='YHOO')
# Internally: BacktraderCSVData(dataname='datas/yhoo-2014.txt', ...)

cerebro = bt.Cerebro()
for data in feed.datas:
    cerebro.adddata(data)
```

---

## Class: DataClone

**File:** `backtrader/feed.py:736-814`
**Inherits from:** `AbstractDataBase`

A lightweight "shadow" data feed that copies bars from another data feed.
Used when you need the same data as a separate object (e.g., for indicators
that need independent line references, or for resample/replay).

### Key Attribute

```python
_clone = True    # Marks this as a clone (affects _getnexteos delegation)
```

### Method: `__init__(self)`

```python
def __init__(self):
    self.data = self.p.dataname             # the source data feed (not a filename!)
    self._dataname = self.data._dataname

    # Copy parameters from source
    self.p.fromdate = self.p.fromdate
    self.p.todate = self.p.todate
    self.p.sessionstart = self.data.p.sessionstart
    self.p.sessionend = self.data.p.sessionend
    self.p.timeframe = self.data.p.timeframe
    self.p.compression = self.data.p.compression
```

### Method: `_start(self)`

Copies timezone and date info from the source data (not from params).

```python
def _start(self):
    self.start()
    self._tz = self.data._tz                       # copy timezone
    self.lines.datetime._settz(self._tz)
    self._calendar = self.data._calendar
    self._tzinput = None                           # already converted by source
    self.fromdate = self.data.fromdate
    self.todate = self.data.todate
    self.sessionstart = self.data.sessionstart
    self.sessionend = self.data.sessionend
```

### Method: `start(self)`

```python
def start(self):
    super(DataClone, self).start()
    self._dlen = 0                                 # tracks source position
    self._preloading = False
```

### Method: `preload(self)`

Preloads by copying all bars from the source.

```python
def preload(self):
    self._preloading = True
    super(DataClone, self).preload()               # calls load() repeatedly
    self.data.home()                               # reset source pointer
    self._preloading = False
```

### Method: `_load(self)`

The core copying logic. Behavior changes depending on whether we're preloading or running live.

```python
def _load(self):
    if self._preloading:
        # Source is preloaded, just copy each bar
        self.data.advance()
        if len(self.data) > self.data.buflen():
            return False                           # past end of source

        for line, dline in zip(self.lines, self.data.lines):
            line[0] = dline[0]                     # copy each line value
        return True

    # Live mode: check if source has advanced past our last seen position
    if not (len(self.data) > self._dlen):
        return False                               # no new bar from source

    self._dlen += 1
    for line, dline in zip(self.lines, self.data.lines):
        line[0] = dline[0]                         # copy each line value
    return True
```

### Method: `advance(self, size=1, datamaster=None, ticks=True)`

```python
def advance(self, size=1, datamaster=None, ticks=True):
    self._dlen += size                             # track position
    super(DataClone, self).advance(size, datamaster, ticks=ticks)
```

**Example — Using DataClone:**

```python
# You rarely create DataClone directly. It's created via .clone() or .copyas():

data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')
cerebro.adddata(data)

# Clone for resample to weekly:
data_weekly = data.clone()
data_weekly.resample(timeframe=bt.TimeFrame.Weeks)
cerebro.adddata(data_weekly)

# In the strategy, you now have:
#   self.data0 = daily data
#   self.data1 = weekly resampled data (clone of data0)

# How the clone works at runtime:
# 1. data0 loads a bar from CSV
# 2. data_weekly._load() copies the bar from data0
# 3. The Resampler filter on data_weekly accumulates daily bars
# 4. When a week boundary is reached, it delivers a weekly bar
```

**Example — Manual Clone Usage:**

```python
# Create original data
data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')
cerebro.adddata(data)

# Create a clone with a different name
data2 = data.copyas('ORCL_2')
cerebro.adddata(data2)

# In strategy:
class MyStrat(bt.Strategy):
    def __init__(self):
        # sma on original
        self.sma1 = bt.ind.SMA(self.data0, period=10)
        # sma on clone (same prices, independent line objects)
        self.sma2 = bt.ind.SMA(self.data1, period=20)
```

---

## Complete Data Loading Flow

Putting it all together, here's the complete flow from CSV file to strategy:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        DATA LOADING LIFECYCLE                              │
└────────────────────────────────────────────────────────────────────────────┘

1. CONSTRUCTION
   data = bt.feeds.BacktraderCSVData(dataname='orcl.txt')
   │
   ├── MetaAbstractDataBase.__new__() → creates class (if first time)
   │   └── registers in _indcol: {'BacktraderCSVData': cls}
   │
   ├── MetaAbstractDataBase.dopreinit()
   │   ├── _feed = findowner(FeedBase)     → None (standalone)
   │   ├── notifs = deque()
   │   └── _dataname = 'orcl.txt'
   │
   ├── MetaLineSeries.donew()
   │   └── Creates 7 LineBuffer objects:
   │       lines.close, .low, .high, .open, .volume, .openinterest, .datetime
   │
   ├── BacktraderCSVData.__init__()  (nothing to do)
   │
   └── MetaAbstractDataBase.dopostinit()
       ├── _name = 'orcl' (from filename)
       ├── _compression = 1
       ├── _timeframe = Days
       ├── sessionstart = time(0,0)
       ├── sessionend = time(23,59,59,999990)
       └── _barstack, _barstash, _filters, _ffilters initialized

2. CEREBRO SETUP
   cerebro.adddata(data)
   │
   ├── data.setenvironment(cerebro)  → data._env = cerebro
   ├── cerebro.datas.append(data)
   └── cerebro.datasbyname['orcl'] = data

3. RUN — START PHASE
   cerebro.run()
   │
   ├── data.reset()        → resets all lines to empty arrays
   ├── data.extend()       → adds lookahead slots if needed
   ├── data._start()
   │   ├── data.start()
   │   │   ├── _barstack = deque()
   │   │   ├── _barstash = deque()
   │   │   ├── _laststatus = CONNECTED
   │   │   └── (CSVDataBase.start opens file, skips headers)
   │   │
   │   └── data._start_finish()
   │       ├── _tz = _gettz()
   │       ├── datetime line gets tz
   │       ├── fromdate → numeric
   │       ├── todate → numeric
   │       └── _started = True
   │
   └── data.preload()      (if runonce mode)
       │
       └── while data.load():
           │   ├── forward()            ← allocate new slot
           │   ├── _fromstack()         ← check filter stack
           │   ├── _load()              ← read CSV line
           │   │   └── _loadline()      ← parse tokens into lines[0]
           │   ├── tz conversion
           │   ├── date filtering
           │   └── user filters
           │
           data._last()                 ← finalize filters
           data.home()                  ← idx = -1 for iteration

4. RUN — ITERATION PHASE (runonce)
   │
   ├── strat._once()       → indicators compute in batch
   │
   └── for each bar:
       data.advance()       → idx += 1 (no new loading)
       strat._oncepost()    → strategy.next() reads data.close[0]

5. RUN — ITERATION PHASE (runnext / live)
   │
   └── for each bar:
       data.next()
       ├── len >= buflen → data.load() → read new bar
       └── len < buflen → data.advance()

6. SHUTDOWN
   data.stop()
   └── (CSVDataBase.stop closes file)
```

---

## Practical Examples

### Example 1: Minimal Custom CSV Data Feed

```python
import backtrader as bt
from datetime import datetime

class MyCSVData(bt.feeds.CSVDataBase):
    """
    Parses CSV with format:
    Date,Close
    2014-01-02,38.01
    """
    params = (('headers', True),)

    def _loadline(self, linetokens):
        dttext = linetokens[0]
        dt = datetime.strptime(dttext, '%Y-%m-%d')
        self.lines.datetime[0] = bt.date2num(dt)

        close = float(linetokens[1])
        self.lines.close[0] = close
        self.lines.open[0] = close
        self.lines.high[0] = close
        self.lines.low[0] = close
        self.lines.volume[0] = 0.0
        self.lines.openinterest[0] = 0.0
        return True

# Usage:
cerebro = bt.Cerebro()
data = MyCSVData(dataname='my_prices.csv')
cerebro.adddata(data)
cerebro.run()
```

### Example 2: In-Memory Data Feed (No File)

```python
import backtrader as bt
from datetime import datetime, timedelta

class ListData(bt.feeds.DataBase):
    """Feed data from Python lists."""
    
    params = (('datalist', None),)

    def start(self):
        super().start()
        self._idx = 0

    def _load(self):
        if self._idx >= len(self.p.datalist):
            return False

        row = self.p.datalist[self._idx]
        self._idx += 1

        self.lines.datetime[0] = bt.date2num(row[0])
        self.lines.open[0] = row[1]
        self.lines.high[0] = row[2]
        self.lines.low[0] = row[3]
        self.lines.close[0] = row[4]
        self.lines.volume[0] = row[5]
        self.lines.openinterest[0] = 0.0
        return True

# Usage:
bars = [
    # (datetime,            open,   high,   low,    close,  volume)
    (datetime(2014, 1, 2),  38.01,  38.06,  37.77,  37.92,  10892000),
    (datetime(2014, 1, 3),  37.88,  38.15,  37.63,  38.10,  8452000),
    (datetime(2014, 1, 6),  38.15,  38.54,  37.92,  38.35,  7653000),
]

cerebro = bt.Cerebro()
data = ListData(datalist=bars)
cerebro.adddata(data)
cerebro.run()
```

### Example 3: Data Feed with Extra Lines

```python
import backtrader as bt

class ExtendedCSVData(bt.feeds.CSVDataBase):
    """CSV with an extra 'sentiment' column."""
    
    lines = ('sentiment',)    # adds to inherited OHLCV lines
    
    params = (('headers', True),)

    def _loadline(self, linetokens):
        # Standard OHLCV parsing
        self.lines.datetime[0] = bt.date2num(
            datetime.strptime(linetokens[0], '%Y-%m-%d'))
        self.lines.open[0] = float(linetokens[1])
        self.lines.high[0] = float(linetokens[2])
        self.lines.low[0] = float(linetokens[3])
        self.lines.close[0] = float(linetokens[4])
        self.lines.volume[0] = float(linetokens[5])
        self.lines.openinterest[0] = 0.0

        # Extra line
        self.lines.sentiment[0] = float(linetokens[6])
        return True

# In a strategy:
class SentimentStrat(bt.Strategy):
    def next(self):
        if self.data.sentiment[0] > 0.8:
            self.buy()
```

### Example 4: Data Feed with Filters

```python
import backtrader as bt
from datetime import datetime, time

# Filter: only keep bars during trading hours
def trading_hours_filter(data):
    dt = data.datetime.datetime(0)
    if dt.time() < time(9, 30) or dt.time() >= time(16, 0):
        data.backwards()    # remove bar
        return True
    return False

# Filter: merge every N bars (poor man's resample)
class BarMerger(object):
    def __init__(self, data, count=5):
        self.count = count
        self.bar_count = 0
        self.accumulated = None

    def __call__(self, data):
        self.bar_count += 1
        if self.accumulated is None:
            # Save first bar
            self.accumulated = [line[0] for line in data.itersize()]
        else:
            # Update high/low/close/volume
            self.accumulated[3] = max(self.accumulated[3], data.high[0])
            self.accumulated[2] = min(self.accumulated[2], data.low[0])
            self.accumulated[1] = data.close[0]  # latest close
            self.accumulated[5] += data.volume[0]

        if self.bar_count < self.count:
            data.backwards()
            return True

        # Deliver merged bar
        for line, val in zip(data.itersize(), self.accumulated):
            line[0] = val
        self.bar_count = 0
        self.accumulated = None
        return False

# Usage:
data = bt.feeds.BacktraderCSVData(dataname='data_1min.csv')
data.addfilter_simple(trading_hours_filter)
data.addfilter(BarMerger, count=5)
cerebro.adddata(data)
```

### Example 5: Using FeedBase for Multiple Tickers

```python
import backtrader as bt

class MyCSVFeed(bt.feeds.CSVFeedBase):
    DataCls = bt.feeds.BacktraderCSVData

# Create a feed with shared parameters:
feed = MyCSVFeed(
    basepath='datas/',
    timeframe=bt.TimeFrame.Days,
    fromdate=datetime(2014, 1, 1),
    todate=datetime(2014, 12, 31),
)

# Load multiple tickers:
tickers = ['orcl-2014.txt', 'yhoo-2014.txt']
for ticker in tickers:
    feed.getdata(dataname=ticker)

# Add all to cerebro:
cerebro = bt.Cerebro()
for data in feed.datas:
    cerebro.adddata(data)

# Strategy sees:
class MultiStrat(bt.Strategy):
    def __init__(self):
        for data in self.datas:
            bt.ind.SMA(data, period=20)

    def next(self):
        for i, data in enumerate(self.datas):
            print(f'{data._name}: {data.close[0]:.2f}')
```

### Example 6: DataClone for Multi-Timeframe

```python
import backtrader as bt

cerebro = bt.Cerebro()

# Daily data (primary)
data = bt.feeds.BacktraderCSVData(
    dataname='datas/orcl-2014.txt',
    timeframe=bt.TimeFrame.Days,
)
cerebro.adddata(data)

# Resample to weekly (uses DataClone internally)
cerebro.resampledata(data, timeframe=bt.TimeFrame.Weeks)
# This internally does:
#   clone = data.clone()
#   clone.resample(timeframe=Weeks)
#   cerebro.adddata(clone)

class MultiTFStrat(bt.Strategy):
    def __init__(self):
        self.sma_daily = bt.ind.SMA(self.data0, period=10)   # daily SMA
        self.sma_weekly = bt.ind.SMA(self.data1, period=4)   # weekly SMA

    def next(self):
        print(f'Daily close:  {self.data0.close[0]:.2f}')
        print(f'Weekly close: {self.data1.close[0]:.2f}')
        print(f'Daily SMA:    {self.sma_daily[0]:.2f}')
        print(f'Weekly SMA:   {self.sma_weekly[0]:.2f}')

cerebro.addstrategy(MultiTFStrat)
cerebro.run()
```

### Example 7: Simulating a Live Data Feed

```python
import backtrader as bt
import queue
import threading
from datetime import datetime

class SimLiveData(bt.feeds.DataBase):
    """
    Simulates a live data feed using a queue.
    Another thread pushes bars into the queue.
    """
    
    params = (
        ('qcheck', 0.5),    # check queue every 0.5 seconds
    )

    def islive(self):
        return True           # tells Cerebro: no preload, no runonce

    def start(self):
        super().start()
        self._queue = queue.Queue()
        self.put_notification(self.CONNECTED)

    def haslivedata(self):
        return not self._queue.empty()

    def _load(self):
        try:
            bar = self._queue.get(timeout=self._qcheck)
        except queue.Empty:
            return None       # no data yet, but not done

        if bar is None:       # sentinel: feed is done
            return False

        self.lines.datetime[0] = bt.date2num(bar['datetime'])
        self.lines.open[0] = bar['open']
        self.lines.high[0] = bar['high']
        self.lines.low[0] = bar['low']
        self.lines.close[0] = bar['close']
        self.lines.volume[0] = bar['volume']
        self.lines.openinterest[0] = 0.0

        self.put_notification(self.LIVE)
        return True

    def push_bar(self, bar):
        """Called from another thread to inject bars."""
        self._queue.put(bar)

    def stop_feed(self):
        """Signal the feed is done."""
        self._queue.put(None)

# Usage:
data = SimLiveData(dataname='SIM')

# In another thread:
def producer(data):
    import time
    for i in range(100):
        data.push_bar({
            'datetime': datetime(2014, 1, 2 + i),
            'open': 100 + i, 'high': 101 + i,
            'low': 99 + i, 'close': 100.5 + i,
            'volume': 1000000,
        })
        time.sleep(0.1)
    data.stop_feed()

t = threading.Thread(target=producer, args=(data,))
t.start()

cerebro = bt.Cerebro()
cerebro.adddata(data)
cerebro.addstrategy(MyStrategy)
cerebro.run()
```

---

## Summary Table

| Class | Purpose | Key Methods |
|-------|---------|-------------|
| **MetaAbstractDataBase** | Metaclass: registers feeds, sets up notifications/filters | `__init__`, `dopreinit`, `dopostinit` |
| **AbstractDataBase** | Core data feed: loading, filtering, lifecycle | `load`, `_load`, `preload`, `next`, `advance`, `start`, `stop` |
| **DataBase** | Empty subclass for naming | (none) |
| **FeedBase** | Multi-data container/factory | `getdata`, `start`, `stop` |
| **MetaCSVDataBase** | Metaclass: auto-extracts name from filename | `dopostinit` |
| **CSVDataBase** | CSV file handling: open, read, tokenize | `start`, `stop`, `preload`, `_load`, `_loadline` |
| **CSVFeedBase** | Multi-CSV container with basepath | `_getdata` |
| **DataClone** | Shadow copy of another data feed | `_load`, `preload`, `advance` |
