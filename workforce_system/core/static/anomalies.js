document.addEventListener("DOMContentLoaded", () => {
    const monthSelect = document.getElementById("monthSelect");
    const anomaliesList = document.getElementById("anomaliesList");
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

    const buildAnomalyCard = (anomaly) => {
        return `
            <div class="anomaly-detail-card">
                <div class="anomaly-detail-header">
                    <div>
                        <h2>
                            <i class="fas fa-calendar-day"></i>
                            ${escapeHtml(anomaly.date)}
                        </h2>
                        <span class="anomaly-status status-${escapeHtml(anomaly.status.toLowerCase())}">
                            ${escapeHtml(anomaly.status)}
                        </span>
                    </div>

                    <div class="anomaly-hours">
                        <strong>${escapeHtml(anomaly.worked_hours)}</strong>
                        <span>hours</span>
                    </div>
                </div>

                <div class="anomaly-times">
                    <div>
                        <i class="fas fa-sign-in-alt"></i>
                        <span>Check In</span>
                        <strong>${escapeHtml(anomaly.check_in)}</strong>
                    </div>

                    <div>
                        <i class="fas fa-sign-out-alt"></i>
                        <span>Check Out</span>
                        <strong>${escapeHtml(anomaly.check_out)}</strong>
                    </div>
                </div>

                <div class="anomaly-reason">
                    <i class="fas fa-info-circle"></i>
                    <p>${escapeHtml(anomaly.reason)}</p>
                </div>
            </div>
        `;
    };

    const buildEmptyState = () => {
        return `
            <div class="empty-anomalies">
                <i class="fas fa-check-circle"></i>
                <h2>No anomalies found</h2>
                <p>This month looks clean. No attendance issues were detected.</p>
            </div>
        `;
    };

    monthSelect.addEventListener("change", async () => {
        const month = monthSelect.value;
        const url = new URL(window.location.href);

        url.searchParams.set("month", month);

        setLoading(true);

        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });

            if (!response.ok) {
                throw new Error("Failed to load anomalies.");
            }

            const data = await response.json();

            document.getElementById("selectedMonthLabel").textContent = data.selected_month_label;

            const anomaliesCount = document.getElementById("anomaliesCount");
            if (anomaliesCount) anomaliesCount.textContent = data.anomalies_count;

            const anomaliesSummary = document.getElementById("anomaliesSummary");
            if (anomaliesSummary) anomaliesSummary.hidden = data.anomalies_count <= 0;

            const backLink = document.getElementById("analyticsBackLink");
            if (backLink) backLink.href = `/analytics/?month=${encodeURIComponent(data.selected_month)}`;

            if (data.anomalies.length > 0) {
                anomaliesList.innerHTML = data.anomalies.map(buildAnomalyCard).join("");
            } else {
                anomaliesList.innerHTML = buildEmptyState();
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
