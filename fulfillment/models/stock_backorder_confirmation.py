# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
import logging

_logger = logging.getLogger(__name__)


class StockBackorderConfirmation(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    show_oos = fields.Boolean(string='Show OOS', default=False)

    def action_process_oos(self):
        """
        Validate the pickings (creating backorders if needed), then for any created backorders:
        - switch their picking_type to the company OOS picking type (if configured)
        - ensure the moves / move lines reflect qty_done equal to the expected qty (product_uom_qty)
          and populate lot_id / lot_name when available (from original moves / lots)
        - validate the backorder so it ends up in done state

        The code is defensive:
        - uses sudo() where necessary and avoids changing existing qty_done if already filled.
        - when creating move lines or updating them, tries to populate lot_name and lot_id
          using the best available source:
            1) move.lot_ids on the backorder move (if set by _set_lot_ids)
            2) corresponding original move's move_line lot_id / lot_name (from the validated pickings)
            3) first available lot on the original move
        """
        pickings_to_validate_ids = self.env.context.get('button_validate_picking_ids')
        if not pickings_to_validate_ids:
            return {'type': 'ir.actions.act_window_close'}

        pickings = self.env['stock.picking'].browse(pickings_to_validate_ids)

        # Force the validation path that creates backorders
        ctx = dict(self.env.context or {})
        ctx.update({'skip_backorder': True})
        if 'picking_ids_not_to_backorder' in self.env.context:
            ctx['picking_ids_not_to_backorder'] = self.env.context.get('picking_ids_not_to_backorder')

        try:
            pickings.with_context(**ctx).button_validate()
        except Exception:
            _logger.exception("Error validating pickings in action_process_oos")
            raise

        # Find backorders created from these pickings (backorder_id references original)
        try:
            backorders = self.env['stock.picking'].search([('backorder_id', 'in', pickings.ids)])
        except Exception:
            _logger.exception("Failed to search for backorders after validation")
            backorders = self.env['stock.picking']

        # Build a simple lookup of original moves grouped by product and by (product, locations)
        # to help resolve lot information for the newly created backorder moves.
        original_moves = pickings.move_ids if pickings else self.env['stock.move']
        orig_by_key = {}
        for om in original_moves:
            key1 = (om.product_id.id,)
            key2 = (om.product_id.id, om.location_id.id, om.location_dest_id.id)
            orig_by_key.setdefault(key1, []).append(om)
            orig_by_key.setdefault(key2, []).append(om)

        for back in backorders.sudo():
            # 1) Switch picking type to OOS if configured
            try:
                oos_pt = back.company_id and back.company_id.fulfillment_default_operation_type_oos_id
                if oos_pt and back.picking_type_id.id != oos_pt.id:
                    back.sudo().write({'picking_type_id': oos_pt.id})
            except Exception:
                _logger.exception("Failed to set OOS picking_type for backorder %s", back.id)

            # 2) Ensure qty_done on move lines equals the move expected qty, create move lines if missing
            try:
                MoveLine = self.env['stock.move.line']
                for move in back.move_ids.filtered(lambda m: m.state != 'done'):
                    # expected qty on the move (in move's uom)
                    expected_qty = float(move.product_uom_qty or 0.0)

                    # Try to collect lot info for this move from multiple places:
                    lot_id_for_move = False
                    lot_name_for_move = False

                    # 1) Prefer lot_ids already attached to the backorder move (set by core _set_lot_ids)
                    if hasattr(move, 'lot_ids') and move.lot_ids:
                        lot_id_for_move = move.lot_ids[0].id
                        lot_name_for_move = move.lot_ids[0].name

                    # 2) Fallback: try to find a corresponding original move and take its lot info
                    if not lot_id_for_move and original_moves:
                        # Prefer matching by product + locations key, then by product-only key
                        candidates = orig_by_key.get((move.product_id.id, move.location_id.id, move.location_dest_id.id)) or orig_by_key.get((move.product_id.id,))
                        if candidates:
                            # Prefer candidate that has move_line_ids with lot info
                            candidate = None
                            for c in candidates:
                                if c.move_line_ids and c.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name):
                                    candidate = c
                                    break
                            if not candidate:
                                candidate = candidates[0]
                            # try to obtain lot info from candidate's move_line_ids or lot_ids
                            if candidate:
                                if candidate.move_line_ids:
                                    # pick first move_line with lot info
                                    ml_with_lot = candidate.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name)
                                    if ml_with_lot:
                                        ml0 = ml_with_lot[0]
                                        lot_id_for_move = ml0.lot_id.id if ml0.lot_id else False
                                        lot_name_for_move = ml0.lot_name or (ml0.lot_id.name if ml0.lot_id else False)
                                if not lot_id_for_move and hasattr(candidate, 'lot_ids') and candidate.lot_ids:
                                    lot_id_for_move = candidate.lot_ids[0].id
                                    lot_name_for_move = candidate.lot_ids[0].name

                    # If there are no move_lines, create a single one with qty_done = expected_qty, including lot info when found
                    if not move.move_line_ids:
                        ml_vals = {
                            'picking_id': back.id,
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'qty_done': expected_qty,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        }
                        if lot_id_for_move:
                            ml_vals['lot_id'] = lot_id_for_move
                        if lot_name_for_move:
                            ml_vals['lot_name'] = lot_name_for_move
                        MoveLine.sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                        continue

                    # If move_lines exist, ensure total qty_done equals expected_qty.
                    mls = move.move_line_ids
                    total_done = sum([float(ml.qty_done or 0.0) for ml in mls])

                    # If already equal (or greater due to rounding), ensure lot_name is present when lot_id exists
                    if abs(total_done - expected_qty) <= 1e-6:
                        for ml in mls:
                            try:
                                if getattr(ml, 'lot_id', False) and not getattr(ml, 'lot_name', False):
                                    ml.sudo().write({'lot_name': ml.lot_id.name})
                                # If ml has no lot_id but we discovered a lot_name_for_move, set it on first ml
                                elif (not getattr(ml, 'lot_id', False)) and lot_name_for_move and not getattr(ml, 'lot_name', False):
                                    ml.sudo().write({'lot_name': lot_name_for_move})
                            except Exception:
                                _logger.exception("Failed to populate lot_name for existing move_line %s on backorder %s", ml.id, back.id)
                        continue

                    if total_done < expected_qty:
                        remaining = expected_qty - total_done
                        first_ml = mls[0]
                        new_qty = float(first_ml.qty_done or 0.0) + remaining
                        write_vals = {'qty_done': new_qty}
                        # Ensure first_ml has lot_name if lot_id exists or we have a fallback lot_name
                        try:
                            if not getattr(first_ml, 'lot_name', False):
                                if getattr(first_ml, 'lot_id', False):
                                    write_vals['lot_name'] = first_ml.lot_id.name
                                elif lot_name_for_move:
                                    write_vals['lot_name'] = lot_name_for_move
                                elif lot_id_for_move:
                                    # set lot_id if we discovered it (and first_ml doesn't have it)
                                    write_vals['lot_id'] = lot_id_for_move
                                    write_vals['lot_name'] = lot_name_for_move or False
                        except Exception:
                            _logger.exception("Error preparing lot_name for move_line %s on backorder %s", first_ml.id, back.id)
                        first_ml.sudo().write(write_vals)
                    else:
                        # total_done > expected_qty, reduce first ml to expected and zero others (best-effort)
                        first_ml = mls[0]
                        write_vals = {'qty_done': expected_qty}
                        try:
                            if not getattr(first_ml, 'lot_name', False):
                                if getattr(first_ml, 'lot_id', False):
                                    write_vals['lot_name'] = first_ml.lot_id.name
                                elif lot_name_for_move:
                                    write_vals['lot_name'] = lot_name_for_move
                        except Exception:
                            _logger.exception("Error preparing lot_name for move_line %s on backorder %s", first_ml.id, back.id)
                        first_ml.sudo().write(write_vals)
                        if len(mls) > 1:
                            for ml in mls[1:]:
                                try:
                                    ml.sudo().write({'qty_done': 0.0, 'lot_name': False})
                                except Exception:
                                    _logger.exception("Failed to zero move_line %s on backorder %s", ml.id, back.id)
            except Exception:
                _logger.exception("Failed to prepare move lines (qty_done) for backorder %s", back.id)

            # 3) Validate the backorder so it goes to done
            try:
                back.sudo().with_context(skip_backorder=True).button_validate()
            except Exception:
                _logger.exception("Failed to validate backorder %s after filling qty_done", back.id)

        return {'type': 'ir.actions.act_window_close'}