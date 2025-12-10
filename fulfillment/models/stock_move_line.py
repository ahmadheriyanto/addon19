# -*- coding: utf-8 -*-
# Fulfillment - customizations for stock.move.line to support inline Detailed Operations UX
# - Auto-default move_id when creating a move.line from a picking that has exactly one move
# - Prevent create/write/unlink when related picking is done or cancelled
# - Require move_id when creating a move.line for a picking that has multiple moves
# - Onchange to copy product/location/UoM from selected move_id (client-side), guarded by picking state
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _action_done(self):
        res = super()._action_done()
        for ml in self:
            picking = ml.picking_id
            if not picking:
                continue
            company = picking.company_id or self.env.company
            dest_loc = ml.location_dest_id if ml.qty_done > 0 else ml.location_id
            domain = [
                ('company_id', '=', company.id),
                ('product_id', '=', ml.product_id.id),
                ('location_id', '=', dest_loc.id),
            ]
            if ml.lot_id:
                domain.append(('lot_id', '=', ml.lot_id.id))
            quants = self.env['stock.quant'].sudo().search(domain)
            if quants:
                quants.write({'partner_type': picking.partner_type or ''})
        return res

    @api.model
    def default_get(self, fields):
        """
        When creating a move.line from the picking view (context has default_picking_id or active_id),
        auto-set move_id if the picking has exactly one move. This allows inline creation without a popup
        when there is only one possible target move.
        """
        res = super(StockMoveLine, self).default_get(fields)
        picking_id = self.env.context.get("default_picking_id") or self.env.context.get("active_id")
        if picking_id and "move_id" in fields and "move_id" not in res:
            picking = self.env["stock.picking"].browse(picking_id)
            if picking.exists() and len(picking.move_ids) == 1:
                res["move_id"] = picking.move_ids[:1].id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        - Block creating move.lines for pickings that are 'done' or 'cancel'.
        - If the picking has multiple moves, require move_id in vals (to force user selection).
        """
        # Pre-check for each set of vals to provide early, informative errors
        for vals in vals_list:
            picking_id = vals.get("picking_id") or self.env.context.get("default_picking_id") or self.env.context.get("active_id")
            if picking_id:
                picking = self.env["stock.picking"].browse(picking_id)
                if picking.exists():
                    if picking.state in ("done", "cancel"):
                        raise ValidationError("Cannot create move lines: the picking is %s." % picking.state)
                    # If picking has multiple moves, ensure the new line explicitly references one
                    if len(picking.move_ids) > 1 and not vals.get("move_id"):
                        raise ValidationError("This picking has multiple moves. Please select which Move the new line belongs to.")
        return super(StockMoveLine, self).create(vals_list)

    # def write(self, vals):
    #     """
    #     Prevent editing move.lines that belong to pickings in 'done' or 'cancel' states.

    #     If vals contains 'picking_id' (moving lines between pickings), also validate the target picking.
    #     """
    #     # Determine all pickings affected by this operation
    #     affected_pickings = self.mapped("picking_id")
    #     # If the write contains a picking_id change, include that target picking in checks
    #     if vals.get("picking_id"):
    #         target = self.env["stock.picking"].browse(vals.get("picking_id"))
    #         if target.exists():
    #             affected_pickings |= target
    #     # Validate none of the affected pickings are done/cancel
    #     for picking in affected_pickings:
    #         if picking and picking.state in ("done", "cancel"):
    #             raise ValidationError("Cannot modify move lines: picking %s is %s." % (picking.name or picking.id, picking.state))
    #     return super(StockMoveLine, self).write(vals)

    def unlink(self):
        """
        Prevent deletion of move.lines that belong to pickings in 'done' or 'cancel'.
        """
        pickings = self.mapped("picking_id")
        for picking in pickings:
            if picking and picking.state in ("done", "cancel"):
                raise ValidationError("Cannot delete move lines: picking %s is %s." % (picking.name or picking.id, picking.state))
        return super(StockMoveLine, self).unlink()

    @api.onchange("move_id")
    def _onchange_move_id_fill_fields(self):
        """
        Client-side onchange: when the user selects a move in the inline list, prefill:
          - product_id
          - location_id (From)
          - location_dest_id (To)
          - product_uom_id (if available on move)

        This onchange only performs filling when the related picking is editable (not 'done'/'cancel').
        If the picking is done/cancel, it returns a warning and does not modify the record.
        """
        for line in self:
            # Determine related picking (line.picking_id should normally be set in the one2many context)
            picking = line.picking_id
            # Fallback to context if picking not yet set on the record
            if not picking and self.env.context.get("default_picking_id"):
                picking = self.env["stock.picking"].browse(self.env.context.get("default_picking_id"))

            if picking and picking.state in ("done", "cancel"):
                # Provide a client warning and do not alter fields
                return {
                    "warning": {
                        "title": "Picking not editable",
                        "message": "This picking is %s. You cannot set fields from the Move." % picking.state,
                    }
                }

            if line.move_id:
                # Copy values from the selected move into the move line
                line.product_id = line.move_id.product_id.id or False
                line.location_id = line.move_id.location_id.id or False
                line.location_dest_id = line.move_id.location_dest_id.id or False
                # stock.move typically uses product_uom (not product_uom_id)
                product_uom = getattr(line.move_id, "product_uom", False)
                line.product_uom_id = product_uom.id if product_uom else False
            else:
                # Do not clear existing values to avoid surprising the user.
                # If you prefer clearing on move change, uncomment the following:
                # line.product_id = False
                # line.location_id = False
                # line.location_dest_id = False
                # line.product_uom_id = False
                pass