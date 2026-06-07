document.addEventListener("DOMContentLoaded", () => {
    const monthSelect = document.getElementById("monthSelect");
    const tbody = document.getElementById("analyticsRowsBody");
    if (!monthSelect) return;

    const page = document.body.dataset.analyticsPage || "";
    const anomaliesUrl = document.body.dataset.anomaliesUrl || "";

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
    }[char]));

    const setLoading = (isLoading) => {
        document.body.classList.toggle("analytics-loading", isLoading);
        monthSelect.disabled = isLoading;
    };

    const updateAnomalyCard = (data) => {
        const link = document.getElementById("anomaliesLink");
        const card = document.getElementById("anomaliesCard");
        const icon = document.getElementById("anomaliesIcon");
        const hint = document.getElementById("anomaliesHint");

        setText("anomalies", data.anomalies);

        if (link && anomaliesUrl) {
            link.href = `${anomaliesUrl}?month=${encodeURIComponent(data.selected_month)}`;
        }

        if (card) {
            card.classList.toggle("has-anomalies", data.anomalies > 0);
            card.classList.toggle("no-anomalies", data.anomalies <= 0);
        }

        if (icon) {
            icon.className = data.anomalies > 0 ? "fas fa-triangle-exclamation" : "fas fa-check-circle";
        }

        if (hint) {
            hint.hidden = data.anomalies <= 0;
        }
    };

    const buildRow = (row) => {
        const name = escapeHtml(row.name);
        const search = escapeHtml(row.search || row.name);

        if (page === "hr") {
            return `
                <tr class="analytics-search-row" data-search="${search}">
                    <td><strong>${name}</strong></td>
                    <td>${escapeHtml(row.role)}</td>
                    <td>${escapeHtml(row.hours)}</td>
                    <td>${escapeHtml(row.completed)}</td>
                    <td>${escapeHtml(row.total_tasks)}</td>
                    <td>${escapeHtml(row.absences)}</td>
                    <td>${escapeHtml(row.anomalies)}</td>
                </tr>
            `;
        }

        return `
            <tr class="analytics-search-row" data-search="${search}">
                <td><strong>${name}</strong></td>
                <td>${escapeHtml(row.hours)}</td>
                <td>${escapeHtml(row.completed)}</td>
                <td>${escapeHtml(row.total_tasks)}</td>
                <td>${escapeHtml(row.absences)}</td>
                <td>${escapeHtml(row.anomalies)}</td>
            </tr>
        `;
    };

    const updateRows = (rows) => {
        if (!tbody) return;

        if (rows.length) {
            tbody.innerHTML = rows.map(buildRow).join("");
        } else {
            tbody.innerHTML = `<tr><td colspan="${page === "hr" ? 7 : 6}" class="empty-cell">No data for this month.</td></tr>`;
        }

        if (typeof window.applyAnalyticsTableSearch === "function") {
            window.applyAnalyticsTableSearch();
        }
    };

    monthSelect.addEventListener("change", async () => {
        const url = new URL(window.location.href);
        url.searchParams.set("month", monthSelect.value);

        setLoading(true);

        try {
            const response = await fetch(url, {
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });

            if (!response.ok) throw new Error("Failed to load analytics.");

            const data = await response.json();

            setText("selectedMonthLabel", data.selected_month_label);
            setText("subjectCount", data.team_count ?? data.manager_count ?? data.staff_count);
            setText("totalHours", data.total_hours);
            setText("avgHours", data.avg_hours);
            updateAnomalyCard(data);

            setText("completedValue", `${data.completed} / ${data.total_tasks}`);
            setText("readyValue", data.ready);
            setText("inProgressValue", data.in_progress);
            setText("pendingValue", data.pending);
            setText("completionRate", `${data.completion_rate}%`);
            setText("absencesValue", data.absences);
            setText("attendanceAnomaliesValue", data.anomalies);
            setText("avgCompletionRatio", data.avg_completion_ratio);
            setText("trackedTasks", data.total_tasks);

            updateRows(data.rows || []);
            window.history.replaceState({}, "", url);
        } catch (error) {
            console.error(error);
            alert("Could not load analytics for this month.");
        } finally {
            setLoading(false);
        }
    });
});
