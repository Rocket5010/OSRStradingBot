"""Client for the OSRS Wiki Real-time Prices API. Stdlib only."""

import json
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"


class ApiError(Exception):
    pass


class WikiClient:
    def __init__(self, user_agent, base_url=BASE_URL, min_interval=1.0):
        self.user_agent = user_agent
        self.base_url = base_url
        self.min_interval = min_interval
        self._last_call = 0.0

    def _get(self, path):
        """Rate-limited HTTP GET. Returns parsed JSON. Override in tests."""
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code} for {url}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"request failed for {url}: {e}") from e
        finally:
            self._last_call = time.monotonic()
        return data

    def latest(self):
        return self._get("/latest")["data"]

    def latest_item(self, item_id):
        return self._get(f"/latest?id={item_id}")["data"][str(item_id)]

    def five_min(self):
        return self._get("/5m")["data"]

    def one_hour(self):
        return self._get("/1h")["data"]

    def mapping(self):
        return self._get("/mapping")

    def timeseries(self, item_id, timestep):
        params = urlencode({"timestep": timestep, "id": item_id})
        return self._get(f"/timeseries?{params}")["data"]
