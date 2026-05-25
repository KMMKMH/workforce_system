document.addEventListener("DOMContentLoaded", function () {
    const calendarEl = document.getElementById("calendar");
    const calendarData = document.getElementsByClassName("data")[0];
    const calendarEvents = JSON.parse(calendarData.innerText);

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: "dayGridMonth",
        events: calendarEvents,
        weekends: true,
        dayCellClassNames: function (arg) {
            const day = arg.date.getDay();

            if (day === 0 || day === 6) {
                return ["weekend-cell"];
            }

            return [];
        },
        eventDidMount: function (info) {
            const props = info.event.extendedProps || {};
            const hoverText = props.is_anomaly
                ? `${props.user}: ${props.anomaly_reason}`
                : props.user && props.status
                ? `${props.user}: ${props.status}`
                : info.event.title;

            info.el.setAttribute("title", hoverText.trim());
            info.el.setAttribute("aria-label", hoverText.trim());
        }
    });

    calendar.render();
});
