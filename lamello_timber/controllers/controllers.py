# from odoo import http


# class LamelloTimber(http.Controller):
#     @http.route('/lamello_timber/lamello_timber', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/lamello_timber/lamello_timber/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('lamello_timber.listing', {
#             'root': '/lamello_timber/lamello_timber',
#             'objects': http.request.env['lamello_timber.lamello_timber'].search([]),
#         })

#     @http.route('/lamello_timber/lamello_timber/objects/<model("lamello_timber.lamello_timber"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('lamello_timber.object', {
#             'object': obj
#         })

