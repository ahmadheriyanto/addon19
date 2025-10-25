from odoo import http
from odoo.http import request, Response
import json

class HelloController(http.Controller):

    # ********************* api_key group ********************************************************
    @http.route('/hello', type='http', auth='api_key', methods=['GET'], csrf=False)
    def test_hello(self, **post):
        user = request.env.user
        rtv = []        
        vals = {
            'response': f'Hello {user.name}',
        }
        rtv.append(vals)

        return Response(json.dumps(rtv),content_type='application/json;charset=utf-8',status=200)