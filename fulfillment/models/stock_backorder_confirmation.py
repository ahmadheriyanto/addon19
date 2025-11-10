# -*- coding: utf-8 -*-
from odoo import api, models, _
import logging

_logger = logging.getLogger(__name__)

class StockBackorderConfirmation(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    def action_process_oos(self):
        """
        Validate the pickings (creating backorders if needed), then set any created backorders'
        picking_type_id to company.fulfillment_default_operation_type_oos_id.

        This method forces the validation path so backorders are actually created (not just another wizard).
        It returns an action to close the wizard UI.
        """
        pickings_to_validate_ids = self.env.context.get('button_validate_picking_ids')
        if not pickings_to_validate_ids:
            return {'type': 'ir.actions.act_window_close'}

        Pick = self.env['stock.picking'].with_context(prefetch_fields=False)
        pickings = Pick.browse(pickings_to_validate_ids)

        # Ensure we trigger the validation that produces backorders (use same context as stock.wizard)
        # Provide picking_ids_not_to_backorder if present in the wizard (mirror process() behaviour).
        ctx = dict(self.env.context) or {}
        # When coming from the wizard, we want to skip opening nested wizards and execute validation.
        ctx.update({'skip_backorder': True})

        # If the wizard had some pickings not to backorder, propagate them so validation doesn't create backorders for them:
        # (the original wizard passes picking_ids_not_to_backorder in process())
        picking_ids_not_to_backorder = self._context.get('picking_ids_not_to_backorder')
        if picking_ids_not_to_backorder:
            ctx.update({'picking_ids_not_to_backorder': picking_ids_not_to_backorder})

        # Call button_validate with the adjusted context. If button_validate returns an action dict
        # (e.g. some modules might return something), we still proceed to search for created backorders.
        try:
            result = pickings.with_context(**ctx).button_validate()
        except Exception:
            _logger.exception("Error validating pickings in action_process_oos")
            # re-raise so client shows the error
            raise

        # At this point, the validation should have created backorders (if any).
        # Search for backorders that reference the original pickings:
        try:
            backorders = self.env['stock.picking'].search([('backorder_id', 'in', pickings.ids)])
        except Exception:
            _logger.exception("Failed to search for backorders after validation")
            backorders = self.env['stock.picking']

        # Update picking_type_id on created backorders to the configured OOS picking type
        for back in backorders:
            try:
                oos_pt = back.company_id and back.company_id.fulfillment_default_operation_type_oos_id
                if oos_pt and back.picking_type_id.id != oos_pt.id:
                    back.sudo().write({'picking_type_id': oos_pt.id})
            except Exception:
                _logger.exception("Failed to set OOS picking_type for backorder %s", back.id)

        # Close the wizard on the client
        return {'type': 'ir.actions.act_window_close'}