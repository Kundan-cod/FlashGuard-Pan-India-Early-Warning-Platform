# SIH 26192 — IMD Verified Data Layer

Verified against the current official India Meteorological Department API
reference and API Management Platform.

Official portal:
https://api.imd.gov.in/public/index.php

Official API reference:
https://api.imd.gov.in/public/api_reference.html

Verified endpoints used by this package:

- GET https://api.imd.gov.in/api/v1/current_wx
- GET https://api.imd.gov.in/api/v1/districtnowcast
- GET https://api.imd.gov.in/api/v1/districtrainfall
- GET https://api.imd.gov.in/api/v1/districtwarning
- GET https://api.imd.gov.in/api/v1/stationnowcast
- GET https://api.imd.gov.in/api/v1/staterainfall

The official reference also documents forecast APIs, AWS/ARG data, river-basin
QPF, radar and lightning APIs. They are intentionally not implemented in this
first adapter until their individual request/response contracts are needed.

Authentication:
The official portal provides account registration/login. The current
registration page states that government-organization registrations require
an official organizational email. Credentials must never be committed.

Important data facts verified from the official reference:
- Current weather includes observation time in UTC and last-24-hour rainfall.
- District nowcast contains warning categories, issue time and validity.
- District rainfall provides daily, weekly, cumulative and monthly rainfall
  actual/normal/departure/category fields.
- District warnings provide Day 1 through Day 5 warning codes and color codes.
- Station nowcast provides the same category framework at station level.

This package provides:
- source registry
- typed normalized contracts
- reusable HTTP collector
- endpoint-specific methods
- response validation
- retry/timeout handling
- tests using mocked official responses
- .env.example

The adapter does NOT invent authentication headers. The exact credential
mechanism must be configured once the user's IMD account/API access details
are available.
