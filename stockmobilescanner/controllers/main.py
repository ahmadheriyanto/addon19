from odoo import http
from odoo.http import request
import json

class MobileWarehouseController(http.Controller):

    @http.route(['/mobile_warehouse'], type='http', auth='user', website=True)
    def index(self, **kw):
        # Render the qweb template with a simple mobile UI
        return request.render('stockmobilescanner.mobile_warehouse_template', {})

    @http.route(['/mobile_warehouse/api/scan'], type='jsonrpc', auth='user', methods=['POST'])
    def api_scan(self, product_barcode=None, quantity=0.0, lot=None, location_id=None, dest_id=None, partner_id=None, picking_id=None, picking_type_id=None):
        """Create a picking and a stock.move for the scanned product (minimal example).
        Returns JSON with created picking/move ids or an error.
        """
        env = request.env
        # Resolve product by barcode
        product = env['product.product'].sudo().search([('barcode', '=', product_barcode)], limit=1)
        if not product:
            return {'error': 'product_not_found', 'barcode': product_barcode}

        # Resolve default locations if not provided
        try:
            if location_id:
                location_id = int(location_id)
            else:
                location_id = env.ref('stock.stock_location_stock').id
        except Exception:
            location_id = env.ref('stock.stock_location_stock').id
        try:
            if dest_id:
                dest_id = int(dest_id)
            else:
                dest_id = env.ref('stock.stock_location_stock').id
        except Exception:
            dest_id = env.ref('stock.stock_location_stock').id

        qty = float(quantity or 0.0)

        # Create a picking if not provided
        if picking_id:
            picking = env['stock.picking'].sudo().browse(int(picking_id))
            if not picking.exists():
                return {'error': 'picking_not_found', 'picking_id': picking_id}
        else:
            picking_vals = {
                'partner_id': int(partner_id) if partner_id else False,
                'picking_type_id': int(picking_type_id) if picking_type_id else env['stock.picking.type'].search([], limit=1).id,
                'location_id': location_id,
                'location_dest_id': dest_id,
                'origin': 'Mobile Scan'
            }
            picking = env['stock.picking'].sudo().create(picking_vals)

        # Create the move
        move_vals = {
            'name': product.display_name,
            'product_id': int(product.id),
            'product_uom_qty': qty,
            'product_uom': int(product.uom_id.id),
            'location_id': int(location_id),
            'location_dest_id': int(dest_id),
            'picking_id': int(picking.id),
        }
        move = env['stock.move'].sudo().create(move_vals)

        return {'success': True, 'picking_id': picking.id, 'move_id': move.id}

    @http.route(['/mobile_warehouse/api/complete'], type='jsonrpc', auth='user', methods=['POST'])
    def api_complete(self, move_id=None, qty_done=0.0, lot_name=None):
        """Minimal flow to create a stock.move.line with qty_done and attempt to mark the move/picking as done."""
        env = request.env
        try:
            move = env['stock.move'].sudo().browse(int(move_id))
        except Exception:
            return {'error': 'invalid_move_id', 'move_id': move_id}

        if not move.exists():
            return {'error': 'move_not_found', 'move_id': move_id}

        ml_vals = {
            'move_id': move.id,
            'product_id': move.product_id.id,
            'product_uom_id': move.product_uom.id,
            'qty_done': float(qty_done or 0.0),
            'location_id': move.location_id.id,
            'location_dest_id': move.location_dest_id.id,
        }
        # handle lot/serial (create minimal lot if missing)
        if lot_name:
            lot = env['stock.lot'].sudo().search([('name', '=', lot_name), ('product_id', '=', move.product_id.id)], limit=1)
            if not lot:
                lot = env['stock.lot'].sudo().create({'name': lot_name, 'product_id': move.product_id.id})
            ml_vals['lot_id'] = lot.id

        ml = env['stock.move.line'].sudo().create(ml_vals)

        # Try to finalize — there are different internal flows. We attempt _action_done then fallback to confirm/assign/validate.
        try:
            move._action_done()
        except Exception:
            try:
                picking = move.picking_id
                picking.action_confirm()
                picking.action_assign()
                picking.button_validate()
            except Exception:
                # if finalize fails, return created move_line and current picking state
                pass

        return {'success': True, 'move_line_id': ml.id, 'picking_state': move.picking_id.state}