from odoo import http
from odoo.http import request

class StockMobileHello(http.Controller):
    @http.route(['/mobile_warehouse/hello'], type='http', auth='public', website=True)
    def hello(self, **kw):
        # Render the QWeb template with a small message
        return request.render('stockmobilescanner.hello_world_template', {
            'message': 'Hello World — Stock Mobile Scanner test page',
        })