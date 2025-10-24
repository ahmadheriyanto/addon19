from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProductCategoryCustom(models.Model):
    _inherit = 'product.category'

    contact_owner = fields.Many2one('res.partner', string='Owner', index=True, ondelete='cascade')

