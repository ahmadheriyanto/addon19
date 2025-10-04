from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied
import json
from odoo.http import Response
from odoo.exceptions import ValidationError

class PlanningApiController(http.Controller):

    @http.route('/hello', type='http', auth='api_key', methods=['GET'], csrf=False)
    def test_hello(self, **post):
        user = request.env.user
        rtv = []
        # job_vals = {
        #     'user': user.name,            
        # }
        # rtv.append(job_vals)
        projects = request.env['bcproject'].with_user(user.id).search([])
        for job in projects:
            job_vals = {
              'job_no': job.job_no,
              'job_desc': job.job_desc,
            }
            rtv.append(job_vals)

        return Response(json.dumps(rtv),content_type='application/json;charset=utf-8',status=200)
    
    # render your QWeb template (portal_projects) as a portal page
    @http.route('/my/projects', type='http', auth='user', website=True)
    def portal_projects(self, **kwargs):
        # You can pass additional context to the template if needed
        return request.render('bcplanning.portal_projects', {})

    # List Projects
    @http.route('/portal/projects', type='http', auth='user', website=True)
    def list_projects(self, **kw):
        user = request.env.user   
        # Get Vendor
        vendors = request.env['bcexternaluser'].with_user(user.id).search([('user_id','=',user.id)], limit=1)
        if not vendors:
            raise ValidationError("setting of user vs vendor does not exist!")
        vendor = vendors[0]

        result = []
        projects = request.env['bcproject'].with_user(user.id).search([('partner_id','=',vendor.vendor_id)])
        if projects:
            for p in projects:
                res = request.env['res.partner'].sudo().search([('id','=',p.partner_id)])
                result.append({
                    'id': p.id,
                    'job_no': p.job_no,
                    'job_desc': p.job_desc,
                    # 'partner_name': 'Forbiden',
                    'partner_name': res.name if res else '',
                })

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json')]
        )

    # Create Project
    @http.route('/portal/projects/create', type='jsonrpc', auth='user', methods=['POST'])
    def create_project(self, **post):
        vals = {
            'job_no': post.get('job_no'),
            'job_desc': post.get('job_desc'),
            'partner_id': int(post.get('partner_id')) if post.get('partner_id') else False,
        }
        project = request.env['bcproject'].create(vals)
        return {'id': project.id}

    # Update Project
    @http.route('/portal/projects/update', type='jsonrpc', auth='user', methods=['POST'])
    def update_project(self, **post):
        project = request.env['bcproject'].browse(int(post['id']))
        vals = {
            'job_no': post.get('job_no'),
            'job_desc': post.get('job_desc'),
            'partner_id': int(post.get('partner_id')) if post.get('partner_id') else False,
        }
        project.write(vals)
        return {'success': True}

    # Delete Project
    @http.route('/portal/projects/delete', type='jsonrpc', auth='user', methods=['POST'])
    def delete_project(self, **post):
        project = request.env['bcproject'].browse(int(post['id']))
        project.unlink()
        return {'success': True}

    