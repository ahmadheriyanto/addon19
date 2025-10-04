from odoo import models, fields, api

class bcplanning_external_user_vendor(models.Model):
    _name = 'bcexternaluser'
    _description = 'bcexternaluser'

    user_id = fields.Many2one('res.users', string='User', domain="[('share', '=', True)]")
    vendor_id = fields.Many2one('res.partner', string='Vendor', domain="[]") #('company_type', '=', 'company'),('supplier_rank','>',0)