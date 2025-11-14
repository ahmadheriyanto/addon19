from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fulfillment_default_operation_type_receipt_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.fulfillment_default_operation_type_receipt_id',
        string='Default Operation Type for Receipt',
        readonly=False,
        help="Company-level default operation type for receipt",
    )

    fulfillment_default_operation_type_pick_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.fulfillment_default_operation_type_pick_id',
        string='Default Operation Type for Pick',
        readonly=False,
        help="Company-level default operation type for pick",
    )

    fulfillment_default_operation_type_oos_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.fulfillment_default_operation_type_oos_id',
        string='Default Operation Type for OOS',
        readonly=False,
        help="Company-level default operation type for Out of Stock",
    )

    fulfillment_priority_cutoff_time = fields.Float(
        related='company_id.fulfillment_priority_cutoff_time',
        string='Priority Cut-off Time',
        readonly=False,
        help="Define cut-off time for Priority picking, reset to draft if more than the time setting.",
    )

    # Company-level transporter category exposed in settings for easy configuration
    fulfillment_transporter_category_id = fields.Many2one(
        'res.partner.category',
        related='company_id.fulfillment_transporter_category_id',
        string='Transporter Category',
        readonly=False,
        help='Company-level partner category used as the Transporter (special) category for courier scoring.',
    )

     # Expose thresholds and labels in settings
    fulfillment_courier_threshold_reguler = fields.Integer(
        related='company_id.fulfillment_courier_threshold_reguler',
        string='Courier threshold (Reguler max)',
        readonly=False,
    )
    fulfillment_courier_threshold_medium = fields.Integer(
        related='company_id.fulfillment_courier_threshold_medium',
        string='Courier threshold (Medium max)',
        readonly=False,
    )
    fulfillment_courier_label_reguler = fields.Char(
        related='company_id.fulfillment_courier_label_reguler',
        string='Label for Reguler',
        readonly=False,
    )
    fulfillment_courier_label_medium = fields.Char(
        related='company_id.fulfillment_courier_label_medium',
        string='Label for Medium',
        readonly=False,
    )
    fulfillment_courier_label_priority = fields.Char(
        related='company_id.fulfillment_courier_label_priority',
        string='Label for Priority',
        readonly=False,
    )

    def action_refresh_courier_scoring(self):
        """
        Button handler invoked from Settings view. Calls partner method to recompute and write
        stored courier fields for all partners.
        """
        # Run as sudo to ensure writing stored values is allowed
        self.env['res.partner'].sudo().refresh_courier_scoring_all()
        # Return a client notification so the user sees the action result
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Refresh Courier Scoring',
                'message': 'Courier scoring refreshed for all partners.',
                'sticky': False,
            },
        }

    def action_run_reset_priority_pickings(self):
        """
        Called from res.config.settings (Run manually button).
        Calls the stock.picking model method that resets priority pickings based on company cutoff.
        Returns a client notification action.
        """
        # Call the worker method as sudo to ensure the operation can update pickings even if a non-admin triggers it.
        result = self.env['stock.picking'].sudo().reset_priority_pickings_based_on_cutoff()

        # result is expected to be a dict with reset_count and reset_ids as implemented.
        reset_count = 0
        if isinstance(result, dict):
            reset_count = int(result.get('reset_count', 0))

        if reset_count:
            message = f"Reset {reset_count} pickings to draft."
        else:
            message = "No pickings were reset."

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reset Priority Pickings',
                'message': message,
                'sticky': False,
            },
        }