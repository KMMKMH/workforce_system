document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("anomalySearchInput");
    if (!input) return;

    const groups = Array.from(document.querySelectorAll(".anomaly-search-group"));
    const summaries = Array.from(document.querySelectorAll(".employee-summary-item, .manager-summary-item"));
    const empty = document.getElementById("anomalySearchEmpty");

    function applySearch() {
        const query = input.value.trim().toLowerCase();
        let visibleGroups = 0;

        groups.forEach(group => {
            const matches = !query || (group.dataset.search || group.textContent).toLowerCase().includes(query);
            group.style.display = matches ? "" : "none";
            if (matches) visibleGroups += 1;
        });

        summaries.forEach(summary => {
            const matches = !query || (summary.dataset.search || summary.textContent).toLowerCase().includes(query);
            summary.style.display = matches ? "" : "none";
        });

        if (empty) {
            empty.hidden = visibleGroups > 0 || groups.length === 0;
        }
    }

    input.addEventListener("input", applySearch);
    applySearch();
});
