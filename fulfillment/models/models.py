# from odoo import models, fields, api


# class fulfillment(models.Model):
#     _name = 'fulfillment.fulfillment'
#     _description = 'fulfillment.fulfillment'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

