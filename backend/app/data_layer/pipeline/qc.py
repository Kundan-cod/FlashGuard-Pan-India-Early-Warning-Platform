from typing import Iterable
from pydantic import BaseModel

def drop_invalid_coordinates(rows: Iterable[BaseModel]) -> list[BaseModel]:
    out = []
    for row in rows:
        lat = getattr(row, "latitude", None)
        lon = getattr(row, "longitude", None)
        if lat is not None and not (-90 <= lat <= 90):
            continue
        if lon is not None and not (-180 <= lon <= 180):
            continue
        out.append(row)
    return out

def require_variable(row: BaseModel) -> None:
    if not getattr(row, "variable", None):
        raise ValueError("normalized observation requires variable")
