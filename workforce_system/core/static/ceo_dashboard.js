function clockOut() {
    showConfirm(
        "Are you sure you want to log out?",
        () => {
            window.location.href = "/face/verify/?mode=logout";
        },
        {
            title: "Logout",
            status: "danger",
            confirmText: "Logout"
        }
    );
}

function updateClock() {
    const now = new Date();
    const clockSpan = document.getElementById("clock");
    if (clockSpan) {
        clockSpan.innerText = now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        });
    }
}

setInterval(updateClock, 1000);
updateClock();

function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

function updateCount(id, difference) {
    const el = document.getElementById(id);
    if (!el) return;

    const current = parseInt(el.textContent, 10) || 0;
    el.textContent = Math.max(0, current + difference);
}

function buildCeoActions(taskId, status) {
    if (status === "READY") {
        return `
            <button type="button" class="task-btn task-review" data-id="${taskId}" data-status="REVIEW">📋 Review</button>
            <button type="button" class="task-btn task-ready" data-id="${taskId}" data-status="DONE">✅ Done</button>
            <button type="button" class="task-btn task-cancel" data-id="${taskId}" data-status="IN_PROGRESS">↩ Send Back</button>
        `;
    }

    if (status === "REVIEW") {
        return `
            <button type="button" class="task-btn task-ready" data-id="${taskId}" data-status="DONE">✅ Done</button>
            <button type="button" class="task-btn task-cancel" data-id="${taskId}" data-status="IN_PROGRESS">↩ Send Back</button>
        `;
    }

    if (status === "DONE") {
        return "<span>✅ Completed</span>";
    }

    return "<span>⏳ Waiting on manager</span>";
}

function updateManagerTask(taskId, newStatus) {
    const card = document.querySelector(`.ceo-task-card[data-id="${taskId}"]`);
    const oldStatus = card?.dataset.status;

    fetch("/tasks/update/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken()
        },
        body: JSON.stringify({
            task_id: taskId,
            status: newStatus
        })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateManagerTaskUI(taskId, oldStatus, newStatus);
            } else {
                showInfo(data.error || "Could not update task.", {
                    title: "Update Task Error",
                    status: "danger"
                });
            }
        })
        .catch(() => {
            showInfo("Failed to update task.", {
                title: "Update Task Error",
                status: "danger"
            });
        });
}

function updateManagerTaskUI(taskId, oldStatus, newStatus) {
    const card = document.querySelector(`.ceo-task-card[data-id="${taskId}"]`);
    if (!card) return;

    card.dataset.status = newStatus;

    const statusText = card.querySelector(".task-status-text");
    if (statusText) statusText.textContent = newStatus;

    const actionsDiv = card.querySelector(".task-actions");
    const editLink = actionsDiv?.querySelector(".icon-link[href]");
    const deleteButton = actionsDiv?.querySelector(".delete-task-btn");

    if (actionsDiv) {
        actionsDiv.innerHTML = buildCeoActions(taskId, newStatus);
        if (editLink) actionsDiv.appendChild(editLink);
        if (deleteButton) actionsDiv.appendChild(deleteButton);
    }

    if (oldStatus === "READY" && newStatus !== "READY") updateCount("readyTasksCount", -1);
    if (oldStatus !== "READY" && newStatus === "READY") updateCount("readyTasksCount", 1);

    if (oldStatus !== "DONE" && newStatus === "DONE") {
        updateCount("openTasksCount", -1);
        updateCount("completedTasksCount", 1);
        moveTaskToCompleted(card);
    } else if (oldStatus === "DONE" && newStatus !== "DONE") {
        updateCount("openTasksCount", 1);
        updateCount("completedTasksCount", -1);
    }

    attachTaskEvents();
}

function moveTaskToCompleted(card) {
    const completedBlock = document.getElementById("completedTasksBlock");
    if (!completedBlock) {
        card.remove();
        return;
    }

    const emptyText = completedBlock.querySelector(".empty-message");
    if (emptyText) emptyText.remove();

    card.classList.add("completed-task-card");
    completedBlock.appendChild(card);
}

function deleteManagerTask(taskId) {
    const card = document.querySelector(`.ceo-task-card[data-id="${taskId}"]`);
    const oldStatus = card?.dataset.status;

    fetch(`/ceo/tasks/${taskId}/delete/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken()
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (oldStatus === "DONE") {
                    updateCount("completedTasksCount", -1);
                } else {
                    updateCount("openTasksCount", -1);
                    if (oldStatus === "READY") updateCount("readyTasksCount", -1);
                }

                if (card) card.remove();
            } else {
                showInfo(data.error || "Could not delete task.", {
                    title: "Delete Task Error",
                    status: "danger"
                });
            }
        })
        .catch(() => {
            showInfo("Failed to delete task.", {
                title: "Delete Task Error",
                status: "danger"
            });
        });
}

function attachTaskEvents() {
    document.querySelectorAll(".task-btn[data-id][data-status]").forEach(btn => {
        btn.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();

            const taskId = this.dataset.id;
            const status = this.dataset.status;

            if (status === "DONE" || status === "IN_PROGRESS") {
                const isDone = status === "DONE";

                showConfirm(
                    isDone
                        ? "Are you sure you want to mark this manager task as done?"
                        : "Are you sure you want to send this task back to the manager?",
                    () => updateManagerTask(taskId, status),
                    {
                        title: isDone ? "Complete Task" : "Send Back Task",
                        status: isDone ? "success" : "warning",
                        confirmText: isDone ? "Mark Done" : "Send Back"
                    }
                );

                return;
            }

            updateManagerTask(taskId, status);
        };
    });

    document.querySelectorAll(".delete-task-btn").forEach(btn => {
        btn.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();

            const taskId = this.dataset.id;

            showConfirm(
                "Are you sure you want to delete this task?",
                () => deleteManagerTask(taskId),
                {
                    title: "Delete Task",
                    status: "danger",
                    confirmText: "Delete"
                }
            );
        };
    });
}

function attachCompletedToggle() {
    const btn = document.getElementById("toggleCompletedBtn");
    const block = document.getElementById("completedTasksBlock");

    if (!btn || !block) return;

    btn.onclick = function () {
        const isHidden = block.classList.toggle("hidden-completed");
        btn.innerHTML = isHidden
            ? btn.innerHTML.replace("Hide", "Show").replace("fa-eye-slash", "fa-eye")
            : btn.innerHTML.replace("Show", "Hide").replace("fa-eye", "fa-eye-slash");
    };
}

document.addEventListener("DOMContentLoaded", function () {
    loadInfoModal();
    loadConfirmModal();
    attachTaskEvents();
    attachCompletedToggle();
});
