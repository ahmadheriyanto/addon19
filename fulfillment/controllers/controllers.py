# from odoo import http


# class Fulfillment(http.Controller):
#     @http.route('/fulfillment/fulfillment', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/fulfillment/fulfillment/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('fulfillment.listing', {
#             'root': '/fulfillment/fulfillment',
#             'objects': http.request.env['fulfillment.fulfillment'].search([]),
#         })

#     @http.route('/fulfillment/fulfillment/objects/<model("fulfillment.fulfillment"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('fulfillment.object', {
#             'object': obj
#         })

