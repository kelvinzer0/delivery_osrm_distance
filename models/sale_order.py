# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Cached result of the most recent OSRM pricing call for this SO.
    # Populated by `delivery.carrier._osrm_compute_price` (see
    # models/delivery_carrier.py).
    osrm_last_distance_km = fields.Float(
        string='OSRM Distance (km)',
        digits=(16, 3),
        readonly=True,
        copy=False,
        help="Distance returned by the most recent OSRM call for this order.",
    )
    osrm_last_price = fields.Monetary(
        string='OSRM Computed Price',
        currency_field='currency_id',
        readonly=True,
        copy=False,
        help="Shipping price computed from the OSRM distance for this order.",
    )
