from unittest.mock import Mock
from sih_ndem.client import NdemClient
from sih_ndem.config import NdemConfig

def test_public_portal():
    r=Mock(); r.raise_for_status.return_value=None; r.text="<html>NDEM</html>"
    c=Mock(); c.get.return_value=r
    assert "NDEM" in NdemClient(client=c).check_public_portal()

def test_no_credentials_means_public_only():
    assert NdemClient(NdemConfig(username=None,password=None)).access_state()=="PUBLIC_ONLY"
