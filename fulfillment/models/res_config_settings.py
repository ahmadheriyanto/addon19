from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fulfillment_default_operation_type_receipt_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Receipt',
        config_parameter='fulfillment.operationtype.receipt_id',
        help="Define default operation type for API as receipt activity"
    )

    fulfillment_default_operation_type_pick_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Pick',
        config_parameter='fulfillment.operationtype.pick_id',
        help="Define default operation type for API as pick activity"
    )