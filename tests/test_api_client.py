from bot.api_client import WikiClient


class FakeClient(WikiClient):
    def __init__(self, payloads):
        super().__init__(user_agent="test")
        self.payloads = payloads
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        return self.payloads[path]


def test_latest_returns_data_dict():
    c = FakeClient({"/latest": {"data": {"2": {"high": 200, "low": 150}}}})
    assert c.latest() == {"2": {"high": 200, "low": 150}}


def test_mapping_returns_list():
    c = FakeClient({"/mapping": [{"id": 2, "name": "Cannonball", "limit": 11000}]})
    assert c.mapping()[0]["name"] == "Cannonball"


def test_timeseries_builds_path_with_params():
    c = FakeClient({"/timeseries?timestep=24h&id=2": {"data": [{"avgHighPrice": 100}]}})
    out = c.timeseries(2, "24h")
    assert out == [{"avgHighPrice": 100}]
    assert c.calls == ["/timeseries?timestep=24h&id=2"]
