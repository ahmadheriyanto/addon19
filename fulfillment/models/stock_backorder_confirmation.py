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
        - validate the backorder so it ends up in done state

        The code tries to be defensive: uses sudo() where necessary and avoids changing
        existing qty_done if already filled. It creates minimal move_lines when none exist.
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
                Move = self.env['stock.move']
                MoveLine = self.env['stock.move.line']
                for move in back.move_ids.filtered(lambda m: m.state != 'done'):
                    # expected qty on the move (in move's uom)
                    expected_qty = float(move.product_uom_qty or 0.0)

                    # If there are no move_lines, create a single one with qty_done = expected_qty
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
                        MoveLine.sudo().create(ml_vals)
                        continue

                    # If move_lines exist, ensure total qty_done equals expected_qty.
                    # We'll preserve existing qty_done where present and allocate the remaining amount
                    # to the first move_line (simple deterministic approach).
                    mls = move.move_line_ids
                    total_done = sum([float(ml.qty_done or 0.0) for ml in mls])
                    # If already equal (or greater due to rounding), continue
                    if abs(total_done - expected_qty) <= 1e-6:
                        continue
                    if total_done < expected_qty:
                        remaining = expected_qty - total_done
                        # add remaining to the first move_line
                        first_ml = mls[0]
                        new_qty = float(first_ml.qty_done or 0.0) + remaining
                        first_ml.sudo().write({'qty_done': new_qty})
                    else:
                        # total_done > expected_qty, reduce first ml to expected and zero others (best-effort)
                        # This is a fallback; ideally this situation won't happen.
                        first_ml = mls[0]
                        first_ml.sudo().write({'qty_done': expected_qty})
                        if len(mls) > 1:
                            for ml in mls[1:]:
                                ml.sudo().write({'qty_done': 0.0})
            except Exception:
                _logger.exception("Failed to prepare move lines (qty_done) for backorder %s", back.id)

            # 3) Validate the backorder so it goes to done
            try:
                # Use skip_backorder to avoid recursive creation, and sudo to avoid ACL issues
                back.sudo().with_context(skip_backorder=True).button_validate()
            except Exception:
                # If button_validate raises (for example due to missing lots/serials),
                # log and continue so other backorders still processed.
                _logger.exception("Failed to validate backorder %s after filling qty_done", back.id)

        return {'type': 'ir.actions.act_window_close'}