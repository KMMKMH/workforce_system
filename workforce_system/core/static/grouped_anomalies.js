document.addEventListener("DOMContentLoaded", () => {
    const monthSelect = document.getElementById("monthSelect");
    const summaryList = document.getElementById("anomalySummaryList");
    const groupsWrap = document.getElementById("groupedAnomalies");
    if (!monthSelect || !summaryList || !groupsWrap) return;

    const page = document.body.dataset.anomalyPage || "employee";
    const analyticsUrl = document.body.dataset.analyticsUrl || "";
    const emptyTitle = page === "employee" ? "No team anomalies found" : "No managers anomalies found";
    const emptyCopy = page === "employee"
        ? "The selected month has no flagged attendance issues for your team."
        : "The selected month has no flagged attendance issues for managers.";
    const personIcon = page === "employee" ? "fa-user" : "fa-user-tie";

    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
    }[char]));

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const setLoading = (isLoading) => {
        document.body.classList.toggle("analytics-loading", isLoading);
        monthSelect.disabled = isLoading;
    };

    const buildSummary = (row) => `
        <div class="${page}-summary-item ${row.count ? "has-issues" : ""}" data-search="${escapeHtml(row.search)}">
            <div>
                <strong>${escapeHtml(row.name)}</strong>
                <span>${escapeHtml(row.position)}</span>
            </div>
            <span class="count-pill">${escapeHtml(row.count)}</span>
        </div>
    `;

    const buildAnomaly = (anomaly) => `
        <article class="anomaly-card">
            <div class="anomaly-card-top">
                <div>
                    <h3><i class="fas fa-calendar-day"></i> ${escapeHtml(anomaly.date)}</h3>
                    <span class="status-pill status-${escapeHtml(anomaly.status_class)}">${escapeHtml(anomaly.status)}</span>
                </div>
                <div class="hours-box">
                    <strong>${escapeHtml(anomaly.worked_hours)}</strong>
                    <span>hours</span>
                </div>
            </div>
            <div class="time-grid">
                <div><span>Check In</span><strong>${escapeHtml(anomaly.check_in)}</strong></div>
                <div><span>Check Out</span><strong>${escapeHtml(anomaly.check_out)}</strong></div>
            </div>
            <div class="reason-box">
                <i class="fas fa-info-circle"></i>
                <p>${escapeHtml(anomaly.reason)}</p>
            </div>
        </article>
    `;

    const buildGroup = (group) => {
        const personClass = `${page}-group anomaly-search-group`;
        const department = group.department ? ` - ${escapeHtml(group.department)}` : "";
        const search = `${group.name} ${group.position} ${group.department} ${group.anomalies.map(item => `${item.status} ${item.reason} ${item.date}`).join(" ")}`;

        return `
            <section class="${personClass}" data-search="${escapeHtml(search)}">
                <div class="${page}-group-header">
                    <div>
                        <h2><i class="fas ${personIcon}"></i> ${escapeHtml(group.name)}</h2>
                        <span>${escapeHtml(group.position)}${department}</span>
                    </div>
                    <div class="group-metrics">
                        <div><strong>${escapeHtml(group.count)}</strong><span>issues</span></div>
                        <div><strong>${escapeHtml(group.hours)}</strong><span>hours</span></div>
                    </div>
                </div>
                <div class="anomaly-card-list">
                    ${group.anomalies.map(buildAnomaly).join("")}
                </div>
            </section>
        `;
    };

    const emptyState = () => `
        <div class="empty-state">
            <i class="fas fa-check-circle"></i>
            <h2>${emptyTitle}</h2>
            <p>${emptyCopy}</p>
        </div>
    `;

    monthSelect.addEventListener("change", async () => {
        const url = new URL(window.location.href);
        url.searchParams.set("month", monthSelect.value);

        setLoading(true);

        try {
            const response = await fetch(url, {
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });

            if (!response.ok) throw new Error("Failed to load anomalies.");

            const data = await response.json();

            setText("totalAnomalies", data.total_anomalies);
            setText("affectedPeople", data.affected_employees ?? data.affected_managers);
            setText("clearPeople", data.clear_employees ?? data.clear_managers);
            setText("selectedMonthLabel", data.selected_month_label);

            const backBtn = document.getElementById("analyticsBackLink");
            if (backBtn && analyticsUrl) {
                backBtn.href = `${analyticsUrl}?month=${encodeURIComponent(data.selected_month)}`;
            }

            summaryList.innerHTML = data.summaries.length
                ? data.summaries.map(buildSummary).join("")
                : `<p class="empty-text">No ${page === "employee" ? "employees are assigned to your team" : "managers found"}.</p>`;

            const searchEmpty = document.getElementById("anomalySearchEmpty");
            groupsWrap.innerHTML = data.groups.length
                ? `${data.groups.map(buildGroup).join("")}${searchEmpty ? searchEmpty.outerHTML : ""}`
                : `${emptyState()}${searchEmpty ? searchEmpty.outerHTML : ""}`;

            if (typeof window.applyAnomalySearch === "function") {
                window.applyAnomalySearch();
            }

            window.history.replaceState({}, "", url);
        } catch (error) {
            console.error(error);
            alert("Could not load anomalies for this month.");
        } finally {
            setLoading(false);
        }
    });
});
