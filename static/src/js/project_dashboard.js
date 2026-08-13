/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";

const CHART_COLORS = ["#6c757d", "#ffc107", "#28a745", "#dc3545"];

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
        });
        this.chartProjectStatusRef = useRef("chartProjectStatus");
        this.chartTaskStageRef = useRef("chartTaskStage");
        this.chartProgressRef = useRef("chartProgress");
        this._charts = {};
        onMounted(() => this.loadData());
        onWillUnmount(() => this._destroyCharts());
    }

    /**
     * Open a project.project list view filtered by domain.
     */
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

    /**
     * Open a project.task list view filtered by domain.
     */
    openTasks(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "project.task",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    /**
     * Open a single project record directly in form view.
     */
    openProjectForm(projectId) {
        if (!projectId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            views: [[false, "form"]],
            res_id: projectId,
            target: "current",
        });
    }

    /**
     * Open a single task record directly in form view.
     */
    openTaskForm(taskId) {
        if (!taskId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            views: [[false, "form"]],
            res_id: taskId,
            target: "current",
        });
    }

    /**
     * Open all tasks assigned to a specific user (resource utilization drill-down).
     */
    openUserTasks(userId, userName) {
        if (!userId) {
            return;
        }
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
        this.openTasks([["project_id", "!=", false], ["project_id.x_project_type", "=", this.state.projectType]], "All Tasks");
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
        this.openUserTasks(userId, userName);
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
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { project_type: this.state.projectType } }),
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
        if (!this.state.data) {
            return;
        }
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
        this._renderProjectStatusChart();
        this._renderTaskStageChart();
        this._renderProgressChart();
    }

    _renderProjectStatusChart() {
        const el = this.chartProjectStatusRef.el;
        if (!el || !window.Chart) {
            return;
        }
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
                    if (!elements.length) {
                        return;
                    }
                    const point = elements[0];
                    const slice = data[point.index];
                    if (!slice) {
                        return;
                    }
                    this.openProjects(
                        [["x_project_status", "=", slice.key]],
                        slice.label + " Projects"
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
            },
        });
    }

    _renderTaskStageChart() {
        const el = this.chartTaskStageRef.el;
        if (!el || !window.Chart) {
            return;
        }
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
                    if (!elements.length) {
                        return;
                    }
                    const point = elements[0];
                    const slice = data[point.index];
                    if (!slice) {
                        return;
                    }
                    this.openTasks(
                        [["stage_id.name", "=", slice.label]],
                        slice.label + " Tasks"
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
            },
        });
    }

    _renderProgressChart() {
        const el = this.chartProgressRef.el;
        if (!el || !window.Chart) {
            return;
        }
        const data = this.state.data.project_progress;
        this._charts.progress = new window.Chart(el, {
            type: "bar",
            data: {
                labels: data.map((d) => d.label),
                datasets: [{
                    label: "Projects",
                    data: data.map((d) => d.count),
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
                onClick: (evt, elements) => {
                    if (!elements.length) {
                        return;
                    }
                    const point = elements[0];
                    const bucket = data[point.index];
                    if (!bucket || !bucket.project_ids || !bucket.project_ids.length) {
                        return;
                    }
                    this.openProjects(
                        [["id", "in", bucket.project_ids]],
                        "Projects at " + bucket.label + " Progress"
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
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
        });
        this.chartTasksStatusRef = useRef("chartTasksStatus");
        this.chartTasksConsultantRef = useRef("chartTasksConsultant");
        this.chartWorkloadRef = useRef("chartWorkload");
        this._charts = {};

        onMounted(() => {
            this.loadProjectsList();
            if (this.state.selectedProjectId) {
                this.loadProjectDetail(this.state.selectedProjectId);
            }
        });
        onWillUnmount(() => this._destroyCharts());
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
        this.state.loading = true;
        this.state.error = null;
        this.state.data = null;
        try {
            const response = await fetch("/project_dashboard_v19c/project_detail", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Csrf-Token": odoo.csrf_token,
                },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { project_id: projectId } }),
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

    setProjectType(type) {
        if (this.state.projectType !== type) {
            this.state.projectType = type;
            this.state.selectedProjectId = null;
            this.state.data = null;
            this.loadProjectsList();
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
                // Reload project details to reflect updated sign-off & progress
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
                // Reload project details to update actions list
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
        this._renderTasksStatusChart();
        this._renderTasksAssigneeChart();
        this._renderWorkloadChart();
    }

    _renderTasksStatusChart() {
        const el = this.chartTasksStatusRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.tasks_by_status || [];
        this._charts.tasksStatus = new window.Chart(el, {
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

    _renderTasksAssigneeChart() {
        const el = this.chartTasksConsultantRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.tasks_by_consultant || [];
        this._charts.tasksConsultant = new window.Chart(el, {
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

    _renderWorkloadChart() {
        const el = this.chartWorkloadRef.el;
        if (!el || !window.Chart) return;
        const data = this.state.data.workload || [];
        this._charts.workload = new window.Chart(el, {
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

registry.category("actions").add("project_detail_dashboard_v19c", ProjectDetailDashboard);