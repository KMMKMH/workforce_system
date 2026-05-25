function getCSRFToken() {
    return document.cookie.split("; ").find(row => row.startsWith("csrftoken="))?.split("=")[1];
}

function escapeHTML(value) {
    return String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function showStaffFeedback(message) {
    const feedback = document.getElementById("staffFeedback");
    if (!feedback) return;
    feedback.hidden = false;
    feedback.querySelector("span").textContent = message;
    setTimeout(() => feedback.hidden = true, 2600);
}

function showStaffError(message) {
    showInfo(message, { title: "Staff Management", status: "danger" });
}

function confirmStaffAction(message, onConfirm, options = {}) {
    showConfirm(message, onConfirm, {
        title: options.title || "Confirm Staff Action",
        status: options.status || "default",
        confirmText: options.confirmText || "Confirm"
    });
}

function managerOptions(selectedId) {
    const managers = window.hrManagers || [];
    return '<option value="">No manager</option>' + managers.map(manager => {
        const selected = String(selectedId || "") === String(manager.id) ? "selected" : "";
        return `<option value="${manager.id}" ${selected}>${escapeHTML(manager.username)}</option>`;
    }).join("");
}

function userCardHTML(user) {
    const stateClass = user.is_active ? "active" : "suspended";
    const stateIcon = user.is_active ? "fa-circle-check" : "fa-ban";
    const stateLabel = user.is_active ? "Active" : "Suspended";
    const toggleIcon = user.is_active ? "fa-ban" : "fa-circle-check";
    const toggleLabel = user.is_active ? "Suspend" : "Activate";
    const suspendedClass = user.is_active ? "" : " is-suspended";
    const roleEmployeeSelected = user.role === "EMPLOYEE" ? "selected" : "";
    const roleManagerSelected = user.role === "MANAGER" ? "selected" : "";

    return `
        <article class="staff-card${suspendedClass}" data-user-id="${user.id}" data-search="${escapeHTML(`${user.username} ${user.email || ""} ${user.role_label} ${user.department} ${user.position} ${user.manager_name || "No manager"}`)}">
            <div class="staff-card-header">
                <div>
                    <strong class="staff-username">${escapeHTML(user.username)}</strong>
                    <span class="staff-email">${escapeHTML(user.email || "No email")}</span>
                    <span>${escapeHTML(user.position || "-")}${user.department ? `, ${escapeHTML(user.department)}` : ""}</span>
                    <span>Manager: <span class="staff-manager-name">${escapeHTML(user.manager_name || "No manager")}</span></span>
                </div>
                <div class="staff-badges">
                    <span class="role-badge"><i class="fas fa-id-badge"></i> <span class="staff-role-label">${escapeHTML(user.role_label)}</span></span>
                    <span class="state-badge ${stateClass}"><i class="fas ${stateIcon}"></i> ${stateLabel}</span>
                </div>
            </div>
            <form method="POST" class="staff-form compact-form" hidden>
                <input type="hidden" name="action" value="update_staff">
                <input type="hidden" name="user_id" value="${user.id}">
                <div class="inline-grid">
                    <div><label>Username</label><input type="text" name="username" value="${escapeHTML(user.username)}" maxlength="150" required></div>
                    <div><label>Email</label><input type="email" name="email" value="${escapeHTML(user.email || "")}" required></div>
                    <div><label>Role</label><select name="role" required><option value="EMPLOYEE" ${roleEmployeeSelected}>Employee</option><option value="MANAGER" ${roleManagerSelected}>Manager</option></select></div>
                    <div><label>Phone</label><input type="text" name="phone" value="${escapeHTML(user.phone)}"></div>
                    <div><label>Department</label><input type="text" name="department" value="${escapeHTML(user.department)}"></div>
                    <div><label>Position</label><input type="text" name="position" value="${escapeHTML(user.position)}"></div>
                    <div><label>Salary</label><input type="number" step="0.01" name="salary" value="${escapeHTML(user.salary)}"></div>
                    <div><label>Manager</label><select name="manager">${managerOptions(user.manager_id)}</select></div>
                    <div><label>New Password</label><input type="password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')" name="password" placeholder="Leave blank to keep"></div>
                    <div><label>Confirm Password</label><input type="password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')" name="confirm_password" placeholder="Leave blank to keep"></div>
                </div>
                <div class="staff-actions"><button type="submit" class="primary-btn small-btn"><i class="fas fa-save"></i> Save Changes</button><button type="button" class="secondary-btn cancel-edit-btn"><i class="fas fa-times"></i> Cancel</button></div>
            </form>
            <div class="staff-actions split-actions">
                <button type="button" class="secondary-btn edit-staff-btn"><i class="fas fa-pen"></i> Edit</button>
                <form method="POST" class="toggle-staff-form"><input type="hidden" name="action" value="toggle_staff"><input type="hidden" name="user_id" value="${user.id}"><button type="submit" class="secondary-btn toggle-staff-btn"><i class="fas ${toggleIcon}"></i> ${toggleLabel}</button></form>
                <form method="POST" class="delete-staff-form"><input type="hidden" name="action" value="delete_staff"><input type="hidden" name="user_id" value="${user.id}"><button type="submit" class="danger-btn"><i class="fas fa-trash"></i> Delete</button></form>
            </div>
        </article>
    `;
}

function updateStaffCount(count) {
    const counter = document.getElementById("staffCount");
    if (counter && count !== undefined) counter.textContent = count;
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
        headers: { "X-CSRFToken": getCSRFToken(), "X-Requested-With": "XMLHttpRequest" },
        body: new FormData(form)
    })
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
            if (!ok || !data.success) throw new Error(data.error || "Could not save changes.");
            onSuccess(data);
        })
        .catch(error => showStaffError(error.message || "Could not save changes."))
        .finally(() => {
            if (button) {
                button.disabled = false;
                button.innerHTML = oldContent;
            }
        });
}

function replaceStaffCard(user) {
    const card = document.querySelector(`.staff-card[data-user-id="${user.id}"]`);
    if (!card) return;
    card.outerHTML = userCardHTML(user);
    attachStaffCardEvents(document.querySelector(`.staff-card[data-user-id="${user.id}"]`));
    applyStaffSearch();
}

function attachStaffCardEvents(card) {
    if (!card) return;
    const editButton = card.querySelector(".edit-staff-btn");
    const editForm = card.querySelector(".compact-form");
    const actionRow = card.querySelector(".split-actions");
    const cancelButton = card.querySelector(".cancel-edit-btn");
    const toggleForm = card.querySelector(".toggle-staff-form");
    const deleteForm = card.querySelector(".delete-staff-form");

    editButton.onclick = () => {
        editForm.hidden = false;
        actionRow.hidden = true;
    };
    cancelButton.onclick = () => {
        editForm.reset();
        editForm.hidden = true;
        actionRow.hidden = false;
    };
    editForm.onsubmit = e => {
        e.preventDefault();
        submitStaffForm(editForm, data => {
            replaceStaffCard(data.user);
            showStaffFeedback(data.message);
        });
    };
    toggleForm.onsubmit = e => {
        e.preventDefault();
        const isActive = !card.classList.contains("is-suspended");
        const username = card.querySelector(".staff-username")?.textContent || "this account";
        confirmStaffAction(`Are you sure you want to ${isActive ? "suspend" : "activate"} ${username}?`, () => {
            submitStaffForm(toggleForm, data => {
                replaceStaffCard(data.user);
                showStaffFeedback(data.message);
            });
        }, { title: isActive ? "Suspend Account" : "Activate Account", status: isActive ? "danger" : "default", confirmText: isActive ? "Suspend" : "Activate" });
    };
    deleteForm.onsubmit = e => {
        e.preventDefault();
        const username = card.querySelector(".staff-username")?.textContent || "this account";
        confirmStaffAction(`Delete ${username} permanently? This cannot be undone.`, () => {
            submitStaffForm(deleteForm, data => {
                card.remove();
                updateStaffCount(data.staff_count);
                const list = document.getElementById("staffList");
                if (list && !list.querySelector(".staff-card")) {
                    list.innerHTML = '<p class="empty-message" id="emptyStaffMessage">No staff accounts have been created yet.</p>';
                }
                showStaffFeedback(data.message);
                applyStaffSearch();
            });
        }, { title: "Delete Account", status: "danger", confirmText: "Delete" });
    };
}

function applyStaffSearch() {
    const input = document.getElementById("staffSearchInput");
    const empty = document.getElementById("staffSearchEmpty");
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
    const createForm = document.getElementById("createStaffForm");
    if (createForm) {
        createForm.onsubmit = e => {
            e.preventDefault();
            submitStaffForm(createForm, data => {
                const list = document.getElementById("staffList");
                document.getElementById("emptyStaffMessage")?.remove();
                list.insertAdjacentHTML("beforeend", userCardHTML(data.user));
                attachStaffCardEvents(list.lastElementChild);
                updateStaffCount(data.staff_count);
                createForm.reset();
                showStaffFeedback(data.message);
                applyStaffSearch();
            });
        };
    }
    document.querySelectorAll(".staff-card").forEach(attachStaffCardEvents);
    document.getElementById("staffSearchInput")?.addEventListener("input", applyStaffSearch);
    applyStaffSearch();
});
