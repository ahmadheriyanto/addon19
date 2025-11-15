# -*- coding: utf-8 -*-
# Integrates with stock.picking where courier_priority is a Char related field.
# Computes counts per picking type x (state × priority string) using robust grouping.
from odoo import api, fields, models, _
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


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

    # overall record count per picking.type (stored); keeps your existing badge working
    picking_count = fields.Integer(
        string="Pickings",
        compute="_compute_picking_count",
        store=True,
        readonly=True,
        help="Total number of stock.picking records for this picking type."
    )

    @api.depends()
    def _compute_picking_count(self):
        """Compute the total number of pickings per picking.type using read_group for performance."""
        Picking = self.env['stock.picking']
        if not self:
            return
        grouped = Picking.read_group([('picking_type_id', 'in', self.ids)], ['picking_type_id'], ['picking_type_id'])
        counts = {g['picking_type_id'][0]: g['picking_type_id_count'] for g in grouped if g.get('picking_type_id')}
        for rec in self:
            rec.picking_count = counts.get(rec.id, 0)

    @api.depends()
    def _compute_priority_counts(self):
        """Robust compute of per-state × per-priority counts.

        - We fetch all pickings for the current picking types and iterate them.
        - courier_priority missing/False is treated as 'reguler'.
        - state values are mapped to the UI buckets.
        """
        Picking = self.env['stock.picking']

        # initialize zero values for all records
        for rec in self:
            for state in ('draft', 'to_process', 'waiting', 'ready', 'backorder', 'done'):
                for pr in ('reguler', 'medium', 'instan'):
                    setattr(rec, f'count_{state}_{pr}', 0)

        if not self:
            return

        # normalization from courier_priority text -> pkey
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
            if t in ('reguler', 'regular'):
                return 'reguler'
            if t == 'medium':
                return 'medium'
            if t in ('instan', 'instant'):
                return 'instan'
            return None

        # map stock.picking.state -> our suffix keys
        state_map = {
            'draft': 'draft',
            'confirmed': 'to_process',  # confirmed = To Process
            'waiting': 'waiting',
            'assigned': 'ready',        # assigned = Ready
            'done': 'done',
        }

        # fetch pickings for these picking_type_ids in one query
        pickings = Picking.search([('picking_type_id', 'in', self.ids)])
        if not pickings:
            return

        # map rec by id for quick lookup
        rec_by_id = {rec.id: rec for rec in self}

        # iterate pickings and increment counters
        for p in pickings:
            ptype = p.picking_type_id and p.picking_type_id.id
            if not ptype or ptype not in rec_by_id:
                continue
            rec = rec_by_id[ptype]

            # normalize priority: treat missing/False/unknown as 'reguler'
            pkey = normalize_priority_text(p.courier_priority) or 'reguler'

            # map state, ignore unknown states
            mapped = state_map.get(p.state)
            if mapped:
                field = f'count_{mapped}_{pkey}'
                # read current, increment by 1
                cur = getattr(rec, field, 0) or 0
                setattr(rec, field, cur + 1)

            # backorder handling: count separately if backorder_id present on the picking
            if hasattr(p, 'backorder_id') and p.backorder_id:
                bfield = f'count_backorder_{pkey}'
                curb = getattr(rec, bfield, 0) or 0
                setattr(rec, bfield, curb + 1)

        # Note: done/other states have been updated by iteration above.

    
    def action_open_pickings(self):
        """Return an action opening stock.picking filtered by picking type, state and priority.

        Context keys expected from the kanban anchor:
          - 'picking_type_id' : int (redundant - we use self.id)
          - 'state'           : 'draft'|'to_process'|'waiting'|'ready'|'backorder'|'done'
          - 'priority'        : 'reguler'|'medium'|'instan'
        """
        self.ensure_one()
        ctx = dict(self.env.context or {})
        state_key = ctx.get('state')
        priority_key = ctx.get('priority')

        domain = [('picking_type_id', '=', self.id)]

        # Backorder special handling
        if state_key == 'backorder':
            domain.append(('backorder_id', '!=', False))
        else:
            state_map = {
                'draft': 'draft',
                'to_process': 'confirmed',
                'waiting': 'waiting',
                'ready': 'assigned',
                'done': 'done',
            }
            mapped_state = state_map.get(state_key)
            if mapped_state:
                domain.append(('state', '=', mapped_state))

        # Priority filter: treat missing/False courier_priority as 'reguler'
        if priority_key:
            if priority_key == 'reguler':
                # include records with no courier_priority as 'reguler' + the usual ilike match
                domain += ['|', ('courier_priority', '=', False), ('courier_priority', 'ilike', 'regul')]
            elif priority_key == 'medium':
                domain.append(('courier_priority', 'ilike', 'med'))
            elif priority_key == 'instan':
                domain.append(('courier_priority', 'ilike', 'inst'))

        # Try to reuse the standard stock pickings action, override domain/context
        try:
            action = self.env.ref('stock.action_picking_tree_all').read()[0]
        except Exception:
            action = {
                'type': 'ir.actions.act_window',
                'name': _('Transfer Orders'),
                'res_model': 'stock.picking',
                'view_mode': 'tree,form',
                'context': {},
            }

        # The action['context'] returned by read() may be:
        # - a dict (already safe)
        # - a string representation of a dict that references names like allowed_company_ids
        # We attempt a safe evaluation and, if needed, provide a minimal globals mapping
        # for commonly used names (e.g. allowed_company_ids) so evaluation succeeds.
        action_context_raw = action.get('context') or {}
        action_context = {}
        if isinstance(action_context_raw, str):
            # provide common names that may appear in stored contexts
            eval_globals = {
                'allowed_company_ids': getattr(self.env.user, 'company_ids', self.env.user.company_id).ids if hasattr(self.env.user, 'company_ids') else [self.env.company.id],
                'uid': self.env.uid,
            }
            try:
                # safe_eval may raise if unknown names are used; catch and fallback
                action_context = safe_eval(action_context_raw, eval_globals)
                if not isinstance(action_context, dict):
                    # if evaluation succeeded but returned e.g. a list, coerce to dict safely
                    action_context = dict(action_context) if isinstance(action_context, (list, tuple)) else {}
            except Exception:
                _logger.exception("Failed to safe_eval action context; falling back to empty dict. Raw context: %r", action_context_raw)
                action_context = {}
        elif isinstance(action_context_raw, dict):
            action_context = dict(action_context_raw)
        else:
            action_context = {}

        # Merge contexts: action context first, then the click ctx overrides
        action_context.update(ctx)
        action['context'] = action_context

        action['domain'] = domain
        return action