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