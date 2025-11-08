# -*- coding: utf-8 -*-
# Controller for Incoming Staging API with CORS support
from datetime import datetime
import json
import logging

from odoo import http, fields
from odoo.http import request, Response
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)

# Development-friendly defaults. In production set a specific origin (not '*').
_ALLOWED_CORS_ORIGIN = '*'
_ALLOWED_CORS_METHODS = 'GET, POST, OPTIONS'
_ALLOWED_CORS_HEADERS = 'Authorization, Content-Type, Accept'


def _cors_headers():
    return {
        'Access-Control-Allow-Origin': _ALLOWED_CORS_ORIGIN,
        'Access-Control-Allow-Methods': _ALLOWED_CORS_METHODS,
        'Access-Control-Allow-Headers': _ALLOWED_CORS_HEADERS,
    }


class IncomingStagingAPI(http.Controller):
    @http.route('/api/incoming_staging', type='http', auth='api_key', methods=['POST'], csrf=False)
    def create_incoming_staging(self, **kw):
        """
        Create an incoming_staging record.

        Expected JSON (application/json):
        {
          "transaction_no": "TRX-001",
          "type": "inbound" | "forder",
          "datetime_string": "YYYY-MM-DDTHH:MM:SS",
          "partner": {"id":123} OR {"email":"x@x.com"},
          "products": [ ... ],
          # The following fields are REQUIRED when type == "forder":
          "principal_courier": "Courier Name",
          "principal_customer_name": "Customer Name",
          "principal_customer_address": "Customer Address"
        }
        """
        headers = _cors_headers()
        try:
            data = request.httprequest.get_json(force=True)
        except Exception as e:
            return Response(
                json.dumps({'error': 'Invalid JSON body', 'details': str(e)}),
                status=400, content_type='application/json;charset=utf-8', headers=headers
            )

        # Required top-level fields (type may be 'inbound' or 'forder')
        required = ['transaction_no', 'type', 'datetime_string', 'partner', 'products']
        for f in required:
            if f not in data:
                return Response(
                    json.dumps({'error': f'Missing field: {f}'}),
                    status=400, content_type='application/json;charset=utf-8', headers=headers
                )

        # Validate type
        if data['type'] not in ('inbound', 'forder'):
            return Response(
                json.dumps({'error': "Invalid 'type' value. Expected 'inbound' or 'forder'."}),
                status=400, content_type='application/json;charset=utf-8', headers=headers
            )

        # Validate datetime_string
        try:
            datetime.fromisoformat(data['datetime_string'])
        except Exception:
            return Response(
                json.dumps({'error': "Invalid 'datetime_string'. Expected ISO format like 2025-10-26T01:13:55"}),
                status=400, content_type='application/json;charset=utf-8', headers=headers
            )

        # # If type == 'forder' then require principal_* fields
        # if data['type'] == 'forder':
        #     principal_fields = ['principal_courier', 'principal_customer_name', 'principal_customer_address']
        #     for pf in principal_fields:
        #         v = data.get(pf)
        #         if not v or (isinstance(v, str) and not v.strip()):
        #             return Response(
        #                 json.dumps({'error': f"Missing or empty field required for 'forder': {pf}"}),
        #                 status=400, content_type='application/json;charset=utf-8', headers=headers
        #             )

        # If type == 'forder' then require principal_* fields and validate courier exists in Transporter category
        if data['type'] == 'forder':
            principal_fields = ['principal_courier', 'principal_customer_name', 'principal_customer_address']
            try:
                # Use sudo() to read company setting and partner/category safely regardless of caller permissions.
                company = request.env.company.sudo()
                transporter_cat = company.fulfillment_transporter_category_id
            except AccessError as ae:
                # If for some reason we cannot read company/category, return a helpful error.
                _logger.exception("Access error when reading company transporter category: %s", ae)
                return Response(
                    json.dumps({
                        'error': 'access_error_reading_transporter_category',
                        'details': 'The API user does not have permission to read company transporter settings (res.company / res.partner.category).'
                                   ' Ask your administrator to grant read access or ensure the endpoint runs with sudo.',
                    }),
                    status=403, content_type='application/json;charset=utf-8', headers=headers
                )

            transporter_info = {
                'id': transporter_cat.id if transporter_cat else None,
                'name': transporter_cat.name if transporter_cat else None,
            }

            # find a sample partner that belongs to the transporter category (no name filter)
            sample_partner_info = []
            if transporter_cat:
                Partner = request.env['res.partner'].sudo()
                sample_partner = Partner.search([('category_id', 'in', [transporter_cat.id])])
                for _courier in sample_partner:
                    # convert sample_partner into a JSON string for inclusion in API error responses
                    sample_obj = {
                        # 'id': sample_partner.id,
                        'name': _courier.name,
                        # 'email': sample_partner.email or None,
                        # 'phone': sample_partner.phone or None,
                    }
                    sample_partner_info.append(sample_obj)
            if sample_partner_info:
                sample_partner_info = json.dumps(sample_partner_info, ensure_ascii=False)
            else:
                sample_partner_info = ''

            for pf in principal_fields:
                v = data.get(pf)
                if not v or (isinstance(v, str) and not v.strip()):
                    # include transporter info to help callers configure system correctly
                    return Response(
                        json.dumps({
                            'error': f"Missing or empty field required for 'forder': {pf}",
                            'transporter_category': transporter_info,
                        }),
                        status=400, content_type='application/json;charset=utf-8', headers=headers
                    )

                # additional validation for principal_courier: ensure a partner exists that belongs to the
                # configured Transporter category and whose name matches (ilike) the provided courier string.
                if pf == 'principal_courier':
                    courier_name = (v or '').strip()
                    if not transporter_cat:
                        # transporter category not configured -> instruct caller
                        return Response(
                            json.dumps({
                                'error': "Transporter category is not configured in company settings.",
                                'expected_setting': 'company.fulfillment_transporter_category_id',
                                'provided_principal_courier': courier_name,
                            }),
                            status=400, content_type='application/json;charset=utf-8', headers=headers
                        )
                    # search partner (sudo to avoid ACL issues), match by transporter category and name ilike courier_name
                    Partner = request.env['res.partner'].sudo()
                    partner = Partner.search([('category_id', 'in', [transporter_cat.id]), ('name', 'ilike', courier_name)], limit=1)
                    if not partner:
                        # No matching transporter partner found — return error with transporter category info
                        return Response(
                            json.dumps({
                                'error': "Transporter partner not found for provided principal_courier.",
                                'provided_principal_courier': courier_name,
                                'available_transporter': sample_partner_info,
                                'hint': "Ensure a partner exists with a name matching the courier and is assigned the configured Transporter category."
                            }),
                            status=400, content_type='application/json;charset=utf-8', headers=headers
                        )

        # Resolve partner (id or email)
        partner = False
        partner_id = None
        partner_val = data.get('partner') or {}
        partner_model = request.env['res.partner'].sudo()
        if isinstance(partner_val, dict) and partner_val.get('id'):
            partner = partner_model.search([('id', '=', int(partner_val.get('id')) )], limit=1)
            if not partner:
                return Response(json.dumps({'error': 'partner id not found'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)
            partner_id = partner.id
        elif isinstance(partner_val, dict) and partner_val.get('email'):
            partner = partner_model.search([('email', '=', partner_val.get('email'))], limit=1)
            if not partner:
                return Response(json.dumps({'error': 'partner email not found'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)
            partner_id = partner.id
        else:
            return Response(json.dumps({'error': 'partner must be an object with id or email'}),
                            status=400, content_type='application/json;charset=utf-8', headers=headers)

        # Check user is member of partner
        user = request.env.user
        if not user.partner_id or not user.partner_id.parent_id or user.partner_id.parent_id.id != partner_id:
            return Response(json.dumps({'error': f'user {user.name} is not contact member of company {partner.name}'}),
                            status=400, content_type='application/json;charset=utf-8', headers=headers)

        # Validate products array and build lines
        products = data.get('products') or []
        if not isinstance(products, list) or len(products) == 0:
            return Response(json.dumps({'error': 'products must be a non-empty array'}),
                            status=400, content_type='application/json;charset=utf-8', headers=headers)

        allowed_tracking = ('serial', 'lot', 'none')
        product_lines = []
        for idx, p in enumerate(products, start=1):
            # product_qty
            try:
                qty = float(p.get('product_qty') or 0)
            except Exception:
                return Response(json.dumps({'error': f'product at index {idx} has invalid product_qty'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)

            if qty < 0:
                return Response(json.dumps({'error': f'product at index {idx} has negative product_qty'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)

            tracking_type = (p.get('tracking_type') or 'none')
            if tracking_type not in allowed_tracking:
                return Response(json.dumps({'error': f'product at index {idx} has invalid tracking_type (allowed: serial, lot, none)'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)

            tracking_no = p.get('tracking_no') or ''
            # note: we do not enforce serial count here; that will be validated later during processing/import.
            product_lines.append({
                'product_no': p.get('product_no') or '',
                'product_nanme': p.get('product_nanme') or '',
                'product_qty': qty,
                'product_uom': p.get('product_uom') or '',
                'tracking_type': tracking_type,
                'tracking_no': tracking_no,
            })

        # Build vals for create; include principal_* only when present (and they are required for 'forder' by earlier check)
        vals = {
            'transaction_no': data['transaction_no'],
            'type': data['type'],
            'datetime_string': data['datetime_string'],
            'partner_id': partner_id,
            'products': [(0, 0, pl) for pl in product_lines],
            'status': 'open',
        }

        if data['type'] == 'forder':
            # include the three principal fields (we validated their presence above)
            vals['principal_courier'] = (data.get('principal_courier') or '').strip()
            vals['principal_customer_name'] = (data.get('principal_customer_name') or '').strip()
            vals['principal_customer_address'] = (data.get('principal_customer_address') or '').strip()

        staging_model = request.env['incoming_staging'].with_user(request.env.user.id)
        try:
            with request.env.cr.savepoint():
                record = staging_model.create(vals)
            res = {'id': record.id, 'transaction_no': record.transaction_no, 'message': 'created'}

            # Please add code here (GitHUb_Copilot_Request#001)
            # if type = 'forder' and courier priority = instan (based on setting) then execute incoming_staging.action_create_transfer()
            rec = record.sudo()
            # principal_courier_id is computed/stored on incoming_staging -> res.partner
            courier_partner = rec.principal_courier_id
            if courier_partner:
                # determine company's configured priority label (fallback to 'Instan' if not set)
                company = rec.partner_id.company_id or request.env.company
                priority_label = (company.fulfillment_courier_label_priority or 'Instan').strip().lower()

                # partner label (may be stored on partner or computed)
                partner_label = (courier_partner.courier_scoring_label or '').strip().lower()

                if partner_label and partner_label == priority_label:
                    _logger.info(
                        "Auto-creating transfer for incoming_staging %s because courier priority is '%s'",
                        rec.id, partner_label
                    )
                    try:
                        # action_create_transfer can return a list of results; run as sudo to avoid ACL issues
                        results = rec.sudo().action_create_transfer()
                        # include summary in API response for client visibility
                        res['auto_transfer'] = {
                            'status': 'ok',
                            'results': results,
                        }
                    except Exception as e:
                        _logger.exception("Auto create transfer failed for incoming_staging %s: %s", rec.id, e)
                        res['auto_transfer'] = {
                            'status': 'error',
                            'error': str(e),
                        }
            else:
                # Optional: include a hint if no principal_courier_id resolved
                res.setdefault('auto_transfer', {'status': 'skipped', 'reason': 'no_principal_courier_id'})

            return Response(json.dumps(res), status=201, content_type='application/json;charset=utf-8', headers=headers)
        except ValidationError as vex:
            return Response(json.dumps({'error': 'validation_error', 'details': str(vex)}),
                            status=400, content_type='application/json;charset=utf-8', headers=headers)
        except Exception as exc:
            # still good to try rollback for unexpected errors
            try:
                request.env.cr.rollback()
            except Exception:
                _logger.exception("rollback failed")
            _logger.exception("unexpected error")
            return Response(json.dumps({'error': 'server_error', 'details': str(exc)}),
                            status=500, content_type='application/json;charset=utf-8', headers=headers)

    # OPTIONS preflight for the API endpoint
    @http.route('/api/incoming_staging', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def create_incoming_staging_options(self, **kw):
        headers = _cors_headers()
        return Response('', status=204, headers=headers)

    @http.route('/api/incoming_staging/docs', type='http', auth='none', methods=['GET'], csrf=False)
    def incoming_staging_docs(self, **kw):
        """
        OpenAPI JSON for the endpoint (use with Swagger UI / Postman).

        Note: tracking_type/tracking_no fields have been replaced with:
          - tracking_type: string enum ['none','lot','serial']
          - tracking_no: string (lot name or serial(s), for multiples use comma/semicolon/newline/pipe)
        """
        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "Incoming Staging API", "version": "1.0.0"},
            "paths": {
                "/api/incoming_staging": {
                    "post": {
                        "summary": "Create incoming staging",
                        "security": [{"bearerAuth": []}],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["transaction_no", "type", "datetime_string", "partner", "products"],
                                        "properties": {
                                            "transaction_no": {"type": "string"},
                                            "type": {"enum": ["inbound", "forder"]},
                                            "datetime_string": {"type": "string", "format": "date-time"},
                                            "partner": {
                                                "oneOf": [
                                                    {"type": "object", "properties": {"id": {"type": "integer"}}},
                                                    {"type": "object", "properties": {"email": {"type": "string"}}}
                                                ]
                                            },
                                            "products": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "product_no": {"type": "string"},
                                                        "product_nanme": {"type": "string"},
                                                        "product_qty": {"type": "number"},
                                                        "product_uom": {"type": "string"},
                                                        "tracking_type": {"type": "string", "enum": ["none", "lot", "serial"]},
                                                        "tracking_no": {"type": "string", "description": "Lot name or serial identifier(s). For multiple serials, separate by comma/semicolon/newline/pipe."}
                                                    }
                                                }
                                            },
                                            # principal_* fields are required when type == "forder"
                                            "principal_courier": {"type": "string", "description": "Courier name (required for type='forder')"},
                                            "principal_customer_name": {"type": "string", "description": "Customer name (required for type='forder')"},
                                            "principal_customer_address": {"type": "string", "description": "Customer address (required for type='forder')"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {"description": "Created"},
                            "400": {"description": "Bad Request"},
                            "401": {"description": "Unauthorized"},
                            "500": {"description": "Server Error"}
                        }
                    }
                }
            },
            "components": {
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "API key"}
                }
            }
        }
        headers = _cors_headers()
        return Response(json.dumps(openapi, indent=2), content_type='application/json;charset=utf-8', status=200, headers=headers)

    # OPTIONS preflight for the docs endpoint
    @http.route('/api/incoming_staging/docs', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def incoming_staging_docs_options(self, **kw):
        headers = _cors_headers()
        return Response('', status=204, headers=headers)