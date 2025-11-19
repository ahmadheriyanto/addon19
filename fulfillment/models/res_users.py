# Safe Odoo 19-compatible override of res.users.action_get
# - Ensures the method is a model method (@api.model) so RPC unpacking is correct
# - Calls the normal implementation but falls back to the base 'base' implementation
#   if the hr override raises IndexError (the observed bug)
# - Computes the 'groups' mapping defensively so missing external ids don't raise
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def action_get(self):
        """
        Call super().action_get() but be defensive:
        - If hr's implementation raises IndexError (due to groups without external ids),
          fall back to the base implementation from odoo.addons.base.models.res_users.
        - Always compute a safe 'groups' mapping (skip empty external-id lists)
          and set it in the result.
        """
        # Try the normal (possibly overridden by hr) implementation first.
        try:
            res = super(ResUsers, self).action_get()
        except IndexError:
            # hr.action_get crashed due to groups with empty external-id lists.
            # Fall back to the base implementation (skip hr override) to obtain a sane result.
            try:
                from odoo.addons.base.models.res_users import ResUsers as BaseResUsers
                # Call the base implementation directly, passing the current recordset as self.
                res = BaseResUsers.action_get(self)
            except Exception:
                # As a last resort, return a minimal safe response structure.
                res = {
                    "groups": {},
                }

        # Compute a defensive groups mapping from external ids.
        groups_map = {}
        try:
            ext_values = self.env.user.all_group_ids._get_external_ids().values()
            for group_xml_list in ext_values:
                if not group_xml_list:
                    # skip empty lists (group has no external id)
                    continue
                try:
                    key = group_xml_list[0]
                except Exception:
                    continue
                if key:
                    groups_map[key] = True
        except Exception:
            # If anything goes wrong while computing groups, fallback to empty map.
            groups_map = {}

        # Ensure the response always contains 'groups' (override whatever res had).
        res["groups"] = groups_map
        return res