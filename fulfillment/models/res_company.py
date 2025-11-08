from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    fulfillment_default_operation_type_receipt_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Receipt',
        help="Define default operation type for API as receipt activity (company-level)",
    )

    fulfillment_default_operation_type_pick_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Pick',
        help="Define default operation type for API as pick activity (company-level)",
    )

    # Configurable "Transporter" partner category used by courier scoring logic.
    # Admins can pick which partner.category acts as the special category (previously hard-coded id 4).
    fulfillment_transporter_category_id = fields.Many2one(
        'res.partner.category',
        string='Transporter Category',
        help='Partner category considered as "Transporter" for courier scoring rules.',
    )