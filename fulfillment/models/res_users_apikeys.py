from odoo import models, fields, api

class ResUsersApikeys(models.Model):
    _inherit = 'res.users.apikeys'

    # Computed helper fields for listing only. Not storing plaintext secret.
    index_prefix = fields.Char(
        string='Key index',
        compute='_compute_masked',
        readonly=True,
        store=False,
        help="Database index prefix for the key (not the secret)."
    )
    masked_key = fields.Char(
        string='API Key (masked)',
        compute='_compute_masked',
        readonly=True,
        store=False,
        help="Masked representation of the API key (prefix + mask)."
    )

    @api.model
    def _fetch_index_for_ids(self, ids):
        """Return dict {id: index} for given ids by a single SQL query."""
        if not ids:
            return {}
        query = "SELECT id, index FROM res_users_apikeys WHERE id = ANY(%s)"
        # psycopg2 adapts Python list into SQL array; pass as single parameter
        self.env.cr.execute(query, (ids,))
        return dict(self.env.cr.fetchall())

    def _compute_masked(self):
        """Compute index_prefix and masked_key values. We intentionally do not expose the real key."""
        if not self:
            return
        # collect ids and fetch in one query for efficiency
        ids = [r.id for r in self]
        idx_map = self._fetch_index_for_ids(ids)
        for rec in self:
            idx = idx_map.get(rec.id)
            if idx:
                rec.index_prefix = idx
                # Masked display: show prefix then masked chars.
                # This is purely cosmetic and does not reveal the real key.
                rec.masked_key = f"{idx}••••••"
            else:
                rec.index_prefix = False
                rec.masked_key = False

    # # Optional: invalidate cache on create/write/unlink so list view reflects changes immediately.
    # # This is useful because the computed fields are non-stored and rely on reading DB 'index' column.
    # def create(self, vals):
    #     rec = super().create(vals)
    #     # ensure computed values are recalculated on next read for affected records
    #     rec.invalidate_cache(['index_prefix', 'masked_key'])
    #     return rec

    # def write(self, vals):
    #     res = super().write(vals)
    #     # invalidate cache for affected records
    #     self.invalidate_cache(['index_prefix', 'masked_key'])
    #     return res

    # def unlink(self):
    #     # store ids for possible logging/audit (self will be invalid after super)
    #     affected = self.ids[:]
    #     res = super().unlink()
    #     # invalidate cache globally for safety (or target specific ids if you prefer)
    #     self.env['res.users.apikeys'].invalidate_cache(['index_prefix', 'masked_key'])
    #     return res