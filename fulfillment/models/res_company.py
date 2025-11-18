from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    fulfillment_default_operation_type_receipt_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Receipt (B2B)',
        help="Define default operation type for API as receipt (B2B) activity (company-level)",
    )

    fulfillment_default_operation_type_receipt2_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Receipt (B2C)',
        help="Define default operation type for API as receipt (B2C) activity (company-level)",
    )

    fulfillment_default_operation_type_pick_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Pick',
        help="Define default operation type for API as pick activity (company-level)",
    )
    fulfillment_do_not_create_pick = fields.Boolean(string="Do not create pick automatically")

    fulfillment_default_operation_type_oos_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for OOS',
        help="Define default operation type for Pick as Out of Stock (company-level).",
    )

    fulfillment_default_operation_type_return_id = fields.Many2one(
        'stock.picking.type',
        string='Default Operation Type for Return',
        help="Define default operation type for API as return activity (company-level)",
    )

    fulfillment_priority_cutoff_time = fields.Float(
        string='Priority Cut-off Time',
        help="Define cut-off time for Priority picking, reset to draft if more than the time setting.",
    )

    @api.constrains('fulfillment_priority_cutoff_time')
    def _check_priority_cutoff_time(self):
        for rec in self:
            val = rec.fulfillment_priority_cutoff_time
            if val is None:
                continue
            # disallow negative and values >= 24 (prevents entries like 27.00)
            if val < 0 or val >= 24.0:
                raise ValidationError(
                    "Priority Cut-off Time must be between 00:00 and 23:59 (use 0.00 - 23.99 hours)."
                )

    @api.onchange('fulfillment_priority_cutoff_time')
    def _onchange_priority_cutoff_time(self):
        for rec in self:
            val = rec.fulfillment_priority_cutoff_time
            if val is not None and val >= 24.0:
                return {
                    'warning': {
                        'title': 'Invalid time',
                        'message': 'Priority Cut-off Time must be less than 24:00 (00:00-23:59).',
                    }
                }

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