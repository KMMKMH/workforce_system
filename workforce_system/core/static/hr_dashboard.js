function updateClock() {
    const clock = document.getElementById("clock");
    if (!clock) return;

    const now = new Date();
    clock.textContent = now.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    });
}

function logOut() {
    window.location.href = "/";
}

function attendanceFilterLabel(value) {
    const labels = {
        ALL: "attendance records",
        ONLINE: "online staff",
        OFFLINE: "offline staff",
        PRESENT: "present staff",
        LOW_HOURS: "short-hours records",
        WORKING_HOLIDAY: "holiday overtime records"
    };

    return labels[value] || "attendance records";
}

function attachAttendanceFilter() {
    const select = document.getElementById("attendanceStatusFilter");
    const searchInput = document.getElementById("attendanceSearchInput");
    const rows = Array.from(document.querySelectorAll(".attendance-row"));
    const empty = document.getElementById("attendanceFilterEmpty");

    if (!select || !rows.length) return;

    function applyFilter() {
        const selected = select.value;
        const query = (searchInput?.value || "").trim().toLowerCase();
        let visibleCount = 0;

        rows.forEach(row => {
            const rowStatus = row.dataset.attendanceStatus;
            const isOnline = row.dataset.isOnline === "true";
            const matchesStatus =
                selected === "ALL" ||
                (selected === "ONLINE" && isOnline) ||
                rowStatus === selected;
            const matchesSearch = !query || (row.dataset.search || row.textContent).toLowerCase().includes(query);
            const shouldShow = matchesStatus && matchesSearch;

            row.hidden = !shouldShow;
            if (shouldShow) visibleCount += 1;
        });

        if (empty) {
            empty.hidden = visibleCount > 0;
            empty.textContent = query
                ? `No ${attendanceFilterLabel(selected)} matching "${query}"`
                : `No ${attendanceFilterLabel(selected)}`;
        }
    }

    select.addEventListener("change", applyFilter);
    searchInput?.addEventListener("input", applyFilter);
    applyFilter();
}

document.addEventListener("DOMContentLoaded", function () {
    updateClock();
    setInterval(updateClock, 1000);
    attachAttendanceFilter();
});
