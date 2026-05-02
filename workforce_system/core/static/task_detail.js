

function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

function attachTaskEvents() {
    document.querySelectorAll('.task-btn').forEach(btn => {
        btn.onclick = function (e) {
            const taskId = this.dataset.id;
            const status = this.dataset.status;
            updateTask(taskId, status);
        };
    });
}

function attachCommitForm() {
    const form = document.getElementById("commitForm");
    if (!form) return;

    const taskId = form.dataset.taskId;
    const textarea = document.getElementById("commitMessage");
    const commitList = document.getElementById("commitList");
    const errorBox = document.getElementById("commitError");
    const noCommitsText = document.getElementById("noCommitsText");

    form.onsubmit = function (e) {
        e.preventDefault();

        const message = textarea.value.trim();

        if (!message) {
            showError("Commit message cannot be empty.");
            return;
        }

        fetch(`/tasks/${taskId}/commit/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken()
            },
            body: new URLSearchParams({
                message: message
            })
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    hideError();

                    if (noCommitsText) {
                        noCommitsText.remove();
                    }

                    const commitHTML = `
                    <div class="commit-card" data-commit-id="${data.commit.id}">
                        <div class="commit-top">
                            <span class="commit-user"><i class="fas fa-user-circle"></i> ${data.commit.user}</span>
                            <span class="commit-date">
                                <i class="fas fa-clock"></i> ${data.commit.updated_at}
                                ${data.commit.edited ? '<span class="edited-label">(edited)</span>' : ''}
                            </span>
                        </div>
                        <p class="commit-message"></p>
                        <div class="commit-actions">
                            <button class="edit-commit-btn" data-commit-id="${data.commit.id}" title="Edit commit">
                                <i class="fas fa-edit"></i> Edit
                            </button>

                            <button class="delete-commit-btn" data-commit-id="${data.commit.id}" title="Delete commit">
                                <i class="fas fa-trash-alt"></i> Delete
                            </button>
                        </div>
                    </div>
                `;

                    commitList.insertAdjacentHTML("afterbegin", commitHTML);

                    const newCommit = commitList.firstElementChild;
                    newCommit.querySelector(".commit-message").textContent = data.commit.message;

                    textarea.value = "";
                    attachDeleteEvents();
                    attachEditEvents();
                } else {
                    showError(data.error || "Something went wrong.");
                }
            })
            .catch(() => {
                showError("Failed to save commit.");
            });
    }

    function showError(message) {
        errorBox.style.display = "block";
        errorBox.textContent = message;
    }

    function hideError() {
        errorBox.style.display = "none";
        errorBox.textContent = "";
    }
}

function enterEditMode(card) {
    const messageEl = card.querySelector(".commit-message");
    const actionsEl = card.querySelector(".commit-actions");
    const oldMessage = messageEl.textContent.trim();

    messageEl.innerHTML = `
        <textarea class="edit-commit-textarea">${oldMessage}</textarea>
    `;

    actionsEl.innerHTML = `
        <button class="save-edit-commit-btn" title="Save changes">
            <i class="fas fa-save"></i> Save
        </button>

        <button class="cancel-edit-commit-btn" title="Cancel edit">
            <i class="fas fa-times"></i> Cancel
        </button>
    `;

    const textarea = card.querySelector(".edit-commit-textarea");
    textarea.focus();

    card.querySelector(".save-edit-commit-btn").onclick = function () {
        const newMessage = textarea.value.trim();

        if (!newMessage) {
            showInfo(
                "Commit message cannot be empty.",
                {
                    title: "Edit Commit Error",
                    status: "danger",
                }
            );
            return;
        }

        const commitId = card.dataset.commitId;
        editCommit(commitId, newMessage);
    };

    card.querySelector(".cancel-edit-commit-btn").onclick = function () {
        exitEditMode(card, oldMessage);
    };
}

function exitEditMode(card, message) {
    const messageEl = card.querySelector(".commit-message");
    const actionsEl = card.querySelector(".commit-actions");
    const commitId = card.dataset.commitId;

    messageEl.textContent = message;

    actionsEl.innerHTML = `
        <button class="edit-commit-btn" data-commit-id="${commitId}" title="Edit commit">
            <i class="fas fa-edit"></i> Edit
        </button>

        <button class="delete-commit-btn" data-commit-id="${commitId}" title="Delete commit">
            <i class="fas fa-trash-alt"></i> Delete
        </button>
    `;

    attachEditEvents();
    attachDeleteEvents();
}

function editCommit(commitId, newMessage) {
    fetch(`/commits/${commitId}/edit/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken()
        },
        body: new URLSearchParams({
            message: newMessage
        })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const card = document.querySelector(`[data-commit-id="${commitId}"]`);
                const messageEl = card.querySelector(".commit-message");
                const dateEl = card.querySelector(".commit-date");

                messageEl.textContent = data.commit.message;

                dateEl.innerHTML = `
                    <i class="fas fa-clock"></i> ${data.commit.updated_at}
                    ${data.commit.edited ? '<span class="edited-label">(edited)</span>' : ''}
                `;

                exitEditMode(card, data.commit.message);
            } else {
                showInfo(
                    data.error || "Could not edit commit.",
                    {
                        title: "Edit Commit Error",
                        status: "danger",
                    }
                );
            }
        })
        .catch(() => {
            showInfo(
                "Failed to edit commit.",
                {
                    title: "Edit Commit Error",
                    status: "danger",
                }
            );
        });
}

function deleteCommit(commitId) {
    fetch(`/commits/${commitId}/delete/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken()
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                removeCommitFromUI(commitId);
            } else {
                showInfo(
                    data.error,
                    {
                        title: "Delete Commit Error",
                        status: "danger",
                    }
                );
            }
        });
}

function attachEditEvents() {
    document.querySelectorAll('.edit-commit-btn').forEach(btn => {
        btn.onclick = function (e) {
            e.stopPropagation();

            const commitId = this.dataset.commitId;
            const card = document.querySelector(`[data-commit-id="${commitId}"]`);

            enterEditMode(card);
        };
    });
}

function attachDeleteEvents() {
    document.querySelectorAll('.delete-commit-btn').forEach(btn => {
        btn.onclick = function (e) {
            e.stopPropagation();

            const commitId = this.dataset.commitId;

            showConfirm(
                "Are you sure you want to delete this commit?",
                () => {
                    deleteCommit(commitId);
                },
                {
                    title: "Delete Commit",
                    status: "danger",
                    confirmText: "Delete"
                }
            );
        };
    });
}

function removeCommitFromUI(commitId) {
    const card = document.querySelector(`[data-commit-id="${commitId}"]`);
    if (card) {
        card.remove();
    }
}

function updateTask(taskId, newStatus) {
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
                updateTaskUI(taskId, newStatus);
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

function updateTaskUI(taskId, status) {
    const statusText = document.querySelector(`.task-status`);
    const commitDiv = document.getElementById(`commitFormContainer`);
    const actionsDiv = document.querySelector('.task-actions');
    const commitActionsDiv = document.querySelectorAll('.commit-actions');

    let html = "";
    let commit = `
        <div class="read-only-box">
            <i class="fas fa-lock"></i> You can only add commits when this task is <strong>IN_PROGRESS</strong> and assigned to you.
        </div>
    `;
    let showCommitActions = false;

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

        commit = `
            <form id="commitForm" class="commit-form" data-task-id="${taskId}">
                <textarea
                    id="commitMessage"
                    name="message"
                    placeholder="Write what you worked on..."
                    required
                ></textarea>
                <button type="submit"><i class="fas fa-save"></i> Save Commit</button>
            </form>
        `;

        showCommitActions = true;
    }

    else if (status === "READY") {
        html = `
            <span>⏳ Waiting for review</span>
            <button class="task-btn task-cancel" data-id="${taskId}" data-status="IN_PROGRESS">
                ↩ Cancel Review
            </button>
        `;
    }

    else if (status === "REVIEW") {
        html = `<span>📋 Under review by manager</span>`;
    }

    else if (status === "DONE") {
        html = `<span>✅ Completed</span>`;
    }

    actionsDiv.innerHTML = html;
    statusText.className = `task-status status-${status.toLowerCase()}`
    statusText.textContent = status;
    commitDiv.innerHTML = commit;
    commitActionsDiv.forEach((actionsEl) => {
        const card = actionsEl.closest(".commit-card");
        const commitId = card.dataset.commitId;

        if (showCommitActions) {
            actionsEl.innerHTML = `
            <button class="edit-commit-btn" data-commit-id="${commitId}" title="Edit commit">
                <i class="fas fa-edit"></i> Edit
            </button>

            <button class="delete-commit-btn" data-commit-id="${commitId}" title="Delete commit">
                <i class="fas fa-trash-alt"></i> Delete
            </button>
        `;
        } else {
            actionsEl.innerHTML = "";
        }
    });

    attachTaskEvents();
    attachCommitForm();
    attachDeleteEvents();
    attachEditEvents();
}

document.addEventListener('DOMContentLoaded', function () {
    attachDeleteEvents();
    attachEditEvents();
    attachCommitForm();
    attachTaskEvents();
    loadConfirmModal();
    loadInfoModal();
});