# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from io import BytesIO
import base64

try:
    import qrcode
except ImportError:
    qrcode = None


class ShProductProduct(models.Model):
    _inherit = "product.product"

    sh_qr_code = fields.Char(string="QR Code", copy=False)
    sh_qr_code_img = fields.Binary(
        string="QR Code Image", copy=False, compute='_compute_sh_qr_code_2')

    def sh_action_open_label_layout_with_qr(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'sh_product_qrcode_generator.sh_action_open_label_layout_with_qr')
        action['context'] = {'default_product_ids': self.ids}
        return action

    @api.constrains('sh_qr_code')
    def _validate_qrcode(self):
        if self.sh_qr_code:
            products = self.env['product.product'].search(
                [('id', '!=', self.id)])
            for rec in products:
                if self.sh_qr_code == rec.sh_qr_code:
                    raise ValidationError("A QR code must be unique !")

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        result = super(ShProductProduct, self)._name_search(
            name, args, operator, limit, name_get_uid)
        if not result:
            if not args:
                args = []
            domain = [('sh_qr_code', '=', name)]
            domain = Domain(args) & Domain(domain)
            result = list(self._search(
                domain, limit=limit, access_rights_uid=name_get_uid, order=order))
        return result
    
    @api.model_create_multi
    def create(self, vals):
        res = super(ShProductProduct, self).create(vals)
        is_create_qr_code = True
        if is_create_qr_code:
            qr_sequence = self.env['ir.sequence'].next_by_code(
                'seq.sh_product_qrcode_generator')
            if qr_sequence:
                qr_code = qr_sequence
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_code)
                qr.make(fit=True)

                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_code_image = base64.b64encode(temp.getvalue())

                res.sh_qr_code = qr_code
                res.sh_qr_code_img = qr_code_image
        return res

    @api.depends('sh_qr_code')
    def _compute_sh_qr_code_2(self):
        if self:
            for rec in self:
                rec.sh_qr_code_img = False
                if rec.sh_qr_code:
                    qr_code = rec.sh_qr_code
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(qr_code)
                    qr.make(fit=True)

                    img = qr.make_image()
                    temp = BytesIO()
                    img.save(temp, format="PNG")
                    qr_code_image = base64.b64encode(temp.getvalue())
                    rec.sh_qr_code_img = qr_code_image
