from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    courier_scoring = fields.Integer(
        string='Courier Scoring',
        compute='_compute_courier_scoring',
        store=True,
        readonly=True,
        help='Computed scoring coming from partner categories (uses category courier_scoring). '
             'If partner has category with id Transporter then this is the sum of courier_scoring of categories EXCLUDING id Transporter, '
             'otherwise 0.',
    )

    courier_scoring_label = fields.Char(
        string='Courier priority',
        compute='_compute_courier_scoring_label',
        store=True,
        readonly=True,
        help="Label based on courier_scoring: 'Standar' (0-30), 'Medium' (31-70), 'Priority' (71-100).",
    )

    @api.depends('category_id.courier_scoring', 'category_id')
    def _compute_courier_scoring(self):
        """
        Compute courier_scoring according to the rule:
         - If the partner has a category with id == Transporter, courier_scoring is the SUM of courier_scoring
           values of the partner's categories excluding the category with id Transporter.
         - If the partner does NOT have category id == Transporter, courier_scoring is 0.
        """
        SPECIAL_ID = 4
        for partner in self:
            cats = partner.category_id
            if not cats:
                partner.courier_scoring = 0
                continue

            # sum of categories excluding the special id
            other_sum = sum(int(c.courier_scoring or 0) for c in cats.filtered(lambda c: c.id != SPECIAL_ID))

            # only assign the sum if partner has special category
            if SPECIAL_ID in cats.ids:
                partner.courier_scoring = int(other_sum or 0)
            else:
                partner.courier_scoring = 0

    @api.depends('courier_scoring')
    def _compute_courier_scoring_label(self):
        for partner in self:
            s = partner.courier_scoring or 0
            if s <= 0:
                partner.courier_scoring_label = ''
            elif 1 <= s <= 30:
                partner.courier_scoring_label = 'Reguler'
            elif 31 <= s <= 70:
                partner.courier_scoring_label = 'Medium'
            else:
                partner.courier_scoring_label = 'Instan'