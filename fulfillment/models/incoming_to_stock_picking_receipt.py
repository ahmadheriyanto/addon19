from odoo import api, fields, models
from odoo import fields as odoo_fields
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class IncomingStagingStockReceipt(models.Model):
    _inherit = 'incoming_staging'

    def action_create_receive_transfer(self):
        """Create receipt pickings for these incoming_staging records.

        This implementation uses the _ensure_* helper methods defined on the same model
        to get/create UoM, Product and Lot. It runs most operations under sudo() to
        avoid permission issues and is idempotent by checking existing pickings with the same origin.
        Returns a list of dicts with created picking ids / errors.
        """
        results = []
        env = self.sudo().env
        for rec in self.sudo():
            try:
                # Server-side visibility rule: only process when status == 'open' and type == 'inbound'
                if not (rec.status == 'open' and rec.type == 'inbound'):
                    results.append({
                        'staging_id': rec.id,
                        'note': 'skipped_not_open_or_not_inbound',
                        'state': rec.status,
                        'type': rec.type,
                    })
                    continue

                # Use rec.with_env(env) so helper methods run under sudo env
                rec_env = rec.with_env(env)

                # idempotency: if a picking with this origin already exists, skip creating a new one
                existing = env['stock.picking'].search([('origin', '=', rec.transaction_no)], limit=1)
                if existing:
                    results.append({
                        'staging_id': rec.id,
                        'picking_id': existing.id,
                        'picking_name': existing.name,
                        'state': existing.state,
                        'note': 'existing_picking_returned',
                    })
                    continue

                picking_type = env['stock.picking.type'].search([('code', '=', 'incoming')], limit=1)
                if not picking_type:
                    raise UserError("No incoming picking type found (code='incoming').")

                # Destination location preference: find 'WH/Input' by complete_name or fallback to picking default
                dest_location = env['stock.location'].search([('complete_name', 'ilike', 'WH/Input')], limit=1)
                if not dest_location:
                    dest_location = picking_type.default_location_dest_id or env['stock.location'].search([('usage', '=', 'internal')], limit=1)

                # Source location: prefer picking type default source or supplier usage
                src_location = picking_type.default_location_src_id or env['stock.location'].search([('usage', '=', 'supplier')], limit=1)
                if not src_location:
                    src_location = env['stock.location'].search([('usage', '=', 'supplier')], limit=1) or env['stock.location'].search([('usage', '=', 'internal')], limit=1)

                move_vals = []
                # build move lines from staging product lines using helpers
                for line in rec.products:
                    # ensure UoM (use 'Unit' fallback)
                    uom = rec_env._ensure_uom(line.product_uom or 'Unit')

                    # ensure product (returns product.product)
                    product = rec_env._ensure_product(line.product_no, line.product_nanme, uom)

                    # ensure lot if provided
                    lot = False
                    if line.product_lot:
                        lot = rec_env._ensure_lot(product, line.product_lot)

                    qty = float(line.product_qty or 0.0)
                    move_vals.append({
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'product_uom': uom.id,
                        'location_id': src_location.id,
                        'location_dest_id': dest_location.id,
                        'origin': rec.transaction_no,
                    })

                picking_vals = {
                    'partner_id': rec.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_id': src_location.id,
                    'location_dest_id': dest_location.id,
                    'origin': rec.transaction_no,
                    'scheduled_date': odoo_fields.Datetime.now(),
                    'move_ids': [(0, 0, m) for m in move_vals],
                }

                picking = env['stock.picking'].create(picking_vals)

                # Confirm / assign / validate (best-effort)
                try:
                    picking.action_confirm()
                except Exception:
                    _logger.exception("action_confirm failed for picking %s", picking.id)
                try:
                    if hasattr(picking, 'action_assign'):
                        picking.action_assign()
                    elif hasattr(picking, '_action_assign'):
                        picking._action_assign()
                except Exception:
                    _logger.exception("assignment failed for picking %s", picking.id)

                # Create move lines with qty_done (and attach lots if available)
                for staging_line in rec.products:
                    # find product using helpers/env (product should already exist via helper when building move_vals)
                    product = env['product.product'].search([('default_code', '=', staging_line.product_no)], limit=1) \
                              or env['product.product'].search([('name', '=', staging_line.product_nanme)], limit=1)

                    # fallback to matching by name if product not found for some reason
                    if product:
                        moves = picking.move_line_ids.filtered(lambda m, pid=product.id: m.product_id.id == pid)
                    else:
                        moves = picking.move_line_ids.filtered(lambda m, nm=(staging_line.product_nanme or staging_line.product_no): m.name == nm)

                    qty_done = float(staging_line.product_qty or 0.0)

                    lot = False
                    if staging_line.product_lot and product:
                        lot = env['stock.lot'].search([('name', '=', staging_line.product_lot), ('product_id', '=', product.id)], limit=1)
                        if not lot:
                            # create lot using helper to keep behavior consistent (use rec_env)
                            lot = rec_env._ensure_lot(product, staging_line.product_lot)

                    for move in moves:
                        try:
                            ml_vals = {
                                'picking_id': picking.id,
                                'move_id': move.id,
                                'product_id': move.product_id.id,
                                'product_uom_id': move.product_uom_id.id,
                                'qty_done': qty_done,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                            }
                            if lot:
                                ml_vals['lot_id'] = lot.id
                            env['stock.move.line'].create(ml_vals)
                        except Exception:
                            _logger.exception("Failed to create move line for picking %s move %s", picking.id, move.id)

                # Try validation
                try:
                    if hasattr(picking, 'button_validate'):
                        picking.button_validate()
                    elif hasattr(picking, 'action_done'):
                        picking.action_done()
                except Exception:
                    _logger.exception("Validation failed for picking %s", picking.id)

                results.append({'staging_id': rec.id, 'picking_id': picking.id, 'state': picking.state})
            except Exception as exc:
                _logger.exception("Failed to create receipt for incoming_staging %s", rec.id)
                results.append({'staging_id': rec.id, 'error': str(exc)})
        return results

    # ---------------------------------------------------------------------
    # Helpers to ensure UoM, Product, Lot exist
    # ---------------------------------------------------------------------
    def _ensure_uom(self, name):
        """Return a uom.uom record matching `name`. Create a simple one if missing.

        Compatible with Odoo 19 where the UoM category model is `uom.category`.
        This implementation does NOT reference `uom.uom.category`.
        """
        # Fallback to the company default product UoM when no name provided
        if not name:
            return (
                self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
                or (self.env['uom.uom'] and self.env['uom.uom'].search([], limit=1))
            )

        # Try to find an existing UoM by name
        uom = self.env['uom.uom'].search([('name', '=', name)], limit=1)
        if uom:
            return uom

        vals = {
            'name': name or 'Unit',
        }
        # Create a simple UoM: newer Odoo uses 'factor' or 'relative_factor'; attempt common fields
        # Try common field names in order to be robust across versions
        try:
            # prefer 'relative_factor' if present (Odoo 19 uses relative_factor / rounding)
            if 'relative_factor' in self.env['uom.uom']._fields:
                vals['relative_factor'] = 1.0
                uom = self.env['uom.uom'].create(vals)
            else:
                # try 'factor' (older API style)
                vals['factor'] = 1.0
                uom = self.env['uom.uom'].create(vals)
        except Exception:
            # fallback to factor_inv style if creation failed
            vals.pop('factor', None)
            vals.pop('relative_factor', None)
            vals['factor_inv'] = 1.0
            uom = self.env['uom.uom'].create(vals)
        return uom

    def _ensure_product(self, product_no, product_name, uom):
        """Find product by default_code or name; create a simple product.template if not found.
        Return a product.product record.
        """
        ProductProduct = self.env['product.product']
        ProductTemplate = self.env['product.template']

        prod = False
        if product_no:
            # search by default_code
            prod = ProductProduct.search([('default_code', '=', product_no)], limit=1)
        if not prod and product_name:
            prod = ProductProduct.search([('name', '=', product_name)], limit=1)
        if prod:
            return prod

        # Create a template then return its variant
        tmpl_vals = {
            'name': product_name or (product_no or 'New Product'),
            'uom_id': uom.id,
        }
        # Try to set default_code on template if supported
        try:
            tmpl_vals['default_code'] = product_no
            tmpl = ProductTemplate.create(tmpl_vals)
        except Exception:
            # Some Odoo versions expect default_code on product.product; try alternate route:
            tmpl_vals.pop('default_code', None)
            tmpl = ProductTemplate.create(tmpl_vals)
            if product_no:
                # set default_code on created product variant if possible
                try:
                    variant = tmpl.product_variant_id
                    variant.sudo().write({'default_code': product_no})
                except Exception:
                    _logger.exception("Unable to set default_code on new product variant for %s", product_no)
        return tmpl.product_variant_id

    def _ensure_lot(self, product, lot_name):
        if not lot_name:
            return False
        Lot = self.env['stock.lot']
        lot = Lot.search([('name', '=', lot_name), ('product_id', '=', product.id)], limit=1)
        if lot:
            return lot
        return Lot.create({'name': lot_name, 'product_id': product.id})