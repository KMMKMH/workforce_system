from datetime import timedelta, datetime, time
from django.utils import timezone
from core.models import Attendance, Holiday, LeaveRequest, TaskCommit

THRESHOLD_HOURS = 7
MAX_HOURS = 12

def is_holiday(date):
    return Holiday.objects.filter(date=date).exists()

def is_weekend(date):
    return date.weekday() in [5, 6]

def is_approved_leave(user, date):
    return LeaveRequest.objects.filter(
        user=user,
        date=date,
        status=LeaveRequest.APPROVED
    ).exists()

def auto_fix_attendance(user):
    if user.role in ['CEO', 'HR', 'ACCOUNTANT']: return
    today = timezone.now().date()

    last_record = (
        Attendance.objects
        .filter(user=user, date__lte=today)
        .order_by('-date')
        .first()
    )

    if not last_record:
        start_date = user.date_joined.date()
    else:
        start_date = last_record.date
        handle_no_checkout(user, last_record)

    current_date = start_date + timedelta(days=1)

    while current_date < today:

        exists = Attendance.objects.filter(
            user=user,
            date=current_date
        ).exists()

        if not exists:
            if is_approved_leave(user, current_date):
                status = "LEAVE"
            elif is_holiday(current_date) or is_weekend(current_date):
                status = "HOLIDAY"
            else:
                status = "ABSENT"

            Attendance.objects.create(
                user=user,
                date=current_date,
                status=status
            )

        current_date += timedelta(days=1)

def handle_no_checkout(user, last_record):
    if user.role in ['CEO', 'HR', 'ACCOUNTANT']: return
    today = timezone.now().date()
    
    if last_record.date == today or last_record.check_out or not last_record.check_in:
        return

    local_tz = timezone.get_current_timezone()

    day_end = timezone.make_aware(
        datetime.combine(last_record.date, time.max),
        local_tz
    )

    last_commit = TaskCommit.objects.filter(
        user=last_record.user,
        created_at__gte=last_record.check_in,
        created_at__lte=day_end
    ).order_by("-created_at").first()

    if last_commit:
        last_record.check_out = last_commit.created_at
        delta = last_record.check_out - last_record.check_in
        session_hours = delta.total_seconds() / 3600

        if last_record.worked_hours:
            last_record.worked_hours += session_hours
        else:
            last_record.worked_hours = session_hours
    else:
        last_record.check_out = day_end

    last_record.is_anomaly = True
    last_record.anomaly_reason = "Missing check-out record (auto-closed by system)"

    last_record.save()


def handle_check_in(user):
    if user.role in ['CEO', 'HR', 'ACCOUNTANT']: return
    today = timezone.now().date()
    now = timezone.now()

    attendance, created = Attendance.objects.get_or_create(
        user=user,
        date=today
    )

    if attendance.check_in and not attendance.check_out:
        return attendance

    if attendance.check_in and attendance.check_out:
        attendance.check_out = None

    attendance.check_in = now

    if not attendance.worked_hours:
        attendance.worked_hours == 0

    if is_holiday(today) or is_weekend(today):
        attendance.status = "WORKING_HOLIDAY"
    elif not attendance.status:
        attendance.status = "PRESENT"

    attendance.save()

    return attendance


def handle_check_out(user):
    if user.role in ['CEO', 'HR', 'ACCOUNTANT']: return
    today = timezone.now().date()
    now = timezone.now()

    try:
        attendance = Attendance.objects.get(user=user, date=today)
    except Attendance.DoesNotExist:
        return None

    if not attendance.check_in:
        return None

    if attendance.check_out:
        return attendance

    attendance.check_out = now

    delta = attendance.check_out - attendance.check_in
    session_hours = delta.total_seconds() / 3600

    if attendance.worked_hours:
        attendance.worked_hours += session_hours
    else:
        attendance.worked_hours = session_hours

    attendance.worked_hours = round(attendance.worked_hours, 2)
    attendance.is_anomaly = False
    attendance.anomaly_reason = ""

    if attendance.worked_hours > MAX_HOURS:
        attendance.is_anomaly = True
        attendance.anomaly_reason = f"Excessive working hours: {attendance.worked_hours}h (limit: {MAX_HOURS}h)"

    if attendance.status in ["LEAVE", "WORKING_HOLIDAY"]:
        attendance.save()
        return attendance

    if attendance.worked_hours >= THRESHOLD_HOURS:
        attendance.status = "PRESENT"
    else:
        attendance.status = "LOW_HOURS"
        attendance.is_anomaly = True
        attendance.anomaly_reason = f"Insufficient working hours: {attendance.worked_hours}h (minimum required: {THRESHOLD_HOURS}h)"

    attendance.save()
    return attendance
