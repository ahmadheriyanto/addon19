# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import ValidationError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def default_get(self, fields):
        """Auto-set move_id when creating a move.line from a picking that has exactly one move."""
        res = super().default_get(fields)
        picking_id = self.env.context.get("default_picking_id") or self.env.context.get("active_id")
        if picking_id and "move_id" in fields and "move_id" not in res:
            picking = self.env["stock.picking"].browse(picking_id)
            if picking.exists() and len(picking.move_ids) == 1:
                res["move_id"] = picking.move_ids[:1].id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure move_id is provided when picking has multiple moves."""
        for vals in vals_list:
            picking_id = vals.get("picking_id") or self.env.context.get("default_picking_id") or self.env.context.get("active_id")
            if picking_id:
                picking = self.env["stock.picking"].browse(picking_id)
                if picking.exists() and len(picking.move_ids) > 1 and not vals.get("move_id"):
                    raise ValidationError(
                        "This picking has multiple moves. Please select which Move the new line belongs to."
                    )
        return super().create(vals_list)

    @api.onchange("move_id")
    def _onchange_move_id_fill_fields(self):
        """
        When the user selects a move in the inline list, prefill the product, from and to (and UoM)
        from the selected stock.move. This runs on the client side as an onchange.
        """
        for line in self:
            if line.move_id:
                # Prefill product and locations from the selected move
                line.product_id = line.move_id.product_id.id or False
                line.location_id = line.move_id.location_id.id or False
                line.location_dest_id = line.move_id.location_dest_id.id or False
                # Prefill UoM from the move if available
                if hasattr(line.move_id, "product_uom"):
                    # stock.move uses product_uom (not product_uom_id)
                    try:
                        line.product_uom_id = line.move_id.product_uom.id or False
                    except Exception:
                        # fallback: set nothing if attribute missing
                        line.product_uom_id = False
            else:
                # if move cleared, do not force values (leave as-is or clear)
                # We choose not to clear product/location automatically to avoid surprise,
                # but you can clear them if you want:
                # line.product_id = False
                # line.location_id = False
                # line.location_dest_id = False
                pass