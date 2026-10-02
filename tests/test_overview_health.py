"""Overview's offline setup read must not probe providers or mutate a home."""

from runesmith import doctor
from test_studio import call, studio  # noqa: F401 -- shared disposable HTTP fixture

import pytest


@pytest.mark.parametrize("url", ["/api/health", "/api/health?network=0"])
def test_overview_health_is_offline_and_read_only(studio, monkeypatch, url):
    config = studio.ws.config()
    config["instruments"] = {
        "unprobed-author": {"kind": "openai", "base_url": "http://provider.invalid/v1", "model": "fixture"}
    }
    config["roles"] = {"plan": ["unprobed-author"], "repair": [], "kaizen": []}
    studio.ws.save_config(config)

    def forbidden_probe(*args, **kwargs):
        pytest.fail("Overview's local diagnostic must not probe an inference provider")

    monkeypatch.setattr(doctor, "_probe_openai", forbidden_probe)
    original_find_spec = doctor.importlib.util.find_spec
    monkeypatch.setattr(doctor.importlib.util, "find_spec",
                        lambda name, *args, **kwargs: None if name == "pytest" else original_find_spec(name, *args, **kwargs))

    def snapshot():
        # The live fixture owns this Windows byte-range lock: reading its held
        # byte is correctly denied. All other retained home bytes are compared.
        return {str(p.relative_to(studio.ws.home)): p.read_bytes()
                for p in studio.ws.home.rglob("*") if p.is_file() and p.name != "studio.instance.lock"}

    before = snapshot()
    worker_before = studio.worker.snapshot()
    status, body, _ = call(studio, "GET", url)
    assert status == 200
    by_check = {row["check"]: row for row in body["checks"]}
    assert by_check["pytest"]["ok"] is False
    assert by_check["pytest"]["fix"] == "pip install pytest"
    assert "pytest-based repair observation" in by_check["pytest"]["detail"]
    assert "Build's unittest checks" in by_check["pytest"]["detail"]
    assert by_check["instrument unprobed-author (plan)"]["ok"] is None
    assert by_check["instrument unprobed-author (plan)"]["detail"] == "not probed (offline)"
    assert snapshot() == before
    after = studio.worker.snapshot()
    for key in ("current", "queue", "history", "paused", "stop_requested", "recovery"):
        assert after.get(key) == worker_before.get(key), key
