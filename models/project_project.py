from odoo import models, fields, api

INTERNAL_SDLC_STAGES = (
    ('Planning', 1, False),
    ('Requirement Analysis', 2, False),
    ('In Development', 3, False),
    ('Testing & Review', 4, False),
    ('Rework', 5, False),
    ('Implemented', 6, True),
    ('On Hold', 7, False),
    ('Cancelled', 8, True),
)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    x_project_status = fields.Selection(
        selection=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('on_hold', 'On Hold'),
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

    x_risk_issue_ids = fields.One2many(
        'project.risk.issue',
        'project_id',
        string='Risks & Issues',
    )

    x_client_action_ids = fields.One2many(
        'project.client.action',
        'project_id',
        string='Client Pending Actions',
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
        # Client projects keep the existing four standard task stages.
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
                project_type = vals.get('x_project_type', self.env.context.get('default_x_project_type', 'client'))
                if project_type == 'client' and not vals.get('type_ids'):
                    vals['type_ids'] = stage_cmd
                if project_type == 'client':
                    vals['allow_milestones'] = True
        
        projects = super().create(vals_list)

        # Give every internal project its own SDLC task stages so its phases
        # are available immediately and remain isolated from client projects.
        projects.filtered(lambda project: project.x_project_type == 'internal')._ensure_internal_sdlc_stages()
        
        milestones_to_create = []
        for project in projects:
            if project.x_project_type == 'client':
                default_milestones = [
                    {'name': 'Preparation', 'sequence': 10},
                    {'name': 'Blueprint', 'sequence': 20},
                    {'name': 'Realization', 'sequence': 30},
                    {'name': 'Testing', 'sequence': 40},
                    {'name': 'Go-Live', 'sequence': 50},
                ]
                for ms in default_milestones:
                    ms['project_id'] = project.id
                    milestones_to_create.append(ms)
        
        if milestones_to_create:
            self.env['project.milestone'].create(milestones_to_create)
            
        return projects

    def write(self, vals):
        res = super().write(vals)
        if vals.get('x_project_type') == 'internal':
            self._ensure_internal_sdlc_stages()
        if vals.get('x_project_type') == 'client':
            # Create milestones if not already present
            milestones_to_create = []
            for project in self:
                if not self.env['project.milestone'].search_count([('project_id', '=', project.id)]):
                    default_milestones = [
                        {'name': 'Preparation', 'sequence': 10},
                        {'name': 'Blueprint', 'sequence': 20},
                        {'name': 'Realization', 'sequence': 30},
                        {'name': 'Testing', 'sequence': 40},
                        {'name': 'Go-Live', 'sequence': 50},
                    ]
                    for ms in default_milestones:
                        ms['project_id'] = project.id
                        milestones_to_create.append(ms)
            if milestones_to_create:
                self.env['project.milestone'].create(milestones_to_create)
        return res

    def _ensure_internal_sdlc_stages(self):
        Stage = self.env['project.task.type'].sudo()
        stage_names = [name for name, _sequence, _fold in INTERNAL_SDLC_STAGES]
        for project in self.filtered(lambda record: record.x_project_type == 'internal'):
            linked_stages = Stage.search([
                ('project_ids', '=', project.id),
                ('name', 'in', stage_names),
            ])
            # Reuse only stages dedicated to this project. Shared standard
            # stages such as New/Done must not leak between client projects.
            linked_stages = linked_stages.filtered(lambda stage: stage.project_ids.ids == [project.id])
            stages_by_name = {stage.name: stage for stage in linked_stages}
            stages = Stage.browse()
            for name, sequence, fold in INTERNAL_SDLC_STAGES:
                stage = stages_by_name.get(name)
                if not stage:
                    stage = Stage.create({
                        'name': name,
                        'sequence': sequence,
                        'fold': fold,
                        'user_id': False,
                        'project_ids': [(6, 0, [project.id])],
                    })
                stages |= stage

            # Earlier versions exposed generic New and Done phases. Move
            # those tasks to their SDLC equivalents before hiding the old
            # stages from this project's status bar.
            legacy_stages = Stage.search([
                ('user_id', '=', False),
                ('name', 'in', ['New', 'Done']),
            ])
            if legacy_stages:
                Task = self.env['project.task'].sudo().with_context(active_test=False)
                project_tasks = Task.search([
                    '&', '|',
                    ('project_id', '=', project.id),
                    ('parent_id.project_id', '=', project.id),
                    ('stage_id', 'in', legacy_stages.ids),
                ])
                stage_by_name = {stage.name.strip().lower(): stage for stage in stages}
                for legacy in legacy_stages:
                    target_name = 'Planning' if legacy.name.strip().lower() == 'new' else 'Implemented'
                    target = stage_by_name.get(target_name.lower())
                    if target:
                        project_tasks.filtered(lambda task: task.stage_id == legacy).write({'stage_id': target.id})

            project.sudo().write({'type_ids': [(6, 0, stages.ids)]})


    def _sync_project_status(self):
        """Auto-update x_project_status based on task completion.

        Rules (never touches Cancelled):
        - No tasks at all          → 'new'
        - Some tasks, none Done    → 'in_progress'
        - Some tasks, some Done    → 'in_progress'
        - All tasks Done/Cancelled → 'done'
        """
        for project in self:
            # Never auto-change a Cancelled project
            if project.x_project_status == 'cancelled':
                continue

            Task = self.env['project.task'].sudo()
            # Only count parent tasks (not subtasks) to avoid double-counting
            tasks = Task.search([
                ('project_id', '=', project.id),
                ('parent_id', '=', False),
            ])

            if not tasks:
                # No tasks yet — keep/set to New
                if project.x_project_status != 'new':
                    project.write({'x_project_status': 'new'})
                continue

            if project.x_project_type == 'internal':
                stage_names = [(task.stage_id.name or 'New').strip().lower() for task in tasks]
                all_cancelled = all(name in ('cancelled', 'canceled') for name in stage_names)
                all_on_hold = all(name in ('on hold', 'on-hold') for name in stage_names)
                all_new = all(name in ('new', 'planning') for name in stage_names)
                terminal = [
                    name in ('done', 'implemented', 'cancelled', 'canceled') or task.is_closed
                    for task, name in zip(tasks, stage_names)
                ]
                if all_cancelled:
                    new_status = 'cancelled'
                elif all(terminal):
                    new_status = 'done'
                elif all_on_hold:
                    new_status = 'on_hold'
                elif all_new:
                    new_status = 'new'
                else:
                    new_status = 'in_progress'
                if project.x_project_status != new_status:
                    project.write({'x_project_status': new_status})
                continue

            terminal_stages = {'Done', 'Cancelled'}
            active_tasks = tasks.filtered(
                lambda t: t.stage_id.name not in terminal_stages
            )
            done_tasks = tasks.filtered(
                lambda t: t.stage_id.name == 'Done'
            )

            if len(done_tasks) == len(tasks):
                # All tasks are Done
                new_status = 'done'
            else:
                # At least one task is still active
                new_status = 'in_progress'

            if project.x_project_status != new_status:
                project.write({'x_project_status': new_status})

    def action_set_status_new(self):
        self.write({'x_project_status': 'new'})

    def action_set_status_in_progress(self):
        self.write({'x_project_status': 'in_progress'})

    def action_set_status_done(self):
        self.write({'x_project_status': 'done'})

    def action_set_status_cancelled(self):
        self.write({'x_project_status': 'cancelled'})

    def action_set_status_on_hold(self):
        self.write({'x_project_status': 'on_hold'})
