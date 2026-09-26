from datetime import datetime, timezone
from unittest.mock import Mock
import httpx

from sih_smap.collector import SmapCollector

def test_search_granules_normalizes_getdata_urls():
    payload = {
        "items": [{
            "meta": {"concept-id": "G123-NSIDC_CPRD"},
            "umm": {
                "ProducerGranuleId": "TEST_GRANULE",
                "EntryTitle": "SMAP TEST",
                "TemporalExtents": [{
                    "RangeDateTime": {
                        "BeginningDateTime": "2026-09-06T00:00:00Z",
                        "EndingDateTime": "2026-09-06T03:00:00Z"
                    }
                }],
                "RelatedUrls": [
                    {"Type": "GET DATA", "URL": "https://example.test/data.h5"},
                    {"Type": "GET RELATED VISUALIZATION", "URL": "https://example.test/image"}
                ]
            }
        }]
    }
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload

    client = Mock()
    client.get.return_value = response

    items = SmapCollector(client=client).search_granules(
        start=datetime(2026, 9, 6, tzinfo=timezone.utc),
        end=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert len(items) == 1
    assert items[0].concept_id == "G123-NSIDC_CPRD"
    assert items[0].downloadable_urls == ["https://example.test/data.h5"]
