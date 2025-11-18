# -*- coding: utf-8 -*-
"""
Enhances incoming_staging transfer creation to support:
 - inbound  -> receipts (existing behavior)
 - forder   -> pickings (existing behavior)
 - return   -> receipts using the company-configured 'return' operation type
              or the per-staging operation_type_id if set.

This file is effectively your original incoming_staging processing code
with added support for type == 'return'. The return flow behaves the same
as inbound receipts but resolves the picking type using:
  - incoming_staging.operation_type_id (if set), else
  - company.fulfillment_default_operation_type_return_id (if set)

If neither is configured a ValidationError is raised.
"""
from odoo import api, fields, models
from odoo import fields as odoo_fields
from odoo.exceptions import ValidationError
from odoo.fields import Command
import logging
import re

_logger = logging.getLogger(__name__)


class IncomingStagingStockReceipt(models.Model):
    _inherit = 'incoming_staging'

    # Field to persist last processing result so the QWeb view can display it
    result_message = fields.Text(string="Result Message", readonly=True)

    def action_create_transfer(self):
        """
        Dispatch method:
        - For incoming_staging records with status == 'open' and type == 'inbound' call action_create_transfer_receive.
        - For incoming_staging records with status == 'open' and type == 'forder' call action_create_transfer_pick.
        - For incoming_staging records with status == 'open' and type == 'return' call action_create_transfer_return.
        - Returns combined results list for all processed records.
        """
        results = []
        # Work on sudo to avoid permission issues when creating lots/move_lines
        recs = self.sudo()

        inbound = recs.filtered(lambda r: r.status == 'open' and r.type == 'inbound')
        forder = recs.filtered(lambda r: r.status == 'open' and r.type == 'forder')
        returns = recs.filtered(lambda r: r.status == 'open' and r.type == 'return')
        others = recs - inbound - forder - returns

        if inbound:
            try:
                results += inbound.action_create_transfer_receive()
            except Exception as e:
                _logger.exception("Error while creating receipts for inbound records: %s", e)
                for r in inbound:
                    results.append({'staging_id': r.id, 'error': str(e)})

        if forder:
            try:
                results += forder.action_create_transfer_pick()
            except Exception as e:
                _logger.exception("Error while creating pick transfers for forder records: %s", e)
                for r in forder:
                    results.append({'staging_id': r.id, 'error': str(e)})

        if returns:
            try:
                results += returns.action_create_transfer_return()
            except Exception as e:
                _logger.exception("Error while creating receipts for return records: %s", e)
                for r in returns:
                    results.append({'staging_id': r.id, 'error': str(e)})

        # mark skipped/others as skipped in results
        for r in others:
            results.append({'staging_id': r.id, 'note': 'skipped_not_open_or_unhandled_type', 'state': r.status, 'type': r.type})

        return results

    def action_create_transfer_pick(self):
        """
        Create 'pick' pickings for incoming_staging records where type == 'forder'.

        Similar to action_create_transfer_receive but:
        - Uses the configured pick operation type (fulfillment.operationtype.pick_id).
        - On success, updates incoming_staging.status to 'pick' (per request).
        - Leaves created pickings confirmed/assigned (Ready) — does not auto-validate.
        """
        results = []
        env = self.sudo().env

        for rec in self.sudo():
            try:
                if not (rec.status == 'open' and rec.type == 'forder'):
                    msg = f"Skipped staging {rec.id}: status={rec.status} type={rec.type}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'note': 'skipped_not_open_or_not_forder', 'state': rec.status, 'type': rec.type})
                    continue

                # Idempotency: if a non-cancelled picking with this origin already exists, return it
                existing = env['stock.picking'].search([('origin', '=', rec.transaction_no), ('state', '!=', 'cancel')], limit=1)
                if existing:
                    msg = f"Picking already exists: {existing.name} (id={existing.id}) state={existing.state}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'picking_id': existing.id, 'picking_name': existing.name, 'state': existing.state, 'note': 'existing_picking_returned'})
                    continue

                # Resolve picking type id from system parameter for pick
                param_val = self.env['ir.config_parameter'].sudo().get_param('fulfillment.operationtype.pick_id')
                if not param_val:
                    raise ValidationError("Default pick operation type is not configured (fulfillment.operationtype.pick_id).")
                try:
                    picking_type_id = int(param_val)
                except Exception:
                    m = re.search(r'(\d+)', str(param_val))
                    if m:
                        picking_type_id = int(m.group(1))
                    else:
                        raise ValidationError(f"Invalid picking type configured: {param_val!r}")

                picking_type = env['stock.picking.type'].browse(picking_type_id)
                if not picking_type.exists():
                    raise ValidationError(f"Picking Type with id {picking_type_id} (configured in fulfillment.operationtype.pick_id) does not exist!")
                if not picking_type.default_location_src_id:
                    raise ValidationError(f"default_location_src_id is not set on picking type {picking_type.name}")
                if not picking_type.default_location_dest_id:
                    raise ValidationError(f"default_location_dest_id is not set on picking type {picking_type.name}")

                # Build moves and collect metadata (preserve order)
                move_vals_list = []
                move_metadata = []
                for line in rec.products:
                    uom = rec._ensure_uom(line.product_uom or 'Unit')
                    product = rec._ensure_product(line.product_no, line.product_nanme, uom)
                    qty = float(line.product_qty or 0.0)

                    incoming_tracking = (line.tracking_type or 'none')
                    incoming_tracking_no = (line.tracking_no or '').strip()

                    # Ensure template is storable and has correct tracking so UI doesn't hide lot fields
                    if incoming_tracking in ('lot', 'serial'):
                        tmpl = product.product_tmpl_id
                        tmpl_vals = {}
                        if not tmpl.is_storable:
                            tmpl_vals['is_storable'] = True
                        if tmpl.tracking != incoming_tracking:
                            tmpl_vals['tracking'] = incoming_tracking
                        if tmpl_vals:
                            tmpl.sudo().write(tmpl_vals)

                    move_vals = {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'product_uom': uom.id,
                        'location_id': picking_type.default_location_src_id.id,
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'origin': rec.transaction_no,
                    }
                    move_vals_list.append((0, 0, move_vals))
                    move_metadata.append({
                        'product': product,
                        'qty': qty,
                        'incoming_tracking': incoming_tracking,
                        'incoming_tracking_no': incoming_tracking_no,
                    })

                # Prepare base picking values
                picking_vals = {
                    'partner_id': rec.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'origin': rec.transaction_no,
                    'scheduled_date': odoo_fields.Datetime.now(),
                    'move_ids': move_vals_list,
                }

                # Prepare context for create (so default_get can pick defaults if used)
                ctx = dict(env.context or {})

                # Carry-forward courier fields from incoming_staging into stock.picking
                # rec is sudo() record, so principal_courier_id is accessible
                if getattr(rec, 'principal_courier_id', False):
                    picking_vals['principal_courier_id'] = rec.principal_courier_id.id
                    picking_vals['courier_priority'] = rec.principal_courier_id.courier_scoring_label or ''

                # --- ADDED CODE START: propagate principal_customer_name/address into picking and context ---
                if getattr(rec, 'principal_customer_name', False):
                    picking_vals['principal_customer_name'] = rec.principal_customer_name
                    ctx.setdefault('default_principal_customer_name', rec.principal_customer_name)
                if getattr(rec, 'principal_customer_address', False):
                    picking_vals['principal_customer_address'] = rec.principal_customer_address
                    ctx.setdefault('default_principal_customer_address', rec.principal_customer_address)
                # --- ADDED CODE END ---

                # Create picking using the prepared context
                picking = env['stock.picking'].with_context(ctx).create(picking_vals)

                # Confirm and assign -> picking should become 'assigned' (Ready)
                try:
                    if hasattr(picking, 'action_confirm'):
                        picking.action_confirm()
                except Exception:
                    _logger.exception("action_confirm failed for picking %s", picking.id)
                    raise ValidationError(f"action_confirm failed for picking {picking.id}")
                try:
                    if hasattr(picking, 'action_assign'):
                        picking.action_assign()
                    elif hasattr(picking, '_action_assign'):
                        picking._action_assign()
                except Exception:
                    _logger.exception("assignment failed for picking %s", picking.id)
                    raise ValidationError(f"assignment failed for picking {picking.id}")

                # Apply lots/serials and canonicalize move lines (leave picking un-validated)
                try:
                    pk = picking.sudo()
                    moves = pk.move_ids.sorted(key=lambda m: m.id)
                    for move, meta in zip(moves, move_metadata):
                        product = meta['product']
                        qty = meta['qty']
                        incoming_tracking = meta['incoming_tracking']
                        incoming_tracking_no = meta['incoming_tracking_no']

                        # Prepare lot ids
                        lot_ids = []
                        if incoming_tracking == 'lot':
                            if not incoming_tracking_no:
                                raise ValidationError(f"tracking_type='lot' but no tracking_no provided for {product.display_name}")
                            lot = env['stock.lot'].search([('name', '=', incoming_tracking_no), ('product_id', '=', product.id)], limit=1)
                            if not lot:
                                lot = env['stock.lot'].sudo().create({'name': incoming_tracking_no, 'product_id': product.id})
                            lot_ids = [lot.id]
                        elif incoming_tracking == 'serial':
                            serials = [s.strip() for s in re.split(r'[,\n;|]+', incoming_tracking_no) if s.strip()]
                            if not serials:
                                raise ValidationError(f"tracking_type='serial' but no serials provided for {product.display_name}")
                            if int(qty) != len(serials):
                                raise ValidationError(f"Qty {qty} does not match number of serials ({len(serials)}) for {product.display_name}")
                            for serial in serials:
                                lot = env['stock.lot'].search([('name', '=', serial), ('product_id', '=', product.id)], limit=1)
                                if not lot:
                                    lot = env['stock.lot'].sudo().create({'name': serial, 'product_id': product.id})
                                lot_ids.append(lot.id)

                        # Attach lot_ids to the move if any
                        if lot_ids:
                            move.sudo().write({'lot_ids': [(6, 0, lot_ids)]})

                        # Ask core to build/update move_line_ids from move.lot_ids
                        try:
                            move.sudo()._set_lot_ids()
                        except Exception:
                            _logger.exception("move._set_lot_ids() failed for move %s", move.id)

                        # Remove placeholders (we'll create canonical move lines ourselves)
                        existing_mls = move.move_line_ids
                        if existing_mls:
                            try:
                                existing_mls.sudo().unlink()
                            except Exception:
                                for ml in existing_mls:
                                    try:
                                        ml.sudo().unlink()
                                    except Exception:
                                        _logger.exception("Could not unlink placeholder move_line %s for move %s", ml.id, move.id)

                        desired_qty = float(move.product_uom_qty or 0.0)
                        move_uom_id = getattr(move, 'product_uom', None)
                        move_uom_id = move_uom_id.id if move_uom_id else product.uom_id.id

                        if lot_ids:
                            if product.tracking == 'serial':
                                for lid in lot_ids:
                                    lot_rec = env['stock.lot'].browse(lid)
                                    ml_vals = {
                                        'picking_id': pk.id,
                                        'move_id': move.id,
                                        'product_id': product.id,
                                        'product_uom_id': move_uom_id,
                                        'quantity': 1.0,
                                        'qty_done': 1.0,
                                        'location_id': move.location_id.id,
                                        'location_dest_id': move.location_dest_id.id,
                                        'lot_id': lid,
                                        'lot_name': lot_rec.name if lot_rec else False,
                                    }
                                    env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                            else:
                                # Lot tracking: set quantity = desired_qty and qty_done = desired_qty
                                lot_rec = env['stock.lot'].browse(lot_ids[0]) if lot_ids else None
                                ml_vals = {
                                    'picking_id': pk.id,
                                    'move_id': move.id,
                                    'product_id': product.id,
                                    'product_uom_id': move_uom_id,
                                    'quantity': desired_qty,
                                    'qty_done': desired_qty,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'lot_id': lot_ids[0],
                                    'lot_name': lot_rec.name if lot_rec else False,
                                }
                                env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                        else:
                            # No tracking: create a single move_line with the full qty
                            ml_vals = {
                                'picking_id': pk.id,
                                'move_id': move.id,
                                'product_id': product.id,
                                'product_uom_id': move_uom_id,
                                'quantity': desired_qty,
                                'qty_done': desired_qty,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                            }
                            env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})

                    # end for moves
                except Exception as e:
                    _logger.exception("Failed to apply lots/serials for picking %s", picking.id)
                    msg = f"Picking {picking.name} (id={picking.id}) created but error applying lots/serials: {e}"
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'error': str(e)})
                    continue

                # Do NOT auto-validate. Leave picking in 'assigned' (Ready).
                # Persist result message for display in the incoming_staging form view.
                msg = f"Picking {picking.name} (id={picking.id}) created and assigned (state={picking.state}). Please process/validate manually."
                # Update status to 'pick' as requested
                rec.sudo().write({'status': 'pick', 'result_message': msg})

                # Optionally send a realtime notification to current user (non-blocking)
                try:
                    env['bus.bus'].sendone(
                        ('res.users', env.uid),
                        {'type': 'simple_notification', 'title': 'Create Pick Result', 'message': msg, 'sticky': True}
                    )
                except Exception:
                    _logger.exception("Failed to send bus notification for picking %s", picking.id)

                results.append({'staging_id': rec.id, 'picking_id': picking.id, 'state': picking.state, 'message': msg})

            except Exception as exc:
                _logger.exception("Failed to create pick for incoming_staging %s", rec.id)
                msg = f"Failed to create pick: {exc}"
                try:
                    rec.sudo().write({'result_message': msg})
                except Exception:
                    _logger.exception("Failed to write result_message on staging %s", rec.id)
                results.append({'staging_id': rec.id, 'error': str(exc)})
        return results

    def action_create_transfer_return(self):
        """
        Create receipt pickings for incoming_staging records where type == 'return'.

        Behavior mirrors action_create_transfer_receive except:
        - The picking_type is resolved from:
            rec.operation_type_id if set, else company.fulfillment_default_operation_type_return_id
        - On success, updates incoming_staging.status to 'return'
        """
        results = []
        env = self.sudo().env

        for rec in self.sudo():
            try:
                if not (rec.status == 'open' and rec.type == 'return'):
                    msg = f"Skipped staging {rec.id}: status={rec.status} type={rec.type}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'note': 'skipped_not_open_or_not_return', 'state': rec.status, 'type': rec.type})
                    continue

                # Idempotency: return existing non-cancelled picking
                existing = env['stock.picking'].search([('origin', '=', rec.transaction_no), ('state', '!=', 'cancel')], limit=1)
                if existing:
                    msg = f"Picking already exists: {existing.name} (id={existing.id}) state={existing.state}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'picking_id': existing.id, 'picking_name': existing.name, 'state': existing.state, 'note': 'existing_picking_returned'})
                    continue

                # Resolve picking type: per-record operation_type_id or company default for returns
                picking_type = None
                if getattr(rec, 'operation_type_id', False):
                    picking_type = env['stock.picking.type'].browse(rec.operation_type_id.id)
                else:
                    picking_type = env.company.sudo().fulfillment_default_operation_type_return_id

                if not picking_type:
                    raise ValidationError("Default return operation type is not configured on the company or in incoming_staging.operation_type_id.")

                if not picking_type.exists():
                    raise ValidationError(f"Picking Type {picking_type} does not exist!")

                if not picking_type.default_location_src_id:
                    raise ValidationError(f"default_location_src_id is not set on picking type {picking_type.name}")
                if not picking_type.default_location_dest_id:
                    raise ValidationError(f"default_location_dest_id is not set on picking type {picking_type.name}")

                # Build moves and collect metadata (preserve order)
                move_vals_list = []
                move_metadata = []
                for line in rec.products:
                    uom = rec._ensure_uom(line.product_uom or 'Unit')
                    product = rec._ensure_product(line.product_no, line.product_nanme, uom)
                    qty = float(line.product_qty or 0.0)

                    incoming_tracking = (line.tracking_type or 'none')
                    incoming_tracking_no = (line.tracking_no or '').strip()

                    # Ensure template is storable and has correct tracking so UI doesn't hide lot fields
                    if incoming_tracking in ('lot', 'serial'):
                        tmpl = product.product_tmpl_id
                        tmpl_vals = {}
                        if not tmpl.is_storable:
                            tmpl_vals['is_storable'] = True
                        if tmpl.tracking != incoming_tracking:
                            tmpl_vals['tracking'] = incoming_tracking
                        if tmpl_vals:
                            tmpl.sudo().write(tmpl_vals)

                    move_vals = {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'product_uom': uom.id,
                        'location_id': picking_type.default_location_src_id.id,
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'origin': rec.transaction_no,
                    }
                    move_vals_list.append((0, 0, move_vals))
                    move_metadata.append({
                        'product': product,
                        'qty': qty,
                        'incoming_tracking': incoming_tracking,
                        'incoming_tracking_no': incoming_tracking_no,
                    })

                picking_vals = {
                    'partner_id': rec.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'origin': rec.transaction_no,
                    'scheduled_date': odoo_fields.Datetime.now(),
                    'move_ids': move_vals_list,
                }

                # Create picking
                picking = env['stock.picking'].create(picking_vals)

                # Confirm and assign -> picking should become 'assigned' (Ready)
                try:
                    if hasattr(picking, 'action_confirm'):
                        picking.action_confirm()
                except Exception:
                    _logger.exception("action_confirm failed for picking %s", picking.id)
                    raise ValidationError(f"action_confirm failed for picking {picking.id}")
                try:
                    if hasattr(picking, 'action_assign'):
                        picking.action_assign()
                    elif hasattr(picking, '_action_assign'):
                        picking._action_assign()
                except Exception:
                    _logger.exception("assignment failed for picking %s", picking.id)
                    raise ValidationError(f"assignment failed for picking {picking.id}")

                # Apply lots/serials and canonicalize move lines (leave picking un-validated)
                try:
                    pk = picking.sudo()
                    moves = pk.move_ids.sorted(key=lambda m: m.id)
                    for move, meta in zip(moves, move_metadata):
                        product = meta['product']
                        qty = meta['qty']
                        incoming_tracking = meta['incoming_tracking']
                        incoming_tracking_no = meta['incoming_tracking_no']

                        # Prepare lot ids
                        lot_ids = []
                        if incoming_tracking == 'lot':
                            if not incoming_tracking_no:
                                raise ValidationError(f"tracking_type='lot' but no tracking_no provided for {product.display_name}")
                            lot = env['stock.lot'].search([('name', '=', incoming_tracking_no), ('product_id', '=', product.id)], limit=1)
                            if not lot:
                                lot = env['stock.lot'].sudo().create({'name': incoming_tracking_no, 'product_id': product.id})
                            lot_ids = [lot.id]
                        elif incoming_tracking == 'serial':
                            serials = [s.strip() for s in re.split(r'[,\n;|]+', incoming_tracking_no) if s.strip()]
                            if not serials:
                                raise ValidationError(f"tracking_type='serial' but no serials provided for {product.display_name}")
                            if int(qty) != len(serials):
                                raise ValidationError(f"Qty {qty} does not match number of serials ({len(serials)}) for {product.display_name}")
                            for serial in serials:
                                lot = env['stock.lot'].search([('name', '=', serial), ('product_id', '=', product.id)], limit=1)
                                if not lot:
                                    lot = env['stock.lot'].sudo().create({'name': serial, 'product_id': product.id})
                                lot_ids.append(lot.id)

                        # Attach lot_ids to the move if any
                        if lot_ids:
                            move.sudo().write({'lot_ids': [(6, 0, lot_ids)]})

                        # Ask core to build/update move_line_ids from move.lot_ids
                        try:
                            move.sudo()._set_lot_ids()
                        except Exception:
                            _logger.exception("move._set_lot_ids() failed for move %s", move.id)

                        # Remove placeholders (we'll create canonical move lines ourselves)
                        existing_mls = move.move_line_ids
                        if existing_mls:
                            try:
                                existing_mls.sudo().unlink()
                            except Exception:
                                for ml in existing_mls:
                                    try:
                                        ml.sudo().unlink()
                                    except Exception:
                                        _logger.exception("Could not unlink placeholder move_line %s for move %s", ml.id, move.id)

                        desired_qty = float(move.product_uom_qty or 0.0)
                        move_uom_id = getattr(move, 'product_uom', None)
                        move_uom_id = move_uom_id.id if move_uom_id else product.uom_id.id

                        if lot_ids:
                            if product.tracking == 'serial':
                                for lid in lot_ids:
                                    lot_rec = env['stock.lot'].browse(lid)
                                    ml_vals = {
                                        'picking_id': pk.id,
                                        'move_id': move.id,
                                        'product_id': product.id,
                                        'product_uom_id': move_uom_id,
                                        'quantity': 1.0,
                                        'qty_done': 1.0,
                                        'location_id': move.location_id.id,
                                        'location_dest_id': move.location_dest_id.id,
                                        'lot_id': lid,
                                        'lot_name': lot_rec.name if lot_rec else False,
                                    }
                                    env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                            else:
                                # Lot tracking: set quantity = desired_qty and qty_done = desired_qty
                                lot_rec = env['stock.lot'].browse(lot_ids[0]) if lot_ids else None
                                ml_vals = {
                                    'picking_id': pk.id,
                                    'move_id': move.id,
                                    'product_id': product.id,
                                    'product_uom_id': move_uom_id,
                                    'quantity': desired_qty,
                                    'qty_done': desired_qty,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'lot_id': lot_ids[0],
                                    'lot_name': lot_rec.name if lot_rec else False,
                                }
                                env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                        else:
                            # No tracking: create a single move_line with the full qty
                            ml_vals = {
                                'picking_id': pk.id,
                                'move_id': move.id,
                                'product_id': product.id,
                                'product_uom_id': move_uom_id,
                                'quantity': desired_qty,
                                'qty_done': desired_qty,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                            }
                            env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})

                    # end for moves
                except Exception as e:
                    _logger.exception("Failed to apply lots/serials for picking %s", picking.id)
                    msg = f"Picking {picking.name} (id={picking.id}) created but error applying lots/serials: {e}"
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'error': str(e)})
                    continue

                # Do NOT auto-validate. Leave picking in 'assigned' (Ready).
                # Persist result message for display in the incoming_staging form view.
                msg = f"Picking {picking.name} (id={picking.id}) created and assigned (state={picking.state}). Please validate manually."
                # Update status to 'return' as requested
                rec.sudo().write({'status': 'return', 'result_message': msg})

                # Optionally send a realtime notification to users (non-blocking)
                try:
                    env['bus.bus'].sendone(
                        ('res.users', 0),
                        {'type': 'simple_notification', 'title': 'Create Return Receipt Result', 'message': msg}
                    )
                except Exception:
                    _logger.exception("Failed to send bus notification for picking %s", picking.id)

                results.append({'staging_id': rec.id, 'picking_id': picking.id, 'state': picking.state, 'message': msg})

            except Exception as exc:
                _logger.exception("Failed to create return receipt for incoming_staging %s", rec.id)
                msg = f"Failed to create return receipt: {exc}"
                try:
                    rec.sudo().write({'result_message': msg})
                except Exception:
                    _logger.exception("Failed to write result_message on staging %s", rec.id)
                results.append({'staging_id': rec.id, 'error': str(exc)})
        return results

    def action_create_transfer_receive(self):
        """
        Create receipt pickings from incoming_staging and ensure lots/serials are applied
        to stock.move and canonical stock.move.line records.

        Important behaviour:
        - Do NOT auto-validate the created picking. We confirm and assign so the picking
          becomes 'Ready' (state 'assigned') and the user can click Validate manually.
        - Persist a human-friendly result message into incoming_staging.result_message so
          it can be displayed in the form view (QWeb).
        """
        results = []
        env = self.sudo().env

        for rec in self.sudo():
            try:
                if not (rec.status == 'open' and rec.type == 'inbound'):
                    msg = f"Skipped staging {rec.id}: status={rec.status} type={rec.type}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'note': 'skipped_not_open_or_not_inbound', 'state': rec.status, 'type': rec.type})
                    continue
                
                if not rec.partner_type:
                    msg = f"Skipped staging {rec.id}: status={rec.status} type={rec.type} partner_type= Invalid"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'note': 'skipped_not_open_or_not_inbound', 'state': rec.status, 'type': rec.type})
                    continue

                # Idempotency: return existing non-cancelled picking
                existing = env['stock.picking'].search([('origin', '=', rec.transaction_no), ('state', '!=', 'cancel')], limit=1)
                if existing:
                    msg = f"Picking already exists: {existing.name} (id={existing.id}) state={existing.state}"
                    _logger.info(msg)
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'picking_id': existing.id, 'picking_name': existing.name, 'state': existing.state, 'note': 'existing_picking_returned'})
                    continue

                # Resolve picking type id from system parameter
                param_val = False
                if rec.partner_type == 'b2b':
                    param_val = self.env['ir.config_parameter'].sudo().get_param('fulfillment.operationtype.receipt_id')
                if rec.partner_type == 'b2c':
                    param_val = self.env['ir.config_parameter'].sudo().get_param('fulfillment.operationtype.receipt2_id')
                if not param_val:
                    raise ValidationError("Default receipt operation type is not configured (fulfillment.operationtype.receipt_id).")
                try:
                    picking_type_id = int(param_val)
                except Exception:
                    m = re.search(r'(\d+)', str(param_val))
                    if m:
                        picking_type_id = int(m.group(1))
                    else:
                        raise ValidationError(f"Invalid picking type configured: {param_val!r}")

                picking_type = env['stock.picking.type'].browse(picking_type_id)
                if not picking_type.exists():
                    raise ValidationError(f"Picking Type with id {picking_type_id} (configured in fulfillment.operationtype.receipt_id) does not exist!")
                if not picking_type.default_location_src_id:
                    raise ValidationError(f"default_location_src_id is not set on picking type {picking_type.name}")
                if not picking_type.default_location_dest_id:
                    raise ValidationError(f"default_location_dest_id is not set on picking type {picking_type.name}")

                # Build moves and collect metadata (preserve order)
                move_vals_list = []
                move_metadata = []
                for line in rec.products:
                    uom = rec._ensure_uom(line.product_uom or 'Unit')
                    product = rec._ensure_product(line.product_no, line.product_nanme, uom)
                    qty = float(line.product_qty or 0.0)

                    incoming_tracking = (line.tracking_type or 'none')
                    incoming_tracking_no = (line.tracking_no or '').strip()

                    # Ensure template is storable and has correct tracking so UI doesn't hide lot fields
                    if incoming_tracking in ('lot', 'serial'):
                        tmpl = product.product_tmpl_id
                        tmpl_vals = {}
                        if not tmpl.is_storable:
                            tmpl_vals['is_storable'] = True
                        if tmpl.tracking != incoming_tracking:
                            tmpl_vals['tracking'] = incoming_tracking
                        if tmpl_vals:
                            tmpl.sudo().write(tmpl_vals)

                    move_vals = {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'product_uom': uom.id,
                        'location_id': picking_type.default_location_src_id.id,
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'origin': rec.transaction_no,
                    }
                    move_vals_list.append((0, 0, move_vals))
                    move_metadata.append({
                        'product': product,
                        'qty': qty,
                        'incoming_tracking': incoming_tracking,
                        'incoming_tracking_no': incoming_tracking_no,
                    })

                picking_vals = {
                    'partner_id': rec.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'origin': rec.transaction_no,
                    'scheduled_date': odoo_fields.Datetime.now(),
                    'move_ids': move_vals_list,
                }

                picking = env['stock.picking'].create(picking_vals)

                # Confirm and assign -> picking should become 'assigned' (Ready)
                try:
                    if hasattr(picking, 'action_confirm'):
                        picking.action_confirm()
                except Exception:
                    _logger.exception("action_confirm failed for picking %s", picking.id)
                    raise ValidationError(f"action_confirm failed for picking {picking.id}")
                try:
                    if hasattr(picking, 'action_assign'):
                        picking.action_assign()
                    elif hasattr(picking, '_action_assign'):
                        picking._action_assign()
                except Exception:
                    _logger.exception("assignment failed for picking %s", picking.id)
                    raise ValidationError(f"assignment failed for picking {picking.id}")

                # Apply lots/serials and canonicalize move lines (leave picking un-validated)
                try:
                    pk = picking.sudo()
                    moves = pk.move_ids.sorted(key=lambda m: m.id)
                    for move, meta in zip(moves, move_metadata):
                        product = meta['product']
                        qty = meta['qty']
                        incoming_tracking = meta['incoming_tracking']
                        incoming_tracking_no = meta['incoming_tracking_no']

                        # Prepare lot ids
                        lot_ids = []
                        if incoming_tracking == 'lot':
                            if not incoming_tracking_no:
                                raise ValidationError(f"tracking_type='lot' but no tracking_no provided for {product.display_name}")
                            lot = env['stock.lot'].search([('name', '=', incoming_tracking_no), ('product_id', '=', product.id)], limit=1)
                            if not lot:
                                lot = env['stock.lot'].sudo().create({'name': incoming_tracking_no, 'product_id': product.id})
                            lot_ids = [lot.id]
                        elif incoming_tracking == 'serial':
                            serials = [s.strip() for s in re.split(r'[,\n;|]+', incoming_tracking_no) if s.strip()]
                            if not serials:
                                raise ValidationError(f"tracking_type='serial' but no serials provided for {product.display_name}")
                            if int(qty) != len(serials):
                                raise ValidationError(f"Qty {qty} does not match number of serials ({len(serials)}) for {product.display_name}")
                            for serial in serials:
                                lot = env['stock.lot'].search([('name', '=', serial), ('product_id', '=', product.id)], limit=1)
                                if not lot:
                                    lot = env['stock.lot'].sudo().create({'name': serial, 'product_id': product.id})
                                lot_ids.append(lot.id)

                        # Attach lot_ids to the move if any
                        if lot_ids:
                            move.sudo().write({'lot_ids': [(6, 0, lot_ids)]})

                        # Ask core to build/update move_line_ids from move.lot_ids
                        try:
                            move.sudo()._set_lot_ids()
                        except Exception:
                            _logger.exception("move._set_lot_ids() failed for move %s", move.id)

                        # Remove placeholders (we'll create canonical move lines ourselves)
                        existing_mls = move.move_line_ids
                        if existing_mls:
                            try:
                                existing_mls.sudo().unlink()
                            except Exception:
                                for ml in existing_mls:
                                    try:
                                        ml.sudo().unlink()
                                    except Exception:
                                        _logger.exception("Could not unlink placeholder move_line %s for move %s", ml.id, move.id)

                        desired_qty = float(move.product_uom_qty or 0.0)
                        move_uom_id = getattr(move, 'product_uom', None)
                        move_uom_id = move_uom_id.id if move_uom_id else product.uom_id.id

                        if lot_ids:
                            if product.tracking == 'serial':
                                for lid in lot_ids:
                                    lot_rec = env['stock.lot'].browse(lid)
                                    ml_vals = {
                                        'picking_id': pk.id,
                                        'move_id': move.id,
                                        'product_id': product.id,
                                        'product_uom_id': move_uom_id,
                                        'quantity': 1.0,
                                        'qty_done': 1.0,
                                        'location_id': move.location_id.id,
                                        'location_dest_id': move.location_dest_id.id,
                                        'lot_id': lid,
                                        'lot_name': lot_rec.name if lot_rec else False,
                                    }
                                    env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                            else:
                                # Lot tracking: set quantity = desired_qty and qty_done = desired_qty
                                lot_rec = env['stock.lot'].browse(lot_ids[0]) if lot_ids else None
                                ml_vals = {
                                    'picking_id': pk.id,
                                    'move_id': move.id,
                                    'product_id': product.id,
                                    'product_uom_id': move_uom_id,
                                    'quantity': desired_qty,
                                    'qty_done': desired_qty,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'lot_id': lot_ids[0],
                                    'lot_name': lot_rec.name if lot_rec else False,
                                }
                                env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})
                        else:
                            # No tracking: create a single move_line with the full qty
                            ml_vals = {
                                'picking_id': pk.id,
                                'move_id': move.id,
                                'product_id': product.id,
                                'product_uom_id': move_uom_id,
                                'quantity': desired_qty,
                                'qty_done': desired_qty,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                            }
                            env['stock.move.line'].sudo().create({k: v for k, v in ml_vals.items() if v is not None and v is not False})

                    # end for moves
                except Exception as e:
                    _logger.exception("Failed to apply lots/serials for picking %s", picking.id)
                    msg = f"Picking {picking.name} (id={picking.id}) created but error applying lots/serials: {e}"
                    rec.sudo().write({'result_message': msg})
                    results.append({'staging_id': rec.id, 'error': str(e)})
                    continue

                # Do NOT auto-validate. Leave picking in 'assigned' (Ready).
                # Persist result message for display in the incoming_staging form view.
                msg = f"Picking {picking.name} (id={picking.id}) created and assigned (state={picking.state}). Please validate manually."
                rec.sudo().write({'status': 'inbound', 'result_message': msg})

                # Optionally send a realtime notification to users (non-blocking)
                try:
                    env['bus.bus'].sendone(
                        ('res.users', 0),
                        {'type': 'simple_notification', 'title': 'Create Receipt Result', 'message': msg}
                    )
                except Exception:
                    _logger.exception("Failed to send bus notification for picking %s", picking.id)

                results.append({'staging_id': rec.id, 'picking_id': picking.id, 'state': picking.state, 'message': msg})

            except Exception as exc:
                _logger.exception("Failed to create receipt for incoming_staging %s", rec.id)
                msg = f"Failed to create receipt: {exc}"
                try:
                    rec.sudo().write({'result_message': msg})
                except Exception:
                    _logger.exception("Failed to write result_message on staging %s", rec.id)
                results.append({'staging_id': rec.id, 'error': str(exc)})
        return results

    # ---------------------------------------------------------------------
    # Helpers copied here to be available under sudo()
    # ---------------------------------------------------------------------
    def _ensure_uom(self, name):
        if not name:
            return (
                self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
                or (self.env['uom.uom'] and self.env['uom.uom'].search([], limit=1))
            )

        uom = self.env['uom.uom'].search([('name', '=', name)], limit=1)
        if uom:
            return uom

        vals = {'name': name or 'Unit'}
        try:
            if 'relative_factor' in self.env['uom.uom']._fields:
                vals['relative_factor'] = 1.0
                uom = self.env['uom.uom'].create(vals)
            else:
                vals['factor'] = 1.0
                uom = self.env['uom.uom'].create(vals)
        except Exception:
            vals.pop('factor', None)
            vals.pop('relative_factor', None)
            vals['factor_inv'] = 1.0
            uom = self.env['uom.uom'].create(vals)
        return uom

    def _ensure_product(self, product_no, product_name, uom):
        ProductProduct = self.env['product.product']
        ProductTemplate = self.env['product.template']

        prod = False
        if product_no:
            prod = ProductProduct.search([('default_code', '=', product_no)], limit=1)
        if not prod and product_name:
            prod = ProductProduct.search([('name', '=', product_name)], limit=1)
        if prod:
            return prod

        tmpl_vals = {
            'name': product_name or (product_no or 'New Product'),
            'uom_id': uom.id,
        }
        try:
            tmpl_vals['default_code'] = product_no
            tmpl = ProductTemplate.create(tmpl_vals)
        except Exception:
            tmpl_vals.pop('default_code', None)
            tmpl = ProductTemplate.create(tmpl_vals)
            if product_no:
                try:
                    variant = tmpl.product_variant_id
                    variant.sudo().write({'default_code': product_no})
                except Exception:
                    _logger.exception("Unable to set default_code on new product variant for %s", product_no)
        return tmpl.product_variant_id

    def _ensure_lot(self, product, lot_name):
        if not lot_name:
            return False
        Lot = self.env['stock.lot']
        lot = Lot.search([('name', '=', lot_name), ('product_id', '=', product.id)], limit=1)
        if lot:
            return lot
        return Lot.sudo().create({'name': lot_name, 'product_id': product.id})