from datetime import datetime, timezone
from sih_history.contracts import HistoricalEvent
from sih_history.labeling import make_positive_label, make_unobserved_label

def test_positive_label():
    e=HistoricalEvent(
        event_id="LS-1",
        hazard="LANDSLIDE",
        source="NRSC_LANDSLIDE_ATLAS",
        event_time_start=datetime(2020,1,1,tzinfo=timezone.utc),
    )
    x=make_positive_label(e,"V123",0.9)
    assert x.target==1
    assert x.hazard=="LANDSLIDE"
    assert x.event_id=="LS-1"

def test_missing_event_is_not_negative():
    x=make_unobserved_label("FLOOD","V123","NRSC_FLOOD")
    assert x.target==-1
