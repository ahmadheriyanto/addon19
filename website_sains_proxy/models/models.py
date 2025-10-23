# from odoo import models, fields, api


# class website_sains_proxy(models.Model):
#     _name = 'website_sains_proxy.website_sains_proxy'
#     _description = 'website_sains_proxy.website_sains_proxy'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

