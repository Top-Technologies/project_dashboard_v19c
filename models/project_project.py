from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    x_project_status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Project Status',
        default='new',
        required=True,
        tracking=True,
    )

    x_project_type = fields.Selection(
        selection=[
            ('client', 'Client Project'),
            ('internal', 'Internal Project'),
        ],
        string='Project Type',
        default='client',
        required=True,
        tracking=True,
    )

    x_assigned_user_ids = fields.Many2many(
        'res.users',
        string='Users Assigned to Any Task',
        compute='_compute_x_assigned_user_ids',
        search='_search_x_assigned_user_ids',
        compute_sudo=True,
        help=(
            "Technical field used for visibility/access rules only. "
            "Holds every user assigned to at least one task in this "
            "project, regardless of the task's current stage."
        ),
    )

    def _compute_x_assigned_user_ids(self):
        # Computed via project.task.project_id rather than a one2many on
        # this model, so this does not depend on guessing the exact name
        # of project.project's inverse task relation field.
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        for project in self:
            tasks = Task.search([('project_id', '=', project.id)])
            project.x_assigned_user_ids = tasks.user_ids

    def _search_x_assigned_user_ids(self, operator, value):
        # Allows this field to be used inside an ir.rule domain (rules
        # need a searchable field, not just a computed one).
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        matching_tasks = Task.search([('user_ids', operator, value)])
        return [('id', 'in', matching_tasks.project_id.ids)]

    @api.model_create_multi
    def create(self, vals_list):
        # Inject the 4 fixed task stages into each vals dict BEFORE super().create()
        # so the new project already has type_ids set when the form first renders —
        # this prevents Odoo's "please add stages" prompt on the tasks kanban.
        fixed_stage_xmlids = [
            'project_dashboard_v19c.project_stage_new',
            'project_dashboard_v19c.project_stage_in_progress',
            'project_dashboard_v19c.project_stage_done',
            'project_dashboard_v19c.project_stage_cancelled',
        ]
        fixed_stage_ids = []
        for xmlid in fixed_stage_xmlids:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                fixed_stage_ids.append(stage.id)
        if fixed_stage_ids:
            stage_cmd = [(6, 0, fixed_stage_ids)]
            for vals in vals_list:
                if not vals.get('type_ids'):
                    vals['type_ids'] = stage_cmd
                if vals.get('x_project_type', 'client') == 'client':
                    vals['allow_milestones'] = True
        
        projects = super().create(vals_list)
        
        milestones_to_create = []
        for project in projects:
            if project.x_project_type == 'client':
                default_milestones = [
                    {'name': 'Preparation', 'x_phase_sequence': 10},
                    {'name': 'Blueprint', 'x_phase_sequence': 20},
                    {'name': 'Realization', 'x_phase_sequence': 30},
                    {'name': 'Testing', 'x_phase_sequence': 40},
                    {'name': 'Go-Live', 'x_phase_sequence': 50},
                ]
                for ms in default_milestones:
                    ms['project_id'] = project.id
                    milestones_to_create.append(ms)
        
        if milestones_to_create:
            self.env['project.milestone'].create(milestones_to_create)
            
        return projects

    def write(self, vals):
        res = super().write(vals)
        if vals.get('x_project_type') == 'client':
            # Create milestones if not already present
            milestones_to_create = []
            for project in self:
                if not self.env['project.milestone'].search_count([('project_id', '=', project.id)]):
                    default_milestones = [
                        {'name': 'Preparation', 'x_phase_sequence': 10},
                        {'name': 'Blueprint', 'x_phase_sequence': 20},
                        {'name': 'Realization', 'x_phase_sequence': 30},
                        {'name': 'Testing', 'x_phase_sequence': 40},
                        {'name': 'Go-Live', 'x_phase_sequence': 50},
                    ]
                    for ms in default_milestones:
                        ms['project_id'] = project.id
                        milestones_to_create.append(ms)
            if milestones_to_create:
                self.env['project.milestone'].create(milestones_to_create)
        return res


    def action_set_status_new(self):
        self.write({'x_project_status': 'new'})

    def action_set_status_in_progress(self):
        self.write({'x_project_status': 'in_progress'})

    def action_set_status_done(self):
        self.write({'x_project_status': 'done'})

    def action_set_status_cancelled(self):
        self.write({'x_project_status': 'cancelled'})