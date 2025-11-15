# -*- coding: utf-8 -*-
"""
When routes/automation assign moves to an existing picking, Odoo may aggregate moves from
different source documents into a single picking (origin concatenated). This module ensures
moves whose 'origin' differs from the target picking are instead moved into a new picking
(per-origin), preserving your custom picking-level fields.

Important safety:
- To avoid recursion, internal writes performed by this override set the context key
  'skip_move_route_split' so the override short-circuits on re-entry.
- When creating a new picking for a move-origin, prefer copying custom fields from the
  original source picking (searched by origin/name) rather than from the current target
  picking. This ensures fields like principal_customer_name/principal_customer_address
  are preserved correctly.
"""
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class StockMoveRouteSplit(models.Model):
    _inherit = 'stock.move'

    @api.model_create_multi
    def create(self, vals_list):
        # Normal create - no special behavior for move creation here.
        # Route flows often write picking_id later; we handle splitting in write().
        return super(StockMoveRouteSplit, self).create(vals_list)

    def write(self, vals):
        # Safety guard: if caller set skip flag, do not attempt splitting (avoid recursion)
        if self.env.context.get('skip_move_route_split'):
            return super(StockMoveRouteSplit, self).write(vals)

        # If no picking assignment is happening, delegate to super immediately.
        if 'picking_id' not in vals:
            return super(StockMoveRouteSplit, self).write(vals)

        assign_pid = vals.get('picking_id')
        moves = self

        # Apply other writes (if any) first
        other_vals = {k: v for k, v in vals.items() if k != 'picking_id'}
        res = True
        if other_vals:
            res = super(StockMoveRouteSplit, moves).write(other_vals)

        # If assign_pid falsy, it means the caller is clearing picking_id -> fallback to normal assignment
        if not assign_pid:
            return super(StockMoveRouteSplit, moves).write({'picking_id': assign_pid})

        target_pick = self.env['stock.picking'].browse(assign_pid)
        if not target_pick.exists():
            # fallback to normal behavior if pick doesn't exist
            return super(StockMoveRouteSplit, moves).write({'picking_id': assign_pid})

        # Group moves by their move.origin (string). Use empty string for falsy values.
        groups = {}
        for mv in moves:
            mv_origin = (mv.origin or '').strip()
            groups.setdefault(mv_origin, self.env['stock.move'])
            groups[mv_origin] = groups[mv_origin] | mv

        # If only one origin group and it matches the target picking origin (or target has no origin),
        # then assign them all to the target picking (normal behavior). Use skip flag to avoid recursion.
        if len(groups) == 1:
            only_origin = next(iter(groups.keys()))
            t_origin = (target_pick.origin or '').strip()
            if only_origin == t_origin or (not t_origin and not only_origin):
                # All moves share the same origin as target -> normal assign
                moves.with_context(skip_move_route_split=True).sudo().write({'picking_id': target_pick.id})
                return res

        # Otherwise, split assignments:
        target_origin = (target_pick.origin or '').strip()
        created_for_origin = {}

        # fields to preserve (extend if you have more)
        custom_fields = [
            'principal_courier_id',
            'principal_customer_name',
            'principal_customer_address',
            'courier_priority',
        ]

        for origin, mv_group in groups.items():
            # If origin matches the target picking origin, assign to target
            if origin == target_origin or (not origin and not target_origin):
                mv_group.with_context(skip_move_route_split=True).sudo().write({'picking_id': target_pick.id})
                continue

            # Create or reuse a picking for this origin
            if origin in created_for_origin:
                new_pick = created_for_origin[origin]
            else:
                # Try to find the original/source picking for this origin to copy fields from
                source_pick = None
                if origin:
                    # 1) exact name match
                    source_pick = self.env['stock.picking'].search([('name', '=', origin)], limit=1)
                    # 2) origin field match
                    if not source_pick:
                        source_pick = self.env['stock.picking'].search([('origin', '=', origin)], limit=1)
                    # 3) fallback ilike search (conservative)
                    if not source_pick:
                        try:
                            source_pick = self.env['stock.picking'].search(['|', ('origin', 'ilike', origin), ('name', 'ilike', origin)], limit=1)
                        except Exception:
                            source_pick = None

                # Build pick values: prefer source_pick when available, otherwise fallback to target_pick
                src = source_pick or target_pick
                pick_vals = {
                    'partner_id': src.partner_id.id or False,
                    'picking_type_id': target_pick.picking_type_id.id or False,
                    'location_id': target_pick.location_id.id or False,
                    'location_dest_id': target_pick.location_dest_id.id or False,
                    'origin': origin or False,
                    'scheduled_date': target_pick.scheduled_date,
                    'company_id': target_pick.company_id.id or False,
                }
                # preserve custom fields from src if present and not falsy
                for cf in custom_fields:
                    try:
                        cf_val = getattr(src, cf)
                    except Exception:
                        cf_val = False
                    if cf_val:
                        pick_vals[cf] = cf_val.id if hasattr(cf_val, 'id') else cf_val

                try:
                    # Create with sudo and no special context so create() logic runs normally.
                    new_pick = self.env['stock.picking'].sudo().create({k: v for k, v in pick_vals.items() if v is not None})
                    created_for_origin[origin] = new_pick
                    _logger.debug("Created split picking %s for origin %r (from source %s)", new_pick.name, origin, (src and src.name) or False)
                except Exception:
                    _logger.exception("Failed to create split picking for origin %r (target %s)", origin, target_pick.id)
                    # fallback: assign to target if creation failed
                    mv_group.with_context(skip_move_route_split=True).sudo().write({'picking_id': target_pick.id})
                    continue

            # Assign the group moves to the new picking (use skip flag to avoid recursion)
            try:
                mv_group.with_context(skip_move_route_split=True).sudo().write({'picking_id': new_pick.id})
            except Exception:
                _logger.exception("Failed to assign moves %s to new picking %s", mv_group.ids, new_pick.id)
                # fallback to assign to target
                mv_group.with_context(skip_move_route_split=True).sudo().write({'picking_id': target_pick.id})

        return res