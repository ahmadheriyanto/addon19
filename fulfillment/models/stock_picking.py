# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    principal_courier_id = fields.Many2one(
        comodel_name='res.partner',
        string='Principal Courier',
        index=True,
        store=True,
        help='Courier partner resolved from incoming_staging.principal_courier_id when this picking '
             'was created from an incoming_staging record (origin = transaction_no).'
    )

    courier_priority = fields.Char(
        string='Courier priority',
        related='principal_courier_id.courier_scoring_label',
        readonly=True,
        store=True,
        help='Related from principal_courier_id.courier_scoring_label'
    )

    # Helper field: precomputed allowed transporter partners (ids).
    transporter_partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Transporter Partners (computed)',
        compute='_compute_transporter_partner_ids',
        store=True,
        help='Precomputed partners that belong to the company-configured Transporter category. '
             'This field is used by the form domain for principal_courier_id.'
    )

    @api.depends('company_id', 'company_id.fulfillment_transporter_category_id', 'principal_courier_id')
    def _compute_transporter_partner_ids(self):
        """
        Compute transporter_partner_ids as partners that have the company-configured transporter category.
        Stored so the client can use transporter_partner_ids in domains (no python-expression evaluation).
        """
        Partner = self.env['res.partner'].sudo()
        for pick in self:
            comp = pick.company_id or self.env.company
            transporter_cat = comp.fulfillment_transporter_category_id
            if transporter_cat and transporter_cat.id:
                partners = Partner.search([('category_id', 'in', [transporter_cat.id])])
                pick.transporter_partner_ids = partners.ids
            else:
                pick.transporter_partner_ids = [(5, 0, 0)]  # clear

    @api.constrains('principal_courier_id')
    def _check_principal_courier_category(self):
        """
        Server-side validation: principal_courier must belong to company's Transporter category.
        """
        for rec in self:
            partner = rec.principal_courier_id
            if not partner:
                continue
            company = rec.company_id or self.env.company
            transporter_cat = company.fulfillment_transporter_category_id
            if not transporter_cat:
                raise ValidationError(
                    "Transporter category is not configured on the current company. "
                    "Please configure 'Transporter Category' in Fulfillment settings."
                )
            if transporter_cat.id not in partner.category_id.ids:
                raise ValidationError(
                    "Selected courier '%s' is not assigned to the configured Transporter category '%s'."
                    % (partner.display_name, transporter_cat.name)
                )


    # Persisted customer information that comes from incoming_staging.
    # These are simple Char fields so they are stored on the picking record permanently.
    principal_customer_name = fields.Char(
        string='Customer Name',
        help='Customer name carried from incoming staging (kept on the picking)'
    )
    principal_customer_address = fields.Char(
        string='Customer Address',
        help='Customer address carried from incoming staging (kept on the picking)'
    )

    @api.model
    def default_get(self, fields_list):
        """Ensure default_get can supply the fields from context if provided."""
        res = super(StockPicking, self).default_get(fields_list)
        # Accept context defaults supplied from code like {'default_principal_customer_name': '...'}
        ctx = dict(self.env.context or {})
        if 'default_principal_customer_name' in ctx and 'principal_customer_name' in fields_list:
            res.setdefault('principal_customer_name', ctx.get('default_principal_customer_name'))
        if 'default_principal_customer_address' in ctx and 'principal_customer_address' in fields_list:
            res.setdefault('principal_customer_address', ctx.get('default_principal_customer_address'))
        return res

    def copy(self, default=None):
        """
        Ensure copies of pickings (e.g. backorders / manual duplication) preserve the
        principal_customer_name and principal_customer_address values by default.
        """
        default = dict(default or {})
        # preserve values from the original if not explicitly overridden
        default.setdefault('principal_customer_name', self.principal_customer_name)
        default.setdefault('principal_customer_address', self.principal_customer_address)
        return super(StockPicking, self).copy(default=default)