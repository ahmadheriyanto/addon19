from odoo import api, fields, models
from odoo import fields as odoo_fields
from odoo.exceptions import UserError, ValidationError
import logging
import json
import base64
import io

_logger = logging.getLogger(__name__)

# Try to use segno (pure-python QR generator) first, fall back to qrcode + PIL
try:
    import segno  # pip install segno
    _HAS_SEGNO = True
except Exception:
    _HAS_SEGNO = False

if not _HAS_SEGNO:
    try:
        import qrcode  # pip install "qrcode[pil]"
        from PIL import Image  # qrcode uses PIL for image creation
        _HAS_QRCODE = True
    except Exception:
        _HAS_QRCODE = False
else:
    _HAS_QRCODE = False


class IncomingStaging(models.Model):
    _name = 'incoming_staging'
    _description = 'incoming_staging'
    _rec_name = 'transaction_no'

    transaction_no = fields.Char(string="Transaction No.", required=True)
    type = fields.Selection(string="Type",
                            selection=[
                                ('', ' '),
                                ('inbound', 'Inbound Order'),
                                ('forder', 'Fulfillment Order')
                            ], default='', required=True)
    datetime_string = fields.Char(string="Date (yyyy-mm-ddTHH:MM:SS)", required=True)
    products = fields.One2many(
        comodel_name='incoming_staging_product',
        inverse_name='incoming_staging_id',
        string="Product Lines",
        copy=True,
        bypass_search_access=True
    )
    status = fields.Selection(string="Status",
                              selection=[
                                  ('open', 'Open'),
                                  ('inbound', 'Inbound'),
                                  ('pick', 'Picking'),
                                  ('pack', 'Packing'),
                                  ('deliver', 'Deliver')
                              ], default='open', required=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        required=True,
        ondelete='cascade',
        index=True
    )

    principal_courier = fields.Char(string="Courier")
    principal_customer_name = fields.Char(string="Customer Name")
    principal_customer_address = fields.Char(string="Customer Address")

    qr_image = fields.Binary("QR Code (PNG)", attachment=True,
                             help="PNG image of QR code representing header + product lines")
    qr_payload = fields.Text("QR Payload (JSON)", help="JSON payload encoded into the QR code", copy=False)

    @api.constrains('transaction_no')
    def _check_name_unique(self):
        for record in self:
            existing = self.env['incoming_staging'].search([
                ('transaction_no', '=', record.transaction_no),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('transaction_no must be unique!')

    def _build_qr_payload(self):
        self.ensure_one()
        payload = {
            'transaction_no': self.transaction_no,
            'type': self.type,
            'datetime_string': self.datetime_string,
            'partner_id': self.partner_id.id or None,
            'partner_name': self.partner_id.name or '',
            'products': []
        }
        for line in self.products:
            payload['products'].append({
                'product_no': line.product_no,
                'product_nanme': line.product_nanme,
                'product_lot': line.product_lot,
                'product_serial': line.product_serial,
                'product_qty': float(line.product_qty) if line.product_qty is not None else 0.0,
                'product_uom': line.product_uom,
            })
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    def _generate_qr_png_bytes(self, text, scale=4):
        if _HAS_SEGNO:
            try:
                qr = segno.make(text)
                buf = io.BytesIO()
                qr.save(buf, kind='png', scale=scale)
                return buf.getvalue()
            except Exception:
                _logger.exception("segno failed to generate QR")
                raise
        elif _HAS_QRCODE:
            try:
                img = qrcode.make(text)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                return buf.getvalue()
            except Exception:
                _logger.exception("qrcode failed to generate QR")
                raise
        else:
            raise ImportError(
                "No QR generator available. Install 'segno' (recommended) or 'qrcode[pil]'."
            )

    def _generate_and_save_qr(self):
        """
        Generate QR payload and PNG and write to qr_payload and qr_image.
        Use sudo() to avoid permission problems and ensure binary saved as base64 string.
        """
        for rec in self:
            try:
                payload_text = rec._build_qr_payload()
                png_bytes = rec._generate_qr_png_bytes(payload_text)
                # Ensure we write a text base64 value (not bytes) and use sudo to avoid rights issues.
                b64 = base64.b64encode(png_bytes).decode('ascii')
                rec.sudo().write({
                    'qr_payload': payload_text,
                    'qr_image': b64,
                })
            except ImportError as ie:
                _logger.warning("QR generation skipped for incoming_staging %s: %s", rec.id or rec.transaction_no, ie)
            except Exception:
                _logger.exception("Failed to generate QR for incoming_staging %s", rec.id or rec.transaction_no)

    @api.model_create_multi
    def create(self, vals_list):
        # Create records first, then generate QR under sudo() to ensure children exist and attachments saved.
        records = super(IncomingStaging, self).create(vals_list)
        try:
            # Use sudo() to avoid permission issues when creating attachments
            records.sudo()._generate_and_save_qr()
        except Exception:
            _logger.exception("Unexpected error while generating QR after create")
        return records

    def write(self, vals):
        # Perform write, then decide whether to regenerate using the same rules.
        res = super(IncomingStaging, self).write(vals)

        regenerate = False
        header_fields = {'transaction_no', 'type', 'datetime_string', 'partner_id'}
        if header_fields.intersection(vals.keys()):
            regenerate = True

        # Consider status transitions and modifications to products
        if 'status' in vals and vals.get('status') and vals.get('status') != 'open':
            regenerate = True

        # When product lines are changed via One2many commands, 'products' key may appear in vals
        if 'products' in vals:
            regenerate = True

        if regenerate:
            try:
                # Use sudo to avoid access-rights problems saving attachments
                self.sudo()._generate_and_save_qr()
            except Exception:
                _logger.exception("Failed to regenerate QR on write for incoming_staging %s", self.ids)

        return res

    @api.model
    def refresh_all_qr(self):
        """
        Utility method to force regeneration of QR image for all records.
        Call from shell, server action or scheduled action.
        """
        records = self.search([])
        _logger.info("Refreshing QR for %s incoming_staging records", len(records))
        # Use sudo so attachment creation works for all records
        records.sudo()._generate_and_save_qr()
        return True

    def refresh_qr(self):
        """
        Instance helper to refresh only these records.
        """
        self.sudo()._generate_and_save_qr()
        return True


class IncomingStagingProduct(models.Model):
    _name = 'incoming_staging_product'
    _description = 'incoming_staging_product'

    incoming_staging_id = fields.Many2one(
        comodel_name='incoming_staging',
        string="Transaction No.",
        required=True,
        ondelete='cascade',
        index=True
    )
    product_no = fields.Char(string="Product No.")
    product_nanme = fields.Char(string="Product Name")
    product_qty = fields.Float(string="Quantity")
    product_uom = fields.Char(string="Unit of Measure")
    tracking_type = fields.Selection([
        ('serial', 'By Unique Serial Number'),
        ('lot', 'By Lots'),
        ('none', 'By Quantity')],
        string="Tracking", required=True, default='none',
        help="Ensure the traceability of a storable product in your warehouse.")
    tracking_no = fields.Char(string="Tracking No.")
