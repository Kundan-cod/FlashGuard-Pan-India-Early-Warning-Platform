from unittest.mock import Mock
from sih_gsi.client import BhusanketClient

def test_portal_fetch():
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = "<a href='https://bhusanket.gsi.gov.in/test.pdf'>x</a>"

    client = Mock()
    client.get.return_value = response

    html = BhusanketClient(client=client).fetch_portal()
    assert "test.pdf" in html
