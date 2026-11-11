from datetime import datetime, timedelta, date

from odoo import http

from odoo.http import request

from odoo.exceptions import AccessError

SDLC_PHASE_LABELS = (
    'Planning',
    'Requirement Analysis',
    'In Development',
    'Testing & Review',
    'Implemented',
    'Rework',
    'On Hold',
    'Cancelled',
)
INTERNAL_PHASE_LABELS = ('New', 'In Progress', 'Done', 'Cancelled')

def is_task_done(t):

    if t.stage_id and t.stage_id.name == 'Done':

        return True

    if t.stage_id:
        project = t.project_id or (t.parent_id.project_id if t.parent_id else False)
        if project and project.x_project_type in ('internal', 'technical') and canonical_internal_stage_label(t.stage_id.name) == 'Implemented':
            return True

    if hasattr(t, 'state') and t.state == '1_done':

        return True

    return False

def canonical_internal_stage_label(name):
    """Map legacy task stages to one of the dashboard's SDLC buckets."""
    label = ' '.join((name or '').strip().replace('&', 'and').replace('-', ' ').lower().split())
    aliases = {
        'new': 'Planning',
        'planning': 'Planning',
        'requirement analysis': 'Requirement Analysis',
        'requirements analysis': 'Requirement Analysis',
        'in development': 'In Development',
        'development': 'In Development',
        'in progress': 'In Development',
        'in process': 'In Development',
        'inprocess': 'In Development',
        'running': 'In Development',
        'testing and review': 'Testing & Review',
        'testing review': 'Testing & Review',
        'testing': 'Testing & Review',
        'test and review': 'Testing & Review',
        'rework': 'Rework',
        're work': 'Rework',
        'on hold': 'On Hold',
        'implemented': 'Implemented',
        'done': 'Implemented',
        'complete': 'Implemented',
        'completed': 'Implemented',
        'cancelled': 'Cancelled',
        'canceled': 'Cancelled',
    }
    return aliases.get(label, 'Other')

def canonical_dashboard_stage_label(name, project_type):
    """Return the stage bucket used by the selected project dashboard."""
    if project_type != 'internal':
        return canonical_internal_stage_label(name)
    label = ' '.join((name or '').strip().lower().split())
    aliases = {
        'new': 'New', 'planning': 'New',
        'in progress': 'In Progress', 'inprocess': 'In Progress',
        'in process': 'In Progress', 'in development': 'In Progress',
        'requirement analysis': 'In Progress', 'testing & review': 'In Progress',
        'rework': 'In Progress', 'on hold': 'In Progress',
        'done': 'Done', 'implemented': 'Done', 'completed': 'Done',
        'cancelled': 'Cancelled', 'canceled': 'Cancelled',
    }
    return aliases.get(label, 'Other')

def to_date(val):

    if not val:

        return None

    if isinstance(val, datetime):

        return val.date()

    return val

def comparison_windows(date_filter, today_date):
    """Return current and previous equal-length windows for KPI comparisons."""
    if date_filter == 'day':
        current_start = today_date
        current_end = today_date + timedelta(days=1)
        previous_start = today_date - timedelta(days=1)
        return current_start, current_end, previous_start, current_start
    if date_filter == 'month':
        current_start = today_date.replace(day=1)
        previous_start = (current_start - timedelta(days=1)).replace(day=1)
        elapsed = (today_date - current_start).days + 1
        current_end = today_date + timedelta(days=1)
        previous_end = min(previous_start + timedelta(days=elapsed), current_start)
        return current_start, current_end, previous_start, previous_end
    if date_filter == 'year':
        current_start = today_date.replace(month=1, day=1)
        previous_start = current_start.replace(year=current_start.year - 1)
        elapsed = (today_date - current_start).days + 1
        current_end = today_date + timedelta(days=1)
        previous_end = min(previous_start + timedelta(days=elapsed), current_start)
        return current_start, current_end, previous_start, previous_end
    return None

def period_metric_trend(records, predicate, date_getter, windows, *, inverse=False, neutral_tone=False, label='records'):
    """Describe event-count change between selected and preceding periods."""
    if not windows:
        return {
            'value': '—', 'icon': 'fa-arrow-right', 'class': 'pd_trend_neutral',
            'title': 'All Time selected; no previous period comparison applies.',
        }
    current_start, current_end, previous_start, previous_end = windows

    def count_between(start, end):
        count = 0
        for record in records:
            if not predicate(record):
                continue
            event_date = to_date(date_getter(record))
            if event_date and start <= event_date < end:
                count += 1
        return count

    current_count = count_between(current_start, current_end)
    previous_count = count_between(previous_start, previous_end)
    delta = current_count - previous_count
    direction = 'up' if delta > 0 else 'down' if delta < 0 else 'neutral'
    tone_direction = ('down' if direction == 'up' else 'up') if inverse else direction
    tone = 'pd_trend_neutral' if neutral_tone or tone_direction == 'neutral' else ('pd_trend_up' if tone_direction == 'up' else 'pd_trend_down')
    icon = {'up': 'fa-arrow-up', 'down': 'fa-arrow-down', 'neutral': 'fa-arrow-right'}[direction]
    value = f'+{delta}' if delta > 0 else str(delta)
    title = f'{label}: {current_count} in the selected period vs {previous_count} in the previous comparable period.'
    return {'value': value, 'icon': icon, 'class': tone, 'title': title}

def add_metric_trend(kpis, key, records, predicate, date_getter, windows, **kwargs):
    trend = period_metric_trend(records, predicate, date_getter, windows, **kwargs)
    kpis[f'{key}_trend'] = trend['value']
    kpis[f'{key}_trend_icon'] = trend['icon']
    kpis[f'{key}_trend_class'] = trend['class']
    kpis[f'{key}_trend_title'] = trend['title']

def get_task_descendants(Task, roots):

    """Fetch every subtask level below roots so dashboard totals stay complete."""

    descendants = Task.browse()

    frontier = roots

    seen_ids = set(roots.ids)

    while frontier:

        children = Task.search([('parent_id', 'in', frontier.ids)])

        new_children = children.filtered(lambda task: task.id not in seen_ids)

        if not new_children:

            break

        seen_ids.update(new_children.ids)

        descendants |= new_children

        frontier = new_children

    return descendants

def get_daily_log_data(tasks, date_filter, today_date):

    """Return recent daily log entries for the supplied dashboard tasks."""

    if 'project.task.log' not in request.env or not tasks:

        return {

            'enabled': 'project.task.log' in request.env,

            'items': [],

            'total': 0,

            'domain': [('id', '=', 0)],

        }

    domain = [('task_id', 'in', tasks.ids)]

    if date_filter == 'day':

        domain += [('date', '=', today_date)]

    elif date_filter == 'month':

        domain += [('date', '>=', today_date.replace(day=1)), ('date', '<=', today_date)]

    elif date_filter == 'year':

        domain += [('date', '>=', today_date.replace(month=1, day=1)), ('date', '<=', today_date)]

    DailyLog = request.env['project.task.log'].sudo()

    total = DailyLog.search_count(domain)

    logs = DailyLog.search(domain, order='date desc, id desc', limit=5)

    items = []

    for log in logs:

        task = log.task_id

        project = task.project_id or task.parent_id.project_id

        items.append({

            'id': log.id,

            'task_id': task.id,

            'name': log.description or task.name,

            'task_name': task.name,

            'project': project.name if project else '',

            'logged_by': log.user_id.name,

            'date': log.date.strftime('%b %d, %Y') if log.date else '',

            'is_done': is_task_done(task),

        })

    return {

        'enabled': True,

        'items': items,

        'total': total,

        'domain': [

            [field, operator, value.isoformat() if hasattr(value, 'isoformat') else value]

            for field, operator, value in domain

        ],

    }

class ProjectDashboardController(http.Controller):

    @http.route('/project_dashboard_v19c/data', type='jsonrpc', auth='user')

    def get_dashboard_data(self, project_type='client', date_filter='month'):

        """Return all data needed for the project dashboard."""

        if not request.env.user.has_group('project.group_project_manager'):

            raise AccessError("Only Project Administrators can access the project dashboard.")

        if project_type == 'client':

            return self._get_client_dashboard_data()

        elif project_type == 'technical':

            return self._get_internal_dashboard_data(date_filter=date_filter, project_type='technical')

        else:

            return self._get_internal_dashboard_data(date_filter=date_filter, project_type='internal')

    # ══════════════════════════════════════════════════════════════════════

    # CLIENT DASHBOARD (100% UNTOUCHED ORIGINAL LOGIC)

    # ══════════════════════════════════════════════════════════════════════

    def _get_client_dashboard_data(self):

        Project = request.env["project.project"].sudo()

        Task = request.env["project.task"].sudo()

        now = datetime.now()

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── KPI: Project counts ──

        all_projects = Project.search([('x_project_type', '=', 'client')])

        total_projects = len(all_projects)

        active_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'in_progress'))

        on_hold_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'on_hold'))

        completed_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'done'))

        cancelled_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'cancelled'))

        # ── KPI: Task counts ──

        parent_tasks = Task.search([('project_id.x_project_type', '=', 'client'), ('project_id', '!=', False)])

        subtasks = Task.search([('parent_id', 'in', parent_tasks.ids)]) if parent_tasks else Task.browse()

        all_tasks = parent_tasks | subtasks

        total_tasks = len(all_tasks)

        overdue_tasks_list = all_tasks.filtered(lambda t: t.x_is_overdue)

        overdue_tasks = len(overdue_tasks_list)

        total_subtasks = len(subtasks)

        total_timesheet_hours = 0.0

        if 'account.analytic.line' in request.env and all_projects:

            AnalyticLine = request.env['account.analytic.line'].sudo()

            ts_agg = AnalyticLine.read_group(

                [('project_id', 'in', all_projects.ids)],

                ['unit_amount'],

                []

            )

            if ts_agg:

                total_timesheet_hours = round(ts_agg[0].get('unit_amount', 0.0), 1)

        # ── Projects by Status (donut) ──

        status_counts = {'new': 0, 'in_progress': 0, 'on_hold': 0, 'done': 0, 'cancelled': 0}

        for p in all_projects:

            status_counts[p.x_project_status] = status_counts.get(p.x_project_status, 0) + 1

        projects_by_status = [

            {'label': 'Planning',        'count': status_counts['new'],         'key': 'new'},

            {'label': 'In Development',  'count': status_counts['in_progress'], 'key': 'in_progress'},

            {'label': 'On Hold',         'count': status_counts['on_hold'],     'key': 'on_hold'},

            {'label': 'Implemented',     'count': status_counts['done'],         'key': 'done'},

            {'label': 'Cancelled',       'count': status_counts['cancelled'],   'key': 'cancelled'},

        ]

        # ── Tasks by Stage (donut) ──

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

        tasks_by_stage = [{'label': s, 'count': stage_data.get(s, 0)} for s in stage_order if stage_data.get(s, 0) > 0]

        # ── Project Progress (bar chart) ──

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

        # ── Top 5 Projects ──

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

        # ── Resource Utilization ──

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

        # ── Overdue Tasks ──

        overdue_task_data = []

        for task in overdue_tasks_list[:10]:

            task_dl = to_date(task.date_deadline)

            days_overdue = (today.date() - task_dl).days if task_dl else 0

            overdue_task_data.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),

                'days_overdue': days_overdue,

                'stage': task.stage_id.name if task.stage_id else '',

            })

        overdue_task_data = sorted(overdue_task_data, key=lambda x: x['days_overdue'], reverse=True)

        # ── Upcoming Deadlines ──

        next_30_days = today.date() + timedelta(days=30)

        upcoming = parent_tasks.filtered(

            lambda t: to_date(t.date_deadline) and today.date() <= to_date(t.date_deadline) <= next_30_days and not is_task_done(t)

        )

        upcoming_subtasks = subtasks.filtered(

            lambda t: to_date(t.date_deadline) and today.date() <= to_date(t.date_deadline) <= next_30_days and not is_task_done(t)

        )

        upcoming = (upcoming | upcoming_subtasks).sorted('date_deadline')[:5]

        upcoming_deadlines = []

        for task in upcoming:

            task_dl = to_date(task.date_deadline)

            days_left = (task_dl - today.date()).days if task_dl else 0

            upcoming_deadlines.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),

                'deadline': task.date_deadline.strftime('%m/%d/%Y') if task.date_deadline else '',

                'days_left': days_left,

            })

        # ── Recently Created Tasks (last 3 days) ──

        three_days_ago = now - timedelta(days=3)

        recent_tasks = (parent_tasks | subtasks).filtered(

            lambda t: t.create_date and t.create_date.strftime('%Y-%m-%d %H:%M:%S') >= three_days_ago.strftime('%Y-%m-%d %H:%M:%S')

        ).sorted('create_date', reverse=True)[:5]

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

        # ── Alerts ──

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

            lambda t: to_date(t.date_deadline) and today.date() <= to_date(t.date_deadline) <= (today.date() + timedelta(days=7)) and not is_task_done(t)

        )

        if due_in_7:

            alerts.append({

                'level': 'info',

                'message': f'{len(due_in_7)} task(s) due in the next 7 days',

            })

        # ── Timesheet Summary ──

        timesheet_summary = []

        if 'account.analytic.line' in request.env:

            AnalyticLine = request.env['account.analytic.line'].sudo()

            timesheets = AnalyticLine.read_group(

                [('project_id', 'in', all_projects.ids)],

                ['project_id', 'unit_amount'],

                ['project_id']

            )

            for ts in timesheets:

                project_id_val = ts['project_id'][0] if ts['project_id'] else False

                project_name = ts['project_id'][1] if ts['project_id'] else 'Unknown'

                if project_id_val:

                    timesheet_summary.append({

                        'project_id': project_id_val,

                        'project_name': project_name,

                        'total_hours': round(ts['unit_amount'], 2) if ts.get('unit_amount') else 0.0,

                    })

            timesheet_summary = sorted(timesheet_summary, key=lambda x: x['total_hours'], reverse=True)[:10]

        return {
            'kpis': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'on_hold_projects': on_hold_projects,
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
            'timesheet_summary': timesheet_summary,
        }

    # ══════════════════════════════════════════════════════════════════════

    # INTERNAL DASHBOARD (LAYOUT OF SCREENSHOT 2 & DYNAMIC DATABASE DATA)

    # ══════════════════════════════════════════════════════════════════════

    def _get_internal_dashboard_data(self, date_filter='month', project_type='internal'):

        Project = request.env["project.project"].sudo()

        Task = request.env["project.task"].sudo()

        now = datetime.now()

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_date = today.date()

        if date_filter == 'day':

            start_date = today_date

        elif date_filter == 'month':

            start_date = today_date.replace(day=1)

        elif date_filter == 'year':

            start_date = today_date.replace(month=1, day=1)

        else:

            start_date = None

        all_projects = Project.search([('x_project_type', '=', project_type)])
        trend_projects = all_projects

        if start_date:

            filtered_projs = all_projects.filtered(

                lambda p: (to_date(p.create_date) and to_date(p.create_date) >= start_date)

                or (to_date(p.write_date) and to_date(p.write_date) >= start_date)

                or (p.x_project_status in ('new', 'in_progress', 'on_hold'))

            )

            if filtered_projs:

                all_projects = filtered_projs

        total_projects = len(all_projects)

        active_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'in_progress'))

        on_hold_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'on_hold'))

        completed_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'done'))

        cancelled_projects = len(all_projects.filtered(lambda p: p.x_project_status == 'cancelled'))

        parent_tasks = Task.search([('project_id.x_project_type', '=', project_type), ('project_id', '!=', False), ('parent_id', '=', False)])
        trend_parent_tasks = parent_tasks

        if start_date:

            filtered_tasks = parent_tasks.filtered(

                lambda t: (to_date(t.create_date) and to_date(t.create_date) >= start_date)

                or (to_date(t.date_deadline) and to_date(t.date_deadline) >= start_date)

                or (to_date(t.write_date) and to_date(t.write_date) >= start_date)

                or (t.project_id.id in all_projects.ids and not is_task_done(t))

            )

            if filtered_tasks:

                parent_tasks = filtered_tasks

        subtasks = get_task_descendants(Task, parent_tasks)

        all_tasks = parent_tasks | subtasks

        trend_subtasks = get_task_descendants(Task, trend_parent_tasks)

        trend_tasks = trend_parent_tasks | trend_subtasks

        total_tasks = len(all_tasks)

        total_subtasks = len(subtasks)

        overdue_tasks_list = all_tasks.filtered(lambda t: t.x_is_overdue)

        overdue_tasks = len(overdue_tasks_list)

        # Projects by status (donut)

        status_counts = {'new': 0, 'in_progress': 0, 'on_hold': 0, 'done': 0, 'cancelled': 0}

        for p in all_projects:

            status_counts[p.x_project_status] = status_counts.get(p.x_project_status, 0) + 1

        total_p_cnt = total_projects or 1

        # Use simple labels for internal, SDLC labels for technical
        if project_type == 'technical':
            projects_by_status = [
                {'label': 'Planning',       'count': status_counts['new'],         'key': 'new',         'pct': round(status_counts['new'] * 100.0 / total_p_cnt, 1)},
                {'label': 'In Development', 'count': status_counts['in_progress'], 'key': 'in_progress', 'pct': round(status_counts['in_progress'] * 100.0 / total_p_cnt, 1)},
                {'label': 'On Hold',        'count': status_counts['on_hold'],     'key': 'on_hold',     'pct': round(status_counts['on_hold'] * 100.0 / total_p_cnt, 1)},
                {'label': 'Implemented',    'count': status_counts['done'],        'key': 'done',        'pct': round(status_counts['done'] * 100.0 / total_p_cnt, 1)},
                {'label': 'Cancelled',      'count': status_counts['cancelled'],   'key': 'cancelled',   'pct': round(status_counts['cancelled'] * 100.0 / total_p_cnt, 1)},
            ]
        else:
            projects_by_status = [
                {'label': 'New',         'count': status_counts['new'],         'key': 'new',         'pct': round(status_counts['new'] * 100.0 / total_p_cnt, 1)},
                {'label': 'In Progress', 'count': status_counts['in_progress'], 'key': 'in_progress', 'pct': round(status_counts['in_progress'] * 100.0 / total_p_cnt, 1)},
                {'label': 'On Hold',     'count': status_counts['on_hold'],     'key': 'on_hold',     'pct': round(status_counts['on_hold'] * 100.0 / total_p_cnt, 1)},
                {'label': 'Done',        'count': status_counts['done'],        'key': 'done',        'pct': round(status_counts['done'] * 100.0 / total_p_cnt, 1)},
                {'label': 'Cancelled',   'count': status_counts['cancelled'],   'key': 'cancelled',   'pct': round(status_counts['cancelled'] * 100.0 / total_p_cnt, 1)},
            ]

        # SDLC Phases · Tasks by Stage (donut)

        stage_data = {}

        stage_task_ids = {}

        for task in parent_tasks:

            stage_name = canonical_dashboard_stage_label(task.stage_id.name, project_type) if task.stage_id else 'Unassigned'

            stage_data[stage_name] = stage_data.get(stage_name, 0) + 1

            stage_task_ids.setdefault(stage_name, []).append(task.id)

        # Only the configured SDLC phases belong in this chart. Keep legacy,
        # unrelated, and unassigned stages out of both the legend and totals.
        stage_order = list(INTERNAL_PHASE_LABELS if project_type == 'internal' else SDLC_PHASE_LABELS)

        tot_sdlc_cnt = sum(stage_data.get(stage, 0) for stage in stage_order) or 1

        tasks_by_stage = [

            {

                'label': s,

                'count': stage_data.get(s, 0),

                'pct': round(stage_data.get(s, 0) * 100.0 / tot_sdlc_cnt, 1),

                'task_ids': stage_task_ids.get(s, []),

            }

            for s in stage_order

        ]

        # Top 5 Projects (Icon instead of emoji)

        top_projects = []

        for project in all_projects[:10]:

            p_t = parent_tasks.filtered(lambda t: t.project_id.id == project.id)

            p_st = subtasks.filtered(lambda t: t.project_id.id == project.id or t.parent_id.id in p_t.ids)

            proj_tasks = p_t | p_st

            if not proj_tasks:

                pct = 0

            else:

                done_c = len(proj_tasks.filtered(is_task_done))

                pct = round((done_c / len(proj_tasks)) * 100)

            top_projects.append({

                'id': project.id,

                'name': project.name,

                'progress': pct,

                'total_tasks': len(proj_tasks),

                'done_tasks': len(proj_tasks.filtered(is_task_done)),

            })

        top_projects = sorted(top_projects, key=lambda x: (x['progress'], x['total_tasks']), reverse=True)[:5]

        # Resource Utilization

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

        resource_utilization = sorted(resource_utilization, key=lambda x: x['utilization'], reverse=True)[:5]

        daily_log_data = get_daily_log_data(all_tasks, date_filter, today_date)

        daily_tasks = daily_log_data['items']

        daily_tasks_total = daily_log_data['total']

        # Main Tasks & Subtasks (Separated)

        main_and_subtasks = []

        for task in parent_tasks:

            children = subtasks.filtered(lambda child: child.parent_id.id == task.id)

            children_data = []

            for c in children:

                children_data.append({

                    'id': c.id,

                    'name': c.name,

                    'stage': c.stage_id.name if c.stage_id else 'New',

                    'is_done': is_task_done(c),

                    'deadline': c.date_deadline.strftime('%b %d, %Y') if c.date_deadline else '',

                })

            children_data = children_data[:5]

            sub_count = len(children)

            sub_done = len(children.filtered(is_task_done))

            if sub_count > 0:

                pct = round((sub_done / sub_count) * 100)

            else:

                pct = 100 if is_task_done(task) else 0

            if is_task_done(task) or (sub_count > 0 and sub_done == sub_count):

                status_label = 'Completed'

                status_color = 'success'

            elif pct > 0 or (task.stage_id and task.stage_id.name in ('In Progress', 'In Development', 'Testing & Review')):

                status_label = 'In Progress'

                status_color = 'primary'

            elif task.stage_id and canonical_internal_stage_label(task.stage_id.name) == 'Planning':

                status_label = 'Planning'

                status_color = 'warning'

            elif task.stage_id and 'rework' in task.stage_id.name.lower():

                status_label = 'Re-Work'

                status_color = 'danger'

            else:

                status_label = 'Not Started'

                status_color = 'secondary'

            main_and_subtasks.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else '',

                'subtasks_count': sub_count,

                'done_subtasks': sub_done,

                'subtask_str': f"{sub_done}/{sub_count}" if sub_count > 0 else ("1/1" if is_task_done(task) else "0/1"),

                'progress': pct,

                'status': status_label,

                'status_color': status_color,

                'due_date': task.date_deadline.strftime('%b %d, %Y') if task.date_deadline else (task.create_date.strftime('%b %d, %Y') if task.create_date else 'No Date'),

                'subtasks': children_data,

            })

        # SDLC Workflow Tracking (replacing milestones & approvals, highlighting Planning & Re-Work)

        # ── SDLC Workflow: 1 row per project, phase derived from x_project_status ──
        # Mapping: new->Planning, in_progress->In Development, on_hold->On Hold,
        #          done->Implemented, cancelled->Cancelled
        _STATUS_TO_SDLC = {
            'new':         ('Planning',       'In Planning',   'info',      'Pending',  'warning', False, True),
            'in_progress': ('In Development', 'In Progress',   'primary',   'In Progress', 'info', False, False),
            'on_hold':     ('On Hold',        'On Hold',       'warning',   'Pending',  'warning', False, False),
            'done':        ('Implemented',    'Completed',     'success',   'Approved', 'success', False, False),
            'cancelled':   ('Cancelled',      'Cancelled',     'secondary', 'N/A',      'secondary', False, False),
        }

        # SDLC Workflow & Stage Tracking: take technical projects (1 row per project)
        sdlc_projects = Project.search([('x_project_type', '=', 'technical')])
        if not sdlc_projects and project_type != 'technical':
            sdlc_projects = all_projects

        sdlc_workflow = []

        for proj in sdlc_projects:

            all_p_tasks = Task.search([('project_id', '=', proj.id)])

            p_t = all_p_tasks.filtered(lambda t: not t.parent_id)

            task_count = len(all_p_tasks)

            done_cnt = len(all_p_tasks.filtered(is_task_done))

            pct = round(done_cnt * 100 / task_count) if task_count else 0

            proj_status = proj.x_project_status or 'new'

            phase, status_lbl, status_color, approval_lbl, approval_color, is_rework, is_planning =                 _STATUS_TO_SDLC.get(proj_status, _STATUS_TO_SDLC['new'])

            # Due date: use first task deadline, else project create date
            due = None
            for t in p_t:
                if t.date_deadline:
                    due = t.date_deadline.strftime('%b %d, %Y')
                    break
            if not due and proj.create_date:
                due = proj.create_date.strftime('%b %d, %Y')
            due = due or 'Active'

            sdlc_workflow.append({

                'project_id': proj.id,

                'project_name': proj.name,

                'phase': phase,

                'task_count': task_count,

                'progress': pct,

                'status': status_lbl,

                'status_color': status_color,

                'approval': approval_lbl,

                'approval_color': approval_color,

                'due_date': due,

                'is_rework': is_rework,

                'is_planning': is_planning,

            })

        # Overdue tasks

        overdue_task_data = []

        for task in overdue_tasks_list[:5]:

            task_dl = to_date(task.date_deadline)

            days_od = (today_date - task_dl).days if task_dl else 1

            overdue_task_data.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),

                'days_overdue': days_od,

                'time_ago': f"{days_od} days ago",

                'stage': task.stage_id.name if task.stage_id else '',

            })

        overdue_task_data = sorted(overdue_task_data, key=lambda x: x['days_overdue'], reverse=True)

        # Upcoming deadlines

        upcoming = (parent_tasks | subtasks).filtered(

            lambda t: to_date(t.date_deadline) and to_date(t.date_deadline) >= today_date and not is_task_done(t)

        ).sorted('date_deadline')[:5]

        if not upcoming:

            upcoming = (parent_tasks | subtasks).filtered(lambda t: t.date_deadline and not is_task_done(t)).sorted('date_deadline')[:5]

        upcoming_deadlines = []

        for task in upcoming:

            task_dl = to_date(task.date_deadline)

            days_left = (task_dl - today_date).days if task_dl else 0

            upcoming_deadlines.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),

                'deadline': task.date_deadline.strftime('%b %d, %Y') if task.date_deadline else 'Upcoming',

                'days_left': days_left,

            })

        # Recently created tasks

        recent_tasks = (parent_tasks | subtasks).sorted('create_date', reverse=True)[:5]

        recent_activities = []

        for task in recent_tasks:

            delta = now - task.create_date if task.create_date else timedelta(hours=2)

            if delta.days == 0:

                hrs = delta.seconds // 3600

                time_ago = f"{max(1, hrs)} hours ago" if hrs > 0 else f"{max(1, delta.seconds // 60)} mins ago"

            elif delta.days == 1:

                time_ago = "1 day ago"

            else:

                time_ago = f"{delta.days} days ago"

            assignees = ', '.join(task.user_ids.mapped('name')) if task.user_ids else 'Unassigned'

            recent_activities.append({

                'id': task.id,

                'name': task.name,

                'project': task.project_id.name if task.project_id else (task.parent_id.project_id.name if task.parent_id else ''),

                'assignees': assignees,

                'stage': task.stage_id.name if task.stage_id else '',

                'created': task.create_date.strftime('%b %d, %H:%M') if task.create_date else '',

                'time_ago': time_ago,

            })

        # Alerts

        alerts = []

        if overdue_tasks > 0:

            alerts.append({

                'level': 'danger',

                'message': f"{overdue_tasks} tasks are overdue",

            })

        rework_count = len(all_tasks.filtered(lambda t: t.stage_id and 'rework' in t.stage_id.name.lower() and not is_task_done(t)))

        if rework_count > 0:

            alerts.append({

                'level': 'warning',

                'message': f"{rework_count} task(s) require re-work",

            })

        stale_date = today - timedelta(days=14)

        stale_projects = all_projects.filtered(

            lambda p: p.x_project_status == 'in_progress' and p.write_date and p.write_date < stale_date

        )

        if stale_projects:

            alerts.append({

                'level': 'warning',

                'message': f"{len(stale_projects)} project(s) have had no updates in 14 days",

            })

        main_tasks_total = len(main_and_subtasks)

        main_and_subtasks = main_and_subtasks[:5]

        sdlc_workflow_total = len(sdlc_workflow) if sdlc_workflow else 0

        sdlc_workflow = sdlc_workflow[:5] if sdlc_workflow else []

        recent_activities_total = len(recent_activities)

        recent_activities = recent_activities[:5]

        kpis = {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'on_hold_projects': on_hold_projects,
            'completed_projects': completed_projects,
            'cancelled_projects': cancelled_projects,
            'total_tasks': total_tasks,
            'total_subtasks': total_subtasks,
            'overdue_tasks': overdue_tasks,
        }

        windows = comparison_windows(date_filter, today_date)
        add_metric_trend(kpis, 'total_projects', trend_projects, lambda p: True, lambda p: p.create_date, windows, label='Projects created')
        add_metric_trend(kpis, 'active_projects', trend_projects, lambda p: p.x_project_status == 'in_progress', lambda p: p.write_date, windows, label='Active projects updated')
        add_metric_trend(kpis, 'on_hold_projects', trend_projects, lambda p: p.x_project_status == 'on_hold', lambda p: p.write_date, windows, neutral_tone=True, label='On-hold projects updated')
        add_metric_trend(kpis, 'completed_projects', trend_projects, lambda p: p.x_project_status == 'done', lambda p: p.write_date, windows, label='Completed projects updated')
        add_metric_trend(kpis, 'cancelled_projects', trend_projects, lambda p: p.x_project_status == 'cancelled', lambda p: p.write_date, windows, neutral_tone=True, label='Cancelled projects updated')
        add_metric_trend(kpis, 'total_tasks', trend_tasks, lambda t: True, lambda t: t.create_date, windows, label='Tasks created')
        add_metric_trend(kpis, 'total_subtasks', trend_subtasks, lambda t: True, lambda t: t.create_date, windows, label='Subtasks created')
        add_metric_trend(kpis, 'overdue_tasks', trend_tasks, lambda t: t.x_is_overdue and not is_task_done(t), lambda t: t.date_deadline, windows, inverse=True, label='Tasks newly overdue')

        return {

            'kpis': kpis,

            'projects_by_status': projects_by_status,

            'tasks_by_stage': tasks_by_stage,
            'sdlc_phases_total_tasks': sum(stage_data.get(stage, 0) for stage in SDLC_PHASE_LABELS),

            'project_progress': [],

            'top_projects': top_projects,

            'resource_utilization': resource_utilization,

            'main_and_subtasks': main_and_subtasks,

            'subtask_ids': subtasks.ids,

            'main_tasks_total': main_tasks_total,

            'sdlc_workflow': sdlc_workflow,

            'sdlc_workflow_total': sdlc_workflow_total,

            'overdue_task_data': overdue_task_data,

            'daily_tasks': daily_tasks,

            'daily_tasks_total': daily_tasks_total,

            'daily_logs_enabled': daily_log_data['enabled'],

            'daily_log_domain': daily_log_data['domain'],

            'upcoming_deadlines': upcoming_deadlines,

            'recent_activities': recent_activities,

            'recent_activities_total': recent_activities_total,

            'alerts': alerts,

            'timesheet_summary': [],

        }

    @http.route('/project_dashboard_v19c/projects_list', type='jsonrpc', auth='user')

    def get_projects_list(self, project_type='client'):

        """Return list of projects for the project selector."""

        if not request.env.user.has_group('project.group_project_manager'):

            raise AccessError("Only Project Administrators can access the project dashboard.")

        Project = request.env['project.project'].sudo()

        projects = Project.search([('x_project_type', '=', project_type)], order='name asc')

        result = []

        for p in projects:

            result.append({

                'id': p.id,

                'name': p.name,

                'status': p.x_project_status,

            })

        return result

    @http.route('/project_dashboard_v19c/project_detail', type='jsonrpc', auth='user')

    def get_project_detail(self, project_id, date_filter='all'):

        """Return detailed dashboard data for a single project."""

        if not request.env.user.has_group('project.group_project_manager'):

            raise AccessError("Only Project Administrators can access the project dashboard.")

        Project = request.env['project.project'].sudo()

        project = Project.browse(project_id)

        if not project.exists():

            return {'error': 'Project not found'}

        if project.x_project_type == 'client':

            return self._get_client_project_detail(project)

        else:

            return self._get_internal_project_detail(project, date_filter=date_filter)

    # ══════════════════════════════════════════════════════════════════════

    # CLIENT PROJECT DETAIL (100% UNTOUCHED ORIGINAL LOGIC)

    # ══════════════════════════════════════════════════════════════════════

    def _get_client_project_detail(self, project):

        Task = request.env['project.task'].sudo()

        Milestone = request.env['project.milestone'].sudo()

        now = datetime.now()

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        parent_tasks = Task.search([('project_id', '=', project.id)])

        subtasks = Task.search([('parent_id', 'in', parent_tasks.ids)]) if parent_tasks else Task.browse()

        all_tasks = parent_tasks | subtasks

        total_tasks = len(all_tasks)

        done_tasks = len(all_tasks.filtered(is_task_done))

        main_tasks_data = []

        for task in parent_tasks:

            children = subtasks.filtered(lambda child: child.parent_id.id == task.id)

            main_tasks_data.append({

                'id': task.id,

                'name': task.name,

                'subtask_count': len(children),

                'done_subtasks': len(children.filtered(is_task_done)),

                'subtasks': [{'id': child.id, 'name': child.name, 'stage': child.stage_id.name if child.stage_id else 'New'} for child in children],

                'stage': task.stage_id.name if task.stage_id else 'New',

            })

        milestones = Milestone.search(

            [('project_id', '=', project.id)],

            order='sequence asc, deadline asc, name asc'

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

            is_reached = bool(ms.is_reached)

            if is_reached:

                acceptance_status = 'signed'

                acceptance_label = 'Signed'

            elif ms_progress == 100 and ms_total > 0:

                acceptance_status = 'awaiting'

                acceptance_label = 'Awaiting'

            elif ms_progress > 0:

                acceptance_status = 'in_progress'

                acceptance_label = 'In Progress'

            else:

                acceptance_status = 'upcoming'

                acceptance_label = 'Pending'

            overall_progress_sum += milestone_weight * (ms_progress / 100.0)

            milestones_data.append({

                'id': ms.id,

                'name': ms.name,

                'sequence': ms.sequence,

                'deadline': ms.deadline.strftime('%b %d, %Y') if ms.deadline else '',

                'is_reached': is_reached,

                'acceptance_status': acceptance_status,

                'acceptance_label': acceptance_label,

                'total_tasks': ms_total,

                'done_tasks': ms_done,

                'progress': ms_progress,

            })

        if len(milestones) > 0:

            overall_progress = round(overall_progress_sum)

        else:

            overall_progress = round((done_tasks / total_tasks) * 100) if total_tasks else 0

        ms_task_dates = {}

        for ms in milestones:

            ms_direct = all_tasks.filtered(lambda t: t.milestone_id.id == ms.id)

            ms_sub = subtasks.filtered(lambda t: t.parent_id.id in ms_direct.ids)

            ms_all = ms_direct | ms_sub

            deadlines = [t.date_deadline for t in ms_all if t.date_deadline]

            ms_task_dates[ms.id] = (

                min(deadlines) if deadlines else None,

                max(deadlines) if deadlines else None,

            )

        timeline = []

        prev_end_date = None

        for i, ms in enumerate(milestones):

            ms_data = milestones_data[i]

            task_min, task_max = ms_task_dates.get(ms.id, (None, None))

            if ms.deadline:

                end_date = ms.deadline

            elif task_max:

                end_date = task_max

            else:

                end_date = None

            if prev_end_date:

                start_date = prev_end_date

            elif project.create_date:

                start_date = project.create_date.date()

            elif task_min:

                start_date = task_min

            else:

                start_date = None

            start_str = start_date.strftime('%b %d') if start_date else ''

            end_str   = end_date.strftime('%b %d')   if end_date   else ''

            bar_width = ms_data['progress'] or 5

            timeline.append({

                'name':       ms_data['name'],

                'start':      start_str,

                'end':        end_str,

                'progress':   bar_width,

                'is_reached': ms_data['is_reached'],

                'has_dates':  bool(start_str or end_str),

            })

            prev_end_date = end_date

        ClientAction = request.env['project.client.action'].sudo()

        client_actions_records = ClientAction.search([('project_id', '=', project.id)], order='is_done asc, date_due asc, create_date desc')

        client_actions = []

        for ca in client_actions_records:

            client_actions.append({

                'id': ca.id,

                'name': ca.name,

                'date_due': ca.date_due.strftime('%b %d') if ca.date_due else '',

                'is_done': ca.is_done,

                'status': ca.status,

                'contact': ca.assigned_partner_id.name if ca.assigned_partner_id else '',

            })

        RiskIssue = request.env['project.risk.issue'].sudo()
        try:
            request.env.cr.execute("""
                ALTER TABLE project_risk_issue 
                ADD COLUMN IF NOT EXISTS submitted_date date,
                ADD COLUMN IF NOT EXISTS closed_date date;
                UPDATE project_risk_issue 
                SET submitted_date = COALESCE(submitted_date, create_date::date, CURRENT_DATE) 
                WHERE submitted_date IS NULL;
            """)
        except Exception:
            pass

        risk_issue_records = RiskIssue.search([('project_id', '=', project.id)], order='severity desc, create_date desc')

        risks_and_issues = []

        for ri in risk_issue_records:

            risks_and_issues.append({

                'id': ri.id,

                'name': ri.name,

                'type': ri.type,

                'severity': ri.severity,

                'status': ri.status,

                'assigned_to': ri.assigned_user_id.name if ri.assigned_user_id else '',

                'target_date': ri.target_date.strftime('%b %d') if ri.target_date else '',

                'submitted_date': ri.submitted_date.strftime('%b %d, %Y') if ri.submitted_date else '',

                'closed_date': ri.closed_date.strftime('%b %d, %Y') if ri.closed_date else '',

            })

        project_info = {
            'id': project.id,
            'name': project.name,
            'status': project.x_project_status,
            'start_date': project.create_date.strftime('%b %d, %Y') if project.create_date else '',
            'overall_progress': overall_progress,
            'total_tasks': total_tasks,
            'done_tasks': done_tasks,
            'done_task_ids': all_tasks.filtered(is_task_done).ids,
            'remaining_task_ids': all_tasks.filtered(lambda t: not is_task_done(t)).ids,
            'all_task_ids': all_tasks.ids,
        }

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

        user_task_counts = {}

        for task in all_tasks:

            for user in task.user_ids:

                if user.name not in user_task_counts:

                    user_task_counts[user.name] = 0

                user_task_counts[user.name] += 1

        tasks_by_consultant = [

            {'name': name, 'count': count}

            for name, count in sorted(user_task_counts.items(), key=lambda x: x[1], reverse=True)

        ][:8]

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

        unassigned_parents = parent_tasks.filtered(lambda t: not t.milestone_id)

        unassigned_subtasks = subtasks.filtered(lambda t: t.parent_id.id in unassigned_parents.ids)

        unassigned_tasks = unassigned_parents | unassigned_subtasks

        if len(unassigned_tasks) > 0:

            workload.append({

                'label': 'Unassigned',

                'count': len(unassigned_tasks),

            })

        go_live_readiness = overall_progress

        next_30_days = today.date() + timedelta(days=30)

        upcoming = parent_tasks.filtered(

            lambda t: to_date(t.date_deadline) and today.date() <= to_date(t.date_deadline) <= next_30_days and not is_task_done(t)

        )

        upcoming_subtasks = subtasks.filtered(

            lambda t: to_date(t.date_deadline) and today.date() <= to_date(t.date_deadline) <= next_30_days and not is_task_done(t)

        )

        upcoming = (upcoming | upcoming_subtasks).sorted('date_deadline')[:8]

        upcoming_deadlines = []

        for task in upcoming:

            task_dl = to_date(task.date_deadline)

            days_left = (task_dl - today.date()).days if task_dl else 0

            upcoming_deadlines.append({

                'id': task.id,

                'name': task.name,

                'deadline': task.date_deadline.strftime('%b %d') if task.date_deadline else '',

                'days_left': days_left,

                'critical': days_left <= 3,

            })

        task_timesheets = []

        if 'account.analytic.line' in request.env and all_tasks:

            AnalyticLine = request.env['account.analytic.line'].sudo()

            task_ts_data = AnalyticLine.read_group(

                [('task_id', 'in', all_tasks.ids)],

                ['task_id', 'unit_amount'],

                ['task_id']

            )

            task_dict = {t.id: t for t in all_tasks}

            for ts in task_ts_data:

                task_id_val = ts['task_id'][0] if ts['task_id'] else False

                task_name = ts['task_id'][1] if ts['task_id'] else 'Unknown'

                if task_id_val:

                    task = task_dict.get(task_id_val)

                    allocated_hours = getattr(task, 'allocated_hours', 0.0) if task else 0.0

                    total_hours = round(ts['unit_amount'], 2) if ts.get('unit_amount') else 0.0

                    is_delayed = False

                    task_dl = to_date(task.date_deadline) if task else None

                    if task and not is_task_done(task) and task_dl and task_dl < today.date():

                        is_delayed = True

                    if allocated_hours > 0 and total_hours > allocated_hours:

                        status = 'Over Allocated'

                        status_color = 'danger'

                    elif is_delayed:

                        status = 'Delayed'

                        status_color = 'warning'

                    else:

                        status = 'On Track'

                        status_color = 'success'

                    task_timesheets.append({

                        'task_id': task_id_val,

                        'task_name': task_name,

                        'allocated_hours': round(allocated_hours, 2),

                        'total_hours': total_hours,

                        'status': status,

                        'status_color': status_color,

                    })

            task_timesheets = sorted(task_timesheets, key=lambda x: x['total_hours'], reverse=True)[:10]

        return {

            'project': project_info,

            'milestones': milestones_data,

            'main_tasks': main_tasks_data,

            'client_actions': client_actions,

            'risks_and_issues': risks_and_issues,

            'tasks_by_status': tasks_by_status,

            'tasks_by_consultant': tasks_by_consultant,

            'workload': workload,

            'go_live_readiness': go_live_readiness,

            'upcoming_deadlines': upcoming_deadlines,

            'timeline': timeline,

            'task_timesheets': task_timesheets,

        }

    # ══════════════════════════════════════════════════════════════════════

    # INTERNAL PROJECT DETAIL (INDIVIDUAL INTERNAL PROJECT LAYOUT)

    # ══════════════════════════════════════════════════════════════════════

    def _get_internal_project_detail(self, project, date_filter='all'):

        Task = request.env['project.task'].sudo()

        Milestone = request.env['project.milestone'].sudo()

        now = datetime.now()

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_date = today.date()

        parent_tasks = Task.search([('project_id', '=', project.id), ('parent_id', '=', False)])

        trend_parent_tasks = parent_tasks

        trend_subtasks = get_task_descendants(Task, trend_parent_tasks)

        trend_tasks = trend_parent_tasks | trend_subtasks

        if date_filter in ('day', 'month', 'year'):

            start_date = today_date if date_filter == 'day' else (today_date.replace(day=1) if date_filter == 'month' else today_date.replace(month=1, day=1))

            filtered_parent = parent_tasks.filtered(

                lambda t: (to_date(t.create_date) and to_date(t.create_date) >= start_date)

                or (to_date(t.date_deadline) and to_date(t.date_deadline) >= start_date)

                or (to_date(t.write_date) and to_date(t.write_date) >= start_date)

                or not is_task_done(t)

            )

            if filtered_parent:

                parent_tasks = filtered_parent

        subtasks = get_task_descendants(Task, parent_tasks)

        all_tasks = parent_tasks | subtasks

        total_tasks = len(all_tasks)

        done_tasks = len(all_tasks.filtered(is_task_done))

        overdue_tasks_list = all_tasks.filtered(lambda t: t.x_is_overdue)

        overdue_tasks = len(overdue_tasks_list)

        subtask_only = subtasks  # already computed

        total_subtasks = len(subtasks)

        planning_tasks = len(parent_tasks.filtered(lambda t: t.stage_id and canonical_internal_stage_label(t.stage_id.name) == 'Planning' and not is_task_done(t)))

        rework_tasks = len(parent_tasks.filtered(lambda t: t.stage_id and 'rework' in t.stage_id.name.lower() and not is_task_done(t)))

        active_tasks = len(parent_tasks.filtered(lambda t: not is_task_done(t) and not (t.stage_id and (canonical_internal_stage_label(t.stage_id.name) == 'Planning' or 'rework' in t.stage_id.name.lower()))))

        total_timesheet_hours = 0.0

        timesheet_by_person = []

        if 'account.analytic.line' in request.env:

            AnalyticLine = request.env['account.analytic.line'].sudo()

            timesheet_domain = [('project_id', '=', project.id)]

            ts_agg = AnalyticLine.read_group(

                timesheet_domain,

                ['unit_amount'],

                []

            )

            if ts_agg:

                total_timesheet_hours = round(ts_agg[0].get('unit_amount', 0.0), 1)

            person_groups = AnalyticLine.read_group(

                timesheet_domain,

                ['unit_amount', 'employee_id'],

                ['employee_id'],

            )

            for group in person_groups:

                employee = group.get('employee_id')

                timesheet_by_person.append({

                    'employee_id': employee[0] if employee else False,

                    'name': employee[1] if employee else 'Unassigned',

                    'hours': round(group.get('unit_amount') or 0.0, 1),

                })

            timesheet_by_person.sort(key=lambda row: row['hours'], reverse=True)

        main_tasks_data = []

        for task in parent_tasks:

            children = subtasks.filtered(lambda child: child.parent_id.id == task.id)

            children_data = []

            for c in children:

                children_data.append({

                    'id': c.id,

                    'name': c.name,

                    'stage': c.stage_id.name if c.stage_id else 'New',

                    'is_done': is_task_done(c),

                    'deadline': c.date_deadline.strftime('%b %d, %Y') if c.date_deadline else '',

                })

            children_data = children_data[:5]

            sub_count = len(children)

            sub_done = len(children.filtered(is_task_done))

            pct = round((sub_done / sub_count) * 100) if sub_count > 0 else (100 if is_task_done(task) else 0)

            if is_task_done(task) or (sub_count > 0 and sub_done == sub_count):

                status_label = 'Completed'

                status_color = 'success'

            elif pct > 0 or (task.stage_id and task.stage_id.name in ('In Progress', 'In Development', 'Testing & Review')):

                status_label = 'In Progress'

                status_color = 'primary'

            elif task.stage_id and canonical_internal_stage_label(task.stage_id.name) == 'Planning':

                status_label = 'Planning'

                status_color = 'warning'

            elif task.stage_id and 'rework' in task.stage_id.name.lower():

                status_label = 'Re-Work'

                status_color = 'danger'

            else:

                status_label = 'Not Started'

                status_color = 'secondary'

            main_tasks_data.append({

                'id': task.id,

                'name': task.name,

                'project': project.name,

                'subtasks_count': sub_count,

                'done_subtasks': sub_done,

                'subtask_str': f"{sub_done}/{sub_count}" if sub_count > 0 else ("1/1" if is_task_done(task) else "0/1"),

                'progress': pct,

                'status': status_label,

                'status_color': status_color,

                'due_date': task.date_deadline.strftime('%b %d, %Y') if task.date_deadline else (task.create_date.strftime('%b %d, %Y') if task.create_date else 'No Date'),

                'subtasks': children_data,

                'stage': task.stage_id.name if task.stage_id else 'New',

            })

        milestones = Milestone.search([('project_id', '=', project.id)], order='sequence asc, deadline asc, name asc')

        milestones_data = []

        for ms in milestones:

            ms_d = all_tasks.filtered(lambda t: t.milestone_id.id == ms.id)

            ms_s = subtasks.filtered(lambda t: t.parent_id.id in ms_d.ids)

            ms_all = ms_d | ms_s

            ms_tot = len(ms_all)

            ms_dn = len(ms_all.filtered(is_task_done))

            ms_pct = round((ms_dn / ms_tot) * 100) if ms_tot else 0

            milestones_data.append({

                'id': ms.id,

                'name': ms.name,

                'deadline': ms.deadline.strftime('%b %d, %Y') if ms.deadline else '',

                'is_reached': bool(ms.is_reached),

                'total_tasks': ms_tot,

                'done_tasks': ms_dn,

                'progress': ms_pct,

            })

        overall_progress = round((done_tasks / total_tasks) * 100) if total_tasks else 0

        project_info = {
            'id': project.id,
            'name': project.name,
            'status': project.x_project_status,
            'start_date': project.create_date.strftime('%b %d, %Y') if project.create_date else '',
            'overall_progress': overall_progress,
            'total_tasks': total_tasks,
            'done_tasks': done_tasks,
            'done_task_ids': all_tasks.filtered(is_task_done).ids,
            'remaining_task_ids': all_tasks.filtered(lambda t: not is_task_done(t)).ids,
            'all_task_ids': all_tasks.ids,
        }

        Stage = request.env['project.task.type'].sudo()

        # Use this project's configured workflow stages, then include only
        # stages actually used by this project's tasks. Avoid unrelated
        # global stages from other projects (TODO, Week 1, Inbox, etc.).
        phase_stages = project.type_ids.filtered(lambda stage: stage.active and not stage.user_id)
        phase_stages |= all_tasks.mapped('stage_id')

        phase_stages = phase_stages.sorted(lambda stage: (stage.sequence, stage.id))

        tasks_by_stage = []

        sdlc_phases = []

        phase_by_label = {}

        project_phase_labels = INTERNAL_PHASE_LABELS if project.x_project_type == 'internal' else SDLC_PHASE_LABELS

        for stage in phase_stages:

            phase_label = canonical_dashboard_stage_label(stage.name, project.x_project_type)

            # Several projects may expose shared and project-specific stages

            # with the same spelling/case. One canonical phase is enough.

            if phase_label in project_phase_labels:
                phase_by_label.setdefault(phase_label, stage)

        phase_order = list(project_phase_labels)
        for phase_label in project_phase_labels:
            phase_by_label.setdefault(phase_label, False)

        sdlc_task_count = sum(
            1 for task in parent_tasks
            if task.stage_id and canonical_dashboard_stage_label(task.stage_id.name, project.x_project_type) in project_phase_labels
        ) or 1

        pipeline_order = (
            ['New', 'In Progress', 'Done'] if project.x_project_type == 'internal'
            else ['Planning', 'Requirement Analysis', 'In Development', 'Testing & Review', 'Implemented']
        )
        pipeline_rank = {p: i for i, p in enumerate(pipeline_order, 1)}
        total_parent_tasks = len(parent_tasks)

        for phase_label in phase_order:

            stage = phase_by_label.get(phase_label)

            stage_tasks = parent_tasks.filtered(

                lambda task: (canonical_dashboard_stage_label(task.stage_id.name, project.x_project_type) if task.stage_id else 'Unassigned') == phase_label

            )

            stage_deadlines = sorted(task.date_deadline for task in stage_tasks if task.date_deadline)

            stage_name_lower = phase_label.lower()

            if phase_label in pipeline_rank:
                target_rank = pipeline_rank[phase_label]
                if total_parent_tasks == 0:
                    stage_progress = 0
                    stage_status = 'Not Started'
                else:
                    task_progs = []
                    for task in parent_tasks:
                        t_stage = canonical_dashboard_stage_label(task.stage_id.name, project.x_project_type) if task.stage_id else ('New' if project.x_project_type == 'internal' else 'Planning')
                        t_rank = pipeline_rank.get(t_stage, 0)
                        terminal_phase = 'Done' if project.x_project_type == 'internal' else 'Implemented'
                        if t_rank > target_rank or (t_rank == target_rank and phase_label == terminal_phase):
                            task_progs.append(100)
                        elif t_rank == target_rank:
                            task_subtasks = subtasks.filtered(lambda st: st.parent_id.id == task.id)
                            if task_subtasks:
                                done_cnt = len(task_subtasks.filtered(is_task_done))
                                task_progs.append(round(done_cnt * 100.0 / len(task_subtasks)))
                            else:
                                task_progs.append(0)
                        else:
                            task_progs.append(0)
                    stage_progress = round(sum(task_progs) / len(task_progs)) if task_progs else 0
                    if stage_progress == 100:
                        stage_status = 'Completed'
                    elif stage_tasks or stage_progress > 0:
                        stage_status = 'In Progress'
                    else:
                        stage_status = 'Not Started'
            else:
                if not stage_tasks:
                    stage_progress = 0
                    stage_status = 'Not Started'
                elif phase_label == 'Cancelled':
                    stage_progress = 100
                    stage_status = 'Cancelled'
                elif phase_label == 'On Hold':
                    stage_progress = 0
                    stage_status = 'On Hold'
                elif phase_label == 'Rework':
                    rw_subtasks = subtasks.filtered(lambda st: st.parent_id.id in stage_tasks.ids)
                    if rw_subtasks:
                        stage_progress = round(len(rw_subtasks.filtered(is_task_done)) * 100.0 / len(rw_subtasks))
                    else:
                        stage_progress = 0
                    stage_status = 'In Progress'
                else:
                    stage_progress = 0
                    stage_status = 'In Progress'

            tasks_by_stage.append({

                'label': phase_label,

                'stage_id': stage.id if stage else False,

                'count': len(stage_tasks),

                'pct': round(len(stage_tasks) * 100.0 / sdlc_task_count, 1),

                'task_ids': stage_tasks.ids,

            })

            sdlc_phases.append({

                'phase': phase_label,

                'stage_id': stage.id if stage else False,

                'task_ids': stage_tasks.ids,

                'task_count': len(stage_tasks),

                'progress': stage_progress,

                'status': stage_status,

                'due_date': stage_deadlines[0].strftime('%b %d, %Y') if stage_deadlines else 'No deadline',

                'is_rework': 'rework' in stage_name_lower,

                'is_planning': phase_label == 'Planning',

            })

        sdlc_phases_total = len(sdlc_phases)

        sdlc_phases_preview = sdlc_phases[:5]

        user_task_counts = {}

        for task in all_tasks:

            for user in task.user_ids:

                if user.id not in user_task_counts:
                    user_task_counts[user.id] = {
                        'name': user.name,
                        'done': 0,
                        'task_ids': [],
                    }
                user_task_counts[user.id]['task_ids'].append(task.id)
                if is_task_done(task):
                    user_task_counts[user.id]['done'] += 1

        resource_utilization = [

            {
                'user_id': user_id,
                'name': data['name'],
                'utilization': round((data['done'] / len(data['task_ids'])) * 100) if data['task_ids'] else 0,
                'done_tasks': data['done'],
                'total_tasks': len(data['task_ids']),
                'task_ids': list(dict.fromkeys(data['task_ids'])),
            }
            for user_id, data in sorted(user_task_counts.items(), key=lambda item: len(item[1]['task_ids']), reverse=True)

        ][:5]

        # SDLC workflow for this project

        sdlc_workflow = []

        rw_tasks = all_tasks.filtered(lambda t: t.stage_id and 'rework' in t.stage_id.name.lower())

        if rw_tasks:

            done_cnt = len(rw_tasks.filtered(is_task_done))

            sdlc_workflow.append({

                'phase': 'Re-Work',

                'task_count': len(rw_tasks),

                'progress': round(done_cnt * 100 / len(rw_tasks)),

                'status': 'Re-Work Required',

                'status_color': 'danger',

                'due_date': rw_tasks[0].date_deadline.strftime('%b %d, %Y') if rw_tasks[0].date_deadline else 'Active',

                'is_rework': True,

                'is_planning': False,

            })

# 'New' phase mapped to 'Planning' via canonical_internal_stage_label

        pl_tasks = parent_tasks.filtered(lambda t: t.stage_id and canonical_internal_stage_label(t.stage_id.name) == 'Planning')

        if pl_tasks:

            done_cnt = len(pl_tasks.filtered(is_task_done))

            sdlc_workflow.append({

                'phase': 'Planning',

                'task_count': len(pl_tasks),

                'progress': round(done_cnt * 100 / len(pl_tasks)),

                'status': 'In Planning',

                'status_color': 'info',

                'due_date': pl_tasks[0].date_deadline.strftime('%b %d, %Y') if pl_tasks[0].date_deadline else 'Active',

                'is_rework': False,

                'is_planning': True,

            })

        dev_tasks = all_tasks.filtered(lambda t: t.stage_id and ('dev' in t.stage_id.name.lower() or t.stage_id.name == 'In Progress'))

        if dev_tasks:

            done_cnt = len(dev_tasks.filtered(is_task_done))

            pct = round(done_cnt * 100 / len(dev_tasks))

            sdlc_workflow.append({

                'phase': 'Development',

                'task_count': len(dev_tasks),

                'progress': pct,

                'status': 'In Progress' if pct < 100 else 'Completed',

                'status_color': 'primary' if pct < 100 else 'success',

                'due_date': dev_tasks[0].date_deadline.strftime('%b %d, %Y') if dev_tasks[0].date_deadline else 'Active',

                'is_rework': False,

                'is_planning': False,

            })

        test_tasks = all_tasks.filtered(lambda t: t.stage_id and ('test' in t.stage_id.name.lower() or 'review' in t.stage_id.name.lower()))

        if test_tasks:

            done_cnt = len(test_tasks.filtered(is_task_done))

            pct = round(done_cnt * 100 / len(test_tasks))

            sdlc_workflow.append({

                'phase': 'Testing & Review',

                'task_count': len(test_tasks),

                'progress': pct,

                'status': 'In Review' if pct < 100 else 'Verified',

                'status_color': 'warning' if pct < 100 else 'success',

                'due_date': test_tasks[0].date_deadline.strftime('%b %d, %Y') if test_tasks[0].date_deadline else 'Active',

                'is_rework': False,

                'is_planning': False,

            })

        if not (rw_tasks or pl_tasks or dev_tasks or test_tasks) and all_tasks:

            pct = round(done_tasks * 100 / len(all_tasks))

            sdlc_workflow.append({

                'phase': 'Implementation',

                'task_count': len(all_tasks),

                'progress': pct,

                'status': 'Completed' if pct == 100 else 'In Progress',

                'status_color': 'success' if pct == 100 else 'primary',

                'due_date': project.create_date.strftime('%b %d, %Y') if project.create_date else 'Active',

                'is_rework': False,

                'is_planning': False,

            })

        daily_log_data = get_daily_log_data(all_tasks, date_filter, today_date)

        daily_tasks = daily_log_data['items']

        daily_tasks_total = daily_log_data['total']

        upcoming = (parent_tasks | subtasks).filtered(

            lambda t: to_date(t.date_deadline) and to_date(t.date_deadline) >= today_date and not is_task_done(t)

        ).sorted('date_deadline')[:5]

        if not upcoming:

            upcoming = (parent_tasks | subtasks).filtered(lambda t: t.date_deadline and not is_task_done(t)).sorted('date_deadline')[:5]

        upcoming_deadlines = []

        for task in upcoming:

            task_dl = to_date(task.date_deadline)

            days_left = (task_dl - today_date).days if task_dl else 0

            upcoming_deadlines.append({

                'id': task.id,

                'name': task.name,

                'deadline': task.date_deadline.strftime('%b %d, %Y') if task.date_deadline else 'Upcoming',

                'days_left': days_left,

            })

        overdue_task_data = []

        for task in overdue_tasks_list[:5]:

            task_dl = to_date(task.date_deadline)

            days_od = (today_date - task_dl).days if task_dl else 1

            overdue_task_data.append({

                'id': task.id,

                'name': task.name,

                'days_overdue': days_od,

                'time_ago': f"{days_od} days ago",

                'stage': task.stage_id.name if task.stage_id else '',

            })

        overdue_task_data = sorted(overdue_task_data, key=lambda x: x['days_overdue'], reverse=True)

        recent_tasks = (parent_tasks | subtasks).sorted('create_date', reverse=True)[:5]

        recent_activities = []

        for task in recent_tasks:

            delta = now - task.create_date if task.create_date else timedelta(hours=2)

            if delta.days == 0:

                hrs = delta.seconds // 3600

                time_ago = f"{max(1, hrs)} hours ago" if hrs > 0 else f"{max(1, delta.seconds // 60)} mins ago"

            elif delta.days == 1:

                time_ago = "1 day ago"

            else:

                time_ago = f"{delta.days} days ago"

            recent_activities.append({

                'id': task.id,

                'name': task.name,

                'time_ago': time_ago,

                'stage': task.stage_id.name if task.stage_id else '',

            })

        alerts = []

        if overdue_tasks > 0:

            alerts.append({'level': 'danger', 'message': f"{overdue_tasks} tasks are overdue in this project"})

        proj_rw = len(all_tasks.filtered(lambda t: t.stage_id and 'rework' in t.stage_id.name.lower() and not is_task_done(t)))

        if proj_rw > 0:

            alerts.append({'level': 'warning', 'message': f"{proj_rw} task(s) require re-work"})

        main_tasks_total = len(main_tasks_data)

        main_tasks_data = main_tasks_data[:5]

        sdlc_workflow_total = len(sdlc_workflow) if sdlc_workflow else 0

        sdlc_workflow = sdlc_workflow[:5] if sdlc_workflow else []

        recent_activities_total = len(recent_activities)

        recent_activities = recent_activities[:5]

        kpis = {
            'total_tasks': total_tasks,
            'total_subtasks': total_subtasks,
            'active_tasks': active_tasks,
            'planning_tasks': planning_tasks,
            'rework_tasks': rework_tasks,
            'completed_tasks': done_tasks,
            'overdue_tasks': overdue_tasks,
            'total_timesheet_hours': total_timesheet_hours,
            'timesheet_people_count': len(timesheet_by_person),
        }
        windows = comparison_windows(date_filter, today_date)
        add_metric_trend(kpis, 'total_tasks', trend_tasks, lambda t: True, lambda t: t.create_date, windows, label='Tasks created')
        add_metric_trend(kpis, 'total_subtasks', trend_subtasks, lambda t: True, lambda t: t.create_date, windows, label='Subtasks created')
        add_metric_trend(kpis, 'active_tasks', trend_parent_tasks, lambda t: not is_task_done(t) and not (t.stage_id and (canonical_internal_stage_label(t.stage_id.name) == 'Planning' or 'rework' in t.stage_id.name.lower())), lambda t: t.date_last_stage_update, windows, label='Current active tasks updated')
        add_metric_trend(kpis, 'planning_tasks', trend_parent_tasks, lambda t: t.stage_id and canonical_internal_stage_label(t.stage_id.name) == 'Planning' and not is_task_done(t), lambda t: t.date_last_stage_update, windows, neutral_tone=True, label='Current Planning tasks updated')
        add_metric_trend(kpis, 'rework_tasks', trend_parent_tasks, lambda t: t.stage_id and 'rework' in t.stage_id.name.lower() and not is_task_done(t), lambda t: t.date_last_stage_update, windows, neutral_tone=True, label='Current Rework tasks updated')
        add_metric_trend(kpis, 'completed_tasks', trend_tasks, is_task_done, lambda t: t.date_end or t.date_last_stage_update, windows, label='Tasks completed')
        add_metric_trend(kpis, 'overdue_tasks', trend_tasks, lambda t: t.x_is_overdue and not is_task_done(t), lambda t: t.date_deadline, windows, inverse=True, label='Tasks newly overdue')

        return {

            'project': project_info,

            'kpis': kpis,

            'milestones': milestones_data,

            'main_tasks': main_tasks_data,

            'main_and_subtasks': main_tasks_data,

            'subtask_ids': subtasks.ids,

            'client_actions': [],

            'risks_and_issues': [],

            'tasks_by_status': tasks_by_stage,

            'tasks_by_stage': tasks_by_stage,
            'sdlc_phases_total_tasks': sum(s['count'] for s in tasks_by_stage if s['label'] in SDLC_PHASE_LABELS),

            'sdlc_phases': sdlc_phases,

            'sdlc_phases_preview': sdlc_phases_preview,

            'sdlc_phases_total': sdlc_phases_total,

            'tasks_by_consultant': resource_utilization,

            'resource_utilization': resource_utilization,

            'resource_task_ids': all_tasks.filtered(lambda task: bool(task.user_ids)).ids,

            'sdlc_workflow': sdlc_workflow,

            'daily_tasks': daily_tasks,

            'daily_logs_enabled': daily_log_data['enabled'],

            'daily_log_domain': daily_log_data['domain'],

            'workload': [],

            'go_live_readiness': overall_progress,

            'upcoming_deadlines': upcoming_deadlines,

            'overdue_task_data': overdue_task_data,

            'recent_activities': recent_activities,

            'alerts': alerts,

            'timeline': [],

            'task_timesheets': [],

            'timesheet_by_person': timesheet_by_person,

            'timesheet_domain': [['project_id', '=', project.id]],

            'main_tasks_total': main_tasks_total,

            'sdlc_workflow_total': sdlc_workflow_total,

            'daily_tasks_total': daily_tasks_total,

            'recent_activities_total': recent_activities_total,

        }

    @http.route('/project_dashboard_v19c/toggle_milestone_reached', type='jsonrpc', auth='user')

    def toggle_milestone_reached(self, milestone_id):

        """Toggle is_reached on a project.milestone."""

        if not request.env.user.has_group('project.group_project_manager'):

            raise AccessError("Access denied. Only Project Administrators can modify milestones.")

        milestone = request.env['project.milestone'].browse(milestone_id)

        if milestone.exists():

            milestone.write({'is_reached': not milestone.is_reached})

            return {'success': True, 'is_reached': milestone.is_reached}

        return {'error': 'Milestone not found'}

    @http.route('/project_dashboard_v19c/toggle_client_action', type='jsonrpc', auth='user')

    def toggle_client_action(self, action_id):

        """Toggle is_done on a project.client.action."""

        if not request.env.user.has_group('project.group_project_manager'):

            raise AccessError("Access denied. Only Project Administrators can modify client actions.")

        ca = request.env['project.client.action'].browse(action_id)

        if ca.exists():

            new_val = not ca.is_done

            ca.write({

                'is_done': new_val,

                'status': 'approved' if new_val else 'pending'

            })

            return {'success': True, 'is_done': new_val}

        return {'error': 'Action not found'}
