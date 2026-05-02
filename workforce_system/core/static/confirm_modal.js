let confirmCallback = null;

function showConfirm(message, onConfirm, options = {}) {
    const modal = document.getElementById("confirmModal");
    const modalBox = document.getElementById("confirmModalBox");

    const title = options.title || "Confirm";
    const status = options.status || "default";
    const confirmText = options.confirmText || "Confirm";

    document.getElementById("confirmModalTitle").textContent = title;
    document.getElementById("confirmModalMessage").textContent = message;
    document.getElementById("confirmModalConfirmBtn").textContent = confirmText;

    modalBox.className = "confirm-modal-box " + status;

    confirmCallback = onConfirm;

    modal.classList.remove("hidden");
}

function closeConfirmModal() {
    confirmCallback = null;
    document.getElementById("confirmModal").classList.add("hidden");
}

function loadConfirmModal() {
    document.getElementById("confirmModalConfirmBtn").onclick = function () {
        if (confirmCallback) confirmCallback();
        closeConfirmModal();
    };

    document.getElementById("confirmModalCancelBtn").onclick = closeConfirmModal;

    document.querySelector(".confirm-modal-overlay").onclick = closeConfirmModal;
}