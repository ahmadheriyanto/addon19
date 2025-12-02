from odoo import api, fields, models
from odoo import fields as odoo_fields
from odoo.exceptions import UserError, ValidationError
import logging
import json
import base64
import io

_logger = logging.getLogger(__name__)

# Try to use segno (pure-python QR generator) first, fall
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
    _rec_name = 'resi_no'

    resi_no = fields.Char(string="Resi No.", required=True)
    type = fields.Selection(string="Type",
                            selection=[
                                ('', ' '),
                                ('inbound', 'Inbound Order'),
                                ('forder', 'Fulfillment Order'),
                                ('return', 'Return Order')
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
                                  ('return', 'Return')
                              ], default='open', required=True)

    tracking_status = fields.Selection(string="Tracking Status",
                              selection=[
                                  ('open', 'Open'),         # Incoming staging belum di buatkan transfer Order
                                  ('inbound', 'Inbound'),   # Incoming Staging sudah menjadi transfer Order dengan picking type = receipt, belum validate
                                  ('storage', 'Storage'),   # Incoming Staging sudah menjadi transfer Order dengan picking type = receipt, sudah validate / Done
                                  ('pick', 'Picking'),      # Incoming Staging sudah menjadi transfer Order dengan picking type = pick, belum validate
                                  ('pack', 'Packing'),      # Incoming Staging sudah menjadi transfer Order dengan picking type = pick, sudah validate / Done
                                                            # Incoming Staging sudah menjadi transfer Order dengan picking type = pack, belum validate
                                  ('deliver', 'Shipping'),  # Incoming Staging sudah menjadi transfer Order dengan picking type = pack, sudah validate / Done
                                                            # Incoming Staging sudah menjadi transfer Order dengan picking type = Delivery Order, belum validate
                                  ('finish', 'Finish'),     # Incoming Staging sudah menjadi transfer Order dengan picking type = Delivery Order, sudah validate / Done
                                  ('return', 'Return')
                              ], default='open', required=True)

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        required=True,
        ondelete='cascade',
        index=True
    )

    partner_type = fields.Selection(string="Partner Type",
            selection=[
                ('', ''),
                ('b2b', 'B2B'),
                ('b2c', 'B2C')
            ], 
            default=''
        )

    principal_courier = fields.Char(string="Courier")

    # 1) Computed Many2one field: find first res.partner whose name ilike principal_courier
    #    and who belongs to the Transporter category configured on the company settings.
    principal_courier_id = fields.Many2one(
        comodel_name='res.partner',
        string="Courier Id",
        compute='_compute_principal_courier_id',
        store=True,
        readonly=True,
        index=True,
        help='Computed: partner record matched by principal_courier name and company Transporter category'
    )

    # 2) Related field: courier_priority resolves through principal_courier_id -> partner.courier_scoring_label
    courier_priority = fields.Char(
        string='Courier priority',
        related='principal_courier_id.courier_scoring_label',
        readonly=True,
        store=True,
        help='Related from principal_courier_id.courier_scoring_label'
    )

    courier_sort_score = fields.Integer(
        string='Courier Sort Score',
        compute='_compute_courier_sort_score',
        store=True,
        index=True,
        readonly=True,
        help='Helper field used to sort incoming staging records by resolved courier scoring. '
             'If no courier resolved, set to 0 so it sorts before known couriers when ascending.'
    )

    @api.depends('principal_courier_id', 'principal_courier_id.courier_scoring')
    def _compute_courier_sort_score(self):
        """Set courier_sort_score from principal_courier_id.courier_scoring.
        If no principal courier is resolved, set score = 0 (highest priority when sorting asc).
        """
        for rec in self:
            pc = rec.principal_courier_id
            if pc and pc.courier_scoring not in (False, None):
                try:
                    rec.courier_sort_score = int(pc.courier_scoring)
                except Exception:
                    # defensive fallback: if conversion fails, treat as 0
                    rec.courier_sort_score = 0
            else:
                # If no principal courier found, use 0 as requested
                rec.courier_sort_score = 0

    principal_customer_name = fields.Char(string="Customer Name")
    principal_customer_address = fields.Char(string="Customer Address")

    qr_image = fields.Binary("QR Code (PNG)", attachment=True,
                             help="PNG image of QR code representing header + product lines")
    qr_payload = fields.Text("QR Payload (JSON)", help="JSON payload encoded into the QR code", copy=False)

    @api.depends('principal_courier')
    def _compute_principal_courier_id(self):
        """
        For each incoming_staging record:
          - if principal_courier is set and a company-level Transporter category configured,
            search res.partner with that category and whose name ilike principal_courier.
          - assign the first match (limit=1) to principal_courier_id; otherwise set False.
        Note: we store the computed partner id because downstream logic / views expect stored values.
        If you change transporter category or partner categories you should run the refresh routine
        (settings button) to update stored values for existing records.
        """
        Partner = self.env['res.partner'].sudo()
        # resolve transporter category from current company (no company on this model)
        transporter_cat = self.env.company.fulfillment_transporter_category_id
        transporter_id = transporter_cat.id if transporter_cat else False

        for rec in self:
            rec.principal_courier_id = False
            name = (rec.principal_courier or '').strip()
            if not name or not transporter_id:
                continue
            # search partners that have the transporter category and name matches (ilike)
            partner = Partner.search([('category_id', 'in', [transporter_id]), ('name', 'ilike', name)], limit=1)
            if partner:
                rec.principal_courier_id = partner.id

    @api.constrains('resi_no')
    def _check_name_unique(self):
        for record in self:
            existing = self.env['incoming_staging'].search([
                ('resi_no', '=', record.resi_no),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('resi_no must be unique!')
    def _build_qr_payload(self):
        self.ensure_one()
        payload = {
            'qr_type': 'incomingstaging',
            'resi_no': self.resi_no,
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
                'product_qty': float(line.product_qty) if line.product_qty is not None else 0.0,
                'product_uom': line.product_uom,
                'tracking_type': line.tracking_type,
                'tracking_no': line.tracking_no,
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
            # No generator available - raise so callers can detect & respond
            raise ImportError(
                "No QR generator available. Install 'segno' (recommended) or 'qrcode[pil]' + 'pillow'."
            )

    def _generate_and_save_qr(self):
        """
        Generate QR payload and PNG and write to qr_payload and qr_image.
        Use sudo() to avoid permission problems and ensure binary saved as base64 string.
        If generation is not possible (missing libs) or fails, raise an exception so callers can handle it.
        """
        for rec in self:
            payload_text = rec._build_qr_payload()
            try:
                png_bytes = rec._generate_qr_png_bytes(payload_text)
            except ImportError as ie:
                # Library missing — log and re-raise so API/UI callers can react
                _logger.error("QR generation unavailable for incoming_staging %s: %s", rec.id or rec.resi_no, ie)
                raise
            except Exception:
                _logger.exception("Failed to generate QR for incoming_staging %s", rec.id or rec.resi_no)
                raise
            # Ensure we write a text base64 value (not bytes) and use sudo to avoid rights issues.
            b64 = base64.b64encode(png_bytes).decode('ascii')
            rec.sudo().write({
                'qr_payload': payload_text,
                'qr_image': b64,
            })

    @api.model_create_multi
    def create(self, vals_list):
        # Create records first, then generate QR under sudo() to ensure children exist and attachments saved.
        records = super(IncomingStaging, self).create(vals_list)
        try:
            # Use sudo() to avoid permission issues when creating attachments
            records.sudo()._generate_and_save_qr()
        except ImportError:
            # Fail creation if QR libs not installed so caller knows immediately
            raise ValidationError(
                "QR generation dependencies are missing on the server. "
                "Install 'segno' (recommended) or 'qrcode[pil]' and 'pillow', then restart Odoo."
            )
        except Exception as e:
            _logger.exception("Unexpected error while generating QR after create: %s", e)
            # surface as ValidationError so the controller returns a clear JSON error
            raise ValidationError(f"QR generation failed: {e}")
        return records

    def write(self, vals):
        # Perform write, then decide whether to regenerate using the same rules.
        res = super(IncomingStaging, self).write(vals)

        regenerate = False
        header_fields = {'resi_no', 'type', 'datetime_string', 'partner_id'}
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
            except ImportError:
                _logger.error("QR generation missing during write for incoming_staging %s", self.ids)
                raise ValidationError(
                    "QR generation dependencies are missing on the server. "
                    "Install 'segno' (recommended) or 'qrcode[pil]' and 'pillow', then restart Odoo."
                )
            except Exception as e:
                _logger.exception("Failed to regenerate QR on write for incoming_staging %s: %s", self.ids, e)
                raise ValidationError(f"QR regeneration failed: {e}")

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
    staging_type = fields.Selection(related='incoming_staging_id.type', readonly=True)  # for visibility control
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
    expiration_date = odoo_fields.Date(string="Expiration Date")
