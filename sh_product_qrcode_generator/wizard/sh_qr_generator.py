# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from io import BytesIO
import base64
try:
    import qrcode
except ImportError:
    qrcode = None

class ShProductQRCodeGeneratorWizard(models.TransientModel):
    _name = 'sh.product.qrcode.generator.wizard'
    _description = 'Product QR Code Generator Wizard'

    product_tmpl_ids = fields.Many2many(
        'product.template', string='Products', copy=False)
    product_var_ids = fields.Many2many(
        'product.product', string='Product Variants', copy=False)
    is_overwrite_existing = fields.Boolean("Overwrite QR code If Exists")

    @api.model
    def default_get(self, default_fields):
        rec = super(ShProductQRCodeGeneratorWizard, self).default_get(default_fields)

        active_ids = self._context.get('active_ids')
        active_model = self._context.get('active_model')

        if not active_ids:
            raise UserError(_("Programming error: wizard action executed without active_ids in context."))

        if active_model == 'product.template':
            products = self.env['product.template'].browse(active_ids)
            rec.update({'product_tmpl_ids': [(6, 0, products.ids)]})
            return rec

        if active_model == 'product.product':
            products = self.env['product.product'].browse(active_ids)
            rec.update({'product_var_ids': [(6, 0, products.ids)]})
            return rec

        return rec

    def action_generate_qr_code(self):
        # Use base.group_user as requested
        if not self.env.user.has_group('base.group_user'):
            raise UserError(_("You don't have rights to generate product QR Code"))

        if qrcode is None:
            raise UserError(_("QR code library not installed. Please install 'qrcode' Python package."))

        def _generate_qr_payload():
            qr_sequence = self.env['ir.sequence'].next_by_code('seq.sh_product_qrcode_generator')
            if not qr_sequence:
                return None, None
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_sequence)
            qr.make(fit=True)
            img = qr.make_image()
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_code_image = base64.b64encode(temp.getvalue())
            return qr_sequence, qr_code_image

        if self.product_tmpl_ids:
            for product in self.product_tmpl_ids:
                if product.sh_qr_code and not self.is_overwrite_existing:
                    continue
                qr_code, qr_code_image = _generate_qr_payload()
                if qr_code:
                    product.sh_qr_code = qr_code
                    product.sh_qr_code_img = qr_code_image

        elif self.product_var_ids:
            for product in self.product_var_ids:
                if product.sh_qr_code and not self.is_overwrite_existing:
                    continue
                qr_code, qr_code_image = _generate_qr_payload()
                if qr_code:
                    product.sh_qr_code = qr_code
                    product.sh_qr_code_img = qr_code_image