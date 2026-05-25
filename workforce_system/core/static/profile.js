function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

function updateBiometricUI(enabled) {
    const status = document.getElementById("biometricStatus");
    const button = document.getElementById("biometricToggleBtn");

    if (status) {
        status.className = enabled ? "status enabled" : "status disabled";
        status.innerHTML = enabled
            ? '<i class="fas fa-check-circle"></i> Enabled'
            : '<i class="fas fa-times-circle"></i> Disabled';
    }

    if (button) {
        button.className = enabled
            ? "btn biometric-toggle-btn toggle-disable"
            : "btn biometric-toggle-btn toggle-enable";
        button.innerHTML = enabled
            ? '<i class="fas fa-toggle-off"></i> Disable'
            : '<i class="fas fa-toggle-on"></i> Enable';
    }
}

function attachBiometricToggle() {
    const form = document.getElementById("biometricToggleForm");
    const button = document.getElementById("biometricToggleBtn");

    if (!form || !button) return;

    form.onsubmit = function (e) {
        e.preventDefault();
        button.disabled = true;

        fetch(window.location.href, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: new FormData(form)
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    updateBiometricUI(data.biometric_enabled);
                }
            })
            .finally(() => {
                button.disabled = false;
            });
    };
}

function attachProfileInfoForm() {
    const form = document.getElementById("profileInfoForm");
    const feedback = document.getElementById("profileFormFeedback");
    const button = form?.querySelector('button[type="submit"]');

    if (!form || !button) return;

    form.onsubmit = function (e) {
        e.preventDefault();
        button.disabled = true;
        const oldContent = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving';
        if (feedback) {
            feedback.classList.remove("error");
            feedback.textContent = "";
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
                    throw new Error(data.error || "Could not save profile.");
                }

                if (feedback) {
                    feedback.textContent = "Saved";
                }

                setTimeout(() => {
                    if (feedback) feedback.textContent = "";
                }, 1800);
            })
            .catch((error) => {
                if (feedback) {
                    feedback.classList.add("error");
                    feedback.textContent = error.message || "Could not save";
                }
            })
            .finally(() => {
                button.disabled = false;
                button.innerHTML = oldContent;
            });
    };
}

function isValidCVFile(file) {
    const allowedExtensions = [".pdf", ".doc", ".docx"];
    const allowedTypes = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ];
    const lowerName = file.name.toLowerCase();

    return allowedExtensions.some(ext => lowerName.endsWith(ext)) && allowedTypes.includes(file.type);
}

function updateCVLink(url) {
    const current = document.getElementById("cvCurrent");
    if (!current) return;

    current.innerHTML = `
        <a href="${url}" target="_blank" class="btn secondary" id="cvViewLink">
            <i class="fas fa-file-pdf"></i> View CV
        </a>
    `;
}

function attachCVUploadForm() {
    const form = document.getElementById("cvUploadForm");
    const input = document.getElementById("cvInput");
    const selected = document.getElementById("cvSelected");
    const feedback = document.getElementById("cvFormFeedback");
    const button = document.getElementById("cvSaveBtn");

    if (!form || !input || !button) return;

    input.onchange = function () {
        const file = input.files[0];

        if (!file) {
            if (selected) selected.textContent = "No document selected";
            return;
        }

        if (!isValidCVFile(file)) {
            input.value = "";
            if (selected) selected.textContent = "No document selected";
            showInfo("Please choose a valid CV document: PDF, DOC, or DOCX.", {
                title: "Invalid CV",
                status: "danger"
            });
            return;
        }

        if (selected) selected.textContent = file.name;
    };

    form.onsubmit = function (e) {
        e.preventDefault();

        const file = input.files[0];
        if (!file || !isValidCVFile(file)) {
            showInfo("Please choose a valid CV document before saving.", {
                title: "Invalid CV",
                status: "danger"
            });
            return;
        }

        button.disabled = true;
        const oldContent = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving CV';
        if (feedback) {
            feedback.classList.remove("error");
            feedback.textContent = "";
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
                    throw new Error(data.error || "Could not save CV.");
                }

                updateCVLink(data.cv_url);
                input.value = "";
                if (selected) selected.textContent = "No document selected";
                if (feedback) feedback.textContent = "CV saved";

                setTimeout(() => {
                    if (feedback) feedback.textContent = "";
                }, 1800);
            })
            .catch((error) => {
                showInfo(error.message || "Could not save CV.", {
                    title: "CV Upload Error",
                    status: "danger"
                });
                if (feedback) {
                    feedback.classList.add("error");
                    feedback.textContent = "Could not save";
                }
            })
            .finally(() => {
                button.disabled = false;
                button.innerHTML = oldContent;
            });
    };
}

document.addEventListener("DOMContentLoaded", function () {
    loadInfoModal();
    attachProfileInfoForm();
    attachBiometricToggle();
    attachCVUploadForm();
});
