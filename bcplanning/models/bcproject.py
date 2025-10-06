from odoo import models, fields, api
from odoo.exceptions import ValidationError


class bcplanning_project(models.Model):
    _name = 'bcproject'
    _description = 'bcproject'
    _rec_name = 'job_no'
    
    job_no = fields.Char(string="Job No.", required=True)
    job_desc = fields.Char(string="Description")
    partner_id = fields.Many2one('res.partner', string='Partner', domain="[]")
    task_line = fields.One2many(
        comodel_name='bctask',
        inverse_name='job_id',
        string="Task Lines",
        copy=True, bypass_search_access=True)

    @api.constrains('job_no')
    def _check_job_no_unique(self):
        for record in self:
            # search for another record with the same job_no
            existing = self.env['bcproject'].search([
                ('job_no', '=', record.job_no),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('Job No must be unique!')

    def projectcreationfrombc(self, posted_data):
        print(posted_data)
        return posted_data

        

class bcplanning_task(models.Model):
    _name = 'bctask'
    _description = 'bctask'
    _rec_name = 'task_no'

    task_no = fields.Char(required=True)
    task_desc = fields.Char()
    job_id = fields.Many2one(
        comodel_name='bcproject',
        string="Project Reference",
        required=True, ondelete='cascade', index=True, copy=False)
    planning_line = fields.One2many(
        comodel_name='bcplanningline',
        inverse_name='task_id',
        string="Planning Lines",
        copy=True, bypass_search_access=True)

    
    @api.constrains('task_no', 'job_id')
    def _check_job_no_unique(self):
        for record in self:
            # search for another record with the same task_no and job_id
            existing = self.env['bctask'].search([
                ('task_no', '=', record.task_no),
                ('job_id', '=', record.job_id),
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('Task No must be unique per Job No.!')


class bcplanning_line(models.Model):
    _name = 'bcplanningline'
    _description = 'bcplanningline'
    _rec_name = 'planning_line_no'

    planning_line_no = fields.Char(required=True)
    planning_line_desc = fields.Char()    
    task_id = fields.Many2one(
        comodel_name='bctask',
        string="Task Reference",
        required=True, ondelete='cascade', index=True, copy=False)
    job_id = fields.Many2one(
        comodel_name='bcproject',
        string="Project Reference",
        compute="_get_job_id", store=True)

    @api.depends('task_id')
    def _get_job_id(self):
        for record in self:
            record.job_id = False
            task = self.env['bctask'].search([('id','=',record.task_id)])
            if task:
                record.job_id = task[0].job_id.id

    @api.constrains('planning_line_no', 'task_id')
    def _check_job_no_unique(self):
        for record in self:
            # search for another record with the same planning_line_no, task_id
            existing = self.env['bcplanningline'].search([
                ('planning_line_no', '=', record.planning_line_no),
                ('task_id', '=', record.task_id),            
                ('id', '!=', record.id)
            ], limit=1)
            if existing:
                raise ValidationError('Planning Line No must be unique per Task No.!')