# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.returns('self', lambda value: value.id)
    def action_geocode_with_nominatim(self):
        """Manually trigger Nominatim geocoding for selected partners.

        Useful for batch-geocoding existing partners, or for retrying
        after a partner's address was corrected. Bound to a server
        action defined in the view XML.
        """
        carrier = self.env['delivery.carrier'].sudo().search(
            [('delivery_type', '=', 'osrm_distance')], limit=1,
        )
        if not carrier:
            # Use defaults if no carrier configured yet.
            carrier = self.env['delivery.carrier'].sudo().new({
                'osrm_nominatim_url': 'https://nominatim.openstreetmap.org',
            })
        for partner in self:
            coords = carrier._osrm_get_partner_coords(partner)
            if coords == (None, None):
                _logger.warning(
                    "Geocode failed for partner %s", partner.display_name,
                )
        return True
