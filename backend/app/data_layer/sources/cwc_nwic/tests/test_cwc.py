from unittest.mock import Mock
from sih_cwc.client import NwdpClient

def test_dataset_page():
    r=Mock(); r.raise_for_status.return_value=None
    r.text='<a href="https://www.nwdp.nwic.gov.in/download/test.csv">download</a>'
    c=Mock(); c.get.return_value=r
    html=NwdpClient(client=c).fetch_dataset_page(
        "/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc"
    )
    assert "test.csv" in html

def test_extract_links():
    html='<a href="https://example.gov/a.csv">a</a>'
    assert NwdpClient.extract_resource_links(html)==["https://example.gov/a.csv"]
