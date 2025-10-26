# -*- coding: utf-8 -*-
# Controller for Incoming Staging API
# - Endpoint: POST /api/incoming_staging
# - Authentication: auth='api_key' (relies on your ir.http._auth_method_api_key extension)
# - Body: application/json with transaction_no, type, datetime_string, partner (id or email), products[]
# - Returns: JSON with created record id / errors
from datetime import datetime
import json
import logging

from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class IncomingStagingAPI(http.Controller):
    @http.route('/api/incoming_staging', type='http', auth='api_key', methods=['POST'], csrf=False)
    def create_incoming_staging(self, **kw):
        """
        Create an incoming_staging record.

        Expected JSON body (application/json):
        {
          "transaction_no": "TRX-001",
          "type": "inbound",                   # 'inbound' or 'forder'
          "datetime_string": "2025-10-26T01:13:55",
          "partner": {"id": 12} OR {"email": "acme@example.com"},
          "products": [
            {
              "product_no": "P001",
              "product_nanme": "Product One",
              "product_lot": "LOT-1",
              "product_serial": "SN-001",
              "product_qty": 2,
              "product_uom": "pcs"
            },
            ...
          ]
        }

        The endpoint requires a valid API key (Authorization: Bearer <key>).
        The request is executed with the API-key user's identity (request.env.user).
        """
        try:
            data = request.httprequest.get_json(force=True)
        except Exception as e:
            return Response(json.dumps({'error': 'Invalid JSON body', 'details': str(e)}),
                            status=400, content_type='application/json;charset=utf-8')

        # Basic required fields validation
        required = ['transaction_no', 'type', 'datetime_string', 'partner', 'products']
        for f in required:
            if f not in data:
                return Response(json.dumps({'error': f'Missing field: {f}'}),
                                status=400, content_type='application/json;charset=utf-8')

        # Validate type
        if data['type'] not in ('inbound', 'forder'):
            return Response(json.dumps({'error': "Invalid 'type' value. Expected 'inbound' or 'forder'."}),
                            status=400, content_type='application/json;charset=utf-8')

        # Validate datetime format (ISO-like expected)
        try:
            # Accept ISO 8601 like 'YYYY-MM-DDTHH:MM:SS' (with or without timezone)
            datetime.fromisoformat(data['datetime_string'])
        except Exception:
            return Response(json.dumps({'error': "Invalid 'datetime_string'. Expected ISO format like 2025-10-26T01:13:55"}),
                            status=400, content_type='application/json;charset=utf-8')

        # Resolve partner: allow { "id": <int> } or { "email": "<email>" }
        partner_id = None
        partner_val = data.get('partner') or {}
        partner_model = request.env['res.partner'].sudo()
        if isinstance(partner_val, dict) and partner_val.get('id'):
            partner = partner_model.search([('id', '=', int(partner_val.get('id')) )], limit=1)
            if not partner:
                return Response(json.dumps({'error': 'partner id not found'}),
                                status=400, content_type='application/json;charset=utf-8')
            partner_id = partner.id
        elif isinstance(partner_val, dict) and partner_val.get('email'):
            partner = partner_model.search([('email', '=', partner_val.get('email'))], limit=1)
            if not partner:
                return Response(json.dumps({'error': 'partner email not found'}),
                                status=400, content_type='application/json;charset=utf-8')
            partner_id = partner.id
        else:
            return Response(json.dumps({'error': 'partner must be an object with id or email'}),
                            status=400, content_type='application/json;charset=utf-8')

        # Build product lines
        products = data.get('products') or []
        if not isinstance(products, list) or len(products) == 0:
            return Response(json.dumps({'error': 'products must be a non-empty array'}),
                            status=400, content_type='application/json;charset=utf-8')

        product_lines = []
        for idx, p in enumerate(products, start=1):
            # allow missing optional fields, but validate qty numeric
            try:
                qty = float(p.get('product_qty') or 0)
            except Exception:
                return Response(json.dumps({'error': f'product at index {idx} has invalid product_qty'}),
                                status=400, content_type='application/json;charset=utf-8')

            product_lines.append({
                'product_no': p.get('product_no') or '',
                'product_nanme': p.get('product_nanme') or '',
                'product_lot': p.get('product_lot') or '',
                'product_serial': p.get('product_serial') or '',
                'product_qty': qty,
                'product_uom': p.get('product_uom') or '',
            })

        # Prepare values for create
        vals = {
            'transaction_no': data['transaction_no'],
            'type': data['type'],
            'datetime_string': data['datetime_string'],
            'partner_id': partner_id,
            'products': [(0, 0, pl) for pl in product_lines],
            'status': 'open',
        }

        # Create record as the authenticated API user (RBAC applies)
        try:
            staging_model = request.env['incoming_staging'].with_user(request.env.user.id)
            # Use sudo() only if you intentionally want to bypass access rules; here we respect user rights.
            record = staging_model.create(vals)
            res = {
                'id': record.id,
                'transaction_no': record.transaction_no,
                'message': 'created',
            }
            return Response(json.dumps(res), status=201, content_type='application/json;charset=utf-8')
        except Exception as exc:
            _logger.exception("Failed to create incoming_staging from API user %s", request.env.user.id)
            return Response(json.dumps({'error': 'server_error', 'details': str(exc)}),
                            status=500, content_type='application/json;charset=utf-8')

    @http.route('/api/incoming_staging/docs', type='http', auth='none', methods=['GET'], csrf=False)
    def incoming_staging_docs(self, **kw):
        """
        Simple OpenAPI-like JSON description to inspect the expected payload (useful for Swagger/Postman).
        Publicly accessible (auth='none') so integrators can fetch the schema. Remove or protect if you prefer.
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
                                                        "product_lot": {"type": "string"},
                                                        "product_serial": {"type": "string"},
                                                        "product_qty": {"type": "number"},
                                                        "product_uom": {"type": "string"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {"description": "Created", "content": {"application/json": {}}},
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
        return Response(json.dumps(openapi, indent=2), content_type='application/json;charset=utf-8', status=200)