function showInfo(message, options = {}) {
    const modal = document.getElementById("infoModal");
    const modalBox = document.getElementById("infoModalBox");

    const title = options.title || "Info";
    const status = options.status || "default";

    document.getElementById("infoModalTitle").textContent = title;
    document.getElementById("infoModalMessage").textContent = message;

    modalBox.className = "info-modal-box " + status;

    modal.classList.remove("hidden");
}

function closeInfoModal() {
    document.getElementById("infoModal").classList.add("hidden");
}

function loadInfoModal() {
    document.getElementById("infoModalCloseBtn").onclick = closeInfoModal;
    document.querySelector(".info-modal-overlay").onclick = closeInfoModal;
}