# -*- coding: utf-8 -*-
# Controller for Incoming Staging API with CORS support
from datetime import datetime
import json
import logging

from odoo import http, fields
from odoo.http import request, Response

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
        Auth: Authorization: Bearer <API_KEY> (relies on your ir.http._auth_method_api_key)

        Expected JSON (application/json):
        {
          "transaction_no": "TRX-001",
          "type": "inbound" | "forder",
          "datetime_string": "YYYY-MM-DDTHH:MM:SS",
          "partner": {"id":123} OR {"email":"x@x.com"},
          "products": [{...}, ...]
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

        # Required fields
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

        # Resolve partner (id or email)
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

        # Validate products array and build lines
        products = data.get('products') or []
        if not isinstance(products, list) or len(products) == 0:
            return Response(json.dumps({'error': 'products must be a non-empty array'}),
                            status=400, content_type='application/json;charset=utf-8', headers=headers)

        product_lines = []
        for idx, p in enumerate(products, start=1):
            try:
                qty = float(p.get('product_qty') or 0)
            except Exception:
                return Response(json.dumps({'error': f'product at index {idx} has invalid product_qty'}),
                                status=400, content_type='application/json;charset=utf-8', headers=headers)

            product_lines.append({
                'product_no': p.get('product_no') or '',
                'product_nanme': p.get('product_nanme') or '',
                'product_lot': p.get('product_lot') or '',
                'product_serial': p.get('product_serial') or '',
                'product_qty': qty,
                'product_uom': p.get('product_uom') or '',
            })

        vals = {
            'transaction_no': data['transaction_no'],
            'type': data['type'],
            'datetime_string': data['datetime_string'],
            'partner_id': partner_id,
            'products': [(0, 0, pl) for pl in product_lines],
            'status': 'open',
        }

        try:
            staging_model = request.env['incoming_staging'].with_user(request.env.user.id)
            record = staging_model.create(vals)
            res = {
                'id': record.id,
                'transaction_no': record.transaction_no,
                'message': 'created',
            }
            return Response(json.dumps(res), status=201, content_type='application/json;charset=utf-8', headers=headers)
        except Exception as exc:
            _logger.exception("Failed to create incoming_staging from API user %s", request.env.user.id)
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