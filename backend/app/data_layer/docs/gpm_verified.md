# NASA GPM IMERG — Verified Integration

Official documentation:
https://gpm.nasa.gov/precip-apps/doc

Official PMM Publisher API:
https://pmmpublisher.pps.eosdis.nasa.gov/opensearch

NASA documents GET/POST requests with:
- q
- lat
- lon
- limit
- startTime
- endTime

The documented precipitation products include 30-minute, 3-hour, 1-day,
3-day and 7-day accumulations.

NASA's current directory lists:
- IMERG Early Run: ~10 km / 0.1 degree, minimum latency about 4 hours
- IMERG Late Run: ~10 km / 0.1 degree, minimum latency about 12 hours
- Final Run: research product with much longer latency

The PMM Publisher API is a dataset-discovery interface. The response
contains dataset metadata and action objects containing actual download
URLs. The collector parses those actions rather than inventing file paths.

Important: a dataset footprint is not itself a numeric rainfall observation.
The later raster ingestion stage must download and parse the actual product
and extract rainfall values spatially.

PPS/STORM research-data server access is separately documented as requiring
registration. Do not assume every NASA download path is anonymous.
