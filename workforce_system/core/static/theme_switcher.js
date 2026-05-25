(function () {
    const storageKey = "workforceTheme";
    const validThemes = ["dark", "light"];

    function getSavedTheme() {
        const saved = localStorage.getItem(storageKey);
        return validThemes.includes(saved) ? saved : "dark";
    }

    function applyTheme(theme) {
        const selectedTheme = validThemes.includes(theme) ? theme : "dark";

        document.documentElement.dataset.theme = selectedTheme;
        localStorage.setItem(storageKey, selectedTheme);
        document.cookie = `${storageKey}=${selectedTheme}; path=/; max-age=31536000; SameSite=Lax`;

        document.querySelectorAll("[data-theme-link]").forEach(link => {
            const href = selectedTheme === "light"
                ? link.dataset.lightTheme
                : link.dataset.darkTheme;

            if (href && link.getAttribute("href") !== href) {
                link.setAttribute("href", href);
            }
        });

        document.querySelectorAll("[data-theme-toggle]").forEach(button => {
            const icon = button.querySelector("i");
            const text = button.querySelector(".theme-toggle-text");
            const isLight = selectedTheme === "light";

            button.classList.toggle("is-light", isLight);
            button.setAttribute("aria-pressed", String(isLight));

            if (icon) {
                icon.className = isLight ? "fas fa-sun" : "fas fa-moon";
            }

            if (text) {
                text.textContent = isLight ? "Light" : "Dark";
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(getSavedTheme());

        document.querySelectorAll("[data-theme-toggle]").forEach(button => {
            button.addEventListener("click", function () {
                const currentTheme = document.documentElement.dataset.theme || getSavedTheme();
                applyTheme(currentTheme === "light" ? "dark" : "light");
            });
        });
    });
})();
