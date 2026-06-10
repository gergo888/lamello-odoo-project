# from odoo import http


# class LamelloCustomizations(http.Controller):
#     @http.route('/lamello_customizations/lamello_customizations', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/lamello_customizations/lamello_customizations/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('lamello_customizations.listing', {
#             'root': '/lamello_customizations/lamello_customizations',
#             'objects': http.request.env['lamello_customizations.lamello_customizations'].search([]),
#         })

#     @http.route('/lamello_customizations/lamello_customizations/objects/<model("lamello_customizations.lamello_customizations"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('lamello_customizations.object', {
#             'object': obj
#         })

