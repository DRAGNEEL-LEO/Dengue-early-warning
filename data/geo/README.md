# Map data

`bd_districts.json`: district (ADM2) boundaries of Bangladesh for the map area, simplified for display.

- Source: Bangladesh Bureau of Statistics (BBS) and UN OCHA ROAP, distributed by geoBoundaries
  (gbOpen, BGD ADM2, boundary year 2020, https://www.geoboundaries.org).
- Licence: Creative Commons Attribution 3.0 IGO (CC BY 3.0 IGO). Attribution is shown in the app.
- Changes: clipped to the area around Dhaka, Gazipur, Narayanganj and Chattogram; simplified (Douglas-Peucker)
  and rounded to 4 decimals.

These are district boundaries, **not ward boundaries**. The onsite dataset has no ward coordinates.

`city_markers.csv`: one marker per city corporation, at the approximate location of the city-corporation office.
Each was checked to fall inside its district boundary. They are labelled approximate in the app and are not ward
locations. To map individual wards, add `data/geo/ward_points.csv` with columns `ward_id,lat,lon` from an
authoritative source; the map uses it automatically when present.
