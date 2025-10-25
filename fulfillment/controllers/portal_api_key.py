import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class PortalAPIKeyController(http.Controller):
    @http.route('/my/api_key', type='http', auth='user', website=True)
    def my_api_key(self, **kw):
        """
        Independent page (no inheritance of portal templates) that shows API key metadata
        and a form to generate a new key. Accessible only to authenticated users
        (portal or internal).
        """
        user = request.env.user
        if not (user._is_portal() or user._is_internal()):
            return request.redirect('/web/login?redirect=/my/api_key')

        apikey_model = request.env['res.users.apikeys'].sudo()
        # Show metadata only; the actual key value is shown only once after creation.
        keys = apikey_model.search([('user_id', '=', user.id)])
        return request.render('fulfillment.portal_api_key_page', {
            'user': user,
            'keys': keys,
        })

    @http.route('/my/api_key/generate', type='http', auth='user', methods=['POST'], website=True)
    def generate_api_key(self, **post):
        """
        Generate a new API key for the logged-in user.
        - Authenticated (session) user only.
        - CSRF-protected (do NOT use csrf=False).
        - Shows the generated key once on a result page.
        """
        user = request.env.user
        if not (user._is_portal() or user._is_internal()):
            return request.redirect('/web/login?redirect=/my/api_key')

        name = post.get('name') or 'Portal API Key'
        expiration = post.get('expiration') or None
        scope = post.get('scope') or None  # optional, you can enforce a default scope here

        apikey_model = request.env['res.users.apikeys'].sudo()
        try:
            # Use the core generator; sudo() required for low-level DB insertion
            generated_key = apikey_model._generate(scope, name, expiration)

            # Refresh metadata list (no plaintext key stored)
            keys = apikey_model.search([('user_id', '=', user.id)])

            return request.render('fulfillment.portal_api_key_created', {
                'user': user,
                'generated_key': generated_key,
                'keys': keys,
                'name': name,
            })
        except Exception as e:
            _logger.exception("Failed to generate API key for user %s", user.id)
            # On error, render the page with an error message
            keys = apikey_model.search([('user_id', '=', user.id)])
            return request.render('fulfillment.portal_api_key_page', {
                'user': user,
                'keys': keys,
                'error': str(e),
            })