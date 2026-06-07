document.addEventListener("DOMContentLoaded", () => {
    const monthSelect = document.getElementById("monthSelect");

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const setWidth = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.style.width = `${value}%`;
    };

    const setLoading = (isLoading) => {
        document.body.classList.toggle("analytics-loading", isLoading);
        monthSelect.disabled = isLoading;
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
                throw new Error("Failed to load analytics.");
            }

            const data = await response.json();

            setText("selectedMonthLabel", data.selected_month_label);

            setText("totalHours", data.total_hours);
            setText("avgHours", data.avg_hours);
            setText("totalDays", data.total_days);
            setText("anomalies", data.anomalies);

            setText("completedValue", `${data.completed} / ${data.total_tasks}`);
            setText("inProgressValue", `${data.in_progress} / ${data.total_tasks}`);
            setText("pendingValue", `${data.pending} / ${data.total_tasks}`);

            setWidth("completedBar", data.completion_rate);
            setWidth("inProgressBar", data.in_progress_rate);
            setWidth("pendingBar", data.pending_rate);

            setText("completionRate", `${data.completion_rate}%`);

            setText("totalCommits", data.total_commits);
            setText("commitsPerDay", data.commits_per_day);
            setText("activeDays", data.active_days);
            setText("salaryAdjustmentTotal", data.net_pay_display);
            setText("salaryAdjustmentLabel", data.salary_adjustment_label);
            setText("salaryMonthly", `$${data.salary_monthly}`);
            setText("salaryDeductions", `$${data.salary_deductions}`);
            setText("salaryAdditions", `$${data.holiday_overtime_addition}`);
            setText("salaryBonuses", `$${data.bonus_total}`);
            setText("absenceDays", data.absence_days);
            setText("shortHours", data.short_hours);

            const salaryCard = document.querySelector(".salary-adjustment-card");
            if (salaryCard) {
                salaryCard.classList.toggle("positive", data.salary_adjustment_class === "positive");
                salaryCard.classList.toggle("warning", data.salary_adjustment_class === "warning");
                salaryCard.classList.toggle("danger", data.salary_adjustment_class === "danger");
            }

            const trendText = document.getElementById("trendText");
            trendText.textContent = data.trend;
            trendText.className = data.trend_class;

            window.history.replaceState({}, "", url);

            const anomaliesLink = document.getElementById("anomaliesLink");
            if (anomaliesLink) {
                anomaliesLink.href = `/analytics/anomalies/?month=${data.selected_month}`;
            }

            const anomaliesCard = document.getElementById("anomaliesCard");
            if (anomaliesCard) {
                anomaliesCard.classList.toggle("has-anomalies", data.anomalies > 0);
                anomaliesCard.classList.toggle("no-anomalies", data.anomalies <= 0);
            }

            const anomaliesIcon = document.getElementById("anomaliesIcon");
            if (anomaliesIcon) {
                anomaliesIcon.className = data.anomalies > 0 ? "fas fa-exclamation-triangle" : "fas fa-check-circle";
            }

            const anomaliesHint = document.getElementById("anomaliesHint");
            if (anomaliesHint) {
                anomaliesHint.hidden = data.anomalies <= 0;
            }

        } catch (error) {
            console.error(error);
            alert("Could not load analytics for this month.");
        } finally {
            setLoading(false);
        }
    });
});
