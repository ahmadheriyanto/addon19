# -*- coding: utf-8 -*-
# Integrates with stock.picking where courier_priority is a Char related field.
# Computes counts per picking type x (state × priority string) using safe search_count queries.
from odoo import api, fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    count_draft_reguler = fields.Integer(string="Draft / Reguler", compute="_compute_priority_counts")
    count_draft_medium = fields.Integer(string="Draft / Medium", compute="_compute_priority_counts")
    count_draft_instan = fields.Integer(string="Draft / Instan", compute="_compute_priority_counts")

    count_to_process_reguler = fields.Integer(string="To Process / Reguler", compute="_compute_priority_counts")
    count_to_process_medium = fields.Integer(string="To Process / Medium", compute="_compute_priority_counts")
    count_to_process_instan = fields.Integer(string="To Process / Instan", compute="_compute_priority_counts")

    count_waiting_reguler = fields.Integer(string="Waiting / Reguler", compute="_compute_priority_counts")
    count_waiting_medium = fields.Integer(string="Waiting / Medium", compute="_compute_priority_counts")
    count_waiting_instan = fields.Integer(string="Waiting / Instan", compute="_compute_priority_counts")

    count_ready_reguler = fields.Integer(string="Ready / Reguler", compute="_compute_priority_counts")
    count_ready_medium = fields.Integer(string="Ready / Medium", compute="_compute_priority_counts")
    count_ready_instan = fields.Integer(string="Ready / Instan", compute="_compute_priority_counts")

    count_backorder_reguler = fields.Integer(string="Backorder / Reguler", compute="_compute_priority_counts")
    count_backorder_medium = fields.Integer(string="Backorder / Medium", compute="_compute_priority_counts")
    count_backorder_instan = fields.Integer(string="Backorder / Instan", compute="_compute_priority_counts")

    count_done_reguler = fields.Integer(string="Done / Reguler", compute="_compute_priority_counts")
    count_done_medium = fields.Integer(string="Done / Medium", compute="_compute_priority_counts")
    count_done_instan = fields.Integer(string="Done / Instan", compute="_compute_priority_counts")

    @api.depends()
    def _compute_priority_counts(self):
        """Compute counts for each picking.type by state and courier_priority (string based).

        This implementation uses search_count per combination and normalizes courier_priority
        string values to the three buckets: 'reguler', 'medium', 'instan'.
        """
        Picking = self.env['stock.picking']
        picking_fields = Picking._fields

        # initialize zero values
        for rec in self:
            for state in ('draft', 'to_process', 'waiting', 'ready', 'backorder', 'done'):
                for pr in ('reguler', 'medium', 'instan'):
                    setattr(rec, f'count_{state}_{pr}', 0)

        if not self:
            return

        # Normalization from courier_priority text -> pkey
        def normalize_priority_text(text):
            if not text:
                return None
            t = str(text).strip().lower()
            if 'regul' in t or 'regular' in t:
                return 'reguler'
            if 'med' in t:
                return 'medium'
            if 'inst' in t or 'instant' in t:
                return 'instan'
            # exact matches fallback
            if t in ('reguler', 'regular'):
                return 'reguler'
            if t == 'medium':
                return 'medium'
            if t in ('instan', 'instant'):
                return 'instan'
            return None

        # If courier_priority exists as a field on stock.picking, gather the distinct texts
        use_priority_field = 'courier_priority' in picking_fields

        # Precollect distinct priority strings for these picking types (optional, reduces empty searches)
        priority_keys_present = set()
        if use_priority_field:
            # collect unique values (could be many; it's just to avoid many empty search_count)
            pr_vals = Picking.search([('picking_type_id', 'in', self.ids)], limit=0).mapped('courier_priority')
            # If the above returns a generator or list, ensure iteration; sometimes limit=0 returns [], keep safe
            for v in set(pr_vals or []):
                pkey = normalize_priority_text(v)
                if pkey:
                    priority_keys_present.add(pkey)

        # mapping for Odoo states -> our suffix names
        state_map = {
            'draft': 'draft',
            'confirmed': 'to_process',
            'waiting': 'waiting',
            'assigned': 'ready',
            'done': 'done',
        }

        # For each picking type, count per state × priority key
        for rec in self:
            base = [('picking_type_id', '=', rec.id)]
            if use_priority_field:
                # iterate priority buckets (always include the three keys)
                for pkey in ('reguler', 'medium', 'instan'):
                    # build domain for priority: match courier_priority strings that map to this pkey
                    # To avoid loading all string variants, we look for known strings:
                    # - If we earlier found present keys, we only count those keys; otherwise, perform domain with ilike filters as fallback.
                    ids_present = priority_keys_present
                    # We can search directly by courier_priority being ilike certain tokens for fallback
                    for state_raw, suffix in state_map.items():
                        # Build domain
                        domain = list(base) + [('state', '=', state_raw)]
                        # If we have priority examples present, filter by those texts
                        if ids_present:
                            # count by matching texts that normalized to pkey
                            # build a list of original texts that matched pkey
                            texts = [v for v in set(Picking.search(base + [('courier_priority', '!=', False)]).mapped('courier_priority') or []) if normalize_priority_text(v) == pkey]
                            if texts:
                                # match any of exact texts
                                domain.append(('courier_priority', 'in', texts))
                            else:
                                # nothing to match: 0
                                cnt = 0
                                setattr(rec, f'count_{suffix}_{pkey}', getattr(rec, f'count_{suffix}_{pkey}', 0) + cnt)
                                continue
                        else:
                            # fallback: use ilike on tokens
                            if pkey == 'reguler':
                                domain.append(('courier_priority', 'ilike', 'regul'))
                            elif pkey == 'medium':
                                domain.append(('courier_priority', 'ilike', 'med'))
                            else:
                                domain.append(('courier_priority', 'ilike', 'inst'))
                        cnt = Picking.search_count(domain)
                        setattr(rec, f'count_{suffix}_{pkey}', getattr(rec, f'count_{suffix}_{pkey}', 0) + cnt)

                    # backorders per priority
                    if 'backorder_id' in picking_fields:
                        domain_b = list(base) + [('backorder_id', '!=', False)]
                        if ids_present:
                            texts = [v for v in set(Picking.search(base + [('courier_priority', '!=', False)]).mapped('courier_priority') or []) if normalize_priority_text(v) == pkey]
                            if texts:
                                domain_b.append(('courier_priority', 'in', texts))
                                bcnt = Picking.search_count(domain_b)
                            else:
                                bcnt = 0
                        else:
                            if pkey == 'reguler':
                                domain_b.append(('courier_priority', 'ilike', 'regul'))
                            elif pkey == 'medium':
                                domain_b.append(('courier_priority', 'ilike', 'med'))
                            else:
                                domain_b.append(('courier_priority', 'ilike', 'inst'))
                            bcnt = Picking.search_count(domain_b)
                        setattr(rec, f'count_backorder_{pkey}', getattr(rec, f'count_backorder_{pkey}', 0) + bcnt)
            else:
                # priority not present: attribute everything to reguler
                for state_raw, suffix in state_map.items():
                    cnt = Picking.search_count(base + [('state', '=', state_raw)])
                    setattr(rec, f'count_{suffix}_reguler', getattr(rec, f'count_{suffix}_reguler', 0) + cnt)
                if 'backorder_id' in picking_fields:
                    bcnt = Picking.search_count(base + [('backorder_id', '!=', False)])
                    rec.count_backorder_reguler = bcnt