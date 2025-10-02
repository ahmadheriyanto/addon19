from odoo import models, fields, api
from odoo.exceptions import ValidationError


class bcplanning_project(models.Model):
    _name = 'bcproject'
    _description = 'bcproject'
    _rec_name = 'job_no'

    job_no = fields.Char(required=True)
    job_desc = fields.Char()
    task_line = fields.One2many(
        comodel_name='bctask',
        inverse_name='job_id',
        string="Task Lines",
        copy=True, bypass_search_access=True)

    _sql_constraints = [
        ('job_no_unique', 'unique(job_no)', 'Job No must be unique!')
    ]    

    # value2 = fields.Float(compute="_value_pc", store=True)
    # @api.depends('value')
    # def _value_pc(self):
    #     for record in self:
    #         record.value2 = float(record.value) / 100

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

    _sql_constraints = [
        (
            'unique_task_per_job',
            'unique(task_no, job_id)',
            'Task No must be unique per Job!'
        )
    ]


class bcplanning_line(models.Model):
    _name = 'bcplanningline'
    _description = 'bcplanningline'
    _rec_name = 'planning_line_no'

    planning_line_no = fields.Char(required=True)
    planning_line_desc = fields.Char()
    job_id = fields.Many2one(
        comodel_name='bcproject',
        string="Project Reference",
        required=True, ondelete='cascade', index=True, copy=False)
    task_id = fields.Many2one(
        comodel_name='bctask',
        string="Task Reference",
        required=True, ondelete='cascade', index=True, copy=False)

    _sql_constraints = [
        (
            'unique_planning_line_no_per_job_task',
            'unique(planning_line_no, job_id, task_id)',
            'Planning Line No must be unique per Job and Task!'
        )
    ]