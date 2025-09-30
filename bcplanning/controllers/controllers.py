# from odoo import http


# class Bcplanning(http.Controller):
#     @http.route('/bcplanning/bcplanning', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/bcplanning/bcplanning/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('bcplanning.listing', {
#             'root': '/bcplanning/bcplanning',
#             'objects': http.request.env['bcplanning.bcplanning'].search([]),
#         })

#     @http.route('/bcplanning/bcplanning/objects/<model("bcplanning.bcplanning"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('bcplanning.object', {
#             'object': obj
#         })

