from bot.curation_status import CurationStatus


def test_lifecycle_snapshot():
    s = CurationStatus()
    snap = s.snapshot()
    assert snap["running"] is False and snap["last_count"] is None
    s.start(total=10)
    assert s.snapshot()["running"] is True and s.snapshot()["total"] == 10
    s.progress(3, 10)
    assert s.snapshot()["done"] == 3
    s.finish(4)
    snap = s.snapshot()
    assert snap["running"] is False and snap["last_count"] == 4
    assert snap["last_finished"] is not None


def test_fail_records_error():
    s = CurationStatus()
    s.start()
    s.fail(ValueError("boom"))
    snap = s.snapshot()
    assert snap["running"] is False and "boom" in snap["last_error"]
