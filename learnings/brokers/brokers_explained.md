# backtrader/brokers — Broker System Explained

This document covers all broker classes in the `backtrader/brokers/` module:
the base class `BrokerBase`, the simulation broker `BackBroker`, and the three
live broker adapters (`IBBroker`, `OandaBroker`, `VCBroker`).

---

## Inheritance Hierarchy

```
object
  └── BrokerBase (metaclass: MetaBroker)              backtrader/broker.py
        │   Abstract base: getcash, getvalue, buy, sell, cancel, next
        │
        ├── BackBroker (alias: BrokerBack)             backtrader/brokers/bbroker.py
        │     Full simulation broker with order matching, slippage, etc.
        │     This is the DEFAULT broker created by Cerebro.
        │
        ├── IBBroker (metaclass: MetaIBBroker)         backtrader/brokers/ibbroker.py
        │     Live broker adapter for Interactive Brokers (via IBPy/ibstore)
        │
        ├── OandaBroker (metaclass: MetaOandaBroker)   backtrader/brokers/oandabroker.py
        │     Live broker adapter for Oanda forex (via oandastore)
        │
        └── VCBroker (metaclass: MetaVCBroker)         backtrader/brokers/vcbroker.py
              Live broker adapter for VisualChart (via vcstore)
```

The `__init__.py` always imports `BackBroker` and `BrokerBack`, and optionally
imports the live brokers (catching `ImportError` if dependencies are missing).

---

## Class: BrokerBase

**File:** `backtrader/broker.py`
**Metaclass:** `MetaBroker`

The abstract base class for all brokers. Defines the interface that every broker
must implement.

### MetaBroker

Creates aliases for method names (`get_cash` → `getcash`, `get_value` → `getvalue`)
to support both naming conventions.

### Parameters

```python
params = (
    ('commission', CommInfoBase(percabs=True)),  # default commission scheme
)
```

### Key Methods (Interface)

```python
class BrokerBase:
    def __init__(self):
        self.comminfo = dict()    # {name_or_None: CommInfoBase}
        self.init()

    def init(self):
        '''Called from __init__ and from start()'''
        if None not in self.comminfo:
            self.comminfo = dict({None: self.p.commission})

    def start(self):     self.init()
    def stop(self):      pass
    def next(self):      pass     # called each bar by Cerebro

    # --- Must be implemented by subclasses ---
    def getcash(self):            raise NotImplementedError
    def getvalue(self, datas=None): raise NotImplementedError
    def getposition(self, data):  raise NotImplementedError
    def buy(self, ...):           raise NotImplementedError
    def sell(self, ...):          raise NotImplementedError
    def submit(self, order):      raise NotImplementedError
    def cancel(self, order):      raise NotImplementedError

    # --- Commission management ---
    def getcommissioninfo(self, data):
        '''Look up CommInfo by data name, fall back to default (None key)'''
        if data._name in self.comminfo:
            return self.comminfo[data._name]
        return self.comminfo[None]

    def setcommission(self, commission=0.0, margin=None, mult=1.0,
                      commtype=None, percabs=True, stocklike=False,
                      interest=0.0, interest_long=False, leverage=1.0,
                      automargin=False, name=None):
        '''Create and register a CommInfoBase for an asset'''
        comm = CommInfoBase(commission=commission, margin=margin, ...)
        self.comminfo[name] = comm

    def addcommissioninfo(self, comminfo, name=None):
        '''Register an existing CommInfoBase object'''
        self.comminfo[name] = comminfo

    # --- Fund mode (optional) ---
    def get_fundshares(self): return 1.0
    def get_fundvalue(self):  return self.getvalue()
    def set_fundmode(self, fundmode, fundstartval=None): pass
    def get_fundmode(self): return False
```

**Example:**

```python
cerebro = bt.Cerebro()

# The default broker is BackBroker, created automatically:
# cerebro._broker = BackBroker()

# Set commission for all assets:
cerebro.broker.setcommission(commission=0.001)  # 0.1% per trade

# Set commission for a specific asset:
cerebro.broker.setcommission(commission=0.0005, name='AAPL')

# Set starting cash:
cerebro.broker.setcash(100000)
```

---

## Commission System Deep Dive

**File:** `backtrader/comminfo.py`

The commission system is built around `CommInfoBase` — a params-based object that
encapsulates all the financial math for commission calculation, position valuation,
margin requirements, profit-and-loss, and credit interest.

### Class Hierarchy

```
CommInfoBase (metaclass: MetaParams)
    └── CommissionInfo
          Default for modern usage, sets percabs=True
```

### CommInfoBase Parameters

```python
params = (
    ('commission', 0.0),        # base commission value
    ('mult', 1.0),              # multiplier for futures ($/point)
    ('margin', None),           # margin per contract (futures)
    ('commtype', None),         # COMM_PERC or COMM_FIXED
    ('stocklike', False),       # True=stock, False=futures
    ('percabs', False),         # True=0.XX format, False=XX% format
    ('interest', 0.0),          # yearly short-selling interest rate
    ('interest_long', False),   # charge interest on longs too
    ('leverage', 1.0),          # leverage multiplier
    ('automargin', False),      # auto-calculate margin from price
)
```

### How `commtype` Auto-Detection Works

When `commtype` is `None` (default), backtrader uses legacy logic to auto-detect:

```
commtype=None?
    │
    ├── margin is set (not None/0)?
    │     YES → _commtype = COMM_FIXED, _stocklike = False
    │           (Futures-like: fixed per-contract commission)
    │
    └── margin is NOT set?
          YES → _commtype = COMM_PERC, _stocklike = True
                (Stock-like: percentage commission)
```

And then `percabs` controls how the `commission` value is interpreted:

```
_commtype == COMM_PERC?
    │
    ├── percabs = True  → commission = 0.001 means 0.1%  (already in 0.XX)
    └── percabs = False → commission = 0.1 means 0.1%    (divided by 100)
```

**Important:** `BrokerBase.setcommission()` always passes `percabs=True`, so
when using `cerebro.broker.setcommission(commission=0.001)`, the value `0.001`
is used directly (not divided by 100).

### Commission Calculation: `_getcommission()`

The core formula depends on `_commtype`:

```python
def _getcommission(self, size, price, pseudoexec):
    if self._commtype == self.COMM_PERC:
        return abs(size) * self.p.commission * price
        #      ─────────   ─────────────────   ─────
        #      # shares    percentage rate      share price
        #
        # Example: 100 shares * 0.001 * $50.00 = $5.00

    return abs(size) * self.p.commission
    #      ─────────   ─────────────────
    #      # contracts  fixed $ per contract
    #
    # Example: 5 contracts * $2.50 = $12.50
```

### Position Valuation: `getvaluesize()` and `getoperationcost()`

```python
def getvaluesize(self, size, price):
    '''Market value of a position'''
    if not self._stocklike:
        return abs(size) * self.get_margin(price)   # futures: margin-based
    return size * price                              # stocks: shares × price
    # Note: for stocks, size can be negative (short),
    # so value is negative for short positions

def getoperationcost(self, size, price):
    '''Cash needed to open a position'''
    if not self._stocklike:
        return abs(size) * self.get_margin(price)   # futures: margin
    return abs(size) * price                         # stocks: always positive
```

#### How `get_margin(price)` Works

For futures-like instruments, holding a position does not require paying the full
notional value. Instead, you post a **margin** (a deposit/guarantee). The
`get_margin` method determines how much margin is needed **per single contract**
at a given price.

```python
def get_margin(self, price):
    if not self.p.automargin:          # automargin is False (default)
        return self.p.margin           # → use the fixed margin parameter
    elif self.p.automargin < 0:
        return price * self.p.mult     # → full notional value
    return price * self.p.automargin   # → fraction of price
```

Three modes, controlled by the `automargin` parameter:

```
automargin = False (default)
    │
    └── Return self.p.margin             # a fixed dollar amount
        Example: margin=5000 → always $5,000 per contract regardless of price

automargin < 0  (e.g. automargin=-1)
    │
    └── Return price * self.p.mult       # full notional value
        Example: ES at 4500, mult=50 → 4500 * 50 = $225,000 per contract

automargin > 0  (e.g. automargin=0.10)
    │
    └── Return price * automargin        # percentage of price
        Example: price=4500, automargin=0.10 → 4500 * 0.10 = $450 per contract
```

**Why does `price` matter?** — For `automargin` modes, the margin changes with
the asset's price. A futures contract at 4500 requires more margin than the same
contract at 3000. When `automargin=False` (default), `price` is ignored entirely
and the fixed `margin` parameter is returned.

#### How `get_margin` Flows Into Position Valuation

```
broker.setcommission(commission=2.50, margin=5000, mult=50, name='ES')
    │
    │   CommInfoBase.__init__:
    │     self.p.margin = 5000
    │     self.p.mult = 50
    │     self.p.automargin = False
    │     _stocklike = False (because margin is set)
    │
    ▼
BackBroker._execute(order, ago=0, price=4500)
    │
    │   comminfo = self.getcommissioninfo(data)  → the ES CommInfoBase
    │
    ├── OPENING 3 contracts:
    │   openedvalue = comminfo.getvaluesize(3, 4500)
    │                 = abs(3) * comminfo.get_margin(4500)
    │                 = 3 * 5000       ← automargin=False, returns fixed 5000
    │                 = $15,000        ← this is how much MARGIN is required
    │
    │   (The notional value is 3 * 4500 * 50 = $675,000, but you only need
    │    $15,000 in margin to control that position)
    │
    │   cash -= openedvalue / leverage   ← if leverage=1.0: cash -= 15000
    │   cash -= openedcomm               ← 3 * 2.50 = $7.50
    │
    └── CLOSING 3 contracts:
        closedvalue = comminfo.getvaluesize(-3, 4500)
                    = abs(-3) * get_margin(4500) = $15,000
        cash += closedvalue / leverage   ← margin returned to cash
```

#### Comparison: All Three Valuation Callers

`get_margin` is used by four methods, all for futures-like instruments only:

```
┌──────────────────────┬────────────────────────────────────────────────────┐
│ Method               │ Formula (futures only)                             │
├──────────────────────┼────────────────────────────────────────────────────┤
│ getvaluesize(s, p)   │ abs(size) * get_margin(price)                     │
│                      │ "What is this position worth in margin terms?"     │
│                      │ Used in _execute for opened/closed value           │
├──────────────────────┼────────────────────────────────────────────────────┤
│ getoperationcost(s,p)│ abs(size) * get_margin(price)                     │
│                      │ "How much cash do I need to open this?"            │
│                      │ Same formula, but always positive (abs)            │
├──────────────────────┼────────────────────────────────────────────────────┤
│ getvalue(pos, price) │ abs(pos.size) * get_margin(price)                 │
│                      │ "What is an existing position worth?"              │
│                      │ Used in _get_value for portfolio valuation         │
├──────────────────────┼────────────────────────────────────────────────────┤
│ getsize(price, cash) │ int(leverage * (cash // get_margin(price)))        │
│                      │ "How many contracts can I afford?"                 │
│                      │ Used by sizers to determine order size             │
└──────────────────────┴────────────────────────────────────────────────────┘
```

#### Examples

```python
# ─── Example 1: Fixed margin (default) ───
cerebro.broker.setcommission(
    commission=2.50, margin=5000, mult=50, name='ES'
)
# get_margin(4500) = 5000   (fixed, price ignored)
# get_margin(3000) = 5000   (same)
# getvaluesize(3, 4500) = 3 * 5000 = $15,000
# getsize(4500, 100000) = int(1.0 * (100000 // 5000)) = 20 contracts

# ─── Example 2: Automargin as full notional ───
cerebro.broker.setcommission(
    commission=2.50, margin=5000, mult=50, automargin=-1, name='ES'
)
# get_margin(4500) = 4500 * 50 = $225,000  (full notional!)
# get_margin(3000) = 3000 * 50 = $150,000  (changes with price)
# getvaluesize(3, 4500) = 3 * 225000 = $675,000
# getsize(4500, 1000000) = int(1.0 * (1000000 // 225000)) = 4 contracts

# ─── Example 3: Automargin as percentage ───
cerebro.broker.setcommission(
    commission=2.50, margin=5000, mult=50, automargin=0.10, name='ES'
)
# get_margin(4500) = 4500 * 0.10 = $450    (10% of price)
# get_margin(3000) = 3000 * 0.10 = $300    (changes with price)
# getvaluesize(3, 4500) = 3 * 450 = $1,350
# getsize(4500, 10000) = int(1.0 * (10000 // 450)) = 22 contracts

# ─── Example 4: Stocks (get_margin not called) ───
cerebro.broker.setcommission(commission=0.001)
# _stocklike = True → getvaluesize/getoperationcost skip get_margin entirely
# getvaluesize(100, 50) = 100 * 50 = $5,000  (shares × price)
# getsize(50, 10000) = int(1.0 * (10000 // 50)) = 200 shares
```

### Profit and Loss

```python
def profitandloss(self, size, price, newprice):
    '''PnL for a position'''
    return size * (newprice - price) * self.p.mult
    # Stocks (mult=1.0):  100 * (55.00 - 50.00) * 1.0 = $500.00
    # Futures (mult=50):  5   * (2100 - 2095)    * 50  = $1250.00
```

### Cash Adjustment (Futures Mark-to-Market)

```python
def cashadjust(self, size, price, newprice):
    '''Daily cash settlement for futures (mark-to-market)'''
    if not self._stocklike:
        return size * (newprice - price) * self.p.mult
    return 0.0  # stocks don't have daily cash adjustment
```

This is called at the end of every bar in `BackBroker.next()`:

```python
# End of bar: adjust cash for futures positions
for data, pos in self.positions.items():
    if pos:
        comminfo = self.getcommissioninfo(data)
        self.cash += comminfo.cashadjust(pos.size, pos.adjbase, data.close[0])
        pos.adjbase = data.close[0]

# Example: Long 5 ES futures, yesterday close=2095, today close=2100
# cashadjust = 5 * (2100 - 2095) * 50 = $1250 added to cash
```

### Credit Interest (Short-Selling Cost)

```python
def get_credit_interest(self, data, pos, dt):
    '''Interest charged for holding a short position'''
    size, price = pos.size, pos.price
    if size > 0 and not self.p.interest_long:
        return 0.0  # longs not charged (unless interest_long=True)

    days = (dt.date() - pos.datetime.date()).days
    return days * (interest / 365.0) * abs(size) * price

# Example: Short 200 shares at $50, interest=0.05 (5%), held 3 days:
# credit = 3 * (0.05/365) * 200 * 50 = $4.11 deducted from cash
```

Called each bar in `BackBroker.next()`:

```python
for data, pos in self.positions.items():
    if pos:
        comminfo = self.getcommissioninfo(data)
        dcredit = comminfo.get_credit_interest(data, pos, dt0)
        self.d_credit[data] += dcredit  # accumulate for PnL assignment
self.cash -= credit
```

### Margin Calculation

```python
def get_margin(self, price):
    if not self.p.automargin:
        return self.p.margin         # use fixed margin parameter
    elif self.p.automargin < 0:
        return price * self.p.mult   # full notional value
    return price * self.p.automargin # custom percentage of price

def getsize(self, price, cash):
    '''How many units can be bought with available cash'''
    if not self._stocklike:
        return int(self.p.leverage * (cash // self.get_margin(price)))
    return int(self.p.leverage * (cash // price))

# Example: Futures, margin=$5000, leverage=1.0, cash=$100,000
# getsize = int(1.0 * (100000 // 5000)) = 20 contracts
```

### Where Commission Is Consumed in `BackBroker._execute()`

```
BackBroker._execute(order, ago=0, price=100.50)
    │
    ├── comminfo = self.getcommissioninfo(order.data)
    │   # Lookup: self.comminfo[data._name] or self.comminfo[None]
    │
    ├── position.pseudoupdate(size, price) → psize, pprice, opened, closed
    │
    ├── CLOSED portion (closing existing position):
    │   │
    │   ├── pnl = comminfo.profitandloss(-closed, pprice_orig, price)
    │   │   # e.g. PnL = -100 * (100.50 - 95.00) * 1.0 = $550
    │   │
    │   ├── closedvalue = comminfo.getvaluesize(-closed, pprice_orig)
    │   │   # Cash returned from closing the position
    │   │
    │   ├── closedcomm = comminfo.getcommission(closed, price)
    │   │   # e.g. COMM_PERC: 100 * 0.001 * 100.50 = $10.05
    │   │
    │   └── cash += closedvalue/leverage + pnl*stocklike - closedcomm
    │       # Cash increases by value + profit, decreases by commission
    │
    └── OPENED portion (opening new position):
        │
        ├── openedvalue = comminfo.getvaluesize(opened, price)
        │   # Cash needed for new position
        │
        ├── openedcomm = comminfo.getcommission(opened, price)
        │   # Commission on newly opened portion
        │
        └── cash -= openedvalue/leverage + openedcomm
            # Cash decreases by position cost + commission
            # If cash < 0 → execution is nullified (margin call)
```

### The Commission Lookup: `comminfo` Dictionary

```python
# BrokerBase maintains:
self.comminfo = {
    None: CommInfoBase(percabs=True),  # default for all assets
    'AAPL': CommInfoBase(...),         # specific to AAPL data feed
    'ES': CommInfoBase(...),           # specific to ES futures
}

# When broker needs commission info:
def getcommissioninfo(self, data):
    if data._name in self.comminfo:
        return self.comminfo[data._name]    # asset-specific
    return self.comminfo[None]               # default fallback
```

### Complete Examples

#### Example 1: Stock Trading — Percentage Commission

```python
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 0.1% commission on each trade (buy and sell)
cerebro.broker.setcommission(commission=0.001)
# Internally:
#   percabs=True (from setcommission) → commission stays 0.001
#   margin=None → _stocklike=True, _commtype=COMM_PERC

# === Trade trace ===
# Buy 100 shares of AAPL at $150.00:
#   openedcomm = 100 * 0.001 * 150.00 = $15.00
#   openedvalue = 100 * 150.00 = $15,000.00
#   cash: 100000 - 15000 - 15.00 = $84,985.00

# Sell 100 shares at $160.00:
#   closedcomm = 100 * 0.001 * 160.00 = $16.00
#   closedvalue = 100 * 150.00 = $15,000.00  (original value)
#   pnl = 100 * (160.00 - 150.00) * 1.0 = $1,000.00
#   cash: 84985 + 15000 + 1000 - 16.00 = $100,969.00

# Net profit: $1000 - $15 - $16 = $969.00
```

#### Example 2: Stock Trading — Fixed Commission

```python
cerebro.broker.setcommission(
    commission=9.99,           # $9.99 flat per trade
    commtype=bt.CommInfoBase.COMM_FIXED,
    stocklike=True,
)
# Internally:
#   _commtype = COMM_FIXED (explicit)
#   _stocklike = True (explicit)

# === Trade trace ===
# Buy 500 shares at $25.00:
#   openedcomm = 500 * 9.99 = $4,995.00  ← WRONG! This is per-share!
#   Actually: with COMM_FIXED, commission = abs(size) * commission
#   So: 500 * 9.99 = $4995  ← that's 500 × $9.99

# For a TRUE flat fee, you need a custom CommInfo:
class FixedCommInfo(bt.CommInfoBase):
    params = (('commission', 9.99), ('stocklike', True),)

    def _getcommission(self, size, price, pseudoexec):
        return self.p.commission  # flat $9.99 regardless of size

cerebro.broker.addcommissioninfo(FixedCommInfo())
# Now: buy 500 shares → commission = $9.99 (flat)
```

#### Example 3: Futures — Fixed Per-Contract Commission

```python
cerebro.broker.setcommission(
    commission=2.50,           # $2.50 per contract per side
    margin=5000.0,             # $5,000 margin per contract
    mult=50.0,                 # $50 per point (e.g. E-mini S&P 500)
    stocklike=False,
    name='ES',
)
# Internally:
#   commtype=None, margin=5000 → _commtype=COMM_FIXED, _stocklike=False

# === Trade trace ===
# Starting cash: $100,000

# Buy 3 ES contracts at 4500:
#   openedcomm = 3 * 2.50 = $7.50
#   openedvalue = 3 * 5000 = $15,000 (margin)
#   cash: 100000 - 15000 - 7.50 = $84,992.50

# End of day, ES closes at 4510 (+10 points):
#   cashadjust = 3 * (4510 - 4500) * 50 = $1,500.00
#   cash: 84992.50 + 1500 = $86,492.50

# Next day, ES closes at 4505 (-5 points from yesterday):
#   cashadjust = 3 * (4505 - 4510) * 50 = -$750.00
#   cash: 86492.50 - 750 = $85,742.50

# Sell 3 contracts at 4505:
#   closedcomm = 3 * 2.50 = $7.50
#   pnl = -3 * (4500 - 4505) * 50 = $750.00  (profit over entry)
#   Margin returned: $15,000
#   cash: 85742.50 + 15000 + ... - 7.50 = ...
#   (Note: daily cashadjust already marked-to-market incrementally)

# Total commission: $7.50 (open) + $7.50 (close) = $15.00
# Total PnL: (4505 - 4500) * 3 * 50 = $750 - $15 commission = $735
```

#### Example 4: Forex — With Leverage

```python
cerebro.broker.setcommission(
    commission=0.00002,        # 2 pip spread as commission
    margin=1000.0,             # $1000 margin per standard lot
    mult=100000.0,             # 1 lot = 100,000 units
    stocklike=False,
    leverage=50.0,             # 50:1 leverage
    name='EURUSD',
)

# === Trade trace ===
# Starting cash: $10,000

# Buy 1 lot EURUSD at 1.1000:
#   margin per lot = $1,000
#   with leverage 50: getsize(1.1, 10000) = int(50 * (10000 // 1000)) = 500 lots!
#   But let's buy just 1 lot:
#
#   openedcomm = 1 * 0.00002 = $0.00002 (tiny, real cost is in spread)
#   openedvalue = 1 * 1000 = $1,000 (margin)
#   cash: 10000 - 1000/50 - 0.00002 = 10000 - 20 ≈ $9,980.00
#   (leverage=50 means only 1/50th of margin is deducted)

# EURUSD moves to 1.1050 (+50 pips):
#   cashadjust = 1 * (1.1050 - 1.1000) * 100000 = $500.00
#   cash: 9980 + 500 = $10,480.00
```

#### Example 5: Short Selling with Interest

```python
cerebro.broker.setcommission(
    commission=0.001,          # 0.1% commission
    interest=0.05,             # 5% annual borrow rate
    stocklike=True,
)

# === Trade trace ===
# Short sell 200 shares at $50.00:
#   openedcomm = 200 * 0.001 * 50 = $10.00
#   With shortcash=True (default):
#     openedvalue = 200 * 50 = $10,000 (negative, but shortcash adds to cash)
#   cash: 100000 + 10000 - 10.00 = $109,990.00

# Each day held, interest is charged:
#   daily_rate = 0.05 / 365 = 0.000137
#   credit = 1 * 0.000137 * 200 * 50 = $1.37 per day
#   cash: 109990 - 1.37 = $109,988.63 (day 1)

# After 30 days, cover at $45.00:
#   closedcomm = 200 * 0.001 * 45 = $9.00
#   pnl = 200 * (50.00 - 45.00) * 1.0 = $1,000.00 profit
#   interest_total ≈ 30 * 1.37 = $41.10
#   Net profit: 1000 - 10 - 9 - 41.10 = $939.90
```

#### Example 6: Multiple Assets, Different Commissions

```python
cerebro = bt.Cerebro()
cerebro.broker.setcash(200000)

# Default: 0.1% for stocks
cerebro.broker.setcommission(commission=0.001)

# Override for specific assets:
cerebro.broker.setcommission(
    commission=2.50, margin=5000, mult=50, name='ES'
)
cerebro.broker.setcommission(
    commission=1.50, margin=2000, mult=20, name='NQ'
)

# Or use addcommissioninfo with a custom class:
class IBCommission(bt.CommInfoBase):
    params = (
        ('commission', 0.005),    # $0.005 per share
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
    )

    def _getcommission(self, size, price, pseudoexec):
        # IB-style: $0.005/share, minimum $1.00
        return max(1.0, abs(size) * self.p.commission)

cerebro.broker.addcommissioninfo(IBCommission(), name='AAPL')

# Now:
# - Trading 'ES' data → $2.50/contract, $5000 margin, $50/point
# - Trading 'NQ' data → $1.50/contract, $2000 margin, $20/point
# - Trading 'AAPL' data → $0.005/share, min $1.00 (IB-style)
# - Trading any other data → 0.1% per trade
```

#### Example 7: Custom CommInfoBase Subclass

```python
class TieredCommission(bt.CommInfoBase):
    '''Volume-based tiered commission like real brokers'''
    params = (
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
    )

    def _getcommission(self, size, price, pseudoexec):
        asize = abs(size)
        if asize <= 500:
            return asize * 0.01        # $0.01/share for ≤500
        elif asize <= 2000:
            return 500 * 0.01 + (asize - 500) * 0.005  # $0.005 for 501-2000
        else:
            return 500*0.01 + 1500*0.005 + (asize-2000)*0.003  # $0.003 above 2000

# Usage:
cerebro.broker.addcommissioninfo(TieredCommission())

# 100 shares: 100 * 0.01 = $1.00
# 1000 shares: 500*0.01 + 500*0.005 = $5.00 + $2.50 = $7.50
# 5000 shares: 500*0.01 + 1500*0.005 + 3000*0.003 = $5 + $7.5 + $9 = $21.50
```

### Visual Summary: Commission Flow

```
cerebro.broker.setcommission(commission=0.001, ...)
    │
    ▼
CommInfoBase.__init__()
    │
    ├── commtype=None, margin=None → _commtype=COMM_PERC, _stocklike=True
    ├── percabs=True → commission stays 0.001 (not divided by 100)
    └── Stored in: broker.comminfo[name] = comminfo
        │
        ▼
Strategy calls self.buy(size=100)
    │
    ▼
BackBroker._execute(order, ago=0, price=150.00)
    │
    ├── comminfo = broker.getcommissioninfo(data)
    │   │   Lookup: comminfo['AAPL'] → found? use it
    │   │           comminfo[None]   → fallback default
    │   └── Returns: CommInfoBase instance
    │
    ├── OPENING: openedcomm = comminfo.getcommission(100, 150.00)
    │            = abs(100) * 0.001 * 150.00 = $15.00
    │            cash -= $15,000 (position cost) + $15.00 (commission)
    │
    └── CLOSING (later): closedcomm = comminfo.getcommission(100, 160.00)
                         = abs(100) * 0.001 * 160.00 = $16.00
                         cash += $15,000 + $1,000(pnl) - $16.00

    Each bar while position is open:
    ├── comminfo.get_credit_interest(data, pos, dt)    → short interest
    └── comminfo.cashadjust(size, adjbase, close[0])   → futures mark-to-market
```

---

## Class: BackBroker (Simulation Broker)

**File:** `backtrader/brokers/bbroker.py`
**Alias:** `BrokerBack`

The default broker used for backtesting. It simulates order execution against
historical OHLC data, supporting slippage, commissions, margin, bracket orders,
OCO orders, and fund-mode performance tracking.

### Parameters

```python
params = (
    ('cash', 10000.0),          # starting cash
    ('checksubmit', True),      # check margin/cash before accepting orders
    ('eosbar', False),          # treat same-time bar as end of session
    ('filler', None),           # volume filler callable(order, price, ago)

    # Slippage options
    ('slip_perc', 0.0),         # percentage slippage (e.g. 0.01 = 1%)
    ('slip_fixed', 0.0),        # fixed-point slippage
    ('slip_open', False),       # slip on open price (Market orders)
    ('slip_match', True),       # cap slippage at high/low
    ('slip_limit', True),       # allow slippage on Limit orders
    ('slip_out', False),        # allow slippage beyond high/low

    # Cheat modes
    ('coc', False),             # Cheat-On-Close: execute Market at bar's close
    ('coo', False),             # Cheat-On-Open: execute in same bar's open

    # Accounting
    ('int2pnl', True),          # assign interest to PnL
    ('shortcash', True),        # increase cash when shorting stocks
    ('fundstartval', 100.0),    # fund-like starting share value
    ('fundmode', False),        # enable fund-mode performance tracking
)
```

### Initialization

```python
def __init__(self):
    super().__init__()
    self._userhist = []       # user-provided order history
    self._fundhist = []       # user-provided fund value history

def init(self):
    super().init()
    self.startingcash = self.cash = self.p.cash
    self._value = self.cash
    self._valuemkt = 0.0              # market value of positions

    self.orders = list()               # all orders ever submitted
    self.pending = collections.deque() # orders awaiting execution
    self._toactivate = collections.deque()  # bracket children to activate
    self.submitted = collections.deque()    # orders pending cash check

    self.positions = collections.defaultdict(Position)  # {data: Position}
    self.d_credit = collections.defaultdict(float)      # interest per data
    self.notifs = collections.deque()  # order notifications for strategies

    # Bracket/OCO support
    self._pchildren = collections.defaultdict(collections.deque)
    self._ocos = dict()               # order_ref → oco_group_ref
    self._ocol = collections.defaultdict(list)  # oco_group → [order_refs]

    # Fund mode
    self._fundval = self.p.fundstartval
    self._fundshares = self.p.cash / self._fundval
```

### Order Lifecycle: Full Call Flow

#### Order Status States

```
┌─────────┐     ┌───────────┐     ┌──────────┐
│ Created  │────▶│ Submitted │────▶│ Accepted │───┐
└─────────┘     └───────────┘     └──────────┘   │
                     │                  │          │
                     ▼                  ▼          ▼
                 ┌────────┐       ┌─────────┐  ┌─────────┐
                 │ Margin │       │ Expired │  │ Partial │
                 └────────┘       └─────────┘  └────┬────┘
                                                    │
                     ┌──────────┐              ┌────▼─────┐
                     │ Rejected │              │Completed │
                     └──────────┘              └──────────┘
                     ┌──────────┐
                     │Cancelled │
                     └──────────┘
```

Status constants (integers 0-8):

```python
Order.Created   = 0   # order just created
Order.Submitted = 1   # sent to broker for cash check
Order.Accepted  = 2   # passed cash check, in pending queue
Order.Partial   = 3   # partially filled (filler or live)
Order.Completed = 4   # fully filled
Order.Canceled  = 5   # cancelled by user or bracket sibling
Order.Expired   = 6   # validity period ended
Order.Margin    = 7   # not enough cash/margin
Order.Rejected  = 8   # rejected by broker
```

#### The Order Object — What Gets Created

When `Strategy.buy()` is called, a `BuyOrder` is created with two key data objects:

```python
class OrderBase:
    def __init__(self):
        self.ref = next(self.refbasis)    # unique ID (auto-incrementing)
        self.status = Order.Created       # initial status
        self._active = (self.parent is None)  # False for bracket children
        self.triggered = False             # for StopLimit two-phase

        # ─── Created data: the ORDER REQUEST ───
        self.created = OrderData(
            dt=data.datetime[0],           # creation datetime (float)
            size=self.size,                # requested size (neg for sell)
            price=price,                   # requested price
            pricelimit=self.pricelimit,    # limit price for StopLimit
            pclose=data.close[0],          # close at creation time
            trailamount=self.trailamount,
            trailpercent=self.trailpercent,
        )

        # ─── Executed data: fills accumulate here ───
        self.executed = OrderData(
            remsize=self.size,             # remaining unfilled size
        )
        # executed.dt, executed.size, executed.price, executed.pnl, etc.
        # are updated as fills occur via order.execute()
```

#### Phase 1: Strategy Creates the Order

```
Strategy.buy(size=100, exectype=bt.Order.Limit, price=50.00)
    │
    │   # Resolve data and size
    │   data = self.datas[0]                    # default data feed
    │   size = 100                              # or from sizer if None
    │
    └── self.broker.buy(owner=self, data=data, size=100, price=50.00,
    │                    exectype=Order.Limit, ...)
    │
    ▼
BackBroker.buy(owner, data, size=100, price=50.00, exectype=Limit, ...)
    │
    ├── order = BuyOrder(owner=owner, data=data, size=100,
    │                     price=50.00, exectype=Order.Limit, ...)
    │   │
    │   │   # Inside BuyOrder.__init__():
    │   │   order.ref = 1                       # unique ID
    │   │   order.ordtype = Order.Buy
    │   │   order.exectype = Order.Limit
    │   │   order.size = 100                    # positive for buy
    │   │   order.status = Order.Created        # ← STATUS: Created
    │   │   order._active = True                # no parent
    │   │   order.created.dt = 738156.0         # matplotlib date
    │   │   order.created.price = 50.00
    │   │   order.created.pclose = 49.80        # close when order placed
    │   │   order.executed.remsize = 100        # nothing filled yet
    │   │
    │   └── Return: BuyOrder(ref=1, Created, Limit, size=100, price=50)
    │
    ├── self._ocoize(order, oco)                # register OCO if needed
    │
    └── self.submit(order)                      # → Phase 2
```

#### Phase 2: Broker Receives and Validates

```
BackBroker.submit(order)
    │
    ├── pref = self._take_children(order)
    │   # order.parent is None → pref = order.ref (= 1)
    │   # No parent rejection issues
    │
    ├── pc = self._pchildren[1]
    │   pc.append(order)                        # stage in family queue
    │   # _pchildren[1] = deque([order])
    │
    └── order.transmit is True?  (default)
        │
        YES → self.transmit(order)
            │
            ├── self.p.checksubmit is True?  (default)
            │   │
            │   YES → Two-step: submit first, check cash later
            │       order.submit()                  # ← STATUS: Submitted
            │       self.submitted.append(order)    # into submitted queue
            │       self.orders.append(order)       # permanent record
            │       self.notify(order)              # → notifs.append(order.clone())
            │
            │   NO → Direct accept (no cash check)
            │       self.submit_accept(order)
            │       │  order.submit()               # ← STATUS: Submitted
            │       │  order.accept()               # ← STATUS: Accepted
            │       │  self.pending.append(order)   # into execution queue
            │       └──self.notify(order)
            │
            └── Return order

    # At this point, order is in EITHER:
    # (a) submitted queue (awaiting cash check), or
    # (b) pending queue (ready for execution)
```

#### Phase 3: Notification Delivery to Strategy

```
Cerebro._brokernotify()                    # called each bar
    │
    └── while True:
            order = self._broker.get_notification()
            if order is None: break        # None = boundary marker

            owner = order.owner            # the Strategy that placed it
            owner._addnotification(order)
                │
                ├── self._orderspending.append(order)  # queue for batch notify
                │
                └── If order has execution data:
                    │   Create/update Trade objects from exbits
                    │   trade = Trade(data=order.data, tradeid=order.tradeid)
                    │   trade.update(order, closed, price, closedvalue, ...)
                    │   self._tradespending.append(trade)

Strategy._notify()                         # called before strategy.next()
    │
    ├── for order in self._orderspending:
    │       self.notify_order(order)        # ← USER CODE HOOK
    │       for analyzer in self.analyzers:
    │           analyzer._notify_order(order)
    │
    ├── for trade in self._tradespending:
    │       self.notify_trade(trade)        # ← USER CODE HOOK
    │       for analyzer in self.analyzers:
    │           analyzer._notify_trade(trade)
    │
    └── Clear pending lists
```

#### Phase 4: broker.next() — Cash Check, Execution, Settlement

```
BackBroker.next()                      # called by Cerebro each bar
    │
    │   ═══ STEP 1: Activate bracket children ═══
    ├── while self._toactivate:
    │       self._toactivate.popleft().activate()
    │
    │   ═══ STEP 2: Cash check on submitted orders ═══
    ├── if self.p.checksubmit:
    │       self.check_submitted()
    │       │
    │       └── for each order in submitted queue:
    │           │
    │           │   # Pseudo-execute: simulate the order against a CLONED position
    │           │   cash = self._execute(order, ago=None, cash=cash,
    │           │                         position=position_clone)
    │           │   # ago=None means "just calculate, don't actually fill"
    │           │
    │           ├── cash >= 0?
    │           │   YES → self.submit_accept(order)
    │           │         order.submit()               # (already Submitted)
    │           │         order.accept()               # ← STATUS: Accepted
    │           │         self.pending.append(order)   # move to execution queue
    │           │         self.notify(order)            # notify Accepted
    │           │
    │           └── cash < 0?
    │               NO  → order.margin()               # ← STATUS: Margin
    │                     self.notify(order)            # notify Margin
    │                     self._bracketize(order, cancel=True)  # cancel siblings
    │
    │   ═══ STEP 3: Credit interest on open positions ═══
    ├── for data, pos in self.positions.items():
    │       if pos:
    │           credit = comminfo.get_credit_interest(data, pos, dt)
    │           self.d_credit[data] += credit
    │           self.cash -= credit
    │
    │   ═══ STEP 4: Process user order history ═══
    ├── self._process_order_history()
    │
    │   ═══ STEP 5: Try to execute pending orders ═══
    ├── self.pending.append(None)           # sentinel (stop marker)
    │   while True:
    │       order = self.pending.popleft()
    │       if order is None: break         # reached sentinel
    │       │
    │       ├── order.expire()?
    │       │   │   # Market orders never expire (return False)
    │       │   │   # Other types: check if data.datetime[0] > order.valid
    │       │   │
    │       │   YES → order.status = Expired        # ← STATUS: Expired
    │       │         self.notify(order)
    │       │         self._ococheck(order)         # cancel OCO siblings
    │       │         self._bracketize(order, cancel=True)  # cancel bracket
    │       │
    │       ├── not order.active()?
    │       │   YES → self.pending.append(order)    # put back, wait for parent
    │       │         # (bracket children sit here until activated)
    │       │
    │       └── order is active → attempt execution
    │           │
    │           │   self._try_exec(order)
    │           │   │
    │           │   │   # Read current bar prices (or tick prices for replay/live):
    │           │   │   popen  = data.tick_open  or data.open[0]
    │           │   │   phigh  = data.tick_high  or data.high[0]
    │           │   │   plow   = data.tick_low   or data.low[0]
    │           │   │   pclose = data.tick_close or data.close[0]
    │           │   │
    │           │   │   # Dispatch to type-specific handler:
    │           │   │   Market     → _try_exec_market(order, popen, phigh, plow)
    │           │   │   Close      → _try_exec_close(order, pclose)
    │           │   │   Limit      → _try_exec_limit(order, popen, phigh, plow, plimit)
    │           │   │   Stop       → _try_exec_stop(order, popen, phigh, plow, pcreated, pclose)
    │           │   │   StopLimit  → _try_exec_stoplimit(...)
    │           │   │   Historical → _try_exec_historical(order)
    │           │   │
    │           │   │   # If matched → _execute(order, ago=0, price=p)
    │           │   │   #   → position updated, cash adjusted
    │           │   │   #   → order.execute(dt, size, price, ...)
    │           │   │   #   → STATUS: Completed (or Partial with filler)
    │           │   │   #   → self.notify(order)
    │           │
    │           ├── order.alive()?  (Created/Submitted/Partial/Accepted)
    │           │   YES → self.pending.append(order)    # try again next bar
    │           │
    │           └── order.status == Completed?
    │               YES → self._bracketize(order)       # activate/cancel siblings
    │
    │   ═══ STEP 6: End-of-bar futures cash adjustment ═══
    └── for data, pos in self.positions.items():
            if pos:
                self.cash += comminfo.cashadjust(pos.size, pos.adjbase,
                                                 data.close[0])
                pos.adjbase = data.close[0]

        self._get_value()                   # recalculate portfolio value
```

#### Example 1: Market Order — Simplest Path

```python
class MarketExample(bt.Strategy):
    def next(self):
        if len(self) == 5 and not self.position:  # bar 5
            self.buy(size=100)  # Market order (default exectype)

    def notify_order(self, order):
        print(f'  [{self.data.datetime.date()}] '
              f'ref={order.ref} {order.getstatusname()} '
              f'price={order.executed.price:.2f}')
```

Trace (assuming `checksubmit=True`):

```
Bar 5: close=50.00
═══════════════════
  Strategy.next():
    self.buy(size=100)
      │
      └── BuyOrder created:
            ref=1, status=Created, exectype=Market
            created.price=50.00, created.pclose=50.00
            executed.remsize=100

      └── broker.submit(order) → broker.transmit(order)
            order.submit()       → status=Submitted
            submitted.append(order)
            orders.append(order)
            notify(order)        → notifs: [Order(ref=1, Submitted)]

  Cerebro._brokernotify():
    order = broker.get_notification()  → Order(ref=1, Submitted)
    strategy._addnotification(order)
    strategy.notify_order(order)
    >>> [2006-01-05] ref=1 Submitted price=0.00

Bar 6: open=50.20, high=51.00, low=49.80, close=50.50
══════════════════════════════════════════════════════
  BackBroker.next():

    STEP 2: check_submitted()
      order ref=1 (Market, size=100)
      pseudo-execute: cash = 10000 - (100 * 50.00) = 5000 ← cash >= 0 ✓
      submit_accept(order)
        order.accept()           → status=Accepted
        pending.append(order)
        notify(order)            → notifs: [Order(ref=1, Accepted)]

    STEP 5: process pending
      order ref=1: active=True, not expired
      _try_exec(order):
        popen=50.20, phigh=51.00, plow=49.80
        exectype=Market → _try_exec_market(order, 50.20, 51.00, 49.80)
          │
          │   coc=False, coo=False
          │   data.datetime[0] > order.created.dt?  YES (bar 6 > bar 5)
          │   exprice = popen = 50.20          # execute at next bar's open
          │   order.isbuy() → _slip_up(51.00, 50.20, doslip=False)
          │   → price = 50.20 (no slippage configured)
          │
          └── _execute(order, ago=0, price=50.20)
                │   size = 100 (full, no filler)
                │   position.update(100, 50.20) → opened=100
                │   openedvalue = 100 * 50.20 = $5,020.00
                │   openedcomm = 100 * 0.001 * 50.20 = $5.02 (if 0.1% comm)
                │   cash: 10000 - 5020 - 5.02 = $4,974.98
                │
                │   order.execute(dt, 100, 50.20, closed=0, opened=100, ...)
                │   → executed.remsize = 100 - 100 = 0
                │   → status = Completed         # ← set inside Order.execute()
                │
                └── notify(order)  → notifs: [Order(ref=1, Completed)]

      order.alive()? NO (Completed) → _bracketize(order) → no-op (no bracket)

  Cerebro._brokernotify():
    notification 1: Order(ref=1, Accepted)
      strategy._addnotification(order)
      >>> [2006-01-06] ref=1 Accepted price=0.00

    notification 2: Order(ref=1, Completed)
      strategy._addnotification(order)
        # Create Trade: Trade(data, tradeid=0)
        # trade.update(order, opened=100, price=50.20, ...)
      >>> [2006-01-06] ref=1 Completed price=50.20

  Final state:
    cash=$4,974.98, position=100 shares @ 50.20
    orders=[Order(ref=1, Completed)]
    pending=deque([])  ← empty, order is done
```

#### Example 2: Limit Order — Multiple Bars Before Fill

```python
class LimitExample(bt.Strategy):
    def next(self):
        if len(self) == 3 and not self.position:
            # Want to buy at 48.00 or lower
            self.buy(size=50, exectype=bt.Order.Limit, price=48.00)
```

Trace:

```
Bar 3: close=50.00
═══════════════════
  buy(size=50, Limit, price=48.00)
    BuyOrder: ref=1, Created, Limit, price=48.00
    → Submitted → notifs: [Submitted]

Bar 4: open=50.10, high=50.80, low=49.50, close=50.30
══════════════════════════════════════════════════════
  check_submitted():
    pseudo cash = 10000 - (50 * 48.00) = 7600 ≥ 0 ✓
    → Accepted, into pending
    → notifs: [Accepted]

  _try_exec(order):
    _try_exec_limit(order, popen=50.10, phigh=50.80, plow=49.50, plimit=48.00)
      isbuy, plimit=48.00:
        plimit(48) < popen(50.10)?  YES → check plow
        plimit(48) >= plow(49.50)?  NO  → 48 < 49.50, price never reached
      → NO FILL

  order.alive()? YES → back in pending

Bar 5: open=49.80, high=50.20, low=49.00, close=49.50
══════════════════════════════════════════════════════
  _try_exec_limit(order, popen=49.80, phigh=50.20, plow=49.00, plimit=48.00)
    plimit(48) < popen(49.80)? YES
    plimit(48) >= plow(49.00)? NO → 48 < 49.00
    → NO FILL (low didn't reach 48)

Bar 6: open=49.20, high=49.50, low=47.50, close=48.80
══════════════════════════════════════════════════════
  _try_exec_limit(order, popen=49.20, phigh=49.50, plow=47.50, plimit=48.00)
    plimit(48) < popen(49.20)? YES
    plimit(48) >= plow(47.50)? YES → MATCH at limit price!
    → _execute(order, ago=0, price=48.00)
      executed.price=48.00, remsize=0 → Completed
    → notifs: [Completed]

  Result: bought 50 shares at $48.00 (3 bars after placement)
```

#### Example 3: Stop Order — Triggered by Price Breakthrough

```python
class StopExample(bt.Strategy):
    def next(self):
        if self.position.size == 100:
            # Protective stop-loss at 45.00
            self.sell(size=100, exectype=bt.Order.Stop, price=45.00)
```

Trace:

```
Bar N: position=100 @ 50.00, stop sell created at 45.00
═══════════════════════════════════════════════════════
  SellOrder: ref=2, Created, Stop, price=45.00, size=-100
  → Submitted → Accepted → pending

Bar N+1: open=48.50, high=49.00, low=47.80, close=48.20
════════════════════════════════════════════════════════
  _try_exec_stop(order, popen=48.50, phigh=49.00, plow=47.80, pcreated=45.00)
    issell():
      popen(48.50) <= pcreated(45.00)?  NO (not a gap down through stop)
      plow(47.80) <= pcreated(45.00)?   NO (low didn't reach stop)
    → NO TRIGGER

Bar N+2: open=46.00, high=46.50, low=44.20, close=45.50
════════════════════════════════════════════════════════
  _try_exec_stop(order, popen=46.00, phigh=46.50, plow=44.20, pcreated=45.00)
    issell():
      popen(46.00) <= pcreated(45.00)?  NO
      plow(44.20) <= pcreated(45.00)?   YES → triggered intraday!
      p = _slip_down(plow=44.20, pcreated=45.00)
        slip_perc=0, slip_fixed=0 → return 45.00 (no slippage)
      → _execute(order, ago=0, price=45.00)
        closed=100, pnl = -100 * (50.00 - 45.00) * 1.0 = -$500
        → Completed
        → notifs: [Completed]

  Result: sold 100 shares at $45.00, loss = -$500
```

#### Example 4: Expired Order

```python
class ExpiryExample(bt.Strategy):
    def next(self):
        if len(self) == 1:
            # Limit order valid for 3 days
            self.buy(size=100, exectype=bt.Order.Limit, price=45.00,
                     valid=datetime.timedelta(days=3))
```

Trace:

```
Bar 1 (Jan 2): create order, valid until Jan 5
═══════════════════════════════════════════════
  BuyOrder: ref=1, Limit, price=45.00
  order.valid = date2num(Jan 5, 23:59:59)
  → Submitted → Accepted → pending

Bar 2 (Jan 3): low=47.50 → no fill (47.50 > 45.00)
Bar 3 (Jan 4): low=46.80 → no fill (46.80 > 45.00)

Bar 4 (Jan 5): low=46.00
══════════════════════════
  order.expire():
    exectype is Limit (not Market)
    data.datetime[0] > order.valid?
    Jan 5 market close > Jan 5 23:59:59?  NO (same day)
  → not expired yet, try execution
  _try_exec_limit: low=46.00 > 45.00 → NO FILL

Bar 5 (Jan 6): open=46.50
══════════════════════════
  order.expire():
    data.datetime[0] > order.valid?
    Jan 6 > Jan 5 23:59:59?  YES!
  → order.status = Expired                  # ← STATUS: Expired
  → self.notify(order)
  → notifs: [Expired]

  Strategy.notify_order(order):
    >>> ref=1 Expired — limit price 45.00 never reached
```

#### Example 5: Partial Fill with Volume Filler

```python
def quarter_filler(order, price, ago):
    """Fill up to 25% of bar volume."""
    volume = order.data.volume[ago]
    return min(int(volume * 0.25), order.executed.remsize)

cerebro.broker.set_filler(quarter_filler)
# Buy 1000 shares as Market order
```

Trace:

```
Bar N: order created, Market buy, size=1000
═══════════════════════════════════════════
  → Submitted → Accepted → pending

Bar N+1: open=50.00, volume=800
════════════════════════════════
  _try_exec_market: exprice = popen = 50.00
  _execute(order, ago=0, price=50.00):
    filler(order, 50.00, 0) → min(800*0.25, 1000) = 200
    size = 200
    order.execute(dt, 200, 50.00, opened=200, ...)
    executed.remsize = 1000 - 200 = 800
    → status = Partial                       # ← STATUS: Partial
    → notify(order)

  order.alive()? YES (Partial) → back in pending

Bar N+2: open=50.20, volume=1600
═════════════════════════════════
  _execute(order, ago=0, price=50.20):
    filler → min(1600*0.25, 800) = 400
    order.execute(dt, 400, 50.20, opened=400, ...)
    executed.remsize = 800 - 400 = 400
    → Partial → notify

Bar N+3: open=50.10, volume=2000
═════════════════════════════════
  _execute(order, ago=0, price=50.10):
    filler → min(2000*0.25, 400) = 400
    order.execute(dt, 400, 50.10, opened=400, ...)
    executed.remsize = 400 - 400 = 0
    → Completed                              # ← STATUS: Completed
    → notify

  Result: filled across 3 bars:
    200 @ 50.00 + 400 @ 50.20 + 400 @ 50.10
    Average price: (200*50 + 400*50.2 + 400*50.1) / 1000 = 50.12
    Commission: 3 separate fills each charged commission
```

#### Example 6: Order Rejected for Insufficient Cash

```python
cerebro.broker.setcash(1000)  # only $1,000
# Try to buy 100 shares at ~$50
self.buy(size=100)  # would cost ~$5,000
```

Trace:

```
Bar N: create Market order for 100 shares
════════════════════════════════════════════
  → Submitted → submitted queue

Bar N+1:
══════════
  check_submitted():
    pseudo-execute: cash = 1000 - (100 * 50.00) = -$4,000
    cash < 0!
    → order.margin()                         # ← STATUS: Margin
    → self.notify(order)
    → _bracketize(order, cancel=True)        # cancel any bracket siblings

  Strategy.notify_order(order):
    >>> ref=1 Margin — not enough cash for 100 shares!

  The order never enters the pending queue.
```

#### Example 7: Full Round-Trip with notify_order and notify_trade

```python
class FullExample(bt.Strategy):
    def __init__(self):
        self.sma = bt.ind.SMA(period=10)
        self.order = None

    def next(self):
        if self.order:
            return  # wait for pending order

        if not self.position:
            if self.data.close[0] > self.sma[0]:
                self.order = self.buy(size=100)
        else:
            if self.data.close[0] < self.sma[0]:
                self.order = self.sell(size=100)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return  # wait for terminal status

        if order.status == order.Completed:
            if order.isbuy():
                print(f'BUY  executed: price={order.executed.price:.2f}, '
                      f'cost={order.executed.value:.2f}, '
                      f'comm={order.executed.comm:.2f}')
            else:
                print(f'SELL executed: price={order.executed.price:.2f}, '
                      f'cost={order.executed.value:.2f}, '
                      f'comm={order.executed.comm:.2f}')

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f'Order {order.ref} FAILED: {order.getstatusname()}')

        self.order = None  # clear, allow new orders

    def notify_trade(self, trade):
        if trade.isclosed:
            print(f'TRADE closed: PnL gross={trade.pnl:.2f}, '
                  f'net={trade.pnlcomm:.2f}')
```

Notification sequence for a complete buy→sell cycle:

```
notify_order: ref=1 Submitted            ← order sent to broker
notify_order: ref=1 Accepted             ← passed cash check
notify_order: ref=1 Completed            ← filled at open
  → BUY executed: price=50.20, cost=5020.00, comm=5.02
notify_trade: TRADE opened: size=100     ← trade created (justopened)

... several bars later ...

notify_order: ref=2 Submitted
notify_order: ref=2 Accepted
notify_order: ref=2 Completed            ← sell filled
  → SELL executed: price=55.00, cost=5500.00, comm=5.50
notify_trade: TRADE closed: PnL gross=480.00, net=469.48
  (gross = (55.00 - 50.20) * 100 = $480, net = 480 - 5.02 - 5.50 = $469.48)
```

#### Summary: The `executed` Object After Fill

After an order completes, `order.executed` contains the accumulated fill data:

```python
order.executed.dt          # datetime of last fill (float)
order.executed.size        # total filled size (accumulated)
order.executed.price       # volume-weighted average fill price
order.executed.value       # total market value of fills
order.executed.comm        # total commission paid
order.executed.pnl         # total PnL from closed portions
order.executed.remsize     # remaining unfilled (0 if Completed)
order.executed.psize       # current position size after fill
order.executed.pprice      # current position average price after fill

# Individual fills (for partial fills):
for exbit in order.executed.exbits:
    print(f'Fill: {exbit.size} @ {exbit.price}, '
          f'opened={exbit.opened}, closed={exbit.closed}, '
          f'pnl={exbit.pnl:.2f}')
```

### Order Execution Methods

#### `_try_exec_market` — Market Orders

```python
def _try_exec_market(self, order, popen, phigh, plow):
    if self.p.coc:                        # Cheat-On-Close
        exprice = order.created.pclose    # execute at bar's close
        dtcoc = order.created.dt
    else:
        if order.data.datetime[0] <= order.created.dt:
            return                        # can only execute AFTER creation bar
        exprice = popen                   # execute at next bar's open

    if order.isbuy():
        p = self._slip_up(phigh, exprice, doslip=self.p.slip_open)
    else:
        p = self._slip_down(plow, exprice, doslip=self.p.slip_open)

    self._execute(order, ago=0, price=p, dtcoc=dtcoc)
```

**Example:**

```python
class MyStrat(bt.Strategy):
    def next(self):
        if some_condition:
            self.buy()   # Market order

# Bar N (order created):
#   close = 100.00
#   order.created.dt = bar_N datetime
#   order.created.pclose = 100.00

# Bar N+1 (order executed):
#   open = 100.50, high = 101.00, low = 99.80
#   _try_exec_market: exprice = 100.50 (open)
#   slip_up(101.00, 100.50) → 100.50 (no slippage configured)
#   _execute(price=100.50) → order filled at 100.50

# With coc=True (Cheat-On-Close):
#   Executes on same bar N at close price 100.00
```

#### `_try_exec_limit` — Limit Orders

```python
def _try_exec_limit(self, order, popen, phigh, plow, plimit):
    if order.isbuy():
        if plimit >= popen:
            # Open is at or below limit → buy at open (better price)
            p = self._slip_up(min(phigh, plimit), popen, ...)
            self._execute(order, ago=0, price=p)
        elif plimit >= plow:
            # Limit price was touched during session → fill at limit
            self._execute(order, ago=0, price=plimit)
    else:  # Sell
        if plimit <= popen:
            # Open is at or above limit → sell at open (better price)
            p = self._slip_down(max(plow, plimit), popen, ...)
            self._execute(order, ago=0, price=p)
        elif plimit <= phigh:
            # Limit price was touched during session → fill at limit
            self._execute(order, ago=0, price=plimit)
```

**Example:**

```python
# Buy Limit at 99.00
self.buy(exectype=bt.Order.Limit, price=99.00)

# Next bar: open=100, high=101, low=98.50, close=99.80
# plimit=99.00, plow=98.50
# plimit(99) < popen(100), but plimit(99) >= plow(98.50)
# → Execute at limit price 99.00 (touched during the day)
```

#### `_try_exec_stop` — Stop Orders

```python
def _try_exec_stop(self, order, popen, phigh, plow, pcreated, pclose):
    if order.isbuy():
        if popen >= pcreated:
            # Gap up through stop → execute at open
            p = self._slip_up(phigh, popen, ...)
            self._execute(order, ago=0, price=p)
        elif phigh >= pcreated:
            # Stop triggered intraday → execute at stop price
            p = self._slip_up(phigh, pcreated)
            self._execute(order, ago=0, price=p)
    # (mirror logic for sell)

    # Trailing stop adjustment
    if order.alive() and order.exectype == Order.StopTrail:
        order.trailadjust(pclose)
```

**Example:**

```python
# Sell Stop at 95.00 (stop-loss)
self.sell(exectype=bt.Order.Stop, price=95.00)

# Next bar: open=96, high=97, low=94.50, close=95.20
# pcreated=95.00, plow=94.50
# popen(96) > pcreated(95) → not gap down
# plow(94.50) <= pcreated(95.00) → triggered intraday
# → Execute at 95.00 (stop price)
```

#### `_try_exec_stoplimit` — StopLimit Orders

A two-stage order: first the stop price must be reached (triggering the order),
then it becomes a limit order.

```python
def _try_exec_stoplimit(self, order, popen, phigh, plow, pclose,
                        pcreated, plimit):
    if order.isbuy():
        if popen >= pcreated:
            order.triggered = True
            self._try_exec_limit(order, popen, phigh, plow, plimit)
        elif phigh >= pcreated:
            order.triggered = True
            # try limit execution for specific price scenarios
    # (mirror for sell)
```

#### `_try_exec_close` — Close Orders

Executes at the session's closing price. Tracks end-of-session with `pannotated`.

### Slippage System

```python
def _slip_up(self, pmax, price, doslip=True, lim=False):
    '''Slip price UP for buy orders'''
    if not doslip:
        return price

    if self.p.slip_perc:
        pslip = price * (1 + self.p.slip_perc)     # e.g. 100 * 1.01 = 101
    elif self.p.slip_fixed:
        pslip = price + self.p.slip_fixed           # e.g. 100 + 0.05 = 100.05
    else:
        return price

    if pslip <= pmax:                 # slipped price within bar range
        return pslip
    elif self.p.slip_match or (lim and self.p.slip_limit):
        if not self.p.slip_out:
            return pmax               # cap at high
        return pslip                  # allow out-of-range
    return None                       # no execution possible

def _slip_down(self, pmin, price, doslip=True, lim=False):
    '''Slip price DOWN for sell orders (mirror of _slip_up)'''
    # ... symmetric logic ...
```

**Example:**

```python
# Configure 0.1% slippage:
cerebro.broker.set_slippage_perc(0.001, slip_open=True)

# Market buy order, next bar open = 100.00:
# _slip_up: pslip = 100.00 * 1.001 = 100.10
# pmax (high) = 101.50
# 100.10 <= 101.50 → execute at 100.10

# Configure fixed 5-cent slippage:
cerebro.broker.set_slippage_fixed(0.05, slip_open=True)

# Market buy, open = 100.00:
# _slip_up: pslip = 100.00 + 0.05 = 100.05
# → execute at 100.05
```

### The `_execute` Method — Core Accounting

Handles all cash/position updates, commission calculation, and PnL tracking.

```python
def _execute(self, order, ago=None, price=None, cash=None, position=None,
             dtcoc=None):
    # ago=None → pseudo-execution (cash check only)
    # ago=0   → real execution

    # 1. Determine execution size (full or partial via filler)
    size = order.executed.remsize  # or filler(order, price, ago)

    # 2. Get commission scheme
    comminfo = self.getcommissioninfo(order.data)

    # 3. Update position
    psize, pprice, opened, closed = position.update(size, price)

    # 4. Handle closed portion (profit/loss)
    if closed:
        pnl = comminfo.profitandloss(-closed, pprice_orig, price)
        closedvalue = comminfo.getvaluesize(-closed, pprice_orig)
        closedcomm = comminfo.getcommission(closed, price)
        self.cash += closedvalue/leverage + pnl - closedcomm

    # 5. Handle opened portion (new position cost)
    if opened:
        openedvalue = comminfo.getvaluesize(opened, price)
        openedcomm = comminfo.getcommission(opened, price)
        self.cash -= openedvalue/leverage + openedcomm

    # 6. Record execution on order object
    order.execute(dt, execsize, price,
                  closed, closedvalue, closedcomm,
                  opened, openedvalue, openedcomm,
                  margin, pnl, psize, pprice)

    # 7. Notify strategy
    self.notify(order)
    self._ococheck(order)
```

### Bracket Orders — Deep Dive

A bracket order is a **group of three linked orders**: a parent (entry) plus two
children (stop-loss and take-profit). The children remain **inactive** until the
parent fills. When either child fills, the other is **automatically cancelled**.

#### The Three Orders

```
buy_bracket:
    ┌─────────────────────────────────────────────────────┐
    │  Parent:     BUY  Limit  @ 100.00   (entry)        │
    │  Stop side:  SELL Stop   @ 95.00    (stop-loss)     │
    │  Limit side: SELL Limit  @ 110.00   (take-profit)   │
    └─────────────────────────────────────────────────────┘

sell_bracket (short selling):
    ┌─────────────────────────────────────────────────────┐
    │  Parent:     SELL Limit  @ 100.00   (entry)         │
    │  Stop side:  BUY  Stop   @ 105.00   (stop-loss)     │
    │  Limit side: BUY  Limit  @ 90.00    (take-profit)   │
    └─────────────────────────────────────────────────────┘
```

#### Key Concepts

1. **`transmit` parameter** — Controls when orders are sent to the broker:
   - `transmit=False`: order is staged but NOT submitted yet
   - `transmit=True`: submits this order AND all previously staged siblings

2. **`parent` parameter** — Links a child order to its parent:
   - `parent=None`: this IS the parent (top-level order)
   - `parent=order`: this is a child of that order

3. **`_active` flag on Order** — Controls whether an order can be executed:
   - `self._active = (self.parent is None)` — set at Order creation
   - Parent orders: `_active=True` (can execute immediately)
   - Child orders: `_active=False` (must wait for parent fill)
   - `activate()` sets `_active=True`

#### How `Strategy.buy_bracket()` Creates the Three Orders

```python
def buy_bracket(self, data=None, size=None, price=None, plimit=None,
                exectype=bt.Order.Limit, valid=None,
                stopprice=None, stopexec=bt.Order.Stop,
                limitprice=None, limitexec=bt.Order.Limit, **kwargs):

    # ─── Step 1: Create PARENT order ───
    kargs['transmit'] = False       # ← DO NOT transmit yet!
    o = self.buy(**kargs)
    # o.parent = None → o._active = True
    # o.transmit = False
    # → broker.submit(o) → _pchildren[o.ref].append(o), but NOT transmitted

    # ─── Step 2: Create STOP SIDE (stop-loss) ───
    kargs['parent'] = o             # ← link to parent
    kargs['transmit'] = False       # ← still not transmitting
    kargs['size'] = o.size          # ← same size as parent
    ostop = self.sell(**kargs)
    # ostop.parent = o → ostop._active = False  (inactive!)
    # → broker.submit(ostop) → _pchildren[o.ref].append(ostop), NOT transmitted

    # ─── Step 3: Create LIMIT SIDE (take-profit) ───
    kargs['parent'] = o             # ← link to parent
    kargs['transmit'] = True        # ← NOW transmit ALL THREE!
    kargs['size'] = o.size          # ← same size as parent
    olimit = self.sell(**kargs)
    # olimit.parent = o → olimit._active = False  (inactive!)
    # → broker.submit(olimit) → _pchildren[o.ref].append(olimit)
    #   transmit=True triggers: transmit ALL orders in _pchildren[o.ref]

    return [o, ostop, olimit]
```

#### Broker-Side: `submit()` and `_take_children()`

```python
def submit(self, order, check=True):
    # Step A: Validate parent-child relationship
    pref = self._take_children(order)
    # pref = parent's ref (or self if this IS the parent)
    # If child's parent was already rejected → reject child too

    # Step B: Stage the order
    pc = self._pchildren[pref]
    pc.append(order)
    # _pchildren[parent_ref] = deque([parent, stop, limit])

    # Step C: If transmit=True, submit ALL staged orders at once
    if order.transmit:
        rets = [self.transmit(x, check=check) for x in pc]
        return rets[-1]
    # If transmit=False, just return — order is staged but not sent

    return order
```

After `transmit=True` fires, the state is:

```
_pchildren = {
    ref_1: deque([parent_order, stop_order, limit_order])
    #  ref_1 = parent's order.ref
}

pending = deque([parent_order, stop_order, limit_order])
#  All three are in the pending queue

parent_order._active = True     ← CAN be executed
stop_order._active   = False    ← CANNOT be executed yet
limit_order._active  = False    ← CANNOT be executed yet
```

#### Runtime: How `broker.next()` Processes Bracket Orders

```python
def next(self):
    # ─── Phase 0: Activate children from PREVIOUS cycle ───
    while self._toactivate:
        self._toactivate.popleft().activate()
        # Sets _active = True on children whose parent just filled

    # ... check_submitted, interest ...

    # ─── Phase 1: Process pending orders ───
    self.pending.append(None)   # sentinel
    while True:
        order = self.pending.popleft()
        if order is None: break

        if order.expire():
            self.notify(order)
            self._bracketize(order, cancel=True)  # cancel siblings too!

        elif not order.active():
            self.pending.append(order)  # ← children put BACK, wait for parent
            # This is where stop/limit children sit until parent fills

        else:
            self._try_exec(order)       # ← parent (or activated child) executed
            if order.alive():
                self.pending.append(order)
            elif order.status == Order.Completed:
                self._bracketize(order)  # ← handle bracket consequences
```

#### The Core: `_bracketize()` — What Happens After a Fill

```python
def _bracketize(self, order, cancel=False):
    oref = order.ref
    pref = getattr(order.parent, 'ref', oref)  # find parent ref
    parent = (oref == pref)                     # am I the parent?

    pc = self._pchildren[pref]                  # the family: [parent, stop, limit]

    if cancel or not parent:
        # ─── CASE 1: Cancel everything ───
        # Either: explicit cancel (margin, expiry)
        # Or: a CHILD filled → cancel the OTHER child
        while pc:
            self.cancel(pc.popleft(), bracket=True)
        del self._pchildren[pref]

    else:
        # ─── CASE 2: PARENT filled → activate children ───
        pc.popleft()                    # remove parent from family
        for o in pc:                    # [stop, limit]
            self._toactivate.append(o)  # schedule activation for NEXT cycle
        # Children stay in _pchildren for later bracketize calls
```

#### Complete Lifecycle Trace

```
═══════════════════════════════════════════════════════════════════
  BRACKET ORDER LIFECYCLE: buy_bracket(price=100, stop=95, limit=110)
═══════════════════════════════════════════════════════════════════

Bar 0: Strategy calls buy_bracket
─────────────────────────────────
  Strategy.buy_bracket(price=100, stopprice=95, limitprice=110, size=100)
    │
    ├── self.buy(price=100, exectype=Limit, transmit=False)
    │   └── broker.submit(parent_order)
    │       └── _pchildren[ref=1] = deque([parent(ref=1)])
    │       └── transmit=False → order staged, not sent
    │       └── Return parent_order
    │
    ├── self.sell(price=95, exectype=Stop, parent=parent, transmit=False)
    │   └── broker.submit(stop_order)
    │       └── _pchildren[ref=1] = deque([parent(1), stop(2)])
    │       └── transmit=False → staged
    │       └── Return stop_order
    │
    └── self.sell(price=110, exectype=Limit, parent=parent, transmit=True)
        └── broker.submit(limit_order)
            └── _pchildren[ref=1] = deque([parent(1), stop(2), limit(3)])
            └── transmit=True → SUBMIT ALL THREE:
                  broker.transmit(parent_order)  → Submitted → Accepted → pending
                  broker.transmit(stop_order)    → Submitted → Accepted → pending
                  broker.transmit(limit_order)   → Submitted → Accepted → pending

  State: pending = [parent(1,active), stop(2,inactive), limit(3,inactive)]
  Strategy receives: notify_order(parent, Submitted)
                     notify_order(parent, Accepted)
                     notify_order(stop, Submitted)
                     notify_order(stop, Accepted)
                     notify_order(limit, Submitted)
                     notify_order(limit, Accepted)

Bar 1-4: Waiting for parent fill
────────────────────────────────
  broker.next():
    for each order in pending:
      parent_order: active=True → _try_exec_limit(price=100)
        → price hasn't reached 100 yet → not filled → back in pending
      stop_order: active=False → put back in pending (skipped)
      limit_order: active=False → put back in pending (skipped)

Bar 5: Parent fills at 100
──────────────────────────
  broker.next():
    parent_order: active=True → _try_exec_limit(price=100)
      → popen=99.50, plow=99.20: plimit(100) >= popen(99.50)
      → Execute at open price 99.50 (better than limit!)
      → order.status = Completed
      → _bracketize(parent_order, cancel=False)
          │ parent=True → activate children:
          │ pc.popleft()              → remove parent from deque
          │ _toactivate.append(stop)  → schedule stop for activation
          │ _toactivate.append(limit) → schedule limit for activation
          │ _pchildren[1] = deque([stop(2), limit(3)])  (children remain)
      → notify_order(parent, Completed)

    stop_order: active=False → put back in pending
    limit_order: active=False → put back in pending

Bar 6+: Children now active, racing each other
───────────────────────────────────────────────
  broker.next():
    # Phase 0: activate children
    _toactivate: [stop(2), limit(3)]
      stop_order.activate()   → _active = True
      limit_order.activate()  → _active = True

    for each order in pending:
      stop_order:  active=True → _try_exec_stop(price=95)
        → phigh=102, plow=97: not triggered (plow=97 > 95)
        → back in pending
      limit_order: active=True → _try_exec_limit(price=110)
        → phigh=102: not triggered (102 < 110)
        → back in pending

═══ Scenario A: Price rises to 110 (take-profit) ═══

Bar 12: limit_order fills at 110
  broker.next():
    limit_order: _try_exec_limit(price=110)
      → phigh=111, plimit=110: touched → Execute at 110
      → order.status = Completed
      → _bracketize(limit_order, cancel=False)
          │ parent=False (limit is a child) → CANCEL everything:
          │ while pc:
          │     cancel(stop_order)  → stop_order.status = Cancelled
          │     cancel(limit_order) → already completed, idempotent
          │ del _pchildren[1]
      → notify_order(limit, Completed)
      → notify_order(stop, Cancelled)

  Result: Bought at 99.50, sold at 110.00
          Profit: (110 - 99.50) × 100 = $1,050

═══ Scenario B: Price drops to 95 (stop-loss) ═══

Bar 8: stop_order fills at 95
  broker.next():
    stop_order: _try_exec_stop(price=95)
      → plow=94.80, pcreated=95: plow <= pcreated → triggered
      → Execute at 95
      → order.status = Completed
      → _bracketize(stop_order, cancel=False)
          │ parent=False (stop is a child) → CANCEL everything:
          │ while pc:
          │     cancel(stop_order)  → already completed, idempotent
          │     cancel(limit_order) → limit_order.status = Cancelled
          │ del _pchildren[1]
      → notify_order(stop, Completed)
      → notify_order(limit, Cancelled)

  Result: Bought at 99.50, sold at 95.00
          Loss: (95 - 99.50) × 100 = -$450

═══ Scenario C: Parent gets margin rejected ═══

Bar 1: parent fails cash check
  broker.check_submitted():
    cash = self._execute(parent, cash=cash, position=pos)  # pseudo
    cash < 0 → insufficient funds!
      parent_order.margin()    → status = Margin
      _bracketize(parent, cancel=True)
          │ cancel=True → CANCEL ALL:
          │ cancel(parent) → idempotent (already Margin)
          │ cancel(stop)   → Cancelled
          │ cancel(limit)  → Cancelled
      → notify_order(parent, Margin)
      → notify_order(stop, Cancelled)
      → notify_order(limit, Cancelled)

═══ Scenario D: Parent expires before filling ═══

Bar 10: parent order expires (valid=date passed)
  broker.next():
    parent_order.expire() → True
      → status = Expired
      → _bracketize(parent, cancel=True)
          │ cancel=True → CANCEL ALL children
      → notify_order(parent, Expired)
      → notify_order(stop, Cancelled)
      → notify_order(limit, Cancelled)
```

#### Data Structures

```python
# _pchildren: tracks which orders belong together
# Key = parent order ref, Value = deque of all orders in the family
self._pchildren = collections.defaultdict(collections.deque)
# Example:
# {
#     1: deque([Order(ref=1, parent), Order(ref=2, stop), Order(ref=3, limit)]),
#     4: deque([Order(ref=4, parent), Order(ref=5, stop), Order(ref=6, limit)]),
# }

# _toactivate: children scheduled for activation next cycle
self._toactivate = collections.deque()
# Populated by _bracketize when parent fills
# Drained at the START of broker.next()
```

Why activate in the **next** cycle (not immediately)?
Because the parent just filled in the current bar's execution loop. Activating
children in the same loop could cause them to be evaluated against the same
bar's prices — which would be incorrect. By deferring to `_toactivate`, children
become active at the start of the next `broker.next()` call, ensuring they see
fresh prices.

#### Strategy-Side: Working with Bracket Orders

```python
class BracketExample(bt.Strategy):
    params = (
        ('stop_pct', 0.05),      # 5% stop-loss
        ('take_pct', 0.10),      # 10% take-profit
    )

    def __init__(self):
        self.bracket_orders = None

    def next(self):
        if not self.position and self.bracket_orders is None:
            close = self.data.close[0]
            self.bracket_orders = self.buy_bracket(
                size=100,
                price=close,                             # entry
                stopprice=close * (1 - self.p.stop_pct), # stop-loss
                limitprice=close * (1 + self.p.take_pct),# take-profit
                exectype=bt.Order.Limit,
            )
            # bracket_orders = [parent, stop, limit]
            print(f'Bracket placed: entry={close:.2f}, '
                  f'stop={close*0.95:.2f}, take={close*1.10:.2f}')

    def notify_order(self, order):
        if order.status == order.Completed:
            if order.ref == self.bracket_orders[0].ref:
                print(f'ENTRY filled at {order.executed.price:.2f}')
            elif order.ref == self.bracket_orders[1].ref:
                print(f'STOP-LOSS hit at {order.executed.price:.2f}')
                self.bracket_orders = None   # bracket done
            elif order.ref == self.bracket_orders[2].ref:
                print(f'TAKE-PROFIT hit at {order.executed.price:.2f}')
                self.bracket_orders = None   # bracket done

        elif order.status in [order.Cancelled, order.Margin, order.Expired]:
            if order.ref == self.bracket_orders[0].ref:
                print(f'Entry failed: {order.getstatusname()}')
                self.bracket_orders = None   # bracket dead
            # Children cancellation is automatic — just clean up
```

#### Manual Bracket Construction (Without `buy_bracket`)

You can construct brackets manually using `transmit` and `parent`:

```python
def next(self):
    if not self.position:
        # Step 1: Parent — DO NOT transmit
        main = self.buy(
            size=100,
            exectype=bt.Order.Limit,
            price=100.00,
            transmit=False,       # ← staged, not sent
        )

        # Step 2: Stop-loss child — DO NOT transmit
        stop = self.sell(
            size=100,
            exectype=bt.Order.Stop,
            price=95.00,
            parent=main,          # ← linked to parent
            transmit=False,       # ← staged
        )

        # Step 3: Take-profit child — TRANSMIT (sends all three!)
        take = self.sell(
            size=100,
            exectype=bt.Order.Limit,
            price=110.00,
            parent=main,          # ← linked to parent
            transmit=True,        # ← sends main + stop + take
        )

        # Equivalent to:
        # self.buy_bracket(price=100, stopprice=95, limitprice=110, size=100)
```

#### Sell Bracket (Short Selling)

```python
# Short bracket: sell entry, buy-stop above (stop-loss), buy-limit below (profit)
orders = self.sell_bracket(
    size=100,
    price=100.00,              # entry: sell at 100
    stopprice=105.00,          # stop-loss: buy back at 105 if price rises
    limitprice=90.00,          # take-profit: buy back at 90 if price drops
)
# Returns: [sell_parent, buy_stop(105), buy_limit(90)]

# Profit scenario: price drops to 90
#   Sold at 100, covered at 90 → profit = (100-90) × 100 = $1,000
# Loss scenario: price rises to 105
#   Sold at 100, covered at 105 → loss = (100-105) × 100 = -$500
```

#### Partial Bracket (Suppress One Side)

```python
# Only stop-loss, no take-profit:
orders = self.buy_bracket(
    price=100, stopprice=95,
    limitexec=None,            # suppress the high side
)
# Returns: [parent, stop, None]

# Only take-profit, no stop-loss:
orders = self.buy_bracket(
    price=100, limitprice=110,
    stopexec=None,             # suppress the low side
)
# Returns: [parent, None, limit]
```

#### Trailing Stop in a Bracket

```python
orders = self.buy_bracket(
    size=100,
    price=100.00,
    # Low side: trailing stop instead of fixed stop
    stopprice=95.00,
    stopexec=bt.Order.StopTrail,
    stopargs=dict(trailamount=5.0),    # trail by $5
    # High side: fixed take-profit
    limitprice=115.00,
)
# The stop follows the price up:
# Price goes 100 → 108 → stop adjusts from 95 to 103
# Price drops 108 → 103 → stop triggered at 103
```

### OCO (One-Cancels-Other) Orders

```python
# Place two orders linked as OCO:
o1 = self.buy(exectype=bt.Order.Limit, price=95.0)
o2 = self.sell(exectype=bt.Order.Stop, price=90.0, oco=o1)
# If o1 fills, o2 is automatically cancelled (and vice versa)

# Internal:
# _ocoize(o1, oco=None) → o1 is the group leader
# _ocoize(o2, oco=o1)   → o2 joins o1's group
# When either executes → _ococheck cancels all others in the group
```

### Cash/Value Tracking

```python
# Get current state:
cash = cerebro.broker.getcash()           # current cash
value = cerebro.broker.getvalue()         # cash + position value
position = cerebro.broker.getposition(data)  # Position object for data

# In a strategy:
class MyStrat(bt.Strategy):
    def next(self):
        print(f'Cash: {self.broker.getcash():.2f}')
        print(f'Value: {self.broker.getvalue():.2f}')
        print(f'Position: {self.getposition(self.data).size}')
```

### Complete Example: BackBroker Configuration

```python
cerebro = bt.Cerebro()

# Set starting cash
cerebro.broker.setcash(100000)

# Set commission: 0.1% per trade for stocks
cerebro.broker.setcommission(
    commission=0.001,    # 0.1%
    stocklike=True,
)

# Set commission for futures
cerebro.broker.setcommission(
    commission=2.0,      # $2 per contract
    margin=5000.0,       # $5000 margin per contract
    mult=50.0,           # $50 per point (e.g. ES futures)
    stocklike=False,
    name='ES',
)

# Configure slippage
cerebro.broker.set_slippage_perc(
    perc=0.001,          # 0.1% slippage
    slip_open=True,      # slip on market orders using open price
    slip_match=True,     # cap slippage at bar high/low
)

# Enable Cheat-On-Close (execute at same bar's close)
cerebro.broker.set_coc(True)

# Or replace the broker entirely:
broker = bt.brokers.BackBroker(cash=50000, slip_perc=0.002)
cerebro.broker = broker
```

---

## Class: IBBroker (Interactive Brokers)

**File:** `backtrader/brokers/ibbroker.py`
**Requires:** `ibpy` library (`import ib.ext.Order`, `import ib.opt`)

A live broker adapter that routes orders to Interactive Brokers' TWS/Gateway
via the IBPy library and `IBStore`.

### Architecture

```
Strategy                     IBBroker                    IBStore/TWS
────────                     ────────                    ───────────
self.buy()  ─────────────►  buy()                       
                             │ create IBOrder             
                             │ (maps bt types → IB types)
                             └── submit(order)           
                                 │ placeOrder() ────────► TWS API
                                 │                        
                            ◄── push_orderstatus(msg) ◄── TWS callback
                            ◄── push_execution(ex)    ◄── TWS execDetails
                            ◄── push_commissionreport ◄── TWS commReport
                                 │
                                 └── order.execute()
                                     notify(order)
                            ◄── push_portupdate()     ◄── TWS updatePortfolio
```

### IBOrder — Order Type Mapping

```python
class IBOrder(OrderBase, ib.ext.Order.Order):
    _IBOrdTypes = {
        Order.Market:         'MKT',
        Order.Limit:          'LMT',
        Order.Close:          'MOC',       # Market-On-Close
        Order.Stop:           'STP',
        Order.StopLimit:      'STPLMT',
        Order.StopTrail:      'TRAIL',
        Order.StopTrailLimit: 'TRAIL LIMIT',
    }
```

### Key Methods

```python
class IBBroker(BrokerBase):
    def __init__(self, **kwargs):
        self.ib = ibstore.IBStore(**kwargs)   # connection to TWS
        self.orderbyid = dict()                # {ib_orderId: IBOrder}
        self.executions = dict()               # {execId: execution}
        self.notifs = queue.Queue()            # thread-safe notifications

    def start(self):
        self.ib.start(broker=self)
        self.ib.reqAccountUpdates()
        self.cash = self.ib.get_acc_cash()
        self.value = self.ib.get_acc_value()

    def getcash(self):
        return self.ib.get_acc_cash()           # real cash from IB

    def getvalue(self, datas=None):
        return self.ib.get_acc_value()          # real portfolio value from IB

    def getposition(self, data, clone=True):
        return self.ib.getposition(data.tradecontract, clone=clone)

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, **kwargs):
        order = IBOrder('BUY', owner=owner, data=data, size=size, ...)
        return self.submit(order)

    def submit(self, order):
        order.submit(self)
        self.orderbyid[order.m_orderId] = order
        self.ib.placeOrder(order.m_orderId, order.data.tradecontract, order)
        self.notify(order)
        return order

    def cancel(self, order):
        self.ib.cancelOrder(order.m_orderId)

    # --- Callbacks from IBStore (called from TWS event thread) ---

    def push_orderstatus(self, msg):
        '''Handles: Submitted, Filled, Cancelled, Inactive, etc.'''
        order = self.orderbyid[msg.orderId]
        if msg.status == 'Submitted' and msg.filled == 0:
            order.accept(self)
            self.notify(order)
        elif msg.status == 'Cancelled':
            order.cancel()
            self.notify(order)
        # ...

    def push_execution(self, ex):
        '''Store execution details, wait for commission report'''
        self.executions[ex.m_execId] = ex

    def push_commissionreport(self, cr):
        '''Commission report arrives last → finalize execution'''
        ex = self.executions.pop(cr.m_execId)
        order = self.orderbyid[ex.m_orderId]
        # update position, calculate PnL, call order.execute()
        self.notify(order)
```

**Example:**

```python
import backtrader as bt
from backtrader.stores import ibstore

# Connect to Interactive Brokers TWS
ibstore = bt.stores.IBStore(host='127.0.0.1', port=7497, clientId=1)

cerebro = bt.Cerebro()
cerebro.broker = bt.brokers.IBBroker()

# Get live data
data = ibstore.getdata(dataname='AAPL-STK-SMART-USD')
cerebro.adddata(data)

class LiveStrategy(bt.Strategy):
    def next(self):
        if not self.position:
            # This sends a real order to Interactive Brokers!
            self.buy(size=100)

    def notify_order(self, order):
        if order.status == order.Completed:
            print(f'IB filled at {order.executed.price:.2f}')
        elif order.status == order.Cancelled:
            print('IB cancelled the order')

cerebro.addstrategy(LiveStrategy)
cerebro.run()
```

---

## Class: OandaBroker (Oanda Forex)

**File:** `backtrader/brokers/oandabroker.py`
**Requires:** `oandapy` library

A live broker adapter for Oanda forex trading via `OandaStore`.

### Architecture

```
Strategy                     OandaBroker                 OandaStore/API
────────                     ───────────                 ──────────────
self.buy()  ─────────────►  buy()                       
                             │ create BuyOrder            
                             └── _transmit(order)        
                                 │ order_create() ──────► Oanda REST API
                                 │                        
                            ◄── _fill(oref,size,price)  ◄── streaming callback
                            ◄── _accept(oref)           ◄── order accepted
                            ◄── _cancel(oref)           ◄── order cancelled
```

### Key Features

- Supports bracket orders (parent + stop-loss + take-profit) via Oanda's native API
- Loads existing positions on startup (`use_positions=True`)
- Creates simulated `BuyOrder`/`SellOrder` notifications for pre-existing positions

### Key Methods

```python
class OandaBroker(BrokerBase):
    params = (
        ('use_positions', True),
        ('commission', OandaCommInfo(mult=1.0, stocklike=False)),
    )

    def __init__(self, **kwargs):
        self.o = oandastore.OandaStore(**kwargs)
        self.orders = collections.OrderedDict()   # {ref: Order}
        self.opending = collections.defaultdict(list)  # bracket staging
        self.brackets = dict()                     # {pref: [parent, stop, take]}
        self.positions = collections.defaultdict(Position)

    def start(self):
        self.o.start(broker=self)
        self.cash = self.o.get_cash()
        self.value = self.o.get_value()

        if self.p.use_positions:
            for p in self.o.get_positions():
                # Create Position objects from existing Oanda positions
                self.positions[p['instrument']] = Position(size, price)

    def buy(self, owner, data, size, ...):
        order = BuyOrder(owner=owner, data=data, size=size, ...)
        order.addcomminfo(self.getcommissioninfo(data))
        return self._transmit(order)

    def _transmit(self, order):
        if order.transmit:
            if order is a bracket child:
                # Bundle parent + stop + take and send together
                self.o.order_create(parent, stopside, takeside)
            else:
                self.orders[order.ref] = order
                self.o.order_create(order)
        else:
            self.opending[pref].append(order)  # stage for later

    def _fill(self, oref, size, price, ttype, **kwargs):
        '''Called by OandaStore when an order is filled'''
        order = self.orders[oref]
        pos = self.getposition(order.data, clone=False)
        pos.update(size, price)
        order.execute(data.datetime[0], size, price, ...)
        if order.executed.remsize:
            order.partial()
        else:
            order.completed()
            self._bracketize(order)   # handle bracket siblings
        self.notify(order)
```

**Example:**

```python
import backtrader as bt

cerebro = bt.Cerebro()

# Oanda broker with API credentials
oandastore = bt.stores.OandaStore(
    token='your-api-token',
    account='your-account-id',
    practice=True,
)
cerebro.broker = bt.brokers.OandaBroker()

data = oandastore.getdata(dataname='EUR_USD',
                          timeframe=bt.TimeFrame.Minutes,
                          compression=5)
cerebro.adddata(data)

class ForexStrat(bt.Strategy):
    def next(self):
        if not self.position:
            # Real forex order to Oanda
            self.buy(size=10000)  # 10K units of EUR/USD

cerebro.addstrategy(ForexStrat)
cerebro.run()
```

---

## Class: VCBroker (VisualChart)

**File:** `backtrader/brokers/vcbroker.py`
**Requires:** VisualChart COM interface

A live broker adapter for VisualChart trading platform via `VCStore`.
Follows the same pattern as IBBroker and OandaBroker.

### Architecture

```
Strategy                     VCBroker                     VCStore/ComTrader
────────                     ────────                     ─────────────────
self.buy()  ─────────────►  buy()                        
                             │ create BuyOrder             
                             │ _makeorder() → VC COM Order 
                             └── submit(order, vcorder)  
                                 │ SendOrder() ──────────► VisualChart API
                                 │                         
                            ◄── OnOrderInMarket(Order)   ◄── VC COM callback
                            ◄── OnPartialExecutedOrder() ◄── VC partial fill
                            ◄── OnTotalExecutedOrder()   ◄── VC full fill
                            ◄── OnCancelledOrder()       ◄── VC cancelled
                            ◄── OnChangedBalance(Acct)   ◄── VC balance update
```

### Key Features

- Connects via COM/ActiveX interface to VisualChart
- Supports multiple accounts (`account` parameter)
- Maps backtrader order types to VC COM order types
- Position accounting via execution events (VC does not report zero positions)
- Commission scheme is auto-generated from instrument metadata if not provided
- Thread-safe with `_lock_orders` and `_lock_pos` locks

### Order Type Mapping

```python
# backtrader Order → VisualChart COM OrderType
_otypes = {
    Order.Market:    vcctmod.OT_Market,
    Order.Close:     vcctmod.OT_Market,      # MOC not natively supported
    Order.Limit:     vcctmod.OT_Limit,
    Order.Stop:      vcctmod.OT_StopMarket,
    Order.StopLimit: vcctmod.OT_StopLimit,
}

# Time in Force
_otrestriction = {
    Order.T_None:  vcctmod.TR_NoRestriction,   # GTC
    Order.T_Date:  vcctmod.TR_Date,            # Good til date
    Order.T_Close: vcctmod.TR_CloseAuction,    # Close auction
    Order.T_Day:   vcctmod.TR_Session,         # Day only
}
```

### Key Methods

```python
class VCBroker(BrokerBase):
    params = (
        ('account', None),       # VisualChart account name (None = first)
        ('commission', None),    # auto-generated from instrument if None
    )

    def __init__(self, **kwargs):
        self.store = vcstore.VCStore(**kwargs)
        self.positions = collections.defaultdict(Position)
        self._lock_orders = threading.Lock()
        self._lock_pos = threading.Lock()
        self.orderbyid = dict()        # {vc_orderId: bt_Order}
        self.notifs = collections.deque()

    def __call__(self, trader):
        '''Called by VCStore to initialize account data'''
        for acc in trader.Accounts:
            if self.p.account is None or self.p.account == acc.Account:
                self.cash = acc.Balance.Cash
                self.value = acc.Balance.NetWorth
                self._acc_name = acc.Account
                break

    def buy(self, owner, data, size, price=None, ...):
        order = BuyOrder(owner=owner, data=data, size=size, ...)
        vcorder = self._makeorder(order.ordtype, ...)  # → VC COM Order object
        return self.submit(order, vcorder)

    def submit(self, order, vcorder):
        order.submit(self)
        oid = self.store.vcct.SendOrder(
            vco.Account, vco.SymbolCode,
            vco.OrderType, vco.OrderSide, vco.Volume, ...)
        order.vcorder = oid
        self.orderbyid[oid] = order
        self.notify(order)
        return order

    def getcommissioninfo(self, data):
        '''Auto-generate from instrument metadata if not provided'''
        comminfo = self.comminfo.get(data._tradename) or self.comminfo[None]
        if comminfo:
            return comminfo
        # Auto-detect: use PointValue and stocklike based on instrument type
        return VCCommInfo(mult=data._syminfo.PointValue,
                         stocklike=(data._syminfo.Type in self._futlikes))

    # --- COM Event Callbacks (called from VC event thread) ---

    def OnChangedBalance(self, Account):
        '''Account balance updated → sync cash/value'''
        self.cash = acc.Balance.Cash
        self.value = acc.Balance.NetWorth

    def OnOrderInMarket(self, Order):
        '''Order accepted by exchange'''
        border = self.orderbyid[Order.OrderId]
        border.accept()
        self.notify(border)

    def OnTotalExecutedOrder(self, Order):
        '''Full fill → completed'''
        self.OnExecutedOrder(Order, partial=False)

    def OnPartialExecutedOrder(self, Order):
        '''Partial fill → still alive'''
        self.OnExecutedOrder(Order, partial=True)

    def OnExecutedOrder(self, Order, partial):
        '''Process a fill event'''
        border = self.orderbyid[Order.OrderId]
        price = Order.Price
        size = Order.Volume * (-1 if border.issell() else 1)

        position = self.getposition(border.data, clone=False)
        psize, pprice, opened, closed = position.update(size, price)
        # ... calculate commissions, PnL ...
        border.execute(dt, size, price, closed, ..., opened, ..., pnl, ...)
        if partial:
            border.partial()
        else:
            border.completed()
        self.notify(border)

    def OnCancelledOrder(self, Order):
        '''Order cancelled by exchange or user'''
        border = self.orderbyid[Order.OrderId]
        border.cancel()
        self.notify(border)
```

### Notes on VCBroker Limitations

- **No zero-position reporting:** VisualChart only reports `OpenPositions` when size > 0.
  Position accounting is done entirely from execution events.
- **No commission reporting:** The ComTrader interface does not provide commission data.
  User must pass a `commission` parameter for accurate accounting.
- **No datetime in expiration:** VisualChart's COM discards time from datetime objects.
  Expiration dates are always full dates.
- **Expired vs Cancelled:** No heuristic to distinguish — expired orders report as cancelled.

---

## Comparison: Simulation vs Live Brokers

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    BROKER COMPARISON                                       │
├──────────────┬───────────────┬──────────────┬─────────────┬──────────────┤
│              │ BackBroker    │ IBBroker     │ OandaBroker │ VCBroker     │
├──────────────┼───────────────┼──────────────┼─────────────┼──────────────┤
│ Mode         │ Simulation    │ Live         │ Live        │ Live         │
│ Connection   │ None          │ TWS/Gateway  │ REST API    │ COM/ActiveX  │
│ Cash source  │ self.cash     │ IB account   │ Oanda acct  │ VC account   │
│ Position src │ self.positions│ IB portfolio │ Oanda API   │ VC positions │
│ Order exec   │ OHLC matching │ Exchange     │ Oanda       │ Exchange     │
│ Slippage     │ Configurable  │ Real         │ Real        │ Real         │
│ Commission   │ CommInfoBase  │ IB (real)    │ Spread      │ VC (real)    │
│ Thread-safe  │ No            │ Yes (queue)  │ Yes (deque) │ Yes (deque)  │
│ Store        │ None          │ IBStore      │ OandaStore  │ VCStore      │
│ Brackets     │ Internal      │ IB native    │ Oanda native│ VC native    │
│ OCO          │ Internal      │ IB OCA group │ N/A         │ N/A          │
│ Order types  │ All simulated │ All IB types │ Market/Limit│ All VC types │
│ Fund mode    │ Yes           │ No           │ No          │ No           │
│ Dependencies │ None          │ ibpy         │ oandapy     │ pywin32/COM  │
└──────────────┴───────────────┴──────────────┴─────────────┴──────────────┘
```

---

## Complete Data Flow: Strategy → Broker → Notifications

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     ORDER DATA FLOW                                       │
└──────────────────────────────────────────────────────────────────────────┘

  Strategy                    Broker                         Market
  ────────                    ──────                         ──────

  1. self.buy(size=100)
     │
     ▼
  2. broker.buy(owner=self, data=data, size=100, exectype=Market)
     │
     ├── [BackBroker] → BuyOrder created, into pending deque
     │                   Waits for next bar's open price
     │
     ├── [IBBroker]   → IBOrder created, placeOrder() → TWS
     │
     └── [OandaBroker]→ BuyOrder created, order_create() → Oanda API
     │
     ▼
  3. Order submitted notification
     broker.notify(order.clone())
     │
     ▼
  4. strategy.notify_order(order)          ← status: Submitted
     │
     ▼
  5. Order accepted
     │
     ├── [BackBroker] → check_submitted: enough cash? → Accepted
     ├── [IBBroker]   → push_orderstatus(Submitted) → Accepted
     └── [OandaBroker]→ _accept callback → Accepted
     │
     ▼
  6. strategy.notify_order(order)          ← status: Accepted
     │
     ▼
  7. Execution (fill)
     │
     ├── [BackBroker] → broker.next() → _try_exec(order) → _execute()
     │                   price = open[0] with slippage
     │                   cash adjusted, position updated
     │
     ├── [IBBroker]   → push_execution(ex) + push_commissionreport(cr)
     │                   price = real execution price from exchange
     │
     └── [OandaBroker]→ _fill(oref, size, price)
                         price = real fill price from Oanda
     │
     ▼
  8. strategy.notify_order(order)          ← status: Completed
     │
     ▼
  9. strategy.notify_trade(trade)          ← trade created/updated
     │
     ▼
  10. strategy.next() continues
      self.broker.getcash()    → updated cash
      self.broker.getvalue()   → updated portfolio value
      self.getposition(data)   → updated position
```

---

## Practical Examples

### Example 1: Custom Filler (Partial Volume Execution)

```python
def volume_filler(order, price, ago):
    """Fill up to 25% of the bar's volume."""
    volume = order.data.volume[ago]
    max_fill = int(volume * 0.25)
    return min(max_fill, order.executed.remsize)

cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)
cerebro.broker.set_filler(volume_filler)

# Now large orders will be partially filled across multiple bars:
# Bar 1: volume=10000, fill 2500 of 10000 requested
# Bar 2: volume=8000, fill 2000 more
# Bar 3: volume=12000, fill 3000 more
# Bar 4: fill remaining 2500
```

### Example 2: Monitoring Broker State

```python
class MonitorStrat(bt.Strategy):
    def next(self):
        print(f'--- Bar {len(self)} ---')
        print(f'  Cash:     {self.broker.getcash():.2f}')
        print(f'  Value:    {self.broker.getvalue():.2f}')
        print(f'  Position: {self.getposition(self.data).size}')

        # Check open orders
        for order in self.broker.get_orders_open():
            print(f'  Open order: {order.ref} {order.getstatusname()}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return  # not interesting yet

        if order.status == order.Completed:
            if order.isbuy():
                print(f'  BUY executed at {order.executed.price:.2f}')
                print(f'  Commission: {order.executed.comm:.2f}')
            else:
                print(f'  SELL executed at {order.executed.price:.2f}')
                print(f'  PnL: {order.executed.pnl:.2f}')

        elif order.status == order.Margin:
            print(f'  ORDER MARGIN: not enough cash!')

        elif order.status == order.Cancelled:
            print(f'  ORDER CANCELLED')
```

### Example 3: Multiple Commission Schemes

```python
cerebro = bt.Cerebro()

# Stocks: 0.1% per trade
cerebro.broker.setcommission(
    commission=0.001,
    stocklike=True,
)

# ES Futures: $2.50 per contract, $50/point, $5000 margin
cerebro.broker.setcommission(
    commission=2.50,
    margin=5000.0,
    mult=50.0,
    stocklike=False,
    name='ES',
)

# Forex (no commission, profit from spread):
cerebro.broker.setcommission(
    commission=0.0,
    margin=1000.0,      # $1000 per lot margin
    mult=100000.0,       # standard lot = 100K units
    stocklike=False,
    name='EURUSD',
)
```

### Example 4: Switching Between Simulation and Live

```python
import backtrader as bt

cerebro = bt.Cerebro()

LIVE_MODE = False

if LIVE_MODE:
    # Live: connect to Interactive Brokers
    ibstore = bt.stores.IBStore(host='127.0.0.1', port=7497, clientId=1)
    cerebro.broker = bt.brokers.IBBroker()
    data = ibstore.getdata(dataname='AAPL-STK-SMART-USD')
else:
    # Simulation: use BackBroker (default)
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)
    data = bt.feeds.BacktraderCSVData(dataname='datas/orcl-2014.txt')

cerebro.adddata(data)
cerebro.addstrategy(MyStrategy)

# Same strategy code works for both modes!
# The broker abstraction handles the differences.
results = cerebro.run()
```
