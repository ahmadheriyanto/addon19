# -*- coding: utf-8 -*-
from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_generate_backorder_wizard(self, show_transfers=False):
        """
        Use the context key 'button_validate_picking_ids' to decide whether
        to show the custom OOS backorder wizard view (fulfillment.view_backorder_confirmation_oos).
        Only choose the custom view when the pickings (from context or self) have
        picking_type == company.fulfillment_default_operation_type_pick_id.
        """
        action = super()._action_generate_backorder_wizard(show_transfers=show_transfers)

        # prefer explicit pick ids from context if provided
        pick_ids_ctx = self.env.context.get('button_validate_picking_ids') or []
        if isinstance(pick_ids_ctx, (list, tuple)):
            pickings = self.env['stock.picking'].browse(list(pick_ids_ctx))
            if not pickings:
                pickings = self
        else:
            pickings = self

        show_oos = False
        for picking in pickings:
            show_oos = picking.picking_type_id.show_oos_button_in_backorder_confirmation
            if show_oos:
                break            
            # company = picking.company_id or self.env.company
            # cfg_pt = company.fulfillment_default_operation_type_pick_id
            # if cfg_pt and picking.picking_type_id and picking.picking_type_id.id == cfg_pt.id:
            #     show_oos = True
            #     break

        if show_oos:
            view = self.env.ref('fulfillment.view_backorder_confirmation_oos', raise_if_not_found=False)
            if view:
                action['view_id'] = view.id
                action['views'] = [(view.id, 'form')] + [v for v in action.get('views', []) if v[1] != 'form']
                ctx = dict(action.get('context') or {})
                ctx['default_show_oos'] = True
                action['context'] = ctx

        return action