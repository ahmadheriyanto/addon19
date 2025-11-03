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