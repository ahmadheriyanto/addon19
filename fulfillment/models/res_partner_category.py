from odoo import models, fields

class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    courier_scoring = fields.Integer(
        string='Courier Scoring',
        help='Numeric scoring value for courier selection/prioritization, high value is high priority',
    )