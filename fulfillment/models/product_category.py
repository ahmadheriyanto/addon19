from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ProductCategoryCustom(models.Model):
    _inherit = 'product.category'

    contact_owner = fields.Many2one('res.partner', string='Owner', index=True, ondelete='cascade')

    @api.constrains('contact_owner', 'parent_id')
    def _check_contact_owner_constraints(self):
        """
        Enforce two rules at save time:
         - Owner may only be set on top-level categories (parent_id == False).
         - Owner must not be a child contact (partner.parent_id must be False).
        This prevents inconsistent DB state from create/write RPCs or server-side calls.
        """
        for rec in self:
            partner = rec.contact_owner
            if not partner:
                continue
            # Rule: only for main/top-level categories
            if rec.parent_id:
                raise ValidationError(
                    _("Owner can only be set on main (top-level) categories. "
                      "Remove the parent category or clear the Owner field.")
                )
            # Rule: partner must be a top-level contact/company (no parent)
            if partner.parent_id:
                raise ValidationError(
                    _("You cannot set a child contact as Owner. "
                      "Please select the parent/company contact instead.")
                )

    @api.onchange('contact_owner', 'parent_id')
    def _onchange_contact_owner_validate(self):
        """
        UX helper: when user selects an invalid owner (child contact) or the record
        is a sub-category, clear the field and show a warning in the form.
        """
        if self.contact_owner:
            if self.contact_owner.parent_id:
                self.contact_owner = False
                return {
                    'warning': {
                        'title': _('Invalid Owner'),
                        'message': _(
                            'Child contact cannot be set as Owner. '
                            'Please choose the parent/company contact.'
                        ),
                    }
                }
            if self.parent_id:
                # clear because Owner only allowed for top-level categories
                self.contact_owner = False
                return {
                    'warning': {
                        'title': _('Owner only for main category'),
                        'message': _(
                            'Owner field is only available for main (top-level) categories. '
                            'Remove the Parent category or set the Owner on the parent category.'
                        ),
                    }
                }