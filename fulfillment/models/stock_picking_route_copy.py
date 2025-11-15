# -*- coding: utf-8 -*-
"""
Ensure custom fulfillment fields are propagated to pickings created automatically
by Routes / automated flows.

Behaviour:
- When a new stock.picking is created, attempt to locate a "source" picking based on
  the new record's origin/name and copy over selected custom fields when they were
  not explicitly provided in create() vals.
- This is defensive and conservative: it won't overwrite values provided by the caller.
- Heuristics used to find the source picking:
  1) exact name match on the origin value
  2) origin match (some pickings store the originating document in .origin)
  3) "Backorder of <PICKING_NAME>" pattern that Odoo sometimes uses
  4) fallback to searching for a picking whose origin equals the origin value
"""
from odoo import api, models
import logging
import re

_logger = logging.getLogger(__name__)


class StockPickingRouteCopy(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        """
        After creating pickings normally, attempt to backfill selected custom fields
        from a likely source picking (if found) when they are missing in the create vals.

        Fields that are copied (only if not provided in vals):
        - principal_courier_id
        - principal_customer_name
        - principal_customer_address

        You can extend the fields_to_copy list if you add other persisted custom fields
        that should be propagated when routes create new pickings.
        """
        # Call super to actually create records first
        records = super(StockPickingRouteCopy, self).create(vals_list)

        # Fields we want to propagate from source picking (if missing)
        fields_to_copy = [
            'principal_courier_id',
            'principal_customer_name',
            'principal_customer_address',
        ]

        # Process each created record. We try to match the created record against a source
        # picking using heuristics. If found, copy missing fields.
        for rec, vals in zip(records, vals_list):
            # If create explicitly supplied the field, skip copying for that field
            # Use the vals provided to create() as the canonical "explicitly set" indicator.
            origin = vals.get('origin') or (rec.origin or '') or vals.get('name') or rec.name
            if not origin:
                continue

            # Try several heuristics to find the source picking
            src = None

            # 1) If origin looks like "Backorder of <NAME>", extract NAME
            m = re.search(r'Backorder of\s+(.+)', origin)
            if m:
                origin_name = m.group(1).strip()
                src = self.env['stock.picking'].search([('name', '=', origin_name)], limit=1)

            # 2) Exact name match on the origin value
            if not src:
                src = self.env['stock.picking'].search([('name', '=', origin)], limit=1)

            # 3) origin match: find picking whose origin equals this origin value
            if not src:
                src = self.env['stock.picking'].search([('origin', '=', origin)], limit=1)

            # 4) As a last resort, try to find recent picking which has origin/name containing the origin token
            if not src:
                # be conservative: search picking with origin or name containing the origin string (case-sensitive)
                try:
                    src = self.env['stock.picking'].search(['|', ('origin', 'ilike', origin), ('name', 'ilike', origin)], limit=1)
                except Exception:
                    src = None

            # If we couldn't find a plausible source, skip
            if not src or src.id == rec.id:
                continue

            # Prepare write vals only for fields that were not explicitly passed to create()
            write_vals = {}
            for f in fields_to_copy:
                # skip if provided in create vals (explicit) even if falsy
                if f in vals:
                    continue
                # get value from source
                try:
                    src_val = getattr(src, f)
                except Exception:
                    src_val = False
                if not src_val:
                    continue
                # If the source value is a record (Many2one), set its id; otherwise set raw value
                if hasattr(src_val, 'id'):
                    write_vals[f] = src_val.id
                else:
                    write_vals[f] = src_val

            if write_vals:
                try:
                    # Use sudo() to avoid ACL issues when automated creation runs under system processes
                    rec.sudo().write(write_vals)
                    _logger.debug("Propagated custom fields %s from picking %s -> %s", list(write_vals.keys()), src.id, rec.id)
                except Exception:
                    _logger.exception("Failed to propagate custom fulfillment fields from picking %s to %s", src.id, rec.id)

        return records