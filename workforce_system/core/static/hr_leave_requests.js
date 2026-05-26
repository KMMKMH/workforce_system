document.addEventListener("DOMContentLoaded", () => {
    const list = document.getElementById("pendingLeaveList");
    const approvedList = document.getElementById("approvedLeaveList");
    const messageBar = document.getElementById("leaveMessage");
    const count = document.getElementById("pendingLeaveCount");

    function csrfToken() {
        const input = document.querySelector("[name=csrfmiddlewaretoken]");
        if (input) return input.value;

        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function showMessage(message, isError = false) {
        if (!messageBar) return;
        messageBar.textContent = message;
        messageBar.classList.toggle("error", isError);
        messageBar.hidden = false;
    }

    function showEmptyIfNeeded() {
        if (!list || list.querySelector(".request-card")) return;
        list.innerHTML = '<p class="empty-message" id="emptyPending">No pending leave requests.</p>';
    }

    function escapeHTML(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function prependApproved(approved) {
        if (!approvedList || !approved) return;

        const empty = document.getElementById("emptyApproved");
        if (empty) empty.remove();

        approvedList.insertAdjacentHTML("afterbegin", `
            <article class="request-card approved-card">
                <div class="request-main">
                    <strong>${escapeHTML(approved.username)}</strong>
                    <span>${escapeHTML(approved.date)} - approved by ${escapeHTML(approved.reviewed_by)}</span>
                </div>
                <span class="status-pill">Approved</span>
            </article>
        `);
    }

    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-leave-action]");
        if (!button) return;

        const card = button.closest(".request-card");
        const leaveId = card ? card.dataset.leaveId : "";
        const action = button.dataset.leaveAction;
        if (!leaveId || !action) return;

        const buttons = card.querySelectorAll("button");
        buttons.forEach((item) => item.disabled = true);

        try {
            const formData = new FormData();
            formData.append("leave_id", leaveId);
            formData.append("action", action);

            const response = await fetch(button.dataset.url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: formData,
            });
            const data = await response.json();

            if (!response.ok || !data.success) {
                showMessage(data.error || "Could not update leave request.", true);
                buttons.forEach((item) => item.disabled = false);
                return;
            }

            card.remove();
            if (count) count.textContent = data.pending_count;
            prependApproved(data.approved);
            showMessage(data.message);
            showEmptyIfNeeded();
        } catch (error) {
            showMessage("Could not update leave request.", true);
            buttons.forEach((item) => item.disabled = false);
        }
    });
});
