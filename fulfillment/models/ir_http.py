# -*- coding: utf-8 -*-
from werkzeug.exceptions import Unauthorized
import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_api_key(cls):
        """
        Authenticate requests using an API key supplied in the Authorization header:
           Authorization: Bearer <api_key>

        This method resolves the API key to a user via res.users.apikeys._check_credentials(...)
        and updates the request environment to act as that user.
        """
        # read header
        auth_header = request.httprequest.headers.get('Authorization') or ''
        if not auth_header:
            _logger.debug("API auth: missing Authorization header")
            raise Unauthorized("Missing API key")

        token = auth_header
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()

        if not token:
            _logger.debug("API auth: empty Bearer token")
            raise Unauthorized("Missing API key")

        # Replace this scope with the one your API expects (or pass None if your _check_credentials accepts it)
        scope = 'odoo.plugin.outlook'

        try:
            user_id = request.env['res.users.apikeys']._check_credentials(scope=scope, key=token)
        except Exception as e:
            _logger.exception("API auth: error checking credentials")
            raise Unauthorized("Invalid API key")

        if not user_id:
            _logger.info("API auth: invalid token (scope=%s) from %s", scope, request.httprequest.remote_addr)
            raise Unauthorized("Invalid API key")

        # set request user (user_id may be integer)
        request.update_env(user=user_id)
        # copy user's context into the request context
        try:
            request.update_context(**request.env.user.context_get())
        except Exception:
            # non-fatal, but log
            _logger.debug("API auth: failed to update context for user %s", user_id)

        _logger.info("API auth: success user=%s (via api key prefix=%s) from %s", request.env.user.login, token[:8], request.httprequest.remote_addr)