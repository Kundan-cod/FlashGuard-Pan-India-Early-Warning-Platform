from .contracts import HistoricalEvent, TrainingLabel

def make_positive_label(event: HistoricalEvent, spatial_unit_id: str, confidence: float) -> TrainingLabel:
    return TrainingLabel(
        spatial_unit_id=spatial_unit_id,
        hazard=event.hazard,
        target=1,
        label_source=event.source,
        label_confidence=max(0.0, min(1.0, confidence)),
        event_id=event.event_id,
    )

def make_unobserved_label(hazard: str, spatial_unit_id: str, source: str) -> TrainingLabel:
    # 0 is deliberately NOT used here: absence of an observed event is not
    # equivalent to a confirmed negative when inventory coverage is incomplete.
    return TrainingLabel(
        spatial_unit_id=spatial_unit_id,
        hazard=hazard,
        target=-1,
        label_source=source,
        label_confidence=0.0,
        observation_coverage=None,
    )
