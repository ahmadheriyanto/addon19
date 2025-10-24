from odoo import models, fields, api
from odoo.exceptions import ValidationError


class IncomingStaging(models.Model):
    _name = 'incoming_staging'
    _description = 'incoming_staging'

    name = fields.Char()
    type = fields.Selection(string="Type",
                            selection=[
                                ('',' '),
                                ('inbound','Inbound Order'),
                                ('forder','Fulfillment Order')
                            ], default='', required=True)


    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            existing = self.env['incoming_staging'].search([
                ('name', '=', record.name),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('name must be unique!')
    

