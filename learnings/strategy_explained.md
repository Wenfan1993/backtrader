# Backtrader Strategy System Explained

This document provides a comprehensive walkthrough of `backtrader/strategy.py`, explaining each class with detailed examples.

---

## Overview

The `strategy.py` file defines the core classes for creating trading strategies:

| Class | Purpose |
|-------|---------|
| `MetaStrategy` | Metaclass for strategy setup and registration |
| `Strategy` | Main base class for all user-defined strategies |
| `MetaSigStrategy` | Metaclass for signal-based strategies |
| `SignalStrategy` | Automated strategy driven by signals |

---

## Class: MetaStrategy

**Purpose**: Metaclass for `Strategy` that handles:
1. Backward compatibility for renamed notification methods
2. Strategy registration
3. Strategy instance setup (cerebro link, broker, orders, trades, analyzers)

**Inherits from**: `StrategyBase.__class__` (which is `MetaLineIterator`)

---

### MetaStrategy - Complete Examples

#### 1. The `__new__` Method - Backward Compatibility

```python
def __new__(meta, name, bases, dct):
    """
    Handle renamed methods for backward compatibility.
    """
    # Old method 'notify' renamed to 'notify_order'
    if 'notify' in dct:
        dct['notify_order'] = dct.pop('notify')
    
    # Old method 'notify_operation' renamed to 'notify_trade'
    if 'notify_operation' in dct:
        dct['notify_trade'] = dct.pop('notify_operation')
    
    return super(MetaStrategy, meta).__new__(meta, name, bases, dct)

# This means old code still works:
class OldStyleStrategy(bt.Strategy):
    def notify(self, order):  # Old name
        pass  # Becomes notify_order internally
```

#### 2. The `__init__` Method - Class Registration

```python
def __init__(cls, name, bases, dct):
    """
    Register strategy classes in the collection.
    """
    super(MetaStrategy, cls).__init__(name, bases, dct)
    
    # Register non-aliased, non-private strategies
    if not cls.aliased and \
       name != 'Strategy' and not name.startswith('_'):
        cls._indcol[name] = cls

# Access registered strategies:
print(bt.Strategy._indcol.keys())
# dict_keys(['MyStrategy', 'MomentumStrategy', ...])
```

#### 3. The `donew` Method - Instance Creation

```python
def donew(cls, *args, **kwargs):
    """
    Set up the strategy instance with cerebro reference and ID.
    """
    _obj, args, kwargs = super(MetaStrategy, cls).donew(*args, **kwargs)
    
    # Find the owning Cerebro and store references
    _obj.env = _obj.cerebro = cerebro = findowner(_obj, bt.Cerebro)
    
    # Get unique strategy ID
    _obj._id = cerebro._next_stid()
    
    return _obj, args, kwargs

# After this, your strategy has:
# - self.env / self.cerebro -> the Cerebro instance
# - self._id -> unique integer identifier
```

#### 4. The `dopreinit` Method - Pre-Initialization Setup

```python
def dopreinit(cls, _obj, *args, **kwargs):
    """
    Set up broker, orders, trades, analyzers, observers.
    Called before __init__.
    """
    _obj, args, kwargs = \
        super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)
    
    # Broker reference
    _obj.broker = _obj.env.broker
    
    # Default sizer (fixed size of 1)
    _obj._sizer = bt.sizers.FixedSize()
    
    # Order tracking
    _obj._orders = list()          # Completed orders history
    _obj._orderspending = list()   # Orders waiting to be notified
    
    # Trade tracking
    # {data: {tradeid: [trades]}}
    _obj._trades = collections.defaultdict(AutoDictList)
    _obj._tradespending = list()   # Trades waiting to be notified
    
    # Observers and Analyzers
    _obj.stats = _obj.observers = ItemCollection()
    _obj.analyzers = ItemCollection()
    _obj._alnames = collections.defaultdict(itertools.count)
    _obj.writers = list()
    
    _obj._slave_analyzers = list()  # Analyzers for observers
    _obj._tradehistoryon = False
    
    return _obj, args, kwargs
```

#### 5. The `dopostinit` Method - Post-Initialization

```python
def dopostinit(cls, _obj, *args, **kwargs):
    """
    Finalize setup after __init__.
    """
    _obj, args, kwargs = \
        super(MetaStrategy, cls).dopostinit(_obj, *args, **kwargs)
    
    # Connect sizer to strategy and broker
    _obj._sizer.set(_obj, _obj.broker)
    
    return _obj, args, kwargs
```

---

## Class: Strategy

**Purpose**: The main base class that all user-defined strategies inherit from. Provides:
1. Order management (buy, sell, close, bracket orders)
2. Position tracking
3. Notification system
4. Timer support
5. Memory management (qbuffer)
6. Writer/CSV support

**Inherits from**: `StrategyBase` (via `MetaStrategy` metaclass)

---

### Strategy - Class Attributes

```python
class Strategy(with_metaclass(MetaStrategy, StrategyBase)):
    _ltype = LineIterator.StratType  # Identifies as strategy (value: 1)
    csv = True                        # Export to CSV by default
    _oldsync = False                  # Use new clock sync method
    
    lines = ('datetime',)  # Strategy has a datetime line
```

---

### Strategy - Memory Management

#### `qbuffer(savemem, replaying)` - Enable Memory Saving

```python
def qbuffer(self, savemem=0, replaying=False):
    """
    Enable memory saving modes.
    
    savemem values:
      0: No savings - keep all data in memory
      1: Maximum savings - minimum memory usage
     -1: Partial savings - keep indicator/observer data for plotting
     -2: Like -1 but also save memory for non-plotted indicators
    """
    if savemem < 0:
        # Partial savings for plotting
        for ind in self._lineiterators[self.IndType]:
            subsave = isinstance(ind, (LineSingle,))
            if not subsave and savemem < -1:
                subsave = not ind.plotinfo.plot
            ind.qbuffer(savemem=subsave)
    
    elif savemem > 0:
        # Maximum savings
        for data in self.datas:
            data.qbuffer(replaying=replaying)
        
        for line in self.lines:
            line.qbuffer(savemem=1)
        
        for itcls in self._lineiterators:
            for it in self._lineiterators[itcls]:
                it.qbuffer(savemem=1)

# Usage:
cerebro = bt.Cerebro()
# ... setup ...
cerebro.run(optreturn=False)  # Memory saving during optimization
```

---

### Strategy - Period Management

#### `_periodset()` - Calculate Minimum Periods

```python
def _periodset(self):
    """
    Calculate minimum periods for all data feeds.
    Handles multiple timeframes and different data lengths.
    """
    # Build map of data IDs
    dataids = [id(data) for data in self.datas]
    
    # Collect minperiods by clock source
    _dminperiods = collections.defaultdict(list)
    
    for lineiter in self._lineiterators[LineIterator.IndType]:
        # Walk up the clock hierarchy to find the data feed
        clk = getattr(lineiter, '_clock', None)
        if clk is None:
            clk = getattr(lineiter._owner, '_clock', None)
        
        # Keep going up until we reach a data feed
        while clk is not None:
            if id(clk) in dataids:
                break  # Found the data feed
            clk = getattr(clk, '_clock', None) or \
                  getattr(getattr(clk, '_owner', None), '_clock', None)
        
        if clk is not None:
            _dminperiods[clk].append(lineiter._minperiod)
    
    # Calculate per-data minperiods
    self._minperiods = []
    for data in self.datas:
        dlminperiods = _dminperiods[data]
        for line in data.lines:
            if line in _dminperiods:
                dlminperiods += _dminperiods[line]
        
        dminperiod = max(dlminperiods or [data._minperiod])
        self._minperiods.append(dminperiod)
    
    # Overall strategy minperiod
    minperiods = [x._minperiod for x in self._lineiterators[LineIterator.IndType]]
    self._minperiod = max(minperiods or [self._minperiod])
```

---

### Strategy - Lifecycle Methods

#### `_start()` and `start()` - Backtest Start

```python
def _start(self):
    """
    Internal start method - called by cerebro.
    """
    # Calculate all minimum periods
    self._periodset()
    
    # Start all analyzers
    for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        analyzer._start()
    
    # Start all observers
    for obs in self.observers:
        if not isinstance(obs, list):
            obs = [obs]
        for o in obs:
            o._start()
    
    # Switch to execution stage (stage 2)
    self._stage2()
    
    # Track data lengths for clock sync
    self._dlens = [len(data) for data in self.datas]
    
    # Start in prenext mode
    self._minperstatus = MAXINT
    
    # Call user's start method
    self.start()

def start(self):
    """
    User-overridable method called at backtest start.
    """
    pass

# Usage:
class MyStrategy(bt.Strategy):
    def start(self):
        print(f"Starting backtest with cash: {self.broker.getcash()}")
        self.order_count = 0
```

#### `_stop()` and `stop()` - Backtest End

```python
def _stop(self):
    """
    Internal stop method - called by cerebro.
    """
    # Call user's stop method
    self.stop()
    
    # Stop all analyzers
    for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
        analyzer._stop()
    
    # Switch back to stage 1 (allows data reuse)
    self._stage1()

def stop(self):
    """
    User-overridable method called at backtest end.
    """
    pass

# Usage:
class MyStrategy(bt.Strategy):
    def stop(self):
        print(f"Final portfolio value: {self.broker.getvalue()}")
```

---

### Strategy - Clock Update

#### `_clk_update()` - Synchronize with Data

```python
def _clk_update(self):
    """
    Update strategy clock based on data feeds.
    Handles multiple data feeds with different lengths.
    """
    if self._oldsync:
        # Old method: sync with data0 only
        clk_len = super(Strategy, self)._clk_update()
        self.lines.datetime[0] = max(
            d.datetime[0] for d in self.datas if len(d)
        )
        return clk_len
    
    # New method: check all datas
    newdlens = [len(d) for d in self.datas]
    if any(nl > l for l, nl in zip(self._dlens, newdlens)):
        self.forward()  # At least one data advanced
    
    # Use latest datetime from any data
    self.lines.datetime[0] = max(
        d.datetime[0] for d in self.datas if len(d)
    )
    self._dlens = newdlens
    
    return len(self)
```

---

### Strategy - Iteration Methods

#### `_next()` - Step-by-Step Processing

```python
def _next(self):
    """
    Process one bar across all data feeds.
    """
    # Call parent's _next (processes indicators)
    super(Strategy, self)._next()
    
    # Get minperiod status and process analyzers/observers
    minperstatus = self._getminperstatus()
    self._next_analyzers(minperstatus)
    self._next_observers(minperstatus)
    
    # Clear pending orders and trades
    self.clear()
```

#### `_oncepost(dt)` - Batch Processing Callback

```python
def _oncepost(self, dt):
    """
    Called after batch processing for each bar.
    Used in runonce mode.
    """
    # Advance indicators that are behind
    for indicator in self._lineiterators[LineIterator.IndType]:
        if len(indicator._clock) > len(indicator):
            indicator.advance()
    
    # Advance or forward based on mode
    if self._oldsync:
        self.advance()
    else:
        self.forward()
    
    # Set datetime
    self.lines.datetime[0] = dt
    
    # Process notifications
    self._notify()
    
    # Call appropriate user method
    minperstatus = self._getminperstatus()
    if minperstatus < 0:
        self.next()
    elif minperstatus == 0:
        self.nextstart()
    else:
        self.prenext()
    
    # Process analyzers and observers
    self._next_analyzers(minperstatus, once=True)
    self._next_observers(minperstatus, once=True)
    
    self.clear()
```

#### `_getminperstatus()` - Check Data Readiness

```python
def _getminperstatus(self):
    """
    Check if all data feeds have enough bars.
    
    Returns:
      < 0: All datas have minperiod bars (ready for next())
      = 0: Just reached minperiod (call nextstart())
      > 0: Still warming up (call prenext())
    """
    dlens = map(operator.sub, self._minperiods, map(len, self.datas))
    self._minperstatus = minperstatus = max(dlens)
    return minperstatus
```

---

### Strategy - Open Price Methods

```python
"""
These methods are called for orders at open price.
Used with cheat-on-open mode.
"""

def prenext_open(self):
    """Called during warmup with open price available."""
    pass

def nextstart_open(self):
    """Called once at minperiod with open price available."""
    self.next_open()

def next_open(self):
    """Called each bar with open price available."""
    pass

# Usage:
cerebro = bt.Cerebro(cheat_on_open=True)

class MyStrategy(bt.Strategy):
    def next_open(self):
        # Can access today's open price before next() is called
        if self.data.open[0] > self.data.close[-1]:
            self.buy()  # Order uses open price
```

---

### Strategy - Notification System

#### `_notify()` - Process Notifications

```python
def _notify(self, qorders=[], qtrades=[]):
    """
    Notify strategy and analyzers of orders, trades, cash, and value.
    """
    # Determine which orders/trades to process
    if self.cerebro.p.quicknotify:
        procorders = qorders
        proctrades = qtrades
    else:
        procorders = self._orderspending
        proctrades = self._tradespending
    
    # Notify orders
    for order in procorders:
        if order.exectype != order.Historical or order.histnotify:
            self.notify_order(order)
        
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._notify_order(order)
    
    # Notify trades
    for trade in proctrades:
        self.notify_trade(trade)
        
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._notify_trade(trade)
    
    # Notify cash/value (on regular notify only)
    if not qorders:
        cash = self.broker.getcash()
        value = self.broker.getvalue()
        fundvalue = self.broker.fundvalue
        fundshares = self.broker.fundshares
        
        self.notify_cashvalue(cash, value)
        self.notify_fund(cash, value, fundvalue, fundshares)
        
        for analyzer in itertools.chain(self.analyzers, self._slave_analyzers):
            analyzer._notify_cashvalue(cash, value)
            analyzer._notify_fund(cash, value, fundvalue, fundshares)
```

#### User-Overridable Notification Methods

```python
def notify_order(self, order):
    """
    Called when an order changes state.
    
    Order states:
    - Order.Created
    - Order.Submitted
    - Order.Accepted
    - Order.Partial
    - Order.Completed
    - Order.Canceled/Cancelled
    - Order.Expired
    - Order.Margin
    - Order.Rejected
    """
    pass

def notify_trade(self, trade):
    """
    Called when a trade changes (opened, updated, closed).
    """
    pass

def notify_cashvalue(self, cash, value):
    """
    Called with current cash and portfolio value.
    """
    pass

def notify_fund(self, cash, value, fundvalue, shares):
    """
    Called with fund value tracking info.
    """
    pass

def notify_store(self, msg, *args, **kwargs):
    """
    Called with store provider notifications (live trading).
    """
    pass

def notify_data(self, data, status, *args, **kwargs):
    """
    Called with data feed status changes (live trading).
    """
    pass

# Complete example:
class NotificationDemo(bt.Strategy):
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return  # Pending
        
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"BUY EXECUTED @ {order.executed.price:.2f}")
            else:
                print(f"SELL EXECUTED @ {order.executed.price:.2f}")
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"Order {order.Status[order.status]}")
    
    def notify_trade(self, trade):
        if trade.isclosed:
            print(f"Trade PnL: Gross={trade.pnl:.2f}, Net={trade.pnlcomm:.2f}")
```

---

### Strategy - Order Methods

#### `buy()` - Create Buy Order

```python
def buy(self, data=None,
        size=None, price=None, plimit=None,
        exectype=None, valid=None, tradeid=0, oco=None,
        trailamount=None, trailpercent=None,
        parent=None, transmit=True,
        **kwargs):
    """
    Create and submit a buy order.
    
    Parameters:
      data: Target data feed (default: first data)
      size: Order size (default: from sizer)
      price: Order price (default: market price)
      plimit: Limit price for StopLimit orders
      exectype: Order.Market, Order.Limit, Order.Stop, etc.
      valid: Validity (None=GTC, datetime, Order.DAY)
      tradeid: Trade identifier for tracking
      oco: Other order for OCO group
      trailamount: Trailing stop amount
      trailpercent: Trailing stop percentage
      parent: Parent order for bracket
      transmit: Whether to submit immediately
    
    Returns:
      The created order or None if size is 0
    """
    # Handle data by name
    if isinstance(data, string_types):
        data = self.getdatabyname(data)
    
    data = data if data is not None else self.datas[0]
    size = size if size is not None else self.getsizing(data, isbuy=True)
    
    if size:
        return self.broker.buy(
            self, data,
            size=abs(size), price=price, plimit=plimit,
            exectype=exectype, valid=valid, tradeid=tradeid, oco=oco,
            trailamount=trailamount, trailpercent=trailpercent,
            parent=parent, transmit=transmit,
            **kwargs)
    
    return None

# Examples:
class OrderExamples(bt.Strategy):
    def next(self):
        # Market order
        self.buy()
        
        # Limit order
        self.buy(price=100.0, exectype=bt.Order.Limit)
        
        # Stop order
        self.buy(price=105.0, exectype=bt.Order.Stop)
        
        # Stop-Limit order
        self.buy(price=105.0, plimit=106.0, exectype=bt.Order.StopLimit)
        
        # Good-till-date order
        self.buy(valid=datetime.datetime(2024, 12, 31))
        
        # Day order
        self.buy(valid=bt.Order.DAY)
        
        # Trailing stop
        self.buy(exectype=bt.Order.StopTrail, trailamount=5.0)
        
        # With specific size
        self.buy(size=100)
        
        # On specific data
        self.buy(data=self.data1)
        self.buy(data='AAPL')  # By name
```

#### `sell()` - Create Sell Order

```python
def sell(self, data=None,
         size=None, price=None, plimit=None,
         exectype=None, valid=None, tradeid=0, oco=None,
         trailamount=None, trailpercent=None,
         parent=None, transmit=True,
         **kwargs):
    """
    Create and submit a sell order.
    Same parameters as buy().
    """
    # Same implementation as buy() but calls broker.sell()
```

#### `close()` - Close Position

```python
def close(self, data=None, size=None, **kwargs):
    """
    Close an existing position.
    
    Automatically determines if long or short and issues
    the appropriate order to close.
    """
    if isinstance(data, string_types):
        data = self.getdatabyname(data)
    elif data is None:
        data = self.data
    
    possize = self.getposition(data, self.broker).size
    size = abs(size if size is not None else possize)
    
    if possize > 0:
        return self.sell(data=data, size=size, **kwargs)
    elif possize < 0:
        return self.buy(data=data, size=size, **kwargs)
    
    return None  # No position

# Usage:
class CloseExample(bt.Strategy):
    def next(self):
        if some_exit_condition:
            self.close()  # Close current position
        
        # Close specific data
        self.close(data=self.data1)
        
        # Partial close
        self.close(size=50)
```

#### `cancel()` - Cancel Order

```python
def cancel(self, order):
    """Cancel a pending order."""
    self.broker.cancel(order)

# Usage:
class CancelExample(bt.Strategy):
    def __init__(self):
        self.order = None
    
    def next(self):
        if self.order is not None:
            # Cancel after 5 bars
            if len(self) - self.order_bar > 5:
                self.cancel(self.order)
                self.order = None
```

---

### Strategy - Bracket Orders

#### `buy_bracket()` - Buy with Stop Loss and Take Profit

```python
def buy_bracket(self, data=None, size=None, price=None, plimit=None,
                exectype=bt.Order.Limit, valid=None, tradeid=0,
                trailamount=None, trailpercent=None, oargs={},
                stopprice=None, stopexec=bt.Order.Stop, stopargs={},
                limitprice=None, limitexec=bt.Order.Limit, limitargs={},
                **kwargs):
    """
    Create a bracket order group:
    - Main buy order
    - Stop loss (low side sell)
    - Take profit (high side sell)
    
    Returns: [main_order, stop_order, limit_order]
    """
    # Main order setup
    kargs = dict(size=size, data=data, price=price, ...)
    kargs['transmit'] = limitexec is None and stopexec is None
    o = self.buy(**kargs)
    
    # Stop loss order
    if stopexec is not None:
        kargs = dict(data=data, price=stopprice, exectype=stopexec, ...)
        kargs['parent'] = o
        kargs['size'] = o.size
        ostop = self.sell(**kargs)
    else:
        ostop = None
    
    # Take profit order
    if limitexec is not None:
        kargs = dict(data=data, price=limitprice, exectype=limitexec, ...)
        kargs['parent'] = o
        kargs['transmit'] = True  # Last order triggers all
        kargs['size'] = o.size
        olimit = self.sell(**kargs)
    else:
        olimit = None
    
    return [o, ostop, olimit]

# Usage:
class BracketExample(bt.Strategy):
    def next(self):
        if not self.position:
            # Buy at 100, stop at 95, take profit at 110
            orders = self.buy_bracket(
                price=100.0,
                stopprice=95.0,
                limitprice=110.0
            )
            self.main_order, self.stop_order, self.limit_order = orders
```

#### `sell_bracket()` - Short with Stop Loss and Take Profit

```python
def sell_bracket(self, ...):
    """
    Create a bracket order group for short position:
    - Main sell order
    - Stop loss (high side buy)
    - Take profit (low side buy)
    
    Returns: [main_order, stop_order, limit_order]
    """
    # Similar to buy_bracket but directions reversed
```

---

### Strategy - Target Orders

#### `order_target_size()` - Rebalance to Target Size

```python
def order_target_size(self, data=None, target=0, **kwargs):
    """
    Place order to achieve target position size.
    
    If target > current: buy the difference
    If target < current: sell the difference
    If target == current: no order
    """
    data = data if data is not None else self.data
    possize = self.getposition(data, self.broker).size
    
    if not target and possize:
        return self.close(data=data, size=possize, **kwargs)
    elif target > possize:
        return self.buy(data=data, size=target - possize, **kwargs)
    elif target < possize:
        return self.sell(data=data, size=possize - target, **kwargs)
    
    return None

# Examples:
class TargetSizeExample(bt.Strategy):
    def next(self):
        # Always hold exactly 100 shares
        self.order_target_size(target=100)
        
        # Short 50 shares
        self.order_target_size(target=-50)
        
        # Close position
        self.order_target_size(target=0)
```

#### `order_target_value()` - Rebalance to Target Value

```python
def order_target_value(self, data=None, target=0.0, price=None, **kwargs):
    """
    Place order to achieve target position value.
    """
    data = data if data is not None else self.data
    possize = self.getposition(data, self.broker).size
    
    if not target and possize:
        return self.close(data=data, size=possize, price=price, **kwargs)
    
    value = self.broker.getvalue(datas=[data])
    comminfo = self.broker.getcommissioninfo(data)
    price = price if price is not None else data.close[0]
    
    if target > value:
        size = comminfo.getsize(price, target - value)
        return self.buy(data=data, size=size, price=price, **kwargs)
    elif target < value:
        size = comminfo.getsize(price, value - target)
        return self.sell(data=data, size=size, price=price, **kwargs)
    
    return None

# Example:
class TargetValueExample(bt.Strategy):
    def next(self):
        # Hold $10,000 worth of stock
        self.order_target_value(target=10000.0)
```

#### `order_target_percent()` - Rebalance to Portfolio Percentage

```python
def order_target_percent(self, data=None, target=0.0, **kwargs):
    """
    Place order to achieve target percentage of portfolio.
    target is in decimal (0.05 = 5%)
    """
    data = data if data is not None else self.data
    possize = self.getposition(data, self.broker).size
    target *= self.broker.getvalue()  # Convert to value
    
    return self.order_target_value(data=data, target=target, **kwargs)

# Example:
class TargetPercentExample(bt.Strategy):
    def next(self):
        # Allocate 25% of portfolio
        self.order_target_percent(target=0.25)
        
        # Multiple assets
        self.order_target_percent(data=self.data0, target=0.30)
        self.order_target_percent(data=self.data1, target=0.30)
        self.order_target_percent(data=self.data2, target=0.40)
```

---

### Strategy - Position Management

#### `getposition()` - Get Current Position

```python
def getposition(self, data=None, broker=None):
    """
    Get position for a data feed.
    """
    data = data if data is not None else self.datas[0]
    broker = broker or self.broker
    return broker.getposition(data)

# Also available as property:
# self.position -> position for first data

# Usage:
class PositionExample(bt.Strategy):
    def next(self):
        pos = self.position  # or self.getposition()
        print(f"Size: {pos.size}")
        print(f"Price: {pos.price}")
        print(f"Value: {pos.size * self.data.close[0]}")
        
        # Check position state
        if pos.size > 0:
            print("Long position")
        elif pos.size < 0:
            print("Short position")
        else:
            print("No position")
```

#### `getpositions()` - Get All Positions

```python
def getpositions(self, broker=None):
    """Get all positions by data."""
    broker = broker or self.broker
    return broker.positions

# Also: positions property
# Also: getpositionsbyname() and positionsbyname property

class MultiAssetExample(bt.Strategy):
    def next(self):
        for data, pos in self.positions.items():
            if pos.size:
                print(f"{data._name}: {pos.size} @ {pos.price}")
```

---

### Strategy - Sizer Management

```python
def setsizer(self, sizer):
    """Set the sizer for automatic position sizing."""
    self._sizer = sizer
    sizer.set(self, self.broker)
    return sizer

def getsizer(self):
    """Get the current sizer."""
    return self._sizer

def getsizing(self, data=None, isbuy=True):
    """Get the size calculated by the sizer."""
    data = data if data is not None else self.datas[0]
    return self._sizer.getsizing(data, isbuy=isbuy)

# Also: sizer property (get/set)

# Usage:
cerebro.addsizer(bt.sizers.PercentSizer, percents=10)
# or
class MyStrategy(bt.Strategy):
    def __init__(self):
        self.setsizer(bt.sizers.FixedSize(stake=100))
```

---

### Strategy - Timer Support

#### `add_timer()` - Schedule Callbacks

```python
def add_timer(self, when,
              offset=datetime.timedelta(), repeat=datetime.timedelta(),
              weekdays=[], weekcarry=False,
              monthdays=[], monthcarry=True,
              allow=None,
              tzdata=None, cheat=False,
              *args, **kwargs):
    """
    Schedule a timer to call notify_timer.
    
    Parameters:
      when: datetime.time, SESSION_START, or SESSION_END
      offset: timedelta offset from 'when'
      repeat: timedelta for repeating within session
      weekdays: list of iso weekdays (1=Mon, 7=Sun)
      weekcarry: execute next day if weekday missed
      monthdays: list of days of month
      monthcarry: execute next day if monthday missed
      allow: callback(date) -> bool for custom filtering
      tzdata: timezone (pytz instance or data feed)
      cheat: call before broker evaluates orders
    """
    return self.cerebro._add_timer(
        owner=self, when=when, ...
    )

def notify_timer(self, timer, when, *args, **kwargs):
    """Called when timer fires."""
    pass

# Example:
class TimerExample(bt.Strategy):
    def __init__(self):
        # Rebalance at market open every Monday
        self.add_timer(
            when=bt.timer.SESSION_START,
            weekdays=[1],  # Monday
        )
        
        # Check at 3pm every day
        self.add_timer(
            when=datetime.time(15, 0),
        )
    
    def notify_timer(self, timer, when, *args, **kwargs):
        print(f"Timer fired at {when}")
        self.rebalance()
```

---

### Strategy - Data Access

```python
def getdatanames(self):
    """Get list of data feed names."""
    return keys(self.env.datasbyname)

def getdatabyname(self, name):
    """Get data feed by name."""
    return self.env.datasbyname[name]

# Usage:
class DataAccessExample(bt.Strategy):
    def __init__(self):
        print(f"Available data: {self.getdatanames()}")
        
        # Access data by name (set when adding data)
        aapl = self.getdatabyname('AAPL')
```

---

### Strategy - Writer Support

```python
def getwriterheaders(self):
    """Get CSV headers for writer output."""
    self.indobscsv = [self]
    indobs = itertools.chain(
        self.getindicators_lines(), self.getobservers()
    )
    self.indobscsv.extend(filter(lambda x: x.csv, indobs))
    
    headers = list()
    for iocsv in self.indobscsv:
        name = iocsv.plotinfo.plotname or iocsv.__class__.__name__
        headers.append(name)
        headers.append('len')
        headers.extend(iocsv.getlinealiases())
    
    return headers

def getwritervalues(self):
    """Get CSV values for current bar."""
    values = list()
    for iocsv in self.indobscsv:
        name = iocsv.plotinfo.plotname or iocsv.__class__.__name__
        values.append(name)
        lio = len(iocsv)
        values.append(lio)
        if lio:
            values.extend(map(lambda l: l[0], iocsv.lines.itersize()))
        else:
            values.extend([''] * iocsv.lines.size())
    
    return values

def getwriterinfo(self):
    """Get strategy info for writer output."""
    # Returns params, indicators, observers, analyzers info
```

---

## Class: MetaSigStrategy

**Purpose**: Metaclass for `SignalStrategy` that:
1. Remaps user's `next()` to `_next_custom`
2. Injects signal processing into `next()`
3. Sets up signal tracking

---

### MetaSigStrategy - Complete Examples

```python
class MetaSigStrategy(Strategy.__class__):
    def __new__(meta, name, bases, dct):
        # If user defined next(), rename it
        if 'next' in dct:
            dct['_next_custom'] = dct.pop('next')
        
        cls = super().__new__(meta, name, bases, dct)
        
        # Replace next with signal processor
        cls.next = cls._next_catch
        return cls
    
    def dopreinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = super().dopreinit(_obj, *args, **kwargs)
        
        # Storage for signals by type
        _obj._signals = collections.defaultdict(list)
        
        # Determine target data for orders
        _data = _obj.p._data
        if _data is None:
            _obj._dtarget = _obj.data0
        elif isinstance(_data, integer_types):
            _obj._dtarget = _obj.datas[_data]
        elif isinstance(_data, string_types):
            _obj._dtarget = _obj.getdatabyname(_data)
        else:
            _obj._dtarget = _obj.data0
        
        return _obj, args, kwargs
    
    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = super().dopostinit(_obj, *args, **kwargs)
        
        # Create signals from params
        for sigtype, sigcls, sigargs, sigkwargs in _obj.p.signals:
            _obj._signals[sigtype].append(sigcls(*sigargs, **sigkwargs))
        
        # Track signal types
        _obj._longshort = bool(_obj._signals[bt.SIGNAL_LONGSHORT])
        _obj._long = bool(_obj._signals[bt.SIGNAL_LONG])
        _obj._short = bool(_obj._signals[bt.SIGNAL_SHORT])
        _obj._longexit = bool(_obj._signals[bt.SIGNAL_LONGEXIT])
        _obj._shortexit = bool(_obj._signals[bt.SIGNAL_SHORTEXIT])
        
        return _obj, args, kwargs
```

---

## Class: SignalStrategy

**Purpose**: An automated strategy that trades based on signals from indicators. Supports:
- Long/short signals
- Entry/exit signals
- Position accumulation
- Concurrent orders

---

### SignalStrategy - Complete Examples

#### 1. Class Definition

```python
class SignalStrategy(with_metaclass(MetaSigStrategy, Strategy)):
    """
    Automated signal-based trading.
    
    Signal values:
      > 0: Long indication
      < 0: Short indication
    
    Signal types:
      LONGSHORT: Both directions
      LONG: Long entries (negative = exit long)
      SHORT: Short entries (positive = exit short)
      LONGEXIT: Explicit long exit signal
      SHORTEXIT: Explicit short exit signal
    """
    
    params = (
        ('signals', []),        # List of (sigtype, sigcls, args, kwargs)
        ('_accumulate', False), # Allow adding to position
        ('_concurrent', False), # Allow multiple pending orders
        ('_data', None),        # Target data for orders
    )
```

#### 2. Signal Types Explained

```python
import backtrader as bt

# SIGNAL_LONGSHORT: Trade both directions
# > 0 = go long, < 0 = go short
cerebro.add_signal(bt.SIGNAL_LONGSHORT, MyIndicator)

# SIGNAL_LONG: Long entries only
# > 0 = go long, < 0 = exit long (if no LONGEXIT)
cerebro.add_signal(bt.SIGNAL_LONG, bt.indicators.RSI, period=14)

# SIGNAL_SHORT: Short entries only
# < 0 = go short, > 0 = exit short (if no SHORTEXIT)
cerebro.add_signal(bt.SIGNAL_SHORT, MyShortIndicator)

# SIGNAL_LONGEXIT: Exit long positions
# < 0 = exit long
cerebro.add_signal(bt.SIGNAL_LONGEXIT, MyExitIndicator)

# SIGNAL_SHORTEXIT: Exit short positions
# > 0 = exit short
cerebro.add_signal(bt.SIGNAL_SHORTEXIT, MyShortExitIndicator)
```

#### 3. The `_next_signal()` Method - Signal Processing

```python
def _next_signal(self):
    """
    Process signals and generate orders.
    """
    if self._sentinel is not None and not self.p._concurrent:
        return  # Order pending and concurrency disabled
    
    sigs = self._signals
    nosig = [[0.0]]  # Default when no signals
    
    # Check LONGSHORT signals
    ls_long = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)
    ls_short = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGSHORT] or nosig)
    
    # Check LONG signals
    l_enter = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_LONG] or nosig)
    
    # Check SHORT signals
    s_enter = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_SHORT] or nosig)
    
    # Check exit signals
    l_exit = all(x[0] < 0.0 for x in sigs[bt.SIGNAL_LONGEXIT] or nosig)
    s_exit = all(x[0] > 0.0 for x in sigs[bt.SIGNAL_SHORTEXIT] or nosig)
    
    # Reversal logic (use opposite signal if no explicit exit)
    l_rev = not self._longexit and s_enter
    s_rev = not self._shortexit and l_enter
    
    # Order logic based on position
    size = self.getposition(self._dtarget).size
    
    if not size:  # No position
        if ls_long or l_enter:
            self._sentinel = self.buy(self._dtarget)
        elif ls_short or s_enter:
            self._sentinel = self.sell(self._dtarget)
    
    elif size > 0:  # Long position
        if ls_short or l_exit or l_rev:
            self.close(self._dtarget)
        if ls_short or l_rev:
            self._sentinel = self.sell(self._dtarget)
        if (ls_long or l_enter) and self.p._accumulate:
            self._sentinel = self.buy(self._dtarget)
    
    elif size < 0:  # Short position
        if ls_long or s_exit or s_rev:
            self.close(self._dtarget)
        if ls_long or s_rev:
            self._sentinel = self.buy(self._dtarget)
        if (ls_short or s_enter) and self.p._accumulate:
            self._sentinel = self.sell(self._dtarget)
```

#### 4. Complete SignalStrategy Example

```python
import backtrader as bt

# Custom signal indicator
class TrendSignal(bt.Indicator):
    lines = ('signal',)
    params = (('fast', 10), ('slow', 30))
    
    def __init__(self):
        fast_ma = bt.indicators.SMA(period=self.p.fast)
        slow_ma = bt.indicators.SMA(period=self.p.slow)
        self.lines.signal = fast_ma - slow_ma

# Using SignalStrategy via cerebro
cerebro = bt.Cerebro()

# Add data
data = bt.feeds.YahooFinanceData(dataname='AAPL', ...)
cerebro.adddata(data)

# Add signals (cerebro creates SignalStrategy automatically)
cerebro.add_signal(bt.SIGNAL_LONGSHORT, TrendSignal)

# Run
results = cerebro.run()


# Custom SignalStrategy subclass
class MySignalStrategy(bt.SignalStrategy):
    def __init__(self):
        # Add signals programmatically
        trend = TrendSignal(self.data)
        self.signal_add(bt.SIGNAL_LONG, trend)
        
        # Or use RSI for exits
        rsi = bt.indicators.RSI(period=14)
        self.signal_add(bt.SIGNAL_LONGEXIT, rsi)
    
    def next(self):
        # This gets called AFTER signal processing
        # via the _next_custom mechanism
        print(f"Position: {self.position.size}")

cerebro.addstrategy(MySignalStrategy)
```

---

## Complete Strategy Example

```python
import backtrader as bt
from datetime import datetime

class ComprehensiveStrategy(bt.Strategy):
    """
    Complete example demonstrating all strategy features.
    """
    
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('rsi_period', 14),
        ('rsi_upper', 70),
        ('rsi_lower', 30),
        ('risk_percent', 0.02),
        ('printlog', True),
    )
    
    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()} {txt}')
    
    def __init__(self):
        # Indicators
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_period)
        self.rsi = bt.indicators.RSI(period=self.p.rsi_period)
        
        # Crossover signal
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        
        # Track orders
        self.order = None
        self.buyprice = None
        self.buycomm = None
        
        # Timer for end-of-day check
        self.add_timer(
            when=bt.timer.SESSION_END,
            offset=datetime.timedelta(minutes=-30)
        )
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, '
                        f'Cost: {order.executed.value:.2f}, '
                        f'Comm: {order.executed.comm:.2f}')
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, '
                        f'Cost: {order.executed.value:.2f}, '
                        f'Comm: {order.executed.comm:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected')
        
        self.order = None
    
    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        self.log(f'TRADE PROFIT, Gross: {trade.pnl:.2f}, Net: {trade.pnlcomm:.2f}')
    
    def notify_timer(self, timer, when, *args, **kwargs):
        self.log(f'Timer fired at {when} - Checking positions')
    
    def start(self):
        self.log(f'Strategy starting with ${self.broker.getcash():.2f}')
    
    def prenext(self):
        self.log(f'Warming up... bar {len(self)}')
    
    def nextstart(self):
        self.log(f'Indicators ready - starting trading')
        self.next()
    
    def next(self):
        # Don't trade if order pending
        if self.order:
            return
        
        # Check position
        if not self.position:
            # Entry logic
            if self.crossover > 0 and self.rsi < self.p.rsi_lower:
                # Calculate position size based on risk
                risk_amount = self.broker.getvalue() * self.p.risk_percent
                stop_price = self.data.close[0] * 0.95  # 5% stop
                risk_per_share = self.data.close[0] - stop_price
                size = int(risk_amount / risk_per_share)
                
                self.log(f'BUY CREATE, {self.data.close[0]:.2f}, Size: {size}')
                self.order = self.buy(size=size)
        
        else:
            # Exit logic
            if self.crossover < 0 or self.rsi > self.p.rsi_upper:
                self.log(f'SELL CREATE, {self.data.close[0]:.2f}')
                self.order = self.sell(size=self.position.size)
    
    def stop(self):
        self.log(f'Strategy ending with ${self.broker.getvalue():.2f}')
        self.log(f'Return: {(self.broker.getvalue() / 100000 - 1) * 100:.2f}%')


# Run the strategy
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # Add data
    data = bt.feeds.GenericCSVData(
        dataname='data.csv',
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5
    )
    cerebro.adddata(data)
    
    # Add strategy
    cerebro.addstrategy(ComprehensiveStrategy)
    
    # Broker settings
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)
    
    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    # Add observers
    cerebro.addobserver(bt.observers.DrawDown)
    
    # Run
    results = cerebro.run()
    strat = results[0]
    
    # Print analyzer results
    print(f"Sharpe Ratio: {strat.analyzers.sharpe.get_analysis()['sharperatio']:.2f}")
    print(f"Max Drawdown: {strat.analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%")
    
    # Plot
    cerebro.plot()
```

---

## Summary: Strategy Class Hierarchy

```
StrategyBase (from lineiterator.py)
    │
    └── Strategy (uses MetaStrategy metaclass)
            │
            ├── _ltype = StratType
            ├── csv = True
            ├── lines = ('datetime',)
            │
            ├── Order Methods:
            │   ├── buy() / sell() / close() / cancel()
            │   ├── buy_bracket() / sell_bracket()
            │   └── order_target_size/value/percent()
            │
            ├── Position Methods:
            │   ├── getposition() / position property
            │   └── getpositions() / positions property
            │
            ├── Lifecycle:
            │   ├── start() / stop()
            │   ├── prenext() / nextstart() / next()
            │   └── prenext_open() / next_open()
            │
            ├── Notifications:
            │   ├── notify_order() / notify_trade()
            │   ├── notify_cashvalue() / notify_fund()
            │   └── notify_timer() / notify_data()
            │
            └── Management:
                ├── setsizer() / getsizer() / getsizing()
                ├── add_timer()
                └── qbuffer()
            │
            └── SignalStrategy (uses MetaSigStrategy)
                    │
                    ├── _next_signal() - auto trading
                    ├── signal_add() - add signals
                    └── params: signals, _accumulate, _concurrent

MetaStrategy (metaclass)
    ├── __new__: backward compat for notify methods
    ├── __init__: class registration
    ├── donew: cerebro/broker setup
    ├── dopreinit: orders/trades/analyzers init
    └── dopostinit: sizer setup

MetaSigStrategy (metaclass)
    ├── __new__: remap next to _next_custom
    ├── dopreinit: signal storage setup
    └── dopostinit: create signal instances
```

---

## Key Takeaways

1. **Lifecycle**: `__init__` → `start()` → `prenext()` → `nextstart()` → `next()` → `stop()`
2. **Order Methods**: Use `buy()`, `sell()`, `close()` for orders; bracket orders for stop/limit
3. **Target Orders**: Use `order_target_*` for rebalancing
4. **Notifications**: Override `notify_order()` and `notify_trade()` for order/trade feedback
5. **Sizers**: Set via `cerebro.addsizer()` or `strategy.setsizer()`
6. **Timers**: Use `add_timer()` for scheduled actions
7. **SignalStrategy**: For indicator-driven automated trading
8. **Memory**: Use `qbuffer()` for memory-constrained environments
