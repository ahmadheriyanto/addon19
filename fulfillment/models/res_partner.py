from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    courier_scoring = fields.Integer(
        string='Courier Scoring',
        compute='_compute_courier_scoring',
        store=True,
        readonly=True,
        help='Computed scoring coming from partner categories (uses category courier_scoring). '
             'If partner has the transporter category (configured on company) then this is the sum of courier_scoring of '
             'categories EXCLUDING the transporter category, otherwise 0.',
    )

    # Boolean used to control visibility of courier fields in the form view.
    show_courier_scoring = fields.Boolean(
        string='Show Courier Scoring Fields',
        compute='_compute_courier_scoring',
        store=True,
        readonly=True,
        help='Computed: True when partner has the configured transporter category, used to show/hide courier fields in the view.'
    )

    courier_scoring_label = fields.Char(
        string='Courier priority',
        compute='_compute_courier_scoring_label',
        store=True,
        readonly=True,
        help="Label based on courier_scoring: 'Standar' (0-30), 'Medium' (31-70), 'Priority' (71-100).",
    )

    @api.depends('category_id.courier_scoring', 'category_id', 'company_id.fulfillment_transporter_category_id')
    def _compute_courier_scoring(self):
        """
        Compute courier_scoring and show_courier_scoring using company-configured transporter category.

        Logic:
         - Determine the transporter category id from partner.company_id.fulfillment_transporter_category_id or
           fallback to current environment company (env.company).
         - If transporter category is configured and partner has that category, courier_scoring = sum of
           courier_scoring of partner's categories excluding transporter category.
         - Otherwise courier_scoring = 0.
         - show_courier_scoring is True iff transporter category is configured and partner has it.
        """
        for partner in self:
            # resolve transporter category id: prefer partner.company_id if set, else env.company
            company = partner.company_id or self.env.company
            transporter_cat = company.fulfillment_transporter_category_id
            transporter_id = transporter_cat.id if transporter_cat else False

            cats = partner.category_id
            if not cats or not transporter_id:
                partner.courier_scoring = 0
                partner.show_courier_scoring = False
                continue

            # sum categories excluding transporter id
            other_sum = sum(int(c.courier_scoring or 0) for c in cats.filtered(lambda c: c.id != transporter_id))

            has_transporter = transporter_id in cats.ids
            partner.show_courier_scoring = bool(has_transporter)

            partner.courier_scoring = int(other_sum or 0) if has_transporter else 0

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """
        Ensure immediate UI update when tags (category_id) change in the form.
        Mirror compute logic to provide updated values to the client before save.
        """
        for partner in self:
            company = partner.company_id or self.env.company
            transporter_cat = company.fulfillment_transporter_category_id
            transporter_id = transporter_cat.id if transporter_cat else False

            cats = partner.category_id
            if not cats or not transporter_id:
                partner.courier_scoring = 0
                partner.show_courier_scoring = False
                continue

            other_sum = sum(int(c.courier_scoring or 0) for c in cats.filtered(lambda c: c.id != transporter_id))
            has_transporter = transporter_id in cats.ids
            partner.show_courier_scoring = bool(has_transporter)
            partner.courier_scoring = int(other_sum or 0) if has_transporter else 0

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

    @api.model
    def refresh_courier_scoring_all(self):
        """
        Recompute and write courier_scoring, show_courier_scoring and courier_scoring_label
        for all partners and persist the stored values.
        Can be called from a settings button.
        """
        Partner = self.sudo()
        partners = Partner.search([])  # consider limiting scope if you have many partners
        for p in partners:
            company = p.company_id or self.env.company
            transporter_cat = company.fulfillment_transporter_category_id
            transporter_id = transporter_cat.id if transporter_cat else False

            cats = p.category_id
            if not cats or not transporter_id:
                score = 0
                show = False
            else:
                other_sum = sum(int(c.courier_scoring or 0) for c in cats.filtered(lambda c: c.id != transporter_id))
                has_transporter = transporter_id in cats.ids
                score = int(other_sum or 0) if has_transporter else 0
                show = bool(has_transporter)

            # compute label
            if score <= 0:
                label = ''
            elif 1 <= score <= 30:
                label = 'Reguler'
            elif 31 <= score <= 70:
                label = 'Medium'
            else:
                label = 'Instan'

            # write only if values changed (optional small optimization)
            vals = {}
            if p.courier_scoring != score:
                vals['courier_scoring'] = score
            if p.show_courier_scoring != show:
                vals['show_courier_scoring'] = show
            if p.courier_scoring_label != label:
                vals['courier_scoring_label'] = label
            if vals:
                p.write(vals)
        return True