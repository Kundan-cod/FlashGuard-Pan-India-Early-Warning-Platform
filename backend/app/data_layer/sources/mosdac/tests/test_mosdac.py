from datetime import date
import pytest

from sih_mosdac.collector import MosdacCollector
from sih_mosdac.contracts import MosdacSearchRequest
from sih_mosdac.config import MosdacConfig

def test_build_search_config():
    req = MosdacSearchRequest(
        dataset_id="3RIMG_L2B_HEM",
        start_time=date(2026, 9, 1),
        end_time=date(2026, 9, 2),
        count=50,
        bounding_box=(70.0, 8.0, 90.0, 28.0),
    )
    cfg = MosdacCollector.build_search_config(req)
    assert cfg["datasetId"] == "3RIMG_L2B_HEM"
    assert cfg["startTime"] == "2026-09-01"
    assert cfg["count"] == "50"
    assert cfg["boundingBox"] == "70.0,8.0,90.0,28.0"

def test_count_limit_is_enforced():
    with pytest.raises(Exception):
        MosdacSearchRequest(dataset_id="X", count=101)

def test_download_requires_credentials():
    c = MosdacCollector(MosdacConfig(username=None, password=None))
    with pytest.raises(RuntimeError):
        c.validate_download_ready()
