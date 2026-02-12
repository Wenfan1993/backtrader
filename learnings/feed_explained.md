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

Returns the next End-Of-Session datetime and its numeric value.
Used for session boundary detection in resampling.

```python
def _getnexteos(self):
    if self._clone:
        return self.data._getnexteos()

    if not len(self):
        return datetime.datetime.min, 0.0

    dt = self.lines.datetime[0]
    dtime = num2date(dt)
    if self._calendar is None:
        nexteos = datetime.datetime.combine(dtime, self.p.sessionend)
        # ... advance if past current time ...
    else:
        _, nexteos = self._calendar.schedule(dtime, self._tz)

    nextdteos = date2num(nexteos)
    return nexteos, nextdteos
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

Manage tick-level price tracking for real-time bar updates.

```python
def _tick_nullify(self):
    '''Reset tick prices to None (new bar starting)'''
    for lalias in self.getlinealiases():
        if lalias != 'datetime':
            setattr(self, 'tick_' + lalias, None)
    self.tick_last = None

def _tick_fill(self, force=False):
    '''Fill tick prices from current bar values'''
    alias0 = self._getlinealias(0)
    if force or getattr(self, 'tick_' + alias0, None) is None:
        for lalias in self.getlinealiases():
            if lalias != 'datetime':
                setattr(self, 'tick_' + lalias,
                        getattr(self.lines, lalias)[0])
        self.tick_last = getattr(self.lines, alias0)[0]
```

**Example:**

```python
# During real-time processing, bars may be updated multiple times:
# A 1-minute bar at 10:00 receives ticks at 10:00:05, 10:00:15, 10:00:45
# Each tick updates tick_close, tick_high, tick_low, etc.
# These reflect the latest sub-bar state

# In a strategy:
class MyStrat(bt.Strategy):
    def next(self):
        print(f"Bar close: {self.data.close[0]}")
        print(f"Tick close: {self.data.tick_close}")  # latest tick
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

**Example — Custom Filter Using Bar Stack:**

```python
class GapFilter(object):
    """Filters out bars that have an overnight gap > 5%."""

    def __init__(self, data):
        self.last_close = None

    def __call__(self, data):
        close = data.close[0]
        if self.last_close is not None:
            gap = abs(close - self.last_close) / self.last_close
            if gap > 0.05:
                # Save bar to stash (can be restored later)
                data._save2stack(erase=True, stash=True)
                return True     # bar removed
        self.last_close = data.close[0]
        return False

data.addfilter(GapFilter)
```

**Example — Resampler Using Bar Stack:**

```python
# The Resampler filter works like this internally:
# 1. Receives 1-minute bars from _load()
# 2. Accumulates them using _Bar.bupdate()
# 3. When a 5-minute boundary is reached:
#    a. Saves the completed 5-minute bar to _barstack via _add2stack()
#    b. The load() loop calls _fromstack() to deliver it
# 4. At the end, _last() delivers any partial bar
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
