document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    const calendarData = document.getElementsByClassName('data')[0];
    const calendarEvents = JSON.parse(calendarData.innerText);

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        events: calendarEvents,
        weekends: true,

        dayCellClassNames: function (arg) {
            const day = arg.date.getDay();

            if (day === 0 || day === 6) {
                return ['weekend-cell'];
            }

            return [];
        },
        eventDidMount: function (info) {
            info.el.setAttribute('title', info.event.title);
            info.el.setAttribute('aria-label', info.event.title);
        }
    });

    calendar.render();
});
