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

    # Company-level transporter category exposed in settings for easy configuration
    fulfillment_transporter_category_id = fields.Many2one(
        'res.partner.category',
        related='company_id.fulfillment_transporter_category_id',
        string='Transporter Category',
        readonly=False,
        help='Company-level partner category used as the Transporter (special) category for courier scoring.',
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