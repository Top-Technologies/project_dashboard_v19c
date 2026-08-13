{
    'name': 'Project Dashboard v19 Community',
    'version': '19.0.1.0.0',
    'summary': 'Custom Project Dashboard with fixed stages and KPI tracking',
    'description': """
        Project Dashboard for Odoo 19 Community
        ========================================
        - Fixed Task Stages: New, In Progress, Done, Cancelled
        - Fixed Project Status: New, In Progress, Done, Cancelled
        - KPI Overview Dashboard
        - Projects by Status Chart
        - Tasks by Stage Chart
        - Project Progress Chart
        - Top 5 Projects Tracker
        - Resource Utilization
        - Overdue Tasks Panel
        - Alerts Panel
        - Recent Activities
        - Upcoming Deadlines
    """,
    'category': 'Project',
    'author': 'Top Technologies',
    'depends': ['project', 'mail', 'web', 'hr_timesheet'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir.rule.xml',
        'data/project_task_type_data.xml',
        'data/project_project_data.xml',
        'views/project_project_views.xml',
        'views/project_task_views.xml',
        'views/project_dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'project_dashboard_v19c/static/src/css/project_dashboard.css',
            'project_dashboard_v19c/static/src/xml/project_dashboard.xml',
            'project_dashboard_v19c/static/src/js/project_dashboard.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
