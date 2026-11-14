# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProjectBaseline(models.Model):
    _name = 'project.baseline'
    _description = 'Project Schedule Baseline'
    _order = 'approved_date desc, baseline_date desc, create_date desc'

    name = fields.Char(
        string='Baseline Name',
        required=True,
        default=lambda self: _('Initial Approved Plan'),
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    baseline_date = fields.Date(
        string='Baseline Date',
        default=fields.Date.context_today,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('approved', 'Approved'),
            ('superseded', 'Superseded'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
    )
    approved_date = fields.Datetime(
        string='Approved On',
        readonly=True,
    )
    task_line_ids = fields.One2many(
        'project.baseline.task.line',
        'baseline_id',
        string='Snapshot Lines',
        copy=True,
    )
    notes = fields.Text(string='Revision / Capture Notes')

    tasks_count = fields.Integer(
        string='Snapshot Tasks Count',
        compute='_compute_tasks_count',
    )
    baseline_finish_date = fields.Date(
        string='Baseline Finish Date',
        compute='_compute_baseline_finish_date',
        store=True,
    )

    @api.depends('task_line_ids')
    def _compute_tasks_count(self):
        for rec in self:
            rec.tasks_count = len(rec.task_line_ids)

    @api.depends('task_line_ids.planned_end_snapshot', 'task_line_ids')
    def _compute_baseline_finish_date(self):
        for rec in self:
            end_dates = [line.planned_end_snapshot for line in rec.task_line_ids if line.planned_end_snapshot]
            rec.baseline_finish_date = max(end_dates) if end_dates else False

    def action_capture_tasks(self):
        """Populate or refresh snapshot lines from current project tasks."""
        self.ensure_one()
        if self.state == 'approved':
            raise UserError(_("Approved baselines cannot be modified. Create a new baseline for schedule changes."))

        self.task_line_ids.unlink()

        tasks = self.env['project.task'].search([('project_id', '=', self.project_id.id)])
        today = fields.Date.context_today(self)
        lines_vals = []
        for task in tasks:
            start = task.start_date or (task.create_date.date() if task.create_date else today)
            end = task.end_date or (task.date_deadline.date() if task.date_deadline else start)
            duration = (end - start).days + 1 if (start and end and end >= start) else 1
            lines_vals.append({
                'baseline_id': self.id,
                'task_id': task.id,
                'task_name_snapshot': task.name,
                'planned_start_snapshot': start,
                'planned_end_snapshot': end,
                'duration_snapshot': duration,
                'is_milestone_snapshot': bool(task.milestone_id) if hasattr(task, 'milestone_id') else False,
            })

        if lines_vals:
            self.env['project.baseline.task.line'].create(lines_vals)

        return True

    def action_approve(self):
        """Approve baseline and supersede any existing approved baseline for this project."""
        self.ensure_one()
        if not self.task_line_ids:
            self.action_capture_tasks()

        # Supersede prior approved baselines for this project
        prior_approved = self.search([
            ('project_id', '=', self.project_id.id),
            ('state', '=', 'approved'),
            ('id', '!=', self.id),
        ])
        prior_approved.write({'state': 'superseded'})

        self.write({
            'state': 'approved',
            'approved_by_id': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })
        return True


class ProjectBaselineTaskLine(models.Model):
    _name = 'project.baseline.task.line'
    _description = 'Project Baseline Task Line'
    _order = 'planned_end_snapshot asc, id asc'

    baseline_id = fields.Many2one(
        'project.baseline',
        string='Baseline',
        required=True,
        ondelete='cascade',
        index=True,
    )
    task_id = fields.Many2one(
        'project.task',
        string='Current Task',
        ondelete='set null',
        index=True,
    )
    task_name_snapshot = fields.Char(string='Task Name (Snapshot)', required=True)
    planned_start_snapshot = fields.Date(string='Planned Start (Snapshot)')
    planned_end_snapshot = fields.Date(string='Planned End (Snapshot)')
    duration_snapshot = fields.Integer(string='Duration (Days)')
    is_milestone_snapshot = fields.Boolean(string='Is Milestone Task', default=False)
