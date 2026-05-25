function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

function escapeHTML(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showStaffFeedback(message) {
    const feedback = document.getElementById("staffFeedback");
    if (!feedback) return;

    feedback.hidden = false;
    feedback.querySelector("span").textContent = message;

    setTimeout(() => {
        feedback.hidden = true;
    }, 2600);
}

function showStaffError(message) {
    showInfo(message, {
        title: "Staff Management",
        status: "danger"
    });
}

function confirmStaffAction(message, onConfirm, options = {}) {
    showConfirm(message, onConfirm, {
        title: options.title || "Confirm Staff Action",
        status: options.status || "default",
        confirmText: options.confirmText || "Confirm"
    });
}

function updateHrCount(count) {
    const counter = document.getElementById("hrCount");
    if (counter && count !== undefined) {
        counter.textContent = count;
    }
}

function emptyHrMessageHTML() {
    return '<p class="empty-message" id="emptyHrMessage">No HR accounts have been created yet.</p>';
}

function hrCardHTML(hr) {
    const stateClass = hr.is_active ? "active" : "suspended";
    const stateIcon = hr.is_active ? "fa-circle-check" : "fa-ban";
    const stateLabel = hr.is_active ? "Active" : "Suspended";
    const toggleIcon = hr.is_active ? "fa-ban" : "fa-circle-check";
    const toggleLabel = hr.is_active ? "Suspend" : "Activate";
    const suspendedClass = hr.is_active ? "" : " is-suspended";
    const username = escapeHTML(hr.username);
    const email = escapeHTML(hr.email || "No email");

    return `
        <article class="staff-card${suspendedClass}" data-hr-id="${hr.id}" data-search="${escapeHTML(`${hr.username} ${hr.email || ""} HR ${stateLabel}`)}">
            <div class="staff-card-header">
                <div>
                    <strong class="hr-username">${username}</strong>
                    <span class="hr-email">${email}</span>
                </div>
                <div class="staff-badges">
                    <span class="role-badge"><i class="fas fa-id-badge"></i> HR</span>
                    <span class="state-badge ${stateClass}"><i class="fas ${stateIcon}"></i> ${stateLabel}</span>
                </div>
            </div>

            <form method="POST" class="staff-form compact-form" hidden>
                <input type="hidden" name="action" value="update_hr">
                <input type="hidden" name="hr_id" value="${hr.id}">

                <div class="inline-grid">
                    <div>
                        <label for="hr_username_${hr.id}">Username</label>
                        <input id="hr_username_${hr.id}" type="text" name="username" value="${username}" maxlength="150" required>
                    </div>
                    <div>
                        <label for="hr_email_${hr.id}">Email</label>
                        <input id="hr_email_${hr.id}" type="email" name="email" value="${email === "No email" ? "" : email}" required>
                    </div>
                    <div>
                        <label for="hr_password_${hr.id}">New Password</label>
                        <input id="hr_password_${hr.id}" type="password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')" name="password" placeholder="Leave blank to keep">
                    </div>
                    <div>
                        <label for="hr_confirm_${hr.id}">Confirm Password</label>
                        <input id="hr_confirm_${hr.id}" type="password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')" name="confirm_password" placeholder="Leave blank to keep">
                    </div>
                </div>

                <div class="staff-actions">
                    <button type="submit" class="primary-btn small-btn">
                        <i class="fas fa-save"></i> Save Changes
                    </button>
                    <button type="button" class="secondary-btn cancel-edit-btn">
                        <i class="fas fa-times"></i> Cancel
                    </button>
                </div>
            </form>

            <div class="staff-actions split-actions">
                <button type="button" class="secondary-btn edit-hr-btn">
                    <i class="fas fa-pen"></i> Edit
                </button>

                <form method="POST" class="toggle-hr-form">
                    <input type="hidden" name="action" value="toggle_hr">
                    <input type="hidden" name="hr_id" value="${hr.id}">
                    <button type="submit" class="secondary-btn toggle-hr-btn">
                        <i class="fas ${toggleIcon}"></i> ${toggleLabel}
                    </button>
                </form>

                <form method="POST" class="delete-hr-form">
                    <input type="hidden" name="action" value="delete_hr">
                    <input type="hidden" name="hr_id" value="${hr.id}">
                    <button type="submit" class="danger-btn">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </form>
            </div>
        </article>
    `;
}

function replaceHrCard(hr) {
    const card = document.querySelector(`.staff-card[data-hr-id="${hr.id}"]`);
    if (!card) return;

    card.outerHTML = hrCardHTML(hr);
    attachStaffCardEvents(document.querySelector(`.staff-card[data-hr-id="${hr.id}"]`));
    applyHrSearch();
}

function attachStaffCardEvents(card) {
    if (!card) return;

    const editButton = card.querySelector(".edit-hr-btn");
    const editForm = card.querySelector(".compact-form");
    const actionRow = card.querySelector(".split-actions");
    const cancelButton = card.querySelector(".cancel-edit-btn");
    const toggleForm = card.querySelector(".toggle-hr-form");
    const deleteForm = card.querySelector(".delete-hr-form");

    if (editButton && editForm && actionRow) {
        editButton.onclick = function () {
            editForm.hidden = false;
            actionRow.hidden = true;
        };
    }

    if (cancelButton && editForm && actionRow) {
        cancelButton.onclick = function () {
            editForm.reset();
            editForm.hidden = true;
            actionRow.hidden = false;
        };
    }

    if (editForm) {
        editForm.onsubmit = function (e) {
            e.preventDefault();
            submitStaffForm(editForm, function (data) {
                replaceHrCard(data.hr);
                showStaffFeedback(data.message);
            });
        };
    }

    if (toggleForm) {
        toggleForm.onsubmit = function (e) {
            e.preventDefault();

            const isActive = !card.classList.contains("is-suspended");
            const username = card.querySelector(".hr-username")?.textContent || "this HR account";
            const action = isActive ? "suspend" : "activate";

            confirmStaffAction(
                `Are you sure you want to ${action} ${username}?`,
                function () {
                    submitStaffForm(toggleForm, function (data) {
                        replaceHrCard(data.hr);
                        showStaffFeedback(data.message);
                    });
                },
                {
                    title: isActive ? "Suspend HR Account" : "Activate HR Account",
                    status: isActive ? "danger" : "default",
                    confirmText: isActive ? "Suspend" : "Activate"
                }
            );
        };
    }

    if (deleteForm) {
        deleteForm.onsubmit = function (e) {
            e.preventDefault();

            const username = card.querySelector(".hr-username")?.textContent || "this HR account";

            confirmStaffAction(
                `Delete ${username} permanently? This cannot be undone.`,
                function () {
                    submitStaffForm(deleteForm, function (data) {
                        card.remove();
                        updateHrCount(data.hr_count);

                        const list = document.getElementById("hrList");
                        if (list && !list.querySelector(".staff-card")) {
                            list.innerHTML = emptyHrMessageHTML();
                        }

                        showStaffFeedback(data.message);
                        applyHrSearch();
                    });
                },
                {
                    title: "Delete HR Account",
                    status: "danger",
                    confirmText: "Delete"
                }
            );
        };
    }
}

function submitStaffForm(form, onSuccess) {
    const button = form.querySelector('button[type="submit"]');
    const oldContent = button ? button.innerHTML : "";

    if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving';
    }

    fetch(window.location.href, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken(),
            "X-Requested-With": "XMLHttpRequest"
        },
        body: new FormData(form)
    })
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
            if (!ok || !data.success) {
                throw new Error(data.error || "Could not save changes.");
            }

            onSuccess(data);
        })
        .catch(error => {
            showStaffError(error.message || "Could not save changes.");
        })
        .finally(() => {
            if (button) {
                button.disabled = false;
                button.innerHTML = oldContent;
            }
        });
}

function attachCreateHrForm() {
    const form = document.getElementById("createHrForm");
    if (!form) return;

    form.onsubmit = function (e) {
        e.preventDefault();

        submitStaffForm(form, function (data) {
            const list = document.getElementById("hrList");
            const emptyMessage = document.getElementById("emptyHrMessage");

            if (emptyMessage) emptyMessage.remove();

            if (list) {
                list.insertAdjacentHTML("beforeend", hrCardHTML(data.hr));
                attachStaffCardEvents(list.lastElementChild);
            }

            updateHrCount(data.hr_count);
            form.reset();
            showStaffFeedback(data.message);
            applyHrSearch();
        });
    };
}

function applyHrSearch() {
    const input = document.getElementById("hrSearchInput");
    const empty = document.getElementById("hrSearchEmpty");
    const cards = Array.from(document.querySelectorAll(".staff-card"));

    if (!input) return;

    const query = input.value.trim().toLowerCase();
    let visibleCount = 0;

    cards.forEach(card => {
        const matches = !query || (card.dataset.search || card.textContent).toLowerCase().includes(query);
        card.style.display = matches ? "" : "none";
        if (matches) visibleCount += 1;
    });

    if (empty) {
        empty.hidden = visibleCount > 0 || cards.length === 0;
    }
}

document.addEventListener("DOMContentLoaded", function () {
    loadInfoModal();
    loadConfirmModal();

    attachCreateHrForm();
    document.querySelectorAll(".staff-card").forEach(attachStaffCardEvents);
    document.getElementById("hrSearchInput")?.addEventListener("input", applyHrSearch);
    applyHrSearch();
});
