from unittest.mock import Mock
from sih_bhuvan.client import BhuvanWmsClient
from sih_bhuvan.contracts import WmsRequest

def test_wms_request():
    response = Mock()
    response.raise_for_status.return_value = None
    response.content = b"fake-image"

    client = Mock()
    client.get.return_value = response

    api = BhuvanWmsClient(client=client)
    out = api.get_map(WmsRequest(
        layer="lulc:BR_LULC50K_1112",
        bbox=(77.0, 10.0, 78.0, 11.0)
    ))
    assert out == b"fake-image"
    client.get.assert_called_once()
