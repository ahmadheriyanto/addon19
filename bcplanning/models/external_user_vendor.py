from odoo import models, fields, api
from odoo.exceptions import ValidationError

class bcplanning_external_user_vendor(models.Model):
    _name = 'bcexternaluser'
    _description = 'bcexternaluser'

    user_id = fields.Many2one('res.users', string='User', required=True, domain="[('share', '=', True)]")
    vendor_id = fields.Many2one('res.partner', string='Vendor', required=True, domain="[]") #('company_type', '=', 'company'),('supplier_rank','>',0)

    @api.constrains('user_id')
    def _check_user_unique(self):
        for record in self:
            # search for another record with the same job_no
            existing = self.env['bcexternaluser'].search([
                ('user_id', '=', record.user_id),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('User must be unique!')