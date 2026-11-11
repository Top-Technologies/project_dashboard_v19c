/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";

const CHART_COLORS = ["#6c757d", "#ffc107", "#28a745", "#dc3545"];
const V2_PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6",
    "#06b6d4", "#ec4899", "#ef4444", "#6366f1",
    "#14b8a6", "#eab308", "#64748b"
];

function loadChartJs() {
    return new Promise((resolve, reject) => {
        if (window.Chart) {
            resolve();
            return;
        }
        const existing = document.querySelector('script[src*="chart.js"]');
        if (existing) {
            existing.addEventListener("load", resolve);
            existing.addEventListener("error", reject);
            return;
        }
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/chart.js";
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

export class ProjectDashboard extends Component {
    static template = "project_dashboard_v19c.ProjectDashboard";

    setup() {
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: null,
            error: null,
            projectType: "client",
            dateFilter: "month",
            expandedTasks: {},
        });
        this.chartProjectStatusRef = useRef("chartProjectStatus");
        this.chartTaskStageRef = useRef("chartTaskStage");
        this.chartProgressRef = useRef("chartProgress");
        this._charts = {};
        onMounted(() => this.loadData());
        onWillUnmount(() => this._destroyCharts());
    }

    toggleSubtasks(taskId) {
        if (!this.state.expandedTasks) {
            this.state.expandedTasks = {};
        }
        this.state.expandedTasks[taskId] = !this.state.expandedTasks[taskId];
    }

    openProjects(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "project.project",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    openTasks(domain, name, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "project.task",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            context: {
                search_default_my_tasks: 0,
                search_default_open_tasks: 0,
                ...context,
            },
            target: "current",
        });
    }

    openProjectForm(projectId) {
        if (!projectId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            views: [[false, "form"]],
            res_id: projectId,
            target: "current",
        });
    }

    openTaskForm(taskId) {
        if (!taskId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            views: [[false, "form"]],
            res_id: taskId,
            target: "current",
        });
    }

    openDailyLog(logId) {
        if (!logId || !this.state.data?.daily_logs_enabled) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Daily Log",
            res_model: "project.task.log",
            views: [[false, "form"]],
            res_id: logId,
            target: "current",
        });
    }

    openDailyLogs() {
        if (!this.state.data?.daily_logs_enabled) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Daily Logs",
            res_model: "project.task.log",
            views: [[false, "list"], [false, "form"]],
            domain: this.state.data.daily_log_domain || [["id", "=", 0]],
            target: "current",
        });
    }

    openUserTasks(userId, userName) {
        if (!userId) return;
        this.openTasks(
            [["user_ids", "in", [userId]]],
            (userName || "User") + "'s Tasks"
        );
    }

    setProjectType(type) {
        if (this.state.projectType !== type) {
            this.state.projectType = type;
            this.loadData();
        }
    }

    onDateFilterChange(ev) {
        this.state.dateFilter = ev.target.value;
        this.loadData();
    }

    onKpiTotalProjectsClick() {
        this.openProjects([["x_project_type", "=", this.state.projectType]], "All Projects");
    }

    onKpiActiveProjectsClick() {
        this.openProjects([["x_project_status", "=", "in_progress"], ["x_project_type", "=", this.state.projectType]], "Active Projects");
    }

    onKpiOnHoldProjectsClick() {
        this.openProjects([["x_project_status", "=", "on_hold"], ["x_project_type", "=", this.state.projectType]], "On Hold Projects");
    }

    onKpiCompletedProjectsClick() {
        this.openProjects([["x_project_status", "=", "done"], ["x_project_type", "=", this.state.projectType]], "Completed Projects");
    }

    onKpiCancelledProjectsClick() {
        this.openProjects([["x_project_status", "=", "cancelled"], ["x_project_type", "=", this.state.projectType]], "Cancelled Projects");
    }

    onKpiTotalTasksClick() {
        this.openTasks(["|", ["project_id.x_project_type", "=", this.state.projectType], ["parent_id.project_id.x_project_type", "=", this.state.projectType]], "All Tasks");
    }

    onKpiSubtasksClick() {
        const subtaskIds = this.state.data?.subtask_ids;
        if (this.state.projectType !== "client" && Array.isArray(subtaskIds) && subtaskIds.length > 0) {
            this.openTasks([["id", "in", subtaskIds]], "Subtasks", { subtask_action: true });
        } else {
            this.openTasks(
                [["parent_id", "!=", false], ["project_id.x_project_type", "=", this.state.projectType]],
                "Subtasks",
                { subtask_action: true }
            );
        }
    }

    onKpiOverdueTasksClick() {
        this.openTasks([["x_is_overdue", "=", true], ["project_id.x_project_type", "=", this.state.projectType]], "Overdue Tasks");
    }

    onTopProjectClick(projectId) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "project_detail_dashboard_v19c",
            name: "Project Dashboard",
            params: { project_id: projectId, projectType: this.state.projectType },
        });
    }

    onDetailedDashboardClick() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "project_detail_dashboard_v19c",
            name: "Detailed Dashboard",
            params: { projectType: this.state.projectType },
        });
    }

    onResourceUtilizationClick(userId, userName) {
        if (this.state.projectType !== "client") {
            this.openTasks([["user_ids", "in", [userId]], ["project_id.x_project_type", "=", this.state.projectType]], (userName || "User") + "'s Tasks");
        } else {
            this.openUserTasks(userId, userName);
        }
    }

    onOverdueTaskClick(taskId) {
        this.openTaskForm(taskId);
    }

    onUpcomingDeadlineClick(taskId) {
        this.openTaskForm(taskId);
    }

    onRecentTaskClick(taskId) {
        this.openTaskForm(taskId);
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = null;
        this.state.data = null;
        try {
            const response = await fetch("/project_dashboard_v19c/data", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { project_type: this.state.projectType, date_filter: this.state.dateFilter } }),
            });
            const result = await response.json();
            if (result.error) {
                this.state.error = result.error.data
                    ? result.error.data.message
                    : result.error.message;
                this.state.loading = false;
                return;
            }
            this.state.data = result.result;
            this.state.loading = false;
            await this._waitForDOM();
            await this._renderCharts();
        } catch (e) {
            console.error("[Dashboard] Load error:", e);
            this.state.error = e.message || "Unexpected error loading dashboard.";
            this.state.loading = false;
        }
    }

    _waitForDOM() {
        return new Promise((resolve) => {
            requestAnimationFrame(() => {
                requestAnimationFrame(resolve);
            });
        });
    }

    _destroyCharts() {
        Object.values(this._charts).forEach((c) => c && c.destroy());
        this._charts = {};
    }

    async _renderCharts() {
        if (!this.state.data) return;
        try {
            await loadChartJs();
        } catch (e) {
            console.error("[Dashboard] Chart.js load failed:", e);
            return;
        }
        if (!window.Chart) {
            console.error("[Dashboard] Chart.js not available after load.");
            return;
        }
        this._destroyCharts();

        if (this.state.projectType === 'internal' || this.state.projectType === 'technical') {
            this._renderInternalProjectStatusChart();
            this._renderInternalTaskStageChart();
            // Bar chart removed for internal projects as requested
        } else {
            this._renderClientProjectStatusChart();
            this._renderClientTaskStageChart();
            this._renderClientProgressChart();
        }
    }

    _renderInternalProjectStatusChart() {
        const el = this.chartProjectStatusRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.projects_by_status || [];
        this._charts.projectStatus = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: data.map((d) => d.label + "  " + d.count + " (" + d.pct + "%)"),
                datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: ["#3b82f6", "#f59e0b", "#10b981", "#06b6d4", "#ef4444"],
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            boxWidth: 10,
                            usePointStyle: true,
                            pointStyle: "circle",
                            font: { size: 12, weight: "500" },
                            padding: 12,
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => " " + data[ctx.dataIndex].label + ": " + ctx.raw + " (" + data[ctx.dataIndex].pct + "%)",
                        },
                    },
                },
                cutout: "70%",
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const slice = data[elements[0].index];
                    if (slice) {
                        this.openProjects([
                            ["x_project_type", "=", this.state.projectType],
                            ["x_project_status", "=", slice.key],
                        ], slice.label + " " + (this.state.projectType === 'technical' ? 'Technical' : 'Internal') + " Projects");
                    }
                },
            },
        });
    }

    _renderInternalTaskStageChart() {
        const el = this.chartTaskStageRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.tasks_by_stage || [];
        this._charts.taskStage = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: data.map((d) => d.label + "  " + d.count + " (" + d.pct + "%)"),
                datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: data.map((_, index) => V2_PALETTE[index % V2_PALETTE.length]),
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            boxWidth: 10,
                            usePointStyle: true,
                            pointStyle: "circle",
                            font: { size: 11, weight: "500" },
                            padding: 8,
                        },
                        onClick: (_event, item) => {
                            const slice = data[item.index];
                            if (slice) {
                                if (slice.task_ids && slice.task_ids.length) {
                                    this.openTasks([["id", "in", slice.task_ids]], slice.label + " Tasks");
                                } else {
                                    this.openTasks([["stage_id.name", "=ilike", slice.label]], slice.label + " Tasks");
                                }
                            }
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => " " + data[ctx.dataIndex].label + ": " + ctx.raw + " (" + data[ctx.dataIndex].pct + "%)",
                        },
                    },
                },
                cutout: "70%",
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const slice = data[elements[0].index];
                    if (slice) {
                        if (slice.task_ids && slice.task_ids.length) {
                            this.openTasks([["id", "in", slice.task_ids]], slice.label + " Tasks");
                        } else {
                            this.openTasks([["stage_id.name", "=ilike", slice.label]], slice.label + " Tasks");
                        }
                    }
                },
            },
        });
    }

    _renderClientProjectStatusChart() {
        const el = this.chartProjectStatusRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.projects_by_status;
        this._charts.projectStatus = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: data.map((d) => d.label),
                datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: CHART_COLORS,
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "right", labels: { boxWidth: 14, font: { size: 12 } } },
                    tooltip: { callbacks: { label: (ctx) => " " + ctx.label + ": " + ctx.raw } },
                },
                cutout: "60%",
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const slice = data[elements[0].index];
                    if (slice) {
                        this.openProjects([["x_project_status", "=", slice.key]], slice.label + " Projects");
                    }
                },
            },
        });
    }

    _renderClientTaskStageChart() {
        const el = this.chartTaskStageRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.tasks_by_stage;
        this._charts.taskStage = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: data.map((d) => d.label),
                datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: CHART_COLORS,
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right", labels: { boxWidth: 14, font: { size: 12 } } } },
                cutout: "60%",
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const slice = data[elements[0].index];
                    if (slice) {
                        this.openTasks([["stage_id.name", "=", slice.label]], slice.label + " Tasks");
                    }
                },
            },
        });
    }

    _renderClientProgressChart() {
        const el = this.chartProgressRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.project_progress || [];
        this._charts.progress = new window.Chart(el, {
            type: "bar",
            data: {
                labels: data.map((item) => item.label),
                datasets: [{
                    label: "Projects",
                    data: data.map((item) => item.count),
                    backgroundColor: ["#dc3545", "#fd7e14", "#ffc107", "#20c997", "#28a745"],
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 }, grid: { color: "rgba(0,0,0,0.05)" } },
                    x: { grid: { display: false } },
                },
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const bucket = data[elements[0].index];
                    if (bucket && bucket.project_ids && bucket.project_ids.length) {
                        this.openProjects([["id", "in", bucket.project_ids]], "Projects at " + bucket.label + " Progress");
                    }
                },
            },
        });
    }

}

registry.category("actions").add("project_dashboard_v19c", ProjectDashboard);

export class ProjectDetailDashboard extends Component {
    static template = "project_dashboard_v19c.ProjectDetailDashboard";

    setup() {
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: null,
            error: null,
            projectsList: [],
            selectedProjectId: this.props.action.params?.project_id || this.props.action.context?.project_id || null,
            projectType: this.props.action.params?.projectType || 'client',
            dateFilter: "month",
            expandedTasks: {},
            showAllPhases: false,
        });
        this.chartTasksStatusRef = useRef("chartTasksStatus");
        this.chartTasksConsultantRef = useRef("chartTasksConsultant");
        this.chartWorkloadRef = useRef("chartWorkload");
        this.chartDetailProgressRef = useRef("chartDetailProgress");
        this.chartDetailTaskStageRef = useRef("chartDetailTaskStage");
        this.chartOverallPlanRef = useRef("chartOverallPlan");
        this._charts = {};

        onMounted(async () => {
            await this.loadProjectsList();
            if (this.state.selectedProjectId) {
                this.loadProjectDetail(this.state.selectedProjectId);
            } else if (this.state.projectsList.length > 0) {
                this.state.selectedProjectId = this.state.projectsList[0].id;
                this.loadProjectDetail(this.state.selectedProjectId);
            }
        });
        onWillUnmount(() => this._destroyCharts());
    }

    toggleSubtasks(taskId) {
        if (!this.state.expandedTasks) {
            this.state.expandedTasks = {};
        }
        this.state.expandedTasks[taskId] = !this.state.expandedTasks[taskId];
    }

    openTasks(domain, name, context = {}) {
        const ctx = {
            search_default_my_tasks: 0,
            search_default_open_tasks: 0,
            ...context,
        };
        if (this.state.selectedProjectId) {
            ctx.default_project_id = this.state.selectedProjectId;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Project Tasks",
            res_model: "project.task",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            context: ctx,
            target: "current",
        });
    }

    openDailyLog(logId) {
        if (!logId || !this.state.data?.daily_logs_enabled) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Daily Log",
            res_model: "project.task.log",
            views: [[false, "form"]],
            res_id: logId,
            target: "current",
        });
    }

    openDailyLogs() {
        if (!this.state.data?.daily_logs_enabled) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Daily Logs",
            res_model: "project.task.log",
            views: [[false, "list"], [false, "form"]],
            domain: this.state.data.daily_log_domain || [["id", "=", 0]],
            target: "current",
        });
    }

    toggleAllPhases() {
        this.state.showAllPhases = !this.state.showAllPhases;
    }

    openStageTasks(stage) {
        if (!stage) return;
        const taskIds = Array.isArray(stage.task_ids) ? stage.task_ids : [];
        let domain;
        if (taskIds.length) {
            // Match the tasks counted by the dashboard, including subtasks
            // whose project_id may not be populated directly.
            domain = [["id", "in", taskIds]];
        } else if (stage.stage_id) {
            domain = [
                ["project_id", "=", this.state.selectedProjectId],
                ["stage_id", "=", stage.stage_id],
            ];
        } else {
            // Keep the drill-down working if the client is still paired with
            // a cached controller response that predates task_ids/stage_id.
            domain = [
                ["project_id", "=", this.state.selectedProjectId],
                ["stage_id.name", "=", stage.label],
            ];
        }
        this.openTasks(domain, stage.label + " Tasks");
    }

    openPhaseTasks(phase) {
        if (!phase) return;
        this.openStageTasks({
            label: phase.phase,
            stage_id: phase.stage_id,
            task_ids: phase.task_ids,
        });
    }

    openResourceTasks(resource) {
        if (!resource) return;
        const taskIds = Array.isArray(resource.task_ids) ? resource.task_ids : [];
        const domain = taskIds.length
            ? [["id", "in", taskIds]]
            : [["project_id", "=", this.state.selectedProjectId], ["user_ids", "in", [resource.user_id]]];
        this.openTasks(domain, (resource.name || "Resource") + "'s Tasks");
    }

    openAllResourceTasks() {
        const taskIds = this.state.data?.resource_task_ids || [];
        this.openTasks([["id", "in", taskIds]], "Assigned Project Tasks");
    }

    openProjects(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Projects",
            res_model: "project.project",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            target: "current",
        });
    }

    onKpiTotalTasksClick() {
        this.openTasks([["project_id", "=", this.state.selectedProjectId]], "Project Tasks");
    }

    openCompletedTasks() {
        const doneIds = this.state.data?.project?.done_task_ids;
        if (Array.isArray(doneIds) && doneIds.length) {
            this.openTasks([["id", "in", doneIds]], "Completed Tasks");
        } else {
            this.openTaskCategory("completed");
        }
    }

    openRemainingTasks() {
        const remIds = this.state.data?.project?.remaining_task_ids;
        if (Array.isArray(remIds) && remIds.length) {
            this.openTasks([["id", "in", remIds]], "Remaining (Planned) Tasks");
        } else {
            this.openTaskCategory("active");
        }
    }

    openPlannedTasks() {
        const planIds = this.state.data?.project?.all_task_ids;
        if (Array.isArray(planIds) && planIds.length) {
            this.openTasks([["id", "in", planIds]], "All Planned Tasks");
        } else {
            this.openTaskCategory("all");
        }
    }

    openTaskCategory(category) {
        const projectId = this.state.selectedProjectId;
        const base = [["project_id", "=", projectId]];
        const subtaskIds = this.state.data?.subtask_ids;
        const subtaskDomain = Array.isArray(subtaskIds) && subtaskIds.length > 0
            ? [["id", "in", subtaskIds]]
            : ["|", ["project_id", "=", projectId], ["parent_id.project_id", "=", projectId], ["parent_id", "!=", false]];

        const filters = {
            all: [base, "Project Tasks", {}],
            active: [[...base, ["stage_id.name", "!=", "Done"], ["state", "!=", "1_done"]], "Active Tasks", {}],
            planning: [[...base, ["stage_id.name", "ilike", "plan"]], "Planning Tasks", {}],
            rework: [[...base, ["stage_id.name", "ilike", "rework"]], "Rework Tasks", {}],
            completed: [[...base, "|", ["stage_id.name", "=", "Done"], ["state", "=", "1_done"]], "Completed Tasks", {}],
            overdue: [[...base, ["x_is_overdue", "=", true]], "Overdue Tasks", {}],
            subtasks: [subtaskDomain, "Subtasks", { subtask_action: true }],
        };
        const [domain, name, context] = filters[category] || filters.all;
        this.openTasks(domain, name, context);
    }

    onKpiSubtasksClick() {
        this.openTaskCategory("subtasks");
    }

    openProjectTimesheets() {
        const domain = this.state.data?.timesheet_domain || [["project_id", "=", this.state.selectedProjectId]];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Project Timesheets by Person",
            res_model: "account.analytic.line",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { group_by: ["employee_id"] },
            target: "current",
        });
    }

    onKpiOverdueTasksClick() {
        this.openTasks([["project_id", "=", this.state.selectedProjectId], ["x_is_overdue", "=", true]], "Overdue Tasks");
    }

    onKpiTotalProjectsClick() {
        this.openProjects([["x_project_type", "=", this.state.projectType]], "Projects");
    }

    async loadProjectsList() {
        try {
            const response = await fetch("/project_dashboard_v19c/projects_list", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { project_type: this.state.projectType } }),
            });
            const result = await response.json();
            if (result.error) {
                console.error("[Dashboard] Load projects error:", result.error);
                return;
            }
            this.state.projectsList = result.result;
        } catch (e) {
            console.error("[Dashboard] Load projects error:", e);
        }
    }

    async loadProjectDetail(projectId) {
        if (!projectId) return;
        this.state.loading = true;
        this.state.error = null;
        this.state.data = null;
        this.state.showAllPhases = false;
        try {
            const response = await fetch("/project_dashboard_v19c/project_detail", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { project_id: projectId, date_filter: this.state.dateFilter } }),
            });
            const result = await response.json();
            if (result.error) {
                this.state.error = result.error.data ? result.error.data.message : result.error.message;
                this.state.loading = false;
                return;
            }
            this.state.data = result.result;
            this.state.loading = false;
            await this._waitForDOM();
            await this._renderCharts();
        } catch (e) {
            console.error("[Dashboard] Load detail error:", e);
            this.state.error = e.message || "Unexpected error loading project detail.";
            this.state.loading = false;
        }
    }

    onProjectChange(ev) {
        const newProjectId = parseInt(ev.target.value, 10);
        this.state.selectedProjectId = newProjectId;
        this.loadProjectDetail(newProjectId);
    }

    onDateFilterChange(ev) {
        this.state.dateFilter = ev.target.value;
        if (this.state.selectedProjectId) this.loadProjectDetail(this.state.selectedProjectId);
    }

    async setProjectType(type) {
        if (this.state.projectType !== type) {
            this.state.projectType = type;
            this.state.selectedProjectId = null;
            this.state.data = null;
            await this.loadProjectsList();
            if (this.state.projectsList.length > 0) {
                this.state.selectedProjectId = this.state.projectsList[0].id;
                this.loadProjectDetail(this.state.selectedProjectId);
            }
        }
    }

    async onToggleMilestone(milestoneId) {
        try {
            const response = await fetch("/project_dashboard_v19c/toggle_milestone_reached", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { milestone_id: milestoneId } }),
            });
            const result = await response.json();
            if (result.result && result.result.success) {
                await this.loadProjectDetail(this.state.selectedProjectId);
            }
        } catch (e) {
            console.error("[Dashboard] Toggle milestone error:", e);
        }
    }

    async onToggleClientAction(actionId) {
        try {
            const response = await fetch("/project_dashboard_v19c/toggle_client_action", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { action_id: actionId } }),
            });
            const result = await response.json();
            if (result.result && result.result.success) {
                await this.loadProjectDetail(this.state.selectedProjectId);
            }
        } catch (e) {
            console.error("[Dashboard] Toggle client action error:", e);
        }
    }

    openTask(taskId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openRiskIssue(riskId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.risk.issue",
            res_id: riskId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    onAddRiskIssue() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Risk / Issue",
            res_model: "project.risk.issue",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_project_id: this.state.selectedProjectId,
            },
        }, {
            onClose: () => {
                this.loadProjectDetail(this.state.selectedProjectId);
            },
        });
    }

    onAddClientAction() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Client Pending Action",
            res_model: "project.client.action",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_project_id: this.state.selectedProjectId,
            },
        }, {
            onClose: () => {
                this.loadProjectDetail(this.state.selectedProjectId);
            },
        });
    }

    onBackClick() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "project_dashboard_v19c",
        }, { clearBreadcrumbs: true });
    }

    _waitForDOM() {
        return new Promise((resolve) => {
            requestAnimationFrame(() => {
                requestAnimationFrame(resolve);
            });
        });
    }

    _destroyCharts() {
        Object.values(this._charts).forEach((c) => c && c.destroy());
        this._charts = {};
    }

    async _renderCharts() {
        if (!this.state.data) return;
        try {
            await loadChartJs();
        } catch (e) {
            console.error("[Dashboard] Chart.js load failed:", e);
            return;
        }
        if (!window.Chart) return;

        this._destroyCharts();

        if (this.state.projectType === 'technical') {
            this._renderInternalDetailProgressChart();
            this._renderInternalDetailTaskStageChart();
            this._renderOverallPlanChart();
        } else {
            // internal and client both use the same chart layout
            this._renderClientDetailCharts();
        }
    }

    _renderOverallPlanChart() {
        const el = this.chartOverallPlanRef.el;
        if (!el || !window.Chart) return;
        const planned = this.state.data.project.total_tasks || 0;
        const completed = this.state.data.project.done_tasks || 0;
        const remaining = Math.max(0, planned - completed);
        this._charts.overallPlan = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: ["Completed", "Remaining"],
                datasets: [{
                    data: [completed, remaining],
                    backgroundColor: ["#22c55e", "#cbd5e1"],
                    hoverBackgroundColor: ["#16a34a", "#94a3b8"],
                    borderColor: "#ffffff",
                    borderWidth: 3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                onHover: (_event, elements, chart) => {
                    chart.canvas.style.cursor = elements.length ? "pointer" : "default";
                },
                onClick: (_event, elements, chart) => {
                    const index = elements.length ? elements[0].index : chart?.legend?.lastActive?.index;
                    if (index === undefined) return;
                    if (index === 0) {
                        this.openCompletedTasks();
                    } else {
                        this.openRemainingTasks();
                    }
                },
                plugins: {
                    legend: {
                        position: "right",
                        labels: { usePointStyle: true, boxWidth: 10, padding: 14, font: { size: 12, weight: "500" } },
                        onClick: (_event, item) => {
                            if (item.index === 0) {
                                this.openCompletedTasks();
                            } else {
                                this.openRemainingTasks();
                            }
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => ` ${context.label}: ${context.raw} (click to view)`
                        }
                    },
                },
            },
        });
    }

    _renderInternalDetailProgressChart() {
        const el = this.chartDetailProgressRef.el;
        if (!el || !window.Chart) return;
        const pct = this.state.data.project.overall_progress || 0;
        this._charts.detailProgress = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: ["Completed (" + pct + "%)", "Remaining (" + (100 - pct) + "%)"],
                datasets: [{
                    data: [pct, Math.max(0, 100 - pct)],
                    backgroundColor: ["#3b82f6", "#e2e8f0"],
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: { boxWidth: 10, usePointStyle: true, pointStyle: "circle", font: { size: 12 } },
                    },
                },
                cutout: "70%",
            },
        });
    }

    _renderInternalDetailTaskStageChart() {
        const el = this.chartDetailTaskStageRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.tasks_by_stage || [];
        this._charts.detailTaskStage = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: data.map((d) => d.label + "  " + d.count + " (" + d.pct + "%)"),
                datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: data.map((_, index) => V2_PALETTE[index % V2_PALETTE.length]),
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onHover: (_event, elements, chart) => {
                    chart.canvas.style.cursor = elements.length ? "pointer" : "default";
                },
                onClick: (_event, elements, chart) => {
                    const index = elements.length ? elements[0].index : chart?.legend?.lastActive?.index;
                    if (index === undefined) return;
                    const slice = data[index];
                    this.openStageTasks(slice);
                },
                plugins: {
                    legend: {
                        position: "right",
                        labels: { boxWidth: 10, usePointStyle: true, pointStyle: "circle", font: { size: 11 }, padding: 8 },
                        onClick: (_event, item) => {
                            const slice = data[item.index];
                            this.openStageTasks(slice);
                        },
                    },
                },
                cutout: "70%",
            },
        });
    }

    _renderClientDetailCharts() {
        const elStatus = this.chartTasksStatusRef.el;
        if (elStatus && window.Chart) {
            const data = this.state.data.tasks_by_status || [];
            this._charts.tasksStatus = new window.Chart(elStatus, {
                type: "bar",
                data: {
                    labels: data.map((d) => d.label),
                    datasets: [{
                        label: "Tasks",
                        data: data.map((d) => d.count),
                        backgroundColor: CHART_COLORS,
                        borderRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                },
            });
        }

        const elConsultant = this.chartTasksConsultantRef.el;
        if (elConsultant && window.Chart) {
            const data = this.state.data.tasks_by_consultant || [];
            this._charts.tasksConsultant = new window.Chart(elConsultant, {
                type: "bar",
                data: {
                    labels: data.map((d) => d.name),
                    datasets: [{
                        label: "Tasks",
                        data: data.map((d) => d.count),
                        backgroundColor: "#0d6efd",
                        borderRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                },
            });
        }

        const elWorkload = this.chartWorkloadRef.el;
        if (elWorkload && window.Chart) {
            const data = this.state.data.workload || [];
            this._charts.workload = new window.Chart(elWorkload, {
                type: "doughnut",
                data: {
                    labels: data.map((d) => d.label),
                    datasets: [{
                        data: data.map((d) => d.count),
                        backgroundColor: CHART_COLORS,
                        borderWidth: 2,
                        borderColor: "#fff",
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } },
                    cutout: "60%",
                },
            });
        }
    }
}

registry.category("actions").add("project_detail_dashboard_v19c", ProjectDetailDashboard);
