document.addEventListener("DOMContentLoaded", () => {
    const chatButton = document.querySelector(".chat-portal-btn[data-unread-status-url]");
    if (!chatButton) return;

    function setChatDot(hasUnread, unreadCount) {
        let dot = chatButton.querySelector(".portal-alert-dot");
        if (hasUnread && !dot) {
            dot = document.createElement("span");
            dot.className = "portal-alert-dot";
            chatButton.appendChild(dot);
        }

        if (!dot) return;

        dot.hidden = !hasUnread;
        dot.setAttribute("aria-label", `${unreadCount || 0} unread chats`);
    }

    async function refreshChatDot() {
        const response = await fetch(chatButton.dataset.unreadStatusUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) return;

        const data = await response.json();
        setChatDot(data.total_unread > 0, data.total_unread);
    }

    refreshChatDot();
    window.setInterval(refreshChatDot, 10000);
});
