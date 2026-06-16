"""Strategy contract and signal datatypes. See the Strategy System spec note."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MarketData:
    item_id: int
    name: str
    low: int            # instant-buy price
    high: int           # instant-sell price
    vol_1h: int
    history: list = field(default_factory=list)   # timeseries candles, if loaded


@dataclass
class BuySignal:
    item_id: int
    price: int
    qty: int
    reason: str


@dataclass
class SellDecision:
    sell: bool
    reason: str


class Strategy(ABC):
    name: str
    description: str

    @abstractmethod
    def find_buys(self, market, budget):
        """Return list[BuySignal] within the given gp budget."""

    @abstractmethod
    def should_sell(self, position, market):
        """Return a SellDecision for a held position."""

    @abstractmethod
    def default_params(self):
        """Return a dict of tunable params with default values."""
