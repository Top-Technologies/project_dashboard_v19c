# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProjectDashboardSnapshot(models.Model):
    _name = 'project.dashboard.snapshot'
    _description = 'Project Daily Dashboard Metrics Snapshot'
    _order = 'snapshot_date desc, id desc'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    snapshot_date = fields.Date(
        string='Snapshot Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    health_score = fields.Float(string='Health Score (0-100)')
    health_status = fields.Selection(
        selection=[
            ('healthy', 'Healthy'),
            ('needs_attention', 'Needs Attention'),
            ('critical', 'Critical'),
            ('not_rated', 'Not Rated'),
        ],
        string='Health Status',
        default='not_rated',
    )
    total_tasks = fields.Integer(string='Total Tasks')
    completed_tasks = fields.Integer(string='Completed Tasks')
    overdue_tasks = fields.Integer(string='Overdue Tasks')
    active_tasks = fields.Integer(string='Active Tasks')
    open_risks = fields.Integer(string='Open Risks')
    high_risks = fields.Integer(string='High / Critical Risks')
    risk_exposure_score = fields.Integer(string='Risk Exposure Aggregate')
    pending_client_actions = fields.Integer(string='Pending Client Actions')
    schedule_variance_days = fields.Integer(string='Schedule Variance (Days)')

    _sql_constraints = [
        (
            'project_snapshot_date_uniq',
            'unique(project_id, snapshot_date)',
            'Only one dashboard snapshot per project per date is allowed.',
        )
    ]

    @api.model
    def cron_capture_daily_snapshots(self):
        """Cron job to capture daily metric snapshots for active projects."""
        today = fields.Date.context_today(self)
        projects = self.env['project.project'].search([
            ('x_project_status', 'in', ['new', 'in_progress', 'on_hold']),
        ])
        for project in projects:
            health = project._compute_project_health_score(reporting_date=today)
            tasks = project.task_ids
            completed = tasks.filtered(lambda t: t.completed_date or (t.stage_id and t.stage_id.name in ('Done', 'Implemented')))
            active = tasks - completed
            overdue = active.filtered(lambda t: t.x_is_overdue or (t.end_date and t.end_date < today))

            # Risks
            risks = project.x_risk_issue_ids.filtered(lambda r: r.type == 'risk' and r.status in ('open', 'in_progress'))
            high_risks = risks.filtered(lambda r: (r.inherent_score or 0) >= 10 or r.severity == 'high')
            risk_exposure = sum(r.inherent_score or 0 for r in risks)

            # Client actions
            client_actions = project.x_client_action_ids.filtered(lambda a: not a.is_done)

            # Schedule variance from approved baseline
            variance_days = 0
            approved_bl = project.baseline_ids.filtered(lambda b: b.state == 'approved')[:1]
            if approved_bl and approved_bl.baseline_finish_date:
                current_finish = max([t.end_date for t in tasks if t.end_date] or [today])
                variance_days = (current_finish - approved_bl.baseline_finish_date).days

            # Upsert snapshot
            existing = self.search([
                ('project_id', '=', project.id),
                ('snapshot_date', '=', today),
            ], limit=1)

            vals = {
                'project_id': project.id,
                'snapshot_date': today,
                'health_score': health.get('score'),
                'health_status': health.get('status', 'not_rated'),
                'total_tasks': len(tasks),
                'completed_tasks': len(completed),
                'overdue_tasks': len(overdue),
                'active_tasks': len(active),
                'open_risks': len(risks),
                'high_risks': len(high_risks),
                'risk_exposure_score': risk_exposure,
                'pending_client_actions': len(client_actions),
                'schedule_variance_days': variance_days,
            }

            if existing:
                existing.write(vals)
            else:
                self.create(vals)

        return True
