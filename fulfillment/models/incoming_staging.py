from odoo import models, fields, api
from odoo.exceptions import ValidationError
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
                                ('',' '),
                                ('inbound','Inbound Order'),
                                ('forder','Fulfillment Order')
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
                                ('open','Open'),
                                ('inbound','Inbound'),
                                ('pick','Picking'),
                                ('pack','Packing'),
                                ('deliver','Deliver')
                            ], default='open', required=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        required=True,
        ondelete='cascade',
        index=True
    )

    # Binary field to store PNG of QR code (attachment=True stores it as an ir.attachment blob)
    qr_image = fields.Binary("QR Code (PNG)", attachment=True,
                             help="PNG image of QR code representing header + product lines")

    # Optional: store the payload (JSON) encoded into the QR for quick inspection / debugging
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
    
    # **** QR code ***********
    # Helper: build the JSON payload that will be encoded inside the QR
    def _build_qr_payload(self):
        """
        Build a deterministic JSON string representing header + products.
        Called per-record.
        """
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
                # Use string for quantity to preserve precision in QR payload if you want
                'product_qty': float(line.product_qty) if line.product_qty is not None else 0.0,
                'product_uom': line.product_uom,
            })
        # Deterministic JSON: sorted keys, compact separators to reduce QR size
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    def _generate_qr_png_bytes(self, text, scale=4):
        """
        Generate a PNG bytes from the given text using segno or qrcode.
        Return bytes (PNG) or raise ImportError if no lib is available.
        """
        if _HAS_SEGNO:
            try:
                qr = segno.make(text)
                buf = io.BytesIO()
                # save as png
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
        Generate QR payload and image for each record and write into the qr_image field.
        This method catches exceptions and logs them, so it won't block record creation if QR lib is missing.
        """
        for rec in self:
            try:
                payload_text = rec._build_qr_payload()
                png_bytes = rec._generate_qr_png_bytes(payload_text)
                # store payload and image (binary stored as base64 in Odoo fields.Binary)
                rec.qr_payload = payload_text
                rec.qr_image = base64.b64encode(png_bytes)
            except ImportError as ie:
                # Missing dependency: do not raise, just log and continue
                _logger.warning("QR generation skipped for incoming_staging %s: %s", rec.id or rec.transaction_no, ie)
            except Exception:
                _logger.exception("Failed to generate QR for incoming_staging %s", rec.id or rec.transaction_no)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to generate QR after creating header and lines.
        We intentionally do not raise on QR-generation failure to avoid blocking record creation.
        """
        records = super(IncomingStaging, self).create(vals_list)
        # Generate QR for newly created records (wrapped in try/except so QR failures don't block creation)
        try:
            # Use a savepoint if you need the QR generation to rollback independently (optional).
            # with self.env.cr.savepoint():
            records._generate_and_save_qr()
        except Exception:
            # Already logged inside _generate_and_save_qr; ensure we don't break creation flow
            _logger.exception("Unexpected error while generating QR after create")
        return records

    def write(self, vals):
        """
        Optionally regenerate QR when header or lines change or when status transitions to a "finished" state.
        This example regenerates QR if:
          - any of the tracked header fields are in vals OR
          - 'status' changed to something other than 'open'
        Adjust logic depending on when you consider the header+lines "finished".
        """
        res = super(IncomingStaging, self).write(vals)

        # Determine whether to regenerate QR:
        regenerate = False
        header_fields = {'transaction_no', 'type', 'datetime_string', 'partner_id'}
        if header_fields.intersection(vals.keys()):
            regenerate = True

        # If status is present and moved out of 'open' we consider it finished and regenerate
        if 'status' in vals and vals.get('status') and vals.get('status') != 'open':
            regenerate = True

        # Also regenerate if product lines were modified (One2many write uses commands; check for key change)
        # Note: modifications to One2many are not listed in vals when lines are modified through relation methods
        # in the same write call; it's common to receive product changes as part of vals via 'products' key.
        if 'products' in vals:
            regenerate = True

        if regenerate:
            try:
                # Only run on the records that were updated
                self._generate_and_save_qr()
            except Exception:
                _logger.exception("Failed to regenerate QR on write for incoming_staging %s", self.ids)

        return res
    # **** end of QR Code ****

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
    product_lot = fields.Char(string="Product Lot No.")
    product_serial = fields.Char(string="Product Serial No.")
    product_qty = fields.Float(string="Quantity")
    product_uom = fields.Char(string="Unit of Measure")