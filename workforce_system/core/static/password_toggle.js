function initPasswordToggles(root = document) {
    root.querySelectorAll('input[type="password"], input[data-password-visible="true"]').forEach(input => {
        if (input.hidden || input.dataset.passwordToggleReady === "true") return;

        input.dataset.passwordToggleReady = "true";

        const wrapper = document.createElement("div");
        wrapper.className = "password-toggle-wrap";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "password-visibility-toggle";
        button.setAttribute("aria-label", "Show password");
        button.setAttribute("title", "Show password");
        button.innerHTML = '<i class="fas fa-eye"></i>';

        button.addEventListener("click", function () {
            const isVisible = input.type === "text";
            input.type = isVisible ? "password" : "text";
            input.dataset.passwordVisible = isVisible ? "false" : "true";
            button.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
            button.setAttribute("title", isVisible ? "Show password" : "Hide password");
            button.innerHTML = isVisible
                ? '<i class="fas fa-eye"></i>'
                : '<i class="fas fa-eye-slash"></i>';
        });

        wrapper.appendChild(button);
    });
}

document.addEventListener("DOMContentLoaded", function () {
    initPasswordToggles();

    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    initPasswordToggles(node);
                }
            });
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});
