# -*- coding: utf-8 -*-
import json
import logging
import urllib.parse
import urllib.request

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Default User-Agent for outbound HTTP calls. Nominatim requires a
# meaningful UA; OSRM public server does not enforce one but it's
# polite to identify ourselves.
_HTTP_USER_AGENT = "Odoo/delivery_osrm_distance (contact: admin@warunglakku.com)"


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    # ----- extend delivery_type selection -----
    delivery_type = fields.Selection(
        selection_add=[('osrm_distance', 'OSRM Distance-based')],
        ondelete={'osrm_distance': lambda recs: recs.write({'delivery_type': 'fixed'})},
    )

    # ----- OSRM distance configuration -----
    osrm_server_url = fields.Char(
        string='OSRM Server URL',
        default='https://router.project-osrm.org',
        help="Base URL of the OSRM routing server (no trailing slash). "
             "Public demo: https://router.project-osrm.org. "
             "For production, self-host OSRM with a regional OSM extract.",
    )
    osrm_origin_lat = fields.Float(
        string='Origin Latitude',
        digits=(16, 6),
        default=-8.188078,
        help="Latitude of the dispatch location (warehouse / store branch).",
    )
    osrm_origin_lng = fields.Float(
        string='Origin Longitude',
        digits=(16, 6),
        default=112.356937,
        help="Longitude of the dispatch location (warehouse / store branch).",
    )
    osrm_price_per_km = fields.Monetary(
        string='Price per km',
        currency_field='company_currency_id',
        default=2000.0,
        help="Shipping price per kilometre of driving distance returned by OSRM.",
    )
    osrm_minimum_price = fields.Monetary(
        string='Minimum Price',
        currency_field='company_currency_id',
        default=5000.0,
        help="Floor price. Applied even if (distance * price_per_km) is lower.",
    )
    osrm_maximum_price = fields.Monetary(
        string='Maximum Price',
        currency_field='company_currency_id',
        default=0.0,
        help="Ceiling price. Set to 0 to disable the cap.",
    )
    osrm_nominatim_url = fields.Char(
        string='Nominatim URL',
        default='https://nominatim.openstreetmap.org',
        help="Geocoding service used to convert customer addresses "
             "to latitude/longitude. For production, self-host Nominatim.",
    )
    osrm_last_distance_km = fields.Float(
        string='Last Computed Distance (km)',
        digits=(16, 3),
        compute='_compute_osrm_last_info',
        help="Distance returned by the most recent OSRM call made by "
             "this carrier (across all orders). For diagnostics only.",
    )
    osrm_last_price = fields.Monetary(
        string='Last Computed Price',
        currency_field='company_currency_id',
        compute='_compute_osrm_last_info',
        help="Price returned by the most recent OSRM call made by "
             "this carrier. For diagnostics only.",
    )

    # The base delivery.carrier model has no `company_currency_id`
    # field; expose one so Monetary fields can resolve their currency.
    company_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Company Currency',
        compute='_compute_company_currency_id',
    )

    @api.depends('company_id')
    def _compute_company_currency_id(self):
        for carrier in self:
            company = carrier.company_id or self.env.company
            carrier.company_currency_id = company.currency_id

    @api.depends('osrm_origin_lat', 'osrm_origin_lng',
                 'osrm_price_per_km', 'osrm_minimum_price',
                 'osrm_maximum_price')
    def _compute_osrm_last_info(self):
        """Diagnostic fields — populated at runtime by `_osrm_compute_price`.
        The compute here only initialises them; we use `sudo().write` in
        the pricing method to override the computed value with real data.
        """
        for carrier in self:
            carrier.osrm_last_distance_km = 0.0
            carrier.osrm_last_price = 0.0

    # ==================================================================
    # Required Odoo hooks for a custom delivery_type.
    # Odoo 17 calls:  <delivery_type>_<method_name>
    # ==================================================================

    def osrm_distance_get_shipping_price_from_so(self, orders):
        """Return one shipping price per sales order in `orders`.

        Called by `delivery.carrier._get_price_available` to compute
        the per-order delivery line price.
        """
        self.ensure_one()
        prices = []
        for order in orders:
            try:
                price = self._osrm_compute_price(order)
                prices.append(price)
            except Exception as exc:
                _logger.warning(
                    "OSRM pricing failed for SO %s: %s",
                    order.name, exc,
                )
                prices.append(self.osrm_minimum_price or 0.0)
        return prices

    def osrm_distance_rate_shipment(self, order):
        """Quote shipping for a sales order.

        Must return dict with keys: success, price, error_message,
        warning_message. Called by `sale.order._get_delivery_methods`
        on the storefront to display carrier price.
        """
        self.ensure_one()
        try:
            price = self._osrm_compute_price(order)
        except Exception as exc:
            _logger.warning("OSRM rate_shipment failed for SO %s: %s",
                            order.name, exc)
            return {
                'success': False,
                'price': 0.0,
                'error_message': _("Could not compute shipping: %s") % exc,
                'warning_message': False,
            }
        return {
            'success': True,
            'price': price,
            'error_message': False,
            'warning_message': False,
        }

    def osrm_distance_send_shipping(self, pickings):
        """Pricing-only carrier: no real label is produced."""
        res = []
        for picking in pickings:
            res.append({
                'exact_price': picking.carrier_price or 0.0,
                'tracking_number': False,
                'labels': [],
            })
        return res

    def osrm_distance_get_tracking_link(self, pickings):
        return [''] * len(pickings)

    def osrm_distance_cancel_shipment(self, pickings):
        pickings.write({'carrier_tracking_ref': False})

    def osrm_distance_get_default_custom_package_code(self):
        return False

    # ==================================================================
    # Pricing implementation
    # ==================================================================

    def _osrm_compute_price(self, order):
        """Compute the dynamic shipping price for one SO."""
        self.ensure_one()
        partner = order.partner_shipping_id or order.partner_id
        if not partner:
            raise UserError(_("Order %s has no shipping partner.") % order.name)

        dest_lat, dest_lng = self._osrm_get_partner_coords(partner)
        if dest_lat is None or dest_lng is None:
            raise UserError(_(
                "Could not geocode the shipping address for partner %s. "
                "Please set lat/lng manually on the partner record.",
                partner.display_name,
            ))

        # OSRM expects LON,LAT;LON,LAT
        url = (
            f"{self.osrm_server_url.rstrip('/')}/route/v1/driving/"
            f"{self.osrm_origin_lng:.6f},{self.osrm_origin_lat:.6f};"
            f"{dest_lng:.6f},{dest_lat:.6f}?overview=false"
        )
        _logger.info("OSRM request for SO %s: %s", order.name, url)
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if data.get('code') != 'Ok' or not data.get('routes'):
            raise UserError(_(
                "OSRM did not return a route. Code: %s, message: %s",
                data.get('code'), data.get('message', ''),
            ))

        distance_m = data['routes'][0].get('distance', 0)
        distance_km = distance_m / 1000.0

        price = distance_km * self.osrm_price_per_km
        if self.osrm_minimum_price:
            price = max(price, self.osrm_minimum_price)
        if self.osrm_maximum_price:
            price = min(price, self.osrm_maximum_price)

        # Cache on the SO for transparency.
        order.sudo().write({
            'osrm_last_distance_km': distance_km,
            'osrm_last_price': price,
        })

        _logger.info(
            "OSRM SO %s: distance=%.2f km, price=%s",
            order.name, distance_km, price,
        )
        return price

    def _osrm_get_partner_coords(self, partner):
        """Return (lat, lng) for a partner, geocoding if needed.

        Odoo ships `partner_latitude` / `partner_longitude` on
        res.partner (added by base). They are populated by
        `base_geolocalize` for the company address book, but for
        guest checkout customers we lazily geocode via Nominatim
        and cache the result on the partner.
        """
        # First check if partner already has coords (from base_geolocalize
        # or from a previous OSRM/Nominatim call we cached).
        if partner.partner_latitude and partner.partner_longitude:
            return partner.partner_latitude, partner.partner_longitude

        address = self._osrm_format_address(partner)
        if not address:
            return None, None

        try:
            url = (
                f"{self.osrm_nominatim_url.rstrip('/')}/search?"
                + urllib.parse.urlencode({
                    'q': address,
                    'format': 'json',
                    'limit': 1,
                    'addressdetails': 0,
                })
            )
            req = urllib.request.Request(url, headers={
                'User-Agent': _HTTP_USER_AGENT,
                'Accept-Language': 'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data:
                lat = float(data[0]['lat'])
                lng = float(data[0]['lon'])
                partner.sudo().write({
                    'partner_latitude': lat,
                    'partner_longitude': lng,
                })
                _logger.info(
                    "Nominatim geocoded %s -> lat=%s, lng=%s",
                    partner.display_name, lat, lng,
                )
                return lat, lng
        except Exception as exc:
            _logger.warning(
                "Nominatim geocode failed for partner %s: %s",
                partner.display_name, exc,
            )
        return None, None

    @staticmethod
    def _osrm_format_address(partner):
        """Compose a single-line address for geocoding."""
        parts = []
        if partner.street:
            parts.append(partner.street)
        if partner.street2:
            parts.append(partner.street2)
        if partner.city:
            parts.append(partner.city)
        if partner.state_id and partner.state_id.name:
            parts.append(partner.state_id.name)
        if partner.zip:
            parts.append(partner.zip)
        if partner.country_id and partner.country_id.name:
            parts.append(partner.country_id.name)
        return ', '.join(p for p in parts if p).strip() or None
