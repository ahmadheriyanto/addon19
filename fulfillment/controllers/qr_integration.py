# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class IncomingStagingQRIntegration(http.Controller):
    @http.route('/mobile_warehouse/api/process_incoming_qr', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def process_incoming_qr(self, payload=None, **kw):
        """
        Accept a JSON payload (sent by stockmobilescanner frontend) that was decoded from a QR.
        Expected payload shape (example):
          {
            "qr_type": "incomingstaging",
            "transaction_no": "IN-00080",
            "type": "forder" | "inbound",
            ... other fields ...
          }

        If qr_type == 'incomingstaging', this endpoint will find the incoming_staging record(s)
        by transaction_no and call action_create_transfer() on the recordset (sudo).
        Returns a JSON structure with the results list returned by action_create_transfer or an error.
        """
        try:
            # payload may be a dict (route type='jsonrpc') or a JSON string - normalize
            data = payload if isinstance(payload, dict) else (json.loads(payload) if isinstance(payload, str) else None)
        except Exception as e:
            _logger.exception("Failed to parse payload for process_incoming_qr: %s", e)
            return {'success': False, 'error': 'invalid_payload', 'details': str(e)}

        if not data:
            return {'success': False, 'error': 'missing_payload'}

        if data.get('qr_type') != 'incomingstaging':
            return {'success': False, 'error': 'unsupported_qr_type', 'qr_type': data.get('qr_type')}

        transaction_no = data.get('transaction_no')
        if not transaction_no:
            return {'success': False, 'error': 'missing_transaction_no'}

        env = request.env
        try:
            # Find incoming_staging records by transaction_no (use sudo to avoid access-rights issues)
            recs = env['incoming_staging'].sudo().search([('transaction_no', '=', transaction_no)])
            if not recs:
                return {'success': False, 'error': 'staging_not_found', 'transaction_no': transaction_no}

            # Call action_create_transfer on the recordset (function already handles inbound/forder/others)
            results = recs.action_create_transfer()
            # ensure serializable (lists/dicts with primitive types expected)
            return {'success': True, 'transaction_no': transaction_no, 'results': results}
        except Exception as exc:
            _logger.exception("Processing incomingstaging QR failed for %s: %s", transaction_no, exc)
            return {'success': False, 'error': 'processing_failed', 'details': str(exc)}