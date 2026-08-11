from datetime import datetime, timedelta
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

def is_task_done(t):
    if t.stage_id and t.stage_id.name == 'Done':
        return True
    if hasattr(t, 'state') and t.state == '1_done':
        return True
    return False

class ProjectDashboardController(http.Controller):

    @http.route('/project_dashboard_v19c/data', type='jsonrpc', auth='user')
    def get_dashboard_data(self):
        """Return all data needed for the project dashboard."""
        if not request.env.user.has_group('base.group_system'):
            raise AccessError("Only System Administrators can access the project dashboard.")

        Project = request.env["project.project"].sudo()
        Task = request.env["project.task"].sudo()
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── KPI: Project counts ──────────────────────────────────────────────
        all_projects = Project.search([('x_project_type', '=', 'client')])
        total_projects = len(all_projects)
        active_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'in_progress'))
        completed_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'done'))
        cancelled_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'cancelled'))

        # ── KPI: Task counts ─────────────────────────────────────────────────
        parent_tasks = Task.search([('project_id.x_project_type', '=', 'client'), ('project_id', '!=', False)])
        subtasks = Task.search([('parent_id', 'in', parent_tasks.ids)]) if parent_tasks else Task.browse()
        all_tasks = parent_tasks | subtasks
        
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
            if is_task_done(task):
                stage_name = 'Done'
            else:
                stage_name = task.stage_id.name if task.stage_id else 'Unknown'
            stage_data[stage_name] = stage_data.get(stage_name, 0) + 1

        # We will dynamically add other stages if subtasks have different stages
        stage_order = ['New', 'In Progress', 'Done', 'Cancelled']
        for s in stage_data:
            if s not in stage_order:
                stage_order.append(s)
        tasks_by_stage = [{'label': s, 'count': stage_data.get(s, 0)} for s in stage_order if stage_data.get(s, 0) > 0]

        # ── Project Progress (bar chart — % of Done tasks) ───────────────────
        progress_buckets = {'0-25': 0, '26-50': 0, '51-75': 0, '76-99': 0, '100': 0}
        progress_bucket_ids = {'0-25': [], '26-50': [], '51-75': [], '76-99': [], '100': []}
        for project in all_projects:
            p_tasks = parent_tasks.filtered(lambda t: t.project_id.id == project.id)
            p_subtasks = subtasks.filtered(lambda t: t.parent_id.id in p_tasks.ids)
            project_tasks = p_tasks | p_subtasks
            if not project_tasks:
                progress_buckets['0-25'] += 1
                progress_bucket_ids['0-25'].append(project.id)
                continue
            done_count = len(project_tasks.filtered(is_task_done))
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
        for project in all_projects.filtered(lambda p: p.x_project_status == 'in_progress')[:10]:
            p_tasks = parent_tasks.filtered(lambda t: t.project_id.id == project.id)
            p_subtasks = subtasks.filtered(lambda t: t.parent_id.id in p_tasks.ids)
            project_tasks = p_tasks | p_subtasks
            if not project_tasks:
                pct = 0
            else:
                done_count = len(project_tasks.filtered(is_task_done))
                pct = round((done_count / len(project_tasks)) * 100)
            top_projects.append({
                'id': project.id,
                'name': project.name,
                'progress': pct,
                'total_tasks': len(project_tasks),
                'done_tasks': len(project_tasks.filtered(is_task_done)),
            })

        top_projects = sorted(top_projects, key=lambda x: x['progress'], reverse=True)[:5]

        # ── Resource Utilization ──────────────────────────────────────────────
        user_tasks = {}
        for task in all_tasks:
            for user in task.user_ids:
                if user.id not in user_tasks:
                    user_tasks[user.id] = {'name': user.name, 'total': 0, 'done': 0}
                user_tasks[user.id]['total'] += 1
                if is_task_done(task):
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
        resource_utilization = sorted(resource_utilization, key=lambda x: x['utilization'], reverse=True)[:6]

        # ── Overdue Tasks ─────────────────────────────────────────────────────
        overdue_task_data = []
        for task in overdue_tasks_list[:10]:
            days_overdue = (today - task.date_deadline).days if task.date_deadline else 0
            overdue_task_data.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),
                'days_overdue': days_overdue,
                'stage': task.stage_id.name if task.stage_id else '',
            })
        overdue_task_data = sorted(overdue_task_data, key=lambda x: x['days_overdue'], reverse=True)

        # ── Upcoming Deadlines ────────────────────────────────────────────────
        next_30_days = today + timedelta(days=30)
        upcoming = parent_tasks.filtered(
            lambda t: t.date_deadline and today.strftime('%Y-%m-%d') <= t.date_deadline.strftime('%Y-%m-%d') <= next_30_days.strftime('%Y-%m-%d') and not is_task_done(t)
        )
        upcoming_subtasks = subtasks.filtered(
            lambda t: t.date_deadline and today.strftime('%Y-%m-%d') <= t.date_deadline.strftime('%Y-%m-%d') <= next_30_days.strftime('%Y-%m-%d') and not is_task_done(t)
        )
        upcoming = (upcoming | upcoming_subtasks).sorted('date_deadline')[:5]

        upcoming_deadlines = []
        for task in upcoming:
            days_left = (task.date_deadline - today).days
            upcoming_deadlines.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),
                'deadline': task.date_deadline.strftime('%m/%d/%Y'),
                'days_left': days_left,
            })

        # ── Recently Created Tasks (last 3 days) ─────────────────────────────
        three_days_ago = now - timedelta(days=3)
        recent_tasks = (parent_tasks | subtasks).filtered(
            lambda t: t.create_date and t.create_date.strftime('%Y-%m-%d %H:%M:%S') >= three_days_ago.strftime('%Y-%m-%d %H:%M:%S')
        ).sorted('create_date', reverse=True)[:10]

        recent_activities = []
        for task in recent_tasks:
            assignees = ', '.join(task.user_ids.mapped('name')) if task.user_ids else 'Unassigned'
            recent_activities.append({
                'id': task.id,
                'name': task.name,
                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),
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
        stale_date = today - timedelta(days=14)
        stale_projects = Project.search([
            ('x_project_type', '=', 'client'),
            ('x_project_status', '=', 'in_progress'),
            ('write_date', '<', stale_date.strftime('%Y-%m-%d %H:%M:%S')),
        ])
        if stale_projects:
            alerts.append({
                'level': 'warning',
                'message': f'{len(stale_projects)} project(s) have had no updates in 14 days',
            })
        due_in_7 = (parent_tasks | subtasks).filtered(
            lambda t: t.date_deadline and today.strftime('%Y-%m-%d') <= t.date_deadline.strftime('%Y-%m-%d') <= (today + timedelta(days=7)).strftime('%Y-%m-%d') and not is_task_done(t)
        )
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

    @http.route('/project_dashboard_v19c/client_projects_list', type='jsonrpc', auth='user')
    def get_client_projects_list(self):
        """Return list of client projects for the project selector."""
        if not request.env.user.has_group('base.group_system'):
            raise AccessError("Only System Administrators can access the project dashboard.")
        
        Project = request.env['project.project'].sudo()
        projects = Project.search([('x_project_type', '=', 'client')], order='name asc')
        result = []
        for p in projects:
            result.append({
                'id': p.id,
                'name': p.name,
                'status': p.x_project_status,
            })
        return result

    @http.route('/project_dashboard_v19c/project_detail', type='jsonrpc', auth='user')
    def get_project_detail(self, project_id):
        """Return detailed dashboard data for a single project."""
        if not request.env.user.has_group('base.group_system'):
            raise AccessError("Only System Administrators can access the project dashboard.")
        
        Project = request.env['project.project'].sudo()
        Task = request.env['project.task'].sudo()
        Milestone = request.env['project.milestone'].sudo()
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        project = Project.browse(project_id)
        if not project.exists():
            return {'error': 'Project not found'}
        
        # Get all tasks for this project, including subtasks
        parent_tasks = Task.search([('project_id', '=', project_id)])
        subtasks = Task.search([('parent_id', 'in', parent_tasks.ids)]) if parent_tasks else Task.browse()
        all_tasks = parent_tasks | subtasks
        
        total_tasks = len(all_tasks)
        done_tasks = len(all_tasks.filtered(is_task_done))
        
        # Milestones data
        milestones = Milestone.search(
            [('project_id', '=', project_id)],
            order='x_phase_sequence asc, deadline asc, name asc'
        )
        milestones_data = []
        overall_progress_sum = 0
        milestone_weight = 100 / len(milestones) if len(milestones) > 0 else 0
        
        for ms in milestones:
            ms_direct_tasks = all_tasks.filtered(lambda t: t.milestone_id.id == ms.id)
            ms_subtasks = subtasks.filtered(lambda t: t.parent_id.id in ms_direct_tasks.ids)
            ms_tasks = ms_direct_tasks | ms_subtasks
            
            ms_total = len(ms_tasks)
            ms_done = len(ms_tasks.filtered(is_task_done))
            ms_progress = round((ms_done / ms_total) * 100) if ms_total else 0
            
            is_reached = (ms_progress == 100) if ms_total > 0 else False
            
            overall_progress_sum += milestone_weight * (ms_progress / 100.0)
            
            milestones_data.append({
                'id': ms.id,
                'name': ms.name,
                'sequence': ms.x_phase_sequence,
                'deadline': ms.deadline.strftime('%b %d, %Y') if ms.deadline else '',
                'is_reached': is_reached,
                'total_tasks': ms_total,
                'done_tasks': ms_done,
                'progress': ms_progress,
            })
            
        if len(milestones) > 0:
            overall_progress = round(overall_progress_sum)
        else:
            overall_progress = round((done_tasks / total_tasks) * 100) if total_tasks else 0
        
        # Timeline data (milestones with date ranges)
        timeline = []
        for i, ms_data in enumerate(milestones_data):
            # Start date: previous milestone deadline or project create date
            if i > 0 and milestones[i-1].deadline:
                start = milestones[i-1].deadline.strftime('%b %d')
            elif project.create_date:
                start = project.create_date.strftime('%b %d')
            else:
                start = ''
            end = ms_data['deadline'] if ms_data['deadline'] else ''
            
            timeline.append({
                'name': ms_data['name'],
                'start': start,
                'end': end,
                'progress': ms_data['progress'],
                'is_reached': ms_data['is_reached'],
            })

        # Project info
        project_info = {
            'id': project.id,
            'name': project.name,
            'status': project.x_project_status,
            'start_date': project.create_date.strftime('%b %d, %Y') if project.create_date else '',
            'overall_progress': overall_progress,
            'total_tasks': total_tasks,
            'done_tasks': done_tasks,
        }
        
        # Tasks by status (bar chart)
        stage_data = {}
        for task in all_tasks:
            if is_task_done(task):
                stage_name = 'Done'
            else:
                stage_name = task.stage_id.name if task.stage_id else 'Unknown'
            stage_data[stage_name] = stage_data.get(stage_name, 0) + 1
        
        stage_order = ['New', 'In Progress', 'Done', 'Cancelled']
        for s in stage_data:
            if s not in stage_order:
                stage_order.append(s)
        tasks_by_status = [{'label': s, 'count': stage_data.get(s, 0)} for s in stage_order if stage_data.get(s, 0) > 0]
        
        # Tasks by consultant (bar chart)
        user_task_counts = {}
        for task in all_tasks:
            for user in task.user_ids:
                if user.name not in user_task_counts:
                    user_task_counts[user.name] = 0
                user_task_counts[user.name] += 1
        tasks_by_consultant = [
            {'name': name, 'count': count}
            for name, count in sorted(user_task_counts.items(), key=lambda x: x[1], reverse=True)
        ][:8]  # top 8 consultants
        
        # Project workload (tasks per milestone for donut)
        workload = []
        for ms in milestones:
            ms_direct_tasks = all_tasks.filtered(lambda t: t.milestone_id.id == ms.id)
            ms_subtasks = subtasks.filtered(lambda t: t.parent_id.id in ms_direct_tasks.ids)
            ms_tasks = ms_direct_tasks | ms_subtasks
            if len(ms_tasks) > 0:
                workload.append({
                    'label': ms.name,
                    'count': len(ms_tasks),
                })
        
        # Add unassigned tasks (no milestone)
        unassigned_parents = parent_tasks.filtered(lambda t: not t.milestone_id)
        unassigned_subtasks = subtasks.filtered(lambda t: t.parent_id.id in unassigned_parents.ids)
        unassigned_tasks = unassigned_parents | unassigned_subtasks
        if len(unassigned_tasks) > 0:
            workload.append({
                'label': 'Unassigned',
                'count': len(unassigned_tasks),
            })
        
        # Go-Live readiness (same as overall progress)
        go_live_readiness = overall_progress
        
        # Upcoming deadlines for this project
        next_30_days = today + timedelta(days=30)
        upcoming = parent_tasks.filtered(
            lambda t: t.date_deadline and today.strftime('%Y-%m-%d') <= t.date_deadline.strftime('%Y-%m-%d') <= next_30_days.strftime('%Y-%m-%d') and not is_task_done(t)
        )
        upcoming_subtasks = subtasks.filtered(
            lambda t: t.date_deadline and today.strftime('%Y-%m-%d') <= t.date_deadline.strftime('%Y-%m-%d') <= next_30_days.strftime('%Y-%m-%d') and not is_task_done(t)
        )
        upcoming = (upcoming | upcoming_subtasks).sorted('date_deadline')[:8]
        
        upcoming_deadlines = []
        for task in upcoming:
            days_left = (task.date_deadline - today).days
            upcoming_deadlines.append({
                'id': task.id,
                'name': task.name,
                'deadline': task.date_deadline.strftime('%b %d'),
                'days_left': days_left,
                'critical': days_left <= 3,
            })
        
        return {
            'project': project_info,
            'milestones': milestones_data,
            'tasks_by_status': tasks_by_status,
            'tasks_by_consultant': tasks_by_consultant,
            'workload': workload,
            'go_live_readiness': go_live_readiness,
            'upcoming_deadlines': upcoming_deadlines,
            'timeline': timeline,
        }