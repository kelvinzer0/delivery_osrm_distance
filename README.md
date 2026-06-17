# Delivery OSRM Distance-based Pricing

Odoo 17 module that adds a new delivery carrier type which prices
shipping dynamically from the OSRM driving distance between your
dispatch location and the customer's address.

## Features

* New `delivery.carrier` type: **OSRM Distance-based**
* Calls the OSRM Route API (`/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=false`)
* Auto-geocodes customer addresses via OSM Nominatim (cached on the
  partner record so the second order from the same address is instant)
* Pricing formula: `max(min_price, min(max_price, km × price_per_km))`
* Pre-configured "Warung Lakku Delivery" carrier seeded with the
  branch coordinates `-8.188078, 112.356937` (Tunjung, East Java)
* Server action: manually geocode selected partners from the
  Partners list view (*Action → Geocode Address*)

## Requirements

* Odoo 17 Community (the official `odoo:17` Docker image works)
* Installed: `delivery`, `website_sale` (the storefront delivery
  integration was merged into `website_sale` in Odoo 17)

## Installation

### Docker / Portainer

1. Drop the folder into your `extra-addons` directory (already mounted
   on the Odoo container at `/mnt/extra-addons`):
   ```bash
   docker cp delivery_osrm_distance odoo:/mnt/extra-addons/
   ```
   Or upload via Portainer (as we did during deployment).
2. Restart the Odoo container:
   ```bash
   docker restart odoo
   ```
3. Activate Developer Mode in Odoo → Settings.
4. Apps → Update Apps List.
5. Search "OSRM Distance" → Install.

## Configuration

1. Inventory → Configuration → Delivery → Shipping Methods
2. Open **Warung Lakku Delivery (Distance-based)**.
3. On the **Settings** tab, adjust:
   * **OSRM Server URL** — defaults to `https://router.project-osrm.org`
   * **Origin Latitude** — `-8.188078` (Tunjung branch)
   * **Origin Longitude** — `112.356937`
   * **Price per km** — `2000` IDR/km
   * **Minimum Price** — `5000` IDR
   * **Maximum Price** — `0` (no cap)
4. Save.

## How pricing works

When the customer reaches the shipping step of checkout:

1. The selected carrier is the OSRM distance one.
2. Odoo calls `delivery.carrier.rate_shipment(order)`.
3. The module:
   a. Reads the customer's `partner_latitude` / `partner_longitude`.
      If empty, geocodes the address via Nominatim (and caches on the
      partner).
   b. Calls the OSRM server:
      ```
      GET https://router.project-osrm.org/route/v1/driving/
          112.356937,-8.188078;<lng>,<lat>?overview=false
      ```
   c. Parses `routes[0].distance` (metres), divides by 1000 → km.
   d. Computes: `price = max(min, min(max, km × price_per_km))`.
4. The price is returned to the checkout page and applied to the
   delivery line on the sales order.

## Rate limits

The public OSRM server is rate-limited to roughly **1 request every
5 seconds**. Nominatim is limited to **1 request per second**. For
a production store you should:

* **Self-host OSRM** with an OSM extract of Indonesia (or your
  service area). Docker images are available:
  https://github.com/Project-OSRM/osrm-backend
* **Self-host Nominatim** or use a commercial geocoder
  (Google, Mapbox, OpenCage, etc.) — Nominatim's public usage
  policy forbids heavy use.

For low-volume stores (< 100 orders/day) the public servers are
tolerable; partner geocoding is cached so subsequent orders from
the same address skip the Nominatim call entirely.

## File map

```
delivery_osrm_distance/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── delivery_carrier.py    # OSRM carrier logic
│   ├── res_partner.py         # Geocode server action
│   └── sale_order.py          # Diagnostic fields
├── views/
│   └── delivery_carrier_views.xml
└── data/
    └── delivery_carrier_data.xml  # Pre-seeded carrier
```

## License

LGPL-3

## Author

kelvinzer0 — https://github.com/kelvinzer0
