from odoo import models, fields, api
from odoo.exceptions import ValidationError


class IncomingStaging(models.Model):
    _name = 'incoming_staging'
    _description = 'incoming_staging'
    _rec_name = 'transaction_no'

    transaction_no = fields.Char(string="Transaction No.", required=True)    
    type = fields.Selection(string="Type",
                            selection=[
                                ('',' '),
                                ('inbound','Inbound Order'),
                                ('forder','Fulfillment Order')
                            ], default='', required=True)
    datetime_string = fields.Char(string="Date (yyyy-mm-ddTHH:MM:SS)", required=True)
    products = fields.One2many(
        comodel_name='incoming_staging_product',
        inverse_name='incoming_staging_id',
        string="Product Lines",
        copy=True,
        bypass_search_access=True
    )
    status = fields.Selection(string="Status",
                            selection=[
                                ('open','Open'),
                                ('inbound','Inbound'),
                                ('pick','Picking'),
                                ('pack','Packing'),
                                ('deliver','Deliver')
                            ], default='open', required=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        required=True,
        ondelete='cascade',
        index=True
    )                            

    @api.constrains('transaction_no')
    def _check_name_unique(self):
        for record in self:
            existing = self.env['incoming_staging'].search([
                ('transaction_no', '=', record.transaction_no),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('transaction_no must be unique!')
    

class IncomingStagingProduct(models.Model):
    _name = 'incoming_staging_product'
    _description = 'incoming_staging_product'

    incoming_staging_id = fields.Many2one(
        comodel_name='incoming_staging',
        string="Transaction No.",
        required=True,
        ondelete='cascade',
        index=True
    )
    product_no = fields.Char(string="Product No.")
    product_nanme = fields.Char(string="Product Name")
    product_lot = fields.Char(string="Product Lot No.")
    product_serial = fields.Char(string="Product Serial No.")
    product_qty = fields.Float(string="Quantity")
    product_uom = fields.Char(string="Unit of Measure")