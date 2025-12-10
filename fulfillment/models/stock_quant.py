from odoo import api, fields, models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    partner_type = fields.Selection(
        string="Partner Type",
        selection=[
            ('', ''),
            ('b2b', 'B2B'),
            ('b2c', 'B2C'),
        ],
        default='',
        index=True,
    )