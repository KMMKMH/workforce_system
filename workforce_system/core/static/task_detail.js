

function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

function canUploadImagesForStatus(status) {
    const role = document.body.dataset.imageRole;

    if (role === "assigner") {
        return status === "PENDING" || status === "REVIEW";
    }

    if (role === "assignee") {
        return status === "IN_PROGRESS";
    }

    return false;
}

function updateImageUploadVisibility(status) {
    const form = document.getElementById("taskImageForm");
    if (!form) return;

    form.classList.toggle("hidden-upload", !canUploadImagesForStatus(status));
}

function imageCardHTML(image) {
    return `
        <button type="button" class="task-image-card" data-full="${image.url}" data-image-id="${image.id}">
            <img src="${image.url}" alt="Task screenshot">
            <span class="delete-image-btn" data-image-id="${image.id}" title="Delete screenshot">
                <i class="fas fa-times"></i>
            </span>
            <span class="image-meta">
                <span class="image-user"><i class="fas fa-user"></i> ${image.uploaded_by}</span>
                <span class="image-date"><i class="fas fa-calendar-alt"></i> ${image.uploaded_at}</span>
            </span>
        </button>
    `;
}

function emptyTextForCarousel(carousel) {
    if (carousel?.id === "assignerImageCarousel") {
        return '<p class="empty-text"><i class="fas fa-folder-open"></i> No assigner screenshots yet.</p>';
    }

    return '<p class="empty-text"><i class="fas fa-folder-open"></i> No assignee screenshots yet.</p>';
}

function attachImagePreviewEvents() {
    const lightbox = document.getElementById("imageLightbox");
    const lightboxImage = document.getElementById("lightboxImage");
    const closeButton = document.getElementById("lightboxClose");

    document.querySelectorAll(".task-image-card[data-full]").forEach(card => {
        card.onclick = function () {
            if (!lightbox || !lightboxImage) return;

            lightboxImage.src = this.dataset.full;
            lightbox.classList.add("is-open");
            lightbox.setAttribute("aria-hidden", "false");
        };
    });

    document.querySelectorAll(".delete-image-btn").forEach(btn => {
        btn.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();
            const imageId = this.dataset.imageId;

            showConfirm(
                "Are you sure you want to delete this screenshot?",
                () => deleteTaskImage(imageId),
                {
                    title: "Delete Screenshot",
                    status: "danger",
                    confirmText: "Delete"
                }
            );
        };
    });

    if (closeButton) {
        closeButton.onclick = closeImageLightbox;
    }

    if (lightbox) {
        lightbox.onclick = function (e) {
            if (e.target === lightbox) closeImageLightbox();
        };
    }
}

function deleteTaskImage(imageId) {
    fetch(`/tasks/images/${imageId}/delete/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken()
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const card = document.querySelector(`.task-image-card[data-image-id="${imageId}"]`);
                if (card) {
                    const carousel = card.closest(".screenshot-carousel");
                    card.remove();

                    if (carousel && !carousel.querySelector(".task-image-card")) {
                        carousel.innerHTML = emptyTextForCarousel(carousel);
                    }
                }
            } else {
                showInfo(data.error || "Could not delete screenshot.", {
                    title: "Delete Screenshot",
                    status: "danger"
                });
            }
        })
        .catch(() => {
            showInfo("Failed to delete screenshot.", {
                title: "Delete Screenshot",
                status: "danger"
            });
        });
}

function closeImageLightbox() {
    const lightbox = document.getElementById("imageLightbox");
    const lightboxImage = document.getElementById("lightboxImage");

    if (!lightbox || !lightboxImage) return;

    lightbox.classList.remove("is-open");
    lightbox.setAttribute("aria-hidden", "true");
    lightboxImage.src = "";
}

function attachImageUploadForm() {
    const form = document.getElementById("taskImageForm");
    const input = document.getElementById("taskImagesInput");

    if (!form || !input) return;

    input.onchange = function () {
        if (!input.files.length) return;

        const formData = new FormData();
        Array.from(input.files).forEach(file => {
            formData.append("images", file);
        });

        fetch(`/tasks/${form.dataset.taskId}/images/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken()
            },
            body: formData
        })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    showInfo(data.error || "Could not upload screenshots.", {
                        title: "Upload Screenshots",
                        status: "danger"
                    });
                    return;
                }

                const targetId = form.dataset.targetRole === "assigner"
                    ? "assignerImageCarousel"
                    : "assigneeImageCarousel";
                const carousel = document.getElementById(targetId);

                if (carousel) {
                    const emptyText = carousel.querySelector(".empty-text");
                    if (emptyText) emptyText.remove();

                    data.images.forEach(image => {
                        carousel.insertAdjacentHTML("afterbegin", imageCardHTML(image));
                    });
                    attachImagePreviewEvents();
                }

                input.value = "";
            })
            .catch(() => {
                showInfo("Failed to upload screenshots.", {
                    title: "Upload Screenshots",
                    status: "danger"
                });
            });
    };
}

function attachTaskEvents() {
    document.querySelectorAll('.task-btn[data-id][data-status]').forEach(btn => {
        btn.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();

            const taskId = this.dataset.id;
            const status = this.dataset.status;

            if (
                document.body.dataset.canManage === "true" &&
                (status === "DONE" || status === "IN_PROGRESS")
            ) {
                const isDone = status === "DONE";

                showConfirm(
                    isDone
                        ? "Are you sure you want to mark this task as done?"
                        : `Are you sure you want to send this task back to the ${document.body.dataset.reviewSubject || "employee"}?`,
                    () => updateTask(taskId, status),
                    {
                        title: isDone ? "Complete Task" : "Send Back Task",
                        status: isDone ? "success" : "warning",
                        confirmText: isDone ? "Mark Done" : "Send Back"
                    }
                );

                return;
            }

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
                if (document.body.dataset.canManage === "true") {
                    updateManagerTaskUI(taskId, newStatus);
                    return;
                }
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

function buildManagerTaskActions(taskId, status) {
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
        return `<span>✅ Completed</span>`;
    }

    return `<span>⏳ Waiting on ${document.body.dataset.reviewSubject || "employee"}</span>`;
}

function updateManagerTaskUI(taskId, status) {
    const statusText = document.querySelector(".task-status");
    const actionsDiv = document.querySelector(".task-actions");
    const editLink = actionsDiv?.querySelector('a[href*="/manager/tasks/"], a[href*="/ceo/tasks/"]');

    if (statusText) {
        statusText.className = `task-status status-${status.toLowerCase()}`;
        statusText.textContent = status;
    }
    updateImageUploadVisibility(status);

    if (actionsDiv) {
        actionsDiv.innerHTML = buildManagerTaskActions(taskId, status);
        if (editLink) actionsDiv.appendChild(editLink);
    }

    attachTaskEvents();
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
            <button type="button" class="task-btn task-start" data-id="${taskId}" data-status="IN_PROGRESS">
                ▶ Start Task
            </button>
        `;
    }

    else if (status === "IN_PROGRESS") {
        html = `
            <button type="button" class="task-btn task-ready" data-id="${taskId}" data-status="READY">
                ✅ Mark as Ready
            </button>
            <button type="button" class="task-btn task-cancel" data-id="${taskId}" data-status="PENDING">
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
            <button type="button" class="task-btn task-cancel" data-id="${taskId}" data-status="IN_PROGRESS">
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
    updateImageUploadVisibility(status);
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
    attachImageUploadForm();
    attachImagePreviewEvents();
    updateImageUploadVisibility(document.querySelector(".task-status")?.textContent.trim());
    loadConfirmModal();
    loadInfoModal();
});
