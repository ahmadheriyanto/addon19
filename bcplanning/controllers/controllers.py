from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied
import json
from odoo.http import Response

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
    
    
    # def authenticate(self, db, username, password):
    #     """Return uid if authentication is successful, else None."""
    #     try:
    #         uid = request.session.authenticate(db, username, password)
    #         return uid
    #     except AccessDenied:
    #         return None

    # @http.route('/api/project', type='json', auth='none', methods=['POST'], csrf=False)
    # def create_project(self, **post):
    #     # Required: db, username, password in payload!
    #     db = post.get('db')
    #     username = post.get('username')
    #     password = post.get('password')
    #     job_no = post.get('job_no')
    #     job_desc = post.get('job_desc')

    #     uid = self.authenticate(db, username, password)
    #     if not uid:
    #         return {'error': 'Authentication failed'}

    #     # Use sudo() if you want to bypass record rules, otherwise use normal env
    #     project = request.env['bcproject'].with_user(uid).create({
    #         'job_no': job_no,
    #         'job_desc': job_desc
    #     })
    #     return {'id': project.id, 'job_no': project.job_no}

    # @http.route('/api/task', type='json', auth='none', methods=['POST'], csrf=False)
    # def create_task(self, **post):
    #     db = post.get('db')
    #     username = post.get('username')
    #     password = post.get('password')
    #     task_no = post.get('task_no')
    #     task_desc = post.get('task_desc')
    #     job_id = post.get('job_id')

    #     uid = self.authenticate(db, username, password)
    #     if not uid:
    #         return {'error': 'Authentication failed'}

    #     task = request.env['bctask'].with_user(uid).create({
    #         'task_no': task_no,
    #         'task_desc': task_desc,
    #         'job_id': job_id
    #     })
    #     return {'id': task.id, 'task_no': task.task_no}

    # @http.route('/api/planningline', type='json', auth='none', methods=['POST'], csrf=False)
    # def create_planningline(self, **post):
    #     db = post.get('db')
    #     username = post.get('username')
    #     password = post.get('password')
    #     planning_line_no = post.get('planning_line_no')
    #     planning_line_desc = post.get('planning_line_desc')
    #     job_id = post.get('job_id')
    #     task_id = post.get('task_id')

    #     uid = self.authenticate(db, username, password)
    #     if not uid:
    #         return {'error': 'Authentication failed'}

    #     planningline = request.env['bcplanningline'].with_user(uid).create({
    #         'planning_line_no': planning_line_no,
    #         'planning_line_desc': planning_line_desc,
    #         'job_id': job_id,
    #         'task_id': task_id
    #     })
    #     return {'id': planningline.id, 'planning_line_no': planningline.planning_line_no}