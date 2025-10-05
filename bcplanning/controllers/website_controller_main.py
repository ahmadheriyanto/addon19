from odoo import http
from odoo.http import request
from odoo.addons.website.controllers.main import Website

class WebsiteCustomLoginRedirect(Website):

    def _login_redirect(self, uid, redirect=None):
        """ Redirect regular users (employees) to the backend) and others to
        the frontend
        """
        if not redirect and request.params.get('login_success'):
            if request.env['res.users'].browse(uid)._is_internal():
                redirect = '/odoo?' + request.httprequest.query_string.decode()
            else:
                redirect = '/partner/projects'
        return super()._login_redirect(uid, redirect=redirect)