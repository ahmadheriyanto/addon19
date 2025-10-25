from odoo import http
from odoo.http import request, Response
import json
import logging

_logger = logging.getLogger(__name__)


class FulfillmentJSONRPCController(http.Controller):
    @http.route('/fulfillment/jsonrpc', type='jsonrpc', auth='none', csrf=False, methods=['POST'])
    def jsonrpc(self, **kw):
        """
        JSON-RPC 2.0 endpoint that accepts requests with Content-Type: application/json.
        Example payload:
        {
          "jsonrpc": "2.0",
          "method": "incoming_staging.create",
          "params": {
            "transaction_no": "TX-001",
            "type": "inbound",
            "date": "2025-10-25",
            "partner_id": 3,
            "status": "open",
            "products": [
              {
                "product_no": "P-001",
                "product_name": "Example",
                "product_lot": "LOT-1",
                "product_serial": "S-1",
                "product_qty": 10.0,
                "product_uom": "Unit"
              }
            ]
          },
          "id": 1
        }

        Authentication:
        - Provide header 'X-API-Key' with the same value as system parameter 'fulfillment.api_key'.
        Notes:
        - Route uses type='jsonrpc' as requested.
        - The controller parses raw request body to ensure correct JSON-RPC handling and returns JSON-RPC formatted responses.
        """
        # Read raw body and parse JSON to strictly validate JSON-RPC structure
        raw = request.httprequest.get_data(as_text=True)
        try:
            data = json.loads(raw)
        except Exception:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error: invalid JSON"},
                "id": None,
            }

        # Basic JSON-RPC validation
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or "method" not in data:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": data.get("id") if isinstance(data, dict) else None,
            }

        # API key check (header preferred)
        api_key_header = request.httprequest.headers.get("X-API-Key")
        api_key_param = (data.get("params") or {}).get("api_key")
        api_key_supplied = api_key_header or api_key_param
        configured_key = request.env["ir.config_parameter"].sudo().get_param("fulfillment.api_key")
        if not configured_key or api_key_supplied != configured_key:
            return {
                "jsonrpc": "2.0",
                "error": {"code": 401, "message": "Unauthorized: invalid or missing API key"},
                "id": data.get("id"),
            }

        method = data.get("method")
        params = data.get("params", {}) or {}

        # Only support incoming_staging.create for now
        if method != "incoming_staging.create":
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": data.get("id"),
            }

        # Required params validation
        transaction_no = params.get("transaction_no")
        partner_id = params.get("partner_id")
        if not transaction_no or not partner_id:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Invalid params: 'transaction_no' and 'partner_id' are required",
                },
                "id": data.get("id"),
            }

        # Prepare values and create records using sudo so external systems can write
        staging_vals = {
            "transaction_no": transaction_no,
            "type": params.get("type", ""),
            "date": params.get("date"),
            "partner_id": partner_id,
            "status": params.get("status", "open"),
        }

        try:
            staging = request.env["incoming_staging"].sudo().create(staging_vals)

            products = params.get("products", []) or []
            for p in products:
                product_vals = {
                    "incoming_staging_id": staging.id,
                    "product_no": p.get("product_no"),
                    # accept either product_name or legacy product_nanme
                    "product_nanme": p.get("product_name") or p.get("product_nanme"),
                    "product_lot": p.get("product_lot"),
                    "product_serial": p.get("product_serial"),
                    "product_qty": p.get("product_qty") or 0.0,
                    "product_uom": p.get("product_uom"),
                }
                request.env["incoming_staging_product"].sudo().create(product_vals)

            return {"jsonrpc": "2.0", "result": {"id": staging.id}, "id": data.get("id")}
        except Exception as e:
            _logger.exception("Error creating incoming_staging via JSON-RPC")
            return {
                "jsonrpc": "2.0",
                "error": {"code": 500, "message": "Server error: %s" % str(e)},
                "id": data.get("id"),
            }