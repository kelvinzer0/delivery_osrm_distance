# -*- coding: utf-8 -*-
{
    'name': 'Delivery OSRM Distance-based Pricing',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Dynamic shipping price based on OSRM driving distance',
    'description': """
Delivery OSRM Distance-based Pricing
=====================================

Adds a new *Delivery Method* type called **OSRM Distance-based** that
quotes shipping costs dynamically from the driving distance between
your dispatch location and the customer's address.

How it works
------------

1. The shop admin configures a `delivery.carrier` with:
   - OSRM server URL (default: https://router.project-osrm.org)
   - Origin latitude / longitude (default: Warung Lakku branch,
     -8.188078, 112.356937)
   - Price per km
   - Minimum and optional maximum price
2. When a customer proceeds to checkout and selects this carrier,
   the module:
   a. Looks up the customer's coordinates (cached on the partner,
      auto-geocoded via OSM Nominatim on first use).
   b. Calls the OSRM Route API:
      GET {osrm_server}/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=false
   c. Reads `routes[0].distance` (metres), converts to km.
   d. Computes: price = max(min_price, min(max_price, km * price_per_km))
3. The computed price is returned to the checkout page and stored
   on the sales order as a delivery line.

Important: rate limits
----------------------

* The OSRM public server (router.project-osrm.org) is rate-limited
  (~1 request / 5 seconds). For production, **self-host OSRM** with
  an OSM extract of your region.
* Nominatim (nominatim.openstreetmap.org) is also rate-limited
  (~1 request / second). For production, self-host Nominatim or use
  a commercial geocoder.

Configuration
-------------

1. After install, go to *Inventory → Configuration → Delivery →
   Shipping Methods*. A pre-configured "Warung Lakku Delivery"
   carrier is created automatically.
2. Open it and adjust:
   - **Price per km** (default: 2000 IDR)
   - **Minimum price** (default: 5000 IDR)
   - **Maximum price** (default: 0 = no cap)
3. To manually geocode a partner, open the partner form and click
   *Action → Geocode Address (OSRM/Nominatim)*.

Author: kelvinzer0
License: LGPL-3
    """,
    'author': 'kelvinzer0',
    'website': 'https://github.com/kelvinzer0',
    'license': 'LGPL-3',
    'depends': [
        'delivery',
        'website_sale',
        'sale_management',
    ],
    'data': [
        'views/delivery_carrier_views.xml',
        'data/delivery_carrier_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
