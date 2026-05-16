function clockOut() {
    showConfirm(
        "Are you sure you want to clock out?",
        () => {
            window.location.href = "/face/verify/?mode=logout";
        },
        {
            title: "Clock Out",
            status: "danger",
            confirmText: "Clock out"
        }
    );
}

function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const clockSpan = document.getElementById('clock');
    if (clockSpan) clockSpan.innerText = timeStr;
}

setInterval(updateClock, 1000);
updateClock();


function initLiveHours() {
    const display = document.getElementById("hours-display");

    if (!display) return;

    const checkInStr = display.dataset.checkin;
    const storedHours = parseFloat(display.dataset.stored) || 0;

    if (!checkInStr) {
        display.innerText = storedHours.toFixed(2) + " h";
        return;
    }

    const checkInTime = new Date(checkInStr);

    function updateHours() {
        const now = new Date();

        const diffMs = now - checkInTime;
        const diffHours = diffMs / (1000 * 60 * 60);

        const totalHours = storedHours + diffHours;

        display.innerText = totalHours.toFixed(2) + " h";
    }

    updateHours();
    setInterval(updateHours, 60000);
}

document.addEventListener("DOMContentLoaded", initLiveHours);


function updateTask(taskId, newStatus, isManager) {
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
            updateTaskUI(taskId, newStatus, isManager);
        } else {
            showInfo(
                data.error,
                {
                    title: "Update Task Error",
                    status: "danger",
                }
            );
        }
    });
}

function updateTaskUI(taskId, status, isManager) {
    const card = document.querySelector(`.task-card[data-id="${taskId}"]`);
    const actionsDiv = card.querySelector('.task-actions');

    let html = "";

    if (status === "PENDING") {
        html = `
            <button class="task-btn task-start" data-id="${taskId}" data-status="IN_PROGRESS">
                ▶ Start Task
            </button>
        `;
    }

    else if (status === "IN_PROGRESS") {
        html = `
            <button class="task-btn task-ready" data-id="${taskId}" data-status="READY">
                ✅ Mark as Ready
            </button>
            <button class="task-btn task-cancel" data-id="${taskId}" data-status="PENDING">
                ↩ Cancel Progress
            </button>
        `;
    }

    else if (status === "READY") {
        html = `
            <span>⏳ Waiting for review</span>
            <button class="task-btn task-cancel" data-id="${taskId}" data-status="IN_PROGRESS">
                ↩ Cancel Review
            </button>
        `;
    }

    else if (status === "REVIEW" && isManager) {
        html = `<span>📋 Under review by CEO</span>`;
    }

    else if (status === "REVIEW") {
        html = `<span>📋 Under review by manager</span>`;
    }

    else if (status === "DONE") {
        html = `<span>✅ Completed</span>`;
    }

    actionsDiv.innerHTML = html;

    const statusText = card.querySelector("p strong");
    statusText.textContent = status;

    attachTaskEvents();
}

function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken"))
        ?.split("=")[1];
}

function attachTaskEvents() {
    document.querySelectorAll('.task-btn').forEach(btn => {
        btn.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();
            const taskId = this.dataset.id;
            const status = this.dataset.status;
            const isManager= Boolean(this.dataset.manager)
            updateTask(taskId, status, isManager);
        };
    });
}

document.addEventListener('DOMContentLoaded', function () {
    attachTaskEvents();
    loadInfoModal();
    loadConfirmModal();
});