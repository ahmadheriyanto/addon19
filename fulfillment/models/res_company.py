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

    fulfillment_default_operation_type_oos_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for OOS',
        help="Define default operation type for Pick as Out of Stock (company-level).",
    )

    # Configurable "Transporter" partner category used by courier scoring logic.
    # Admins can pick which partner.category acts as the special category (previously hard-coded id 4).
    fulfillment_transporter_category_id = fields.Many2one(
        'res.partner.category',
        string='Transporter Category',
        help='Partner category considered as "Transporter" for courier scoring rules.',
    )

    # Courier scoring classification thresholds and labels (configurable per company)
    # Thresholds are upper bounds for the category:
    # - Reguler: score <= threshold_reguler
    # - Medium: threshold_reguler < score <= threshold_medium
    # - Priority/Instan: score > threshold_medium
    fulfillment_courier_threshold_reguler = fields.Integer(
        string='Courier threshold (Reguler max)',
        default=30,
        help='Maximum courier_scoring value considered "Reguler" (inclusive).'
    )
    fulfillment_courier_threshold_medium = fields.Integer(
        string='Courier threshold (Medium max)',
        default=70,
        help='Maximum courier_scoring value considered "Medium" (inclusive). Values above this are Priority/Instan.'
    )

    # Labels (strings) for the categories
    fulfillment_courier_label_reguler = fields.Char(
        string='Label for Reguler',
        default='Reguler',
        help='Label used when courier_scoring is in Reguler range.'
    )
    fulfillment_courier_label_medium = fields.Char(
        string='Label for Medium',
        default='Medium',
        help='Label used when courier_scoring is in Medium range.'
    )
    fulfillment_courier_label_priority = fields.Char(
        string='Label for Priority',
        default='Instan',
        help='Label used when courier_scoring is Priority (above medium threshold).'
    )