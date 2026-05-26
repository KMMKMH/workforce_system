document.addEventListener("DOMContentLoaded", () => {
    const messages = document.getElementById("messages");
    const form = document.getElementById("messageForm");
    const bodyInput = document.getElementById("messageBody");
    const errorBox = document.getElementById("chatError");
    let messagesRefreshInFlight = false;
    let unreadRefreshInFlight = false;

    function csrfToken() {
        const tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
        return tokenInput ? tokenInput.value : "";
    }

    function escapeHTML(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function scrollToBottom() {
        if (messages) {
            messages.scrollTop = messages.scrollHeight;
        }
    }

    function renderMessage(message) {
        return `
            <article class="message ${message.is_own ? "own" : ""}" data-message-id="${message.id}">
                <div class="message-bubble">
                    <div class="message-meta">
                        <strong>${escapeHTML(message.sender)}</strong>
                        <span>${escapeHTML(message.created_at)}</span>
                    </div>
                    <p>${escapeHTML(message.body)}</p>
                </div>
            </article>
        `;
    }

    function selectedConversationItem() {
        const selectedId = document.body.dataset.selectedConversation;
        if (!selectedId) return null;
        return document.querySelector(`.conversation-item[data-conversation-id="${selectedId}"]`);
    }

    function updateLastMessagePreview(message) {
        if (!message) return;

        const item = selectedConversationItem();
        if (!item) return;

        const preview = item.querySelector(".last-message");
        if (!preview) return;

        const text = `${message.sender}: ${message.body}`.replace(/\s+/g, " ");
        preview.textContent = text.length > 42 ? `${text.slice(0, 39)}...` : text;
    }

    function setConversationUnread(item, hasUnread) {
        if (!item) return;

        item.classList.toggle("unread", hasUnread);
        const dot = item.querySelector(".chat-unread-dot");
        if (dot) {
            dot.hidden = !hasUnread;
        }
    }

    function updateConversationPreview(item, lastMessage) {
        if (!item || !lastMessage) return;

        const preview = item.querySelector(".last-message");
        if (preview) {
            preview.textContent = lastMessage.preview || "No messages yet";
        }
    }

    async function refreshUnreadStatus() {
        const statusUrl = document.body.dataset.unreadStatusUrl;
        if (!statusUrl || unreadRefreshInFlight) return;

        unreadRefreshInFlight = true;
        try {
            const response = await fetch(statusUrl, {
                cache: "no-store",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) return;

            const selectedId = document.body.dataset.selectedConversation;
            const data = await response.json();
            data.conversations.forEach((conversation) => {
                const item = document.querySelector(`.conversation-item[data-conversation-id="${conversation.id}"]`);
                if (!item) return;

                updateConversationPreview(item, conversation.last_message);
                setConversationUnread(item, String(conversation.id) !== selectedId && conversation.unread_count > 0);
            });
        } finally {
            unreadRefreshInFlight = false;
        }
    }

    function showError(message) {
        if (!errorBox) return;
        errorBox.textContent = message;
        errorBox.hidden = !message;
    }

    async function refreshMessages(keepPosition = false) {
        if (!messages || !messages.dataset.messagesUrl || messagesRefreshInFlight) return;

        messagesRefreshInFlight = true;
        try {
            const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
            const response = await fetch(messages.dataset.messagesUrl, {
                cache: "no-store",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });

            if (!response.ok) return;

            const data = await response.json();
            messages.innerHTML = data.messages.length
                ? data.messages.map(renderMessage).join("")
                : '<p class="empty-chat" id="emptyChat">No messages yet.</p>';

            if (data.messages.length) {
                updateLastMessagePreview(data.messages[data.messages.length - 1]);
            }
            setConversationUnread(selectedConversationItem(), false);

            if (!keepPosition || nearBottom) {
                scrollToBottom();
            }
        } finally {
            messagesRefreshInFlight = false;
        }
    }

    if (form && bodyInput) {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            showError("");

            const body = bodyInput.value.trim();
            if (!body) return;

            const submitButton = form.querySelector("button[type='submit']");
            submitButton.disabled = true;

            try {
                const formData = new FormData();
                formData.append("body", body);

                const response = await fetch(form.dataset.sendUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: formData,
                });
                const data = await response.json();

                if (!response.ok) {
                    showError(data.error || "Message could not be sent.");
                    return;
                }

                bodyInput.value = "";
                bodyInput.style.height = "";
                updateLastMessagePreview(data.message);
                setConversationUnread(selectedConversationItem(), false);
                await refreshMessages(false);
            } catch (error) {
                showError("Message could not be sent.");
            } finally {
                submitButton.disabled = false;
                bodyInput.focus();
            }
        });
    }

    if (bodyInput) {
        bodyInput.addEventListener("input", () => {
            bodyInput.style.height = "auto";
            bodyInput.style.height = `${Math.min(bodyInput.scrollHeight, 130)}px`;
        });
    }

    scrollToBottom();
    refreshUnreadStatus();
    if (messages) {
        window.setInterval(() => {
            refreshMessages(true);
            refreshUnreadStatus();
        }, 10000);
    }
    window.setInterval(refreshUnreadStatus, 5000);
});
