document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("analyticsSearchInput");
    if (!input) return;

    const empty = document.getElementById(input.dataset.emptyTarget || "");

    function applySearch() {
        const rows = Array.from(document.querySelectorAll(input.dataset.searchTarget || ""));
        const query = input.value.trim().toLowerCase();
        let visibleCount = 0;

        rows.forEach(row => {
            const matches = !query || (row.dataset.search || row.textContent).toLowerCase().includes(query);
            row.style.display = matches ? "" : "none";
            if (matches) visibleCount += 1;
        });

        if (empty) {
            empty.hidden = visibleCount > 0 || rows.length === 0;
        }
    }

    window.applyAnalyticsTableSearch = applySearch;
    input.addEventListener("input", applySearch);
    applySearch();
});
