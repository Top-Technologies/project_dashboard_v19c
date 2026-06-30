from datetime import datetime, timedelta
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError


class ProjectDashboardController(http.Controller):

    @http.route('/project_dashboard_v19c/data', type='json', auth='user')
    def get_dashboard_data(self):
        """Return all data needed for the project dashboard.
        """
        if not request.env.user.has_group('base.group_system'):
            raise AccessError("Only System Administrators can access the project dashboard.")

        Project = request.env["project.project"].sudo()
        Task = request.env["project.task"].sudo()
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── KPI: Project counts ──────────────────────────────────────────────
        all_projects = Project.search([])
        total_projects = len(all_projects)
        active_projects = len(all_projects.filtered(
            lambda p: p.x_project_status == 'in_progress'
        ))
        completed_projects = len(all_projects.filtered(
            lambda p: p.x_project_status == 'done'
        ))
        cancelled_projects = len(all_projects.filtered(
            lambda p: p.x_project_status == 'cancelled'
        ))

        # ── KPI: Task counts ─────────────────────────────────────────────────
        all_tasks = Task.search([('project_id', '!=', False)])
        total_tasks = len(all_tasks)
        overdue_tasks_list = all_tasks.filtered(lambda t: t.x_is_overdue)
        overdue_tasks = len(overdue_tasks_list)

        # ── Projects by Status (donut) ────────────────────────────────────────
        status_counts = {'new': 0, 'in_progress': 0, 'done': 0, 'cancelled': 0}
        for p in all_projects:
            status_counts[p.x_project_status] = status_counts.get(p.x_project_status, 0) + 1

        projects_by_status = [
            {'label': 'New',         'count': status_counts['new'],         'key': 'new'},
            {'label': 'In Progress', 'count': status_counts['in_progress'], 'key': 'in_progress'},
            {'label': 'Done',        'count': status_counts['done'],         'key': 'done'},
            {'label': 'Cancelled',   'count': status_counts['cancelled'],   'key': 'cancelled'},
        ]

        # ── Tasks by Stage (donut) ────────────────────────────────────────────
        stage_data = {}
        for task in all_tasks:
            stage_name = task.stage_id.name if task.stage_id else 'Unknown'
            stage_data[stage_name] = stage_data.get(stage_name, 0) + 1

        stage_order = ['New', 'In Progress', 'Done', 'Cancelled']
        tasks_by_stage = [
            {'label': s, 'count': stage_data.get(s, 0)}
            for s in stage_order
        ]

        # ── Project Progress (bar chart — % of Done tasks) ───────────────────
        progress_buckets = {'0-25': 0, '26-50': 0, '51-75': 0, '76-99': 0, '100': 0}
        progress_bucket_ids = {'0-25': [], '26-50': [], '51-75': [], '76-99': [], '100': []}
        for project in all_projects:
            project_tasks = all_tasks.filtered(lambda t: t.project_id.id == project.id)
            if not project_tasks:
                progress_buckets['0-25'] += 1
                progress_bucket_ids['0-25'].append(project.id)
                continue
            done_count = len(project_tasks.filtered(
                lambda t: t.stage_id.name == 'Done'
            ))
            pct = (done_count / len(project_tasks)) * 100
            if pct <= 25:
                bucket = '0-25'
            elif pct <= 50:
                bucket = '26-50'
            elif pct <= 75:
                bucket = '51-75'
            elif pct < 100:
                bucket = '76-99'
            else:
                bucket = '100'
            progress_buckets[bucket] += 1
            progress_bucket_ids[bucket].append(project.id)

        project_progress = [
            {'label': '0-25%',  'count': progress_buckets['0-25'],  'project_ids': progress_bucket_ids['0-25']},
            {'label': '26-50%', 'count': progress_buckets['26-50'], 'project_ids': progress_bucket_ids['26-50']},
            {'label': '51-75%', 'count': progress_buckets['51-75'], 'project_ids': progress_bucket_ids['51-75']},
            {'label': '76-99%', 'count': progress_buckets['76-99'], 'project_ids': progress_bucket_ids['76-99']},
            {'label': '100%',   'count': progress_buckets['100'],   'project_ids': progress_bucket_ids['100']},
        ]

        # ── Top 5 Projects ────────────────────────────────────────────────────
        top_projects = []
        for project in all_projects.filtered(
            lambda p: p.x_project_status == 'in_progress'
        )[:10]:
            project_tasks = all_tasks.filtered(lambda t: t.project_id.id == project.id)
            if not project_tasks:
                pct = 0
            else:
                done_count = len(project_tasks.filtered(
                    lambda t: t.stage_id.name == 'Done'
                ))
                pct = round((done_count / len(project_tasks)) * 100)
            top_projects.append({
                'id': project.id,
                'name': project.name,
                'progress': pct,
                'total_tasks': len(project_tasks),
                'done_tasks': len(project_tasks.filtered(
                    lambda t: t.stage_id.name == 'Done'
                )),
            })

        top_projects = sorted(top_projects, key=lambda x: x['progress'], reverse=True)[:5]

        # ── Resource Utilization ──────────────────────────────────────────────
        # Utilization = % of a person's assigned tasks that they have completed.
        # e.g. assigned 5 tasks, completed 2 -> utilization = 40%.
        user_tasks = {}
        for task in all_tasks:
            for user in task.user_ids:
                if user.id not in user_tasks:
                    user_tasks[user.id] = {'name': user.name, 'total': 0, 'done': 0}
                user_tasks[user.id]['total'] += 1
                if task.stage_id.name == 'Done':
                    user_tasks[user.id]['done'] += 1

        resource_utilization = []
        for uid, data in user_tasks.items():
            if data['total'] > 0:
                util_pct = round((data['done'] / data['total']) * 100)
                resource_utilization.append({
                    'user_id': uid,
                    'name': data['name'],
                    'utilization': util_pct,
                    'done_tasks': data['done'],
                    'total_tasks': data['total'],
                })
        resource_utilization = sorted(
            resource_utilization, key=lambda x: x['utilization'], reverse=True
        )[:6]

        # ── Overdue Tasks ─────────────────────────────────────────────────────
        overdue_task_data = []
        for task in overdue_tasks_list[:10]:
            days_overdue = (today - task.date_deadline).days if task.date_deadline else 0
            overdue_task_data.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else '',
                'days_overdue': days_overdue,
                'stage': task.stage_id.name if task.stage_id else '',
            })
        overdue_task_data = sorted(overdue_task_data, key=lambda x: x['days_overdue'], reverse=True)

        # ── Upcoming Deadlines ────────────────────────────────────────────────
        next_30_days = today + timedelta(days=30)
        upcoming = Task.search([
            ('date_deadline', '>=', today.strftime('%Y-%m-%d')),
            ('date_deadline', '<=', next_30_days.strftime('%Y-%m-%d')),
            ('project_id', '!=', False),
            ('stage_id.name', 'not in', ['Done', 'Cancelled']),
        ], order='date_deadline asc', limit=5)

        upcoming_deadlines = []
        for task in upcoming:
            days_left = (task.date_deadline - today).days
            upcoming_deadlines.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else '',
                'deadline': task.date_deadline.strftime('%m/%d/%Y'),
                'days_left': days_left,
            })

        # ── Recently Created Tasks (last 3 days) ─────────────────────────────
        three_days_ago = now - timedelta(days=3)
        recent_tasks = Task.search([
            ('project_id', '!=', False),
            ('create_date', '>=', three_days_ago.strftime('%Y-%m-%d %H:%M:%S')),
        ], order='create_date desc', limit=10)

        recent_activities = []
        for task in recent_tasks:
            assignees = ', '.join(task.user_ids.mapped('name')) if task.user_ids else 'Unassigned'
            recent_activities.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else '',
                'assignees': assignees,
                'stage': task.stage_id.name if task.stage_id else '',
                'created': task.create_date.strftime('%b %d, %H:%M') if task.create_date else '',
            })

        # ── Alerts ────────────────────────────────────────────────────────────
        alerts = []
        if overdue_tasks > 0:
            alerts.append({
                'level': 'danger',
                'message': f'{overdue_tasks} task(s) are overdue',
            })
        # Projects with no activity for 14 days
        stale_date = today - timedelta(days=14)
        stale_projects = Project.search([
            ('x_project_status', '=', 'in_progress'),
            ('write_date', '<', stale_date.strftime('%Y-%m-%d %H:%M:%S')),
        ])
        if stale_projects:
            alerts.append({
                'level': 'warning',
                'message': f'{len(stale_projects)} project(s) have had no updates in 14 days',
            })
        due_in_7 = Task.search([
            ('date_deadline', '>=', today.strftime('%Y-%m-%d')),
            ('date_deadline', '<=', (today + timedelta(days=7)).strftime('%Y-%m-%d')),
            ('project_id', '!=', False),
            ('stage_id.name', 'not in', ['Done', 'Cancelled']),
        ])
        if due_in_7:
            alerts.append({
                'level': 'info',
                'message': f'{len(due_in_7)} task(s) due in the next 7 days',
            })

        return {
            'kpis': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'completed_projects': completed_projects,
                'cancelled_projects': cancelled_projects,
                'total_tasks': total_tasks,
                'overdue_tasks': overdue_tasks,
            },
            'projects_by_status': projects_by_status,
            'tasks_by_stage': tasks_by_stage,
            'project_progress': project_progress,
            'top_projects': top_projects,
            'resource_utilization': resource_utilization,
            'overdue_task_data': overdue_task_data,
            'upcoming_deadlines': upcoming_deadlines,
            'recent_activities': recent_activities,
            'alerts': alerts,
        }