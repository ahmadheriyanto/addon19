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
    

    @http.route('/partner/projects', type='http', auth='user', website=True)
    def partner_project(self):
        user = request.env.user
        # Get Vendor
        vendors = request.env['bcexternaluser'].with_user(user.id).search([('user_id','=',user.id)], limit=1)
        if not vendors:
            raise ValidationError("setting of user vs vendor does not exist!")
        vendor = vendors[0]
        res = request.env['res.partner'].sudo().search([('id','=',vendor.vendor_id.id)])

        project_data = []
        projects = request.env['bcproject'].with_user(user.id).search([('partner_id','=',vendor.vendor_id.id)])
        if projects:
            for p in projects:                
                project_data.append({
                    'id': p.id,
                    'job_no': p.job_no if p.job_no else '-',
                    'job_desc': p.job_desc if p.job_desc else '-',
                    'task_count': len(p.task_line),
                    'partner_name': res.name if res else '',
                })
        datas = {
            'partner_id': vendor.vendor_id,
            'partner_name': res.name if res else '',
            'projects': project_data,
        }
        return request.render('bcplanning.web_partner_project_template',datas)

    @http.route('/partner/tasks', type='http', auth='user', website=True)
    def partner_tasks(self, job_id=None, job_no=None, job_name=None, **kwargs):
        print(job_id)
        print(job_no)
        print(job_name)
        
        user = request.env.user

        # Get Vendor from bcexternaluser (adapt this if your vendor relation is different)
        vendors = request.env['bcexternaluser'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not vendors:
            raise ValidationError("User to vendor mapping not found!")
        vendor = vendors[0]
        partner_id = vendor.vendor_id.id

        # Get projects for vendor
        project = request.env['bcproject'].with_user(user.id).search([('id', '=', job_id),('partner_id', '=', partner_id)])
        if not project:
            raise ValidationError(f"Project {job_no} for user {user.name} is not found!")

        # Get tasks for projects
        tasks = request.env['bctask'].with_user(user.id).search([('job_id', '=', project.id)])

        # Build task data
        task_data = []
        for t in tasks:
            task_data.append({
                'id': t.id,
                'task_no': t.task_no,
                'task_desc': t.task_desc,                
            })

        datas = {
            'tasks': task_data,
            'job_id': job_id,
            'job_no': job_no,
            'job_desc': job_name,
            'partner_name': vendor.vendor_id.name if vendor.vendor_id else 'No partner found.',
        }
        return request.render('bcplanning.web_partner_task_template', datas)
        

    # # render your QWeb template (portal_projects) as a portal page
    # @http.route('/my/projects', type='http', auth='user', website=True)
    # def portal_projects(self, **kwargs):
    #     # You can pass additional context to the template if needed
    #     return request.render('bcplanning.portal_projects', {})

    # # List Projects
    # @http.route('/portal/projects', type='http', auth='user', website=True)
    # def list_projects(self, **kw):
    #     user = request.env.user   
    #     # Get Vendor
    #     vendors = request.env['bcexternaluser'].with_user(user.id).search([('user_id','=',user.id)], limit=1)
    #     if not vendors:
    #         raise ValidationError("setting of user vs vendor does not exist!")
    #     vendor = vendors[0]

    #     result = []
    #     projects = request.env['bcproject'].with_user(user.id).search([('partner_id','=',vendor.vendor_id.id)])
    #     if projects:
    #         for p in projects:
    #             res = request.env['res.partner'].sudo().search([('id','=',p.partner_id.id)])
    #             result.append({
    #                 'id': p.id,
    #                 'job_no': p.job_no,
    #                 'job_desc': p.job_desc,
    #                 'partner_name': res.name if res else '',
    #             })

    #     return request.make_response(
    #         json.dumps(result),
    #         headers=[('Content-Type', 'application/json')]
    #     )

    # # Create Project
    # @http.route('/portal/projects/create', type='jsonrpc', auth='user', methods=['POST'])
    # def create_project(self, **post):
    #     vals = {
    #         'job_no': post.get('job_no'),
    #         'job_desc': post.get('job_desc'),
    #         'partner_id': int(post.get('partner_id')) if post.get('partner_id') else False,
    #     }
    #     project = request.env['bcproject'].create(vals)
    #     return {'id': project.id}

    # # Update Project
    # @http.route('/portal/projects/update', type='jsonrpc', auth='user', methods=['POST'])
    # def update_project(self, **post):
    #     project = request.env['bcproject'].browse(int(post['id']))
    #     vals = {
    #         'job_no': post.get('job_no'),
    #         'job_desc': post.get('job_desc'),
    #         'partner_id': int(post.get('partner_id')) if post.get('partner_id') else False,
    #     }
    #     project.write(vals)
    #     return {'success': True}

    # # Delete Project
    # @http.route('/portal/projects/delete', type='jsonrpc', auth='user', methods=['POST'])
    # def delete_project(self, **post):
    #     project = request.env['bcproject'].browse(int(post['id']))
    #     project.unlink()
    #     return {'success': True}

    