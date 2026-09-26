# IMD — Verified Integration Notes

Official portal:
https://api.imd.gov.in/public/index.php

Official reference:
https://api.imd.gov.in/public/api_reference.html

## Authentication/access

The official portal provides account registration and login. The registration
page currently states that government-organization registrations require an
official organizational email. Do not commit credentials.

This package therefore leaves credential transport configurable. It does not
invent a secret/header contract that is not explicitly established for the
project account.

## Verified endpoints

### Current Weather
`GET https://api.imd.gov.in/api/v1/current_wx`
Optional `id=StationId`.

Official fields include:
- Station Id
- Station
- Date of Observation
- Time of Observation (UTC)
- M.S.L.P
- Wind Direction
- Wind Speed (KMPH)
- Temperature
- Weather Code
- Humidity
- Last 24 hrs Rainfall (mm)

### District Nowcast
`GET https://api.imd.gov.in/api/v1/districtnowcast`
Optional `id`.

Official documentation includes warning categories, issue time (`toi`),
valid-until (`Vupto`), message and color.

The reference maps:
- Cat7: moderate rain 5–15 mm/hr
- Cat12: heavy rain >15 mm/hr
and documents additional snow, thunderstorm and lightning categories.

These are IMD nowcast category definitions, not our ML risk thresholds.

### District Rainfall
`GET https://api.imd.gov.in/api/v1/districtrainfall`
Optional `id`.

The response includes daily, weekly, cumulative and monthly actual/normal/
departure/category fields.

### District Warning
`GET https://api.imd.gov.in/api/v1/districtwarning`
Optional `id`.

The response includes Day 1–Day 5 warning codes and color codes.

### Station Nowcast
`GET https://api.imd.gov.in/api/v1/stationnowcast`
Optional `id`.

The reference documents the same nowcast category framework.

### State Rainfall
`GET https://api.imd.gov.in/api/v1/staterainfall`
Optional `id`.

## SIH use

IMD contributes:
- authoritative government weather observations
- district rainfall context
- nowcast signals
- official warnings
- station-level weather context

Do not treat district rainfall as village-level rainfall.

Do not convert IMD warning color into our ML probability.

Preserve:
source
issued time
validity
original warning code
original color
raw payload
normalized representation
