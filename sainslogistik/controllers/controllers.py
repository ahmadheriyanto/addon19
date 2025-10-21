# from odoo import http


# class Sainslogistik(http.Controller):
#     @http.route('/sainslogistik/sainslogistik', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sainslogistik/sainslogistik/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sainslogistik.listing', {
#             'root': '/sainslogistik/sainslogistik',
#             'objects': http.request.env['sainslogistik.sainslogistik'].search([]),
#         })

#     @http.route('/sainslogistik/sainslogistik/objects/<model("sainslogistik.sainslogistik"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sainslogistik.object', {
#             'object': obj
#         })

