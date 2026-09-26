from unittest.mock import Mock
from sih_lgd.client import LgdClient

def test_directory_page():
    r=Mock(); r.raise_for_status.return_value=None
    r.text="<html>Districts Villages Wards</html>"
    c=Mock(); c.get.return_value=r
    html=LgdClient(client=c).fetch_directory_page()
    assert "Villages" in html
