# GE Tax and P/L

OSRS charges a **2% sell tax** (since 2021), floored, capped at 5M per item. Some items exempt. Used by `positions.py` ([[Modules]]) to compute [[Data Model|realized_pl]].

```python
ge_tax(price)  = min(floor(price * 0.02), 5_000_000)   # per item
realized_pl    = (sell_price - ge_tax(sell_price)) * qty - buy_price * qty
```

## Why it matters
Margins lie if you ignore tax. Every [[Strategy System|strategy]] subtracts tax when computing margin/ROI, and [[Backtesting]] uses the same formula so results are honest.

## Related
- [[Bond Goal]] — net profit target after tax
- [[margin_flip]] — margin = high − tax − low
