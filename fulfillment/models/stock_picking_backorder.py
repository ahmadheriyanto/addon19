# -*- coding: utf-8 -*-
from odoo import api, models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_generate_backorder_wizard(self, show_transfers=False):
        """
        Override to return a backorder confirmation wizard view variant that includes
        the OOS button when the pickings match the configured 'fulfillment_default_operation_type_pick_id'.

        We keep the default behavior for all other cases.
        """
        action = super(StockPicking, self)._action_generate_backorder_wizard(show_transfers=show_transfers)

        # Determine if ANY of the pickings (self) use the configured pick-type for fulfillment picks.
        # If so, switch the action to use our custom view that includes the OOS button.
        try:
            show_oos_view = False
            for picking in self:
                cfg_pt = picking.company_id and picking.company_id.fulfillment_default_operation_type_pick_id or None
                if cfg_pt and picking.picking_type_id and picking.picking_type_id.id == cfg_pt.id:
                    show_oos_view = True
                    break
        except Exception:
            show_oos_view = False

        if show_oos_view:
            # Use our custom view (defined in fulfillment/views/stock_backorder_confirmation_oos_view.xml)
            # xmlid: fulfillment.fulfillment_view_backorder_confirmation_oos_inherit
            try:
                view = self.env.ref('fulfillment.fulfillment_view_backorder_confirmation_oos_inherit', raise_if_not_found=False)
                if view:
                    action['view_id'] = view.id
                    # Ensure the views list includes the form view first
                    action['views'] = [(view.id, 'form')] + [v for v in action.get('views', []) if v[1] != 'form']
            except Exception:
                # fall back to default action if anything goes wrong
                pass

        return action