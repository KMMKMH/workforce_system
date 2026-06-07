from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import localtime
from django.http import FileResponse, Http404, JsonResponse
from django.contrib.auth import authenticate, login
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import models
from django.db.models import Sum
from datetime import datetime, time, date, timedelta
from pathlib import Path
import mimetypes
import json, cv2, base64, ast, random, calendar
import numpy as np

from deepface import DeepFace
from core.utils.helpers import ensure_holidays_exist, get_head_turn_direction
from core.utils.attendance import auto_fix_attendance, handle_check_in, handle_check_out
from core.models import Attendance, ChatMessage, ChatParticipant, Conversation, LeaveRequest, PayrollAdjustment, Task, Holiday, TaskCommit, TaskImage, User
from core.data.display import STATUS_DISPLAY
from core.forms import EmployeeProfileForm, HRCreationForm, HRStaffCreationForm, HRStaffUpdateForm, HRUpdateForm, LeaveRequestForm, ManagerTaskForm, CEOTaskForm, PayrollBonusForm


def manager_team_queryset(manager):
    return manager.team_members.filter(user__role='EMPLOYEE').select_related('user')


def manager_team_users(manager):
    return [profile.user for profile in manager_team_queryset(manager)]


def manager_team_start_date(manager, today):
    team_users = manager_team_users(manager)

    if not team_users:
        return today

    return min(user.date_joined.date() for user in team_users)


def user_can_manage_task(user, task):
    return (
        user.role == 'MANAGER'
        and task.assigned_to.profile.manager_id == user.id
    )


def user_can_manage_manager_task(user, task):
    return (
        user.role == 'CEO'
        and task.assigned_to.role == 'MANAGER'
    )


def user_can_review_task(user, task):
    return user_can_manage_task(user, task) or user_can_manage_manager_task(user, task)


def user_can_upload_task_image(user, task):
    if user == task.assigned_by:
        return task.status in ["PENDING", "REVIEW"]

    if user == task.assigned_to:
        return task.status == "IN_PROGRESS"

    return False


def user_can_delete_task_image(user, task_image):
    return task_image.uploaded_by == user


def is_valid_cv_file(file):
    allowed_extensions = {".pdf", ".doc", ".docx"}
    allowed_content_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    extension = Path(file.name).suffix.lower()

    return extension in allowed_extensions and file.content_type in allowed_content_types


def manager_users_queryset():
    return User.objects.filter(
        role='MANAGER'
    ).order_by('username')


def hr_managed_users_queryset():
    return User.objects.filter(
        role__in=["MANAGER", "EMPLOYEE"]
    ).select_related("profile").order_by("role", "username")


def task_status_filter_options(selected_status):
    options = [{"value": "ACTIVE", "label": "Active Tasks"}]
    options.extend(
        {"value": value, "label": label}
        for value, label in Task.STATUS_CHOICES
    )

    for option in options:
        option["selected"] = option["value"] == selected_status

    return options


def selected_task_status_filter(request):
    selected_status = request.GET.get("status", "ACTIVE")
    valid_statuses = {value for value, _ in Task.STATUS_CHOICES}
    valid_statuses.add("ACTIVE")

    if selected_status not in valid_statuses:
        return "ACTIVE"

    return selected_status


def filter_tasks_by_status(tasks, selected_status):
    if selected_status == "ACTIVE":
        return tasks.exclude(status="DONE")

    return tasks.filter(status=selected_status)


def task_calendar_event(task, title):
    TASK_CALENDAR_STATUS_STYLES = {
        "PENDING": {"color": "#64748b"},
        "IN_PROGRESS": {"color": "#f97316"},
        "READY": {"color": "#0891b2"},
        "REVIEW": {"color": "#9333ea"},
        "DONE": {"color": "#0f766e"},
    }

    status_style = TASK_CALENDAR_STATUS_STYLES.get(task.status, {})
    deadline = localtime(task.deadline).strftime("%Y-%m-%dT%H:%M:%S")
    deadline_time = localtime(task.deadline).strftime("%H:%M")
    display = f"{deadline_time} {title}"

    return {
        "title": display,
        "start": deadline,
        "allDay": True,
        "extendedProps": {
            "title": title,
            "status": task.status
        },
        **status_style
    }


def direct_chat_contacts(user):
    active_users = User.objects.filter(
        is_active=True,
        role__in=["CEO", "HR", "MANAGER", "EMPLOYEE"]
    ).exclude(id=user.id).select_related("profile").order_by("role", "username")

    if user.role == "CEO":
        return active_users.filter(role__in=["HR", "MANAGER"])

    if user.role == "EMPLOYEE":
        contact_ids = list(User.objects.filter(role="HR", is_active=True).values_list("id", flat=True))
        if user.profile.manager_id:
            contact_ids.append(user.profile.manager_id)
        return active_users.filter(id__in=contact_ids)

    if user.role == "MANAGER":
        contact_ids = list(User.objects.filter(role__in=["CEO", "HR"], is_active=True).values_list("id", flat=True))
        contact_ids.extend(
            user.team_members.filter(user__role="EMPLOYEE", user__is_active=True).values_list("user_id", flat=True)
        )
        return active_users.filter(id__in=contact_ids)

    if user.role == "HR":
        return active_users

    return User.objects.none()


def users_can_direct_chat(user, other):
    if not user.is_active or not other.is_active:
        return False

    if user.role == "HR" or other.role == "HR":
        return True

    if user.role == "CEO":
        return other.role == "MANAGER"
    if other.role == "CEO":
        return user.role == "MANAGER"

    if user.role == "MANAGER" and other.role == "EMPLOYEE":
        return other.profile.manager_id == user.id
    if user.role == "EMPLOYEE" and other.role == "MANAGER":
        return user.profile.manager_id == other.id

    return False


def direct_conversation_for_users(user, contact):
    user_ids = sorted([user.id, contact.id])
    direct_key = f"{user_ids[0]}:{user_ids[1]}"
    conversation, _ = Conversation.objects.get_or_create(
        conversation_type=Conversation.DIRECT,
        direct_key=direct_key,
        defaults={"title": "Direct chat"}
    )
    ChatParticipant.objects.get_or_create(
        conversation=conversation,
        user=user,
        defaults={"last_seen_at": timezone.now()}
    )
    ChatParticipant.objects.get_or_create(
        conversation=conversation,
        user=contact,
        defaults={"last_seen_at": timezone.now()}
    )
    return conversation


def sync_team_conversation(manager):
    conversation, _ = Conversation.objects.get_or_create(
        conversation_type=Conversation.TEAM,
        team_manager=manager,
        defaults={"title": f"{manager.username}'s Team"}
    )
    ChatParticipant.objects.get_or_create(
        conversation=conversation,
        user=manager,
        defaults={"last_seen_at": timezone.now()}
    )

    current_participant_ids = {manager.id}
    for profile in manager.team_members.filter(user__role="EMPLOYEE", user__is_active=True).select_related("user"):
        ChatParticipant.objects.get_or_create(
            conversation=conversation,
            user=profile.user,
            defaults={"last_seen_at": timezone.now()}
        )
        current_participant_ids.add(profile.user_id)

    ChatParticipant.objects.filter(conversation=conversation).exclude(user_id__in=current_participant_ids).delete()
    return conversation


def sync_managers_conversation():
    ceo = User.objects.filter(role="CEO", is_active=True).order_by("id").first()
    if not ceo:
        return None

    conversation, _ = Conversation.objects.get_or_create(
        conversation_type=Conversation.TEAM,
        team_manager=ceo,
        defaults={"title": "Managers"}
    )

    current_participant_ids = {ceo.id}
    ChatParticipant.objects.get_or_create(
        conversation=conversation,
        user=ceo,
        defaults={"last_seen_at": timezone.now()}
    )

    for manager in User.objects.filter(role="MANAGER", is_active=True).order_by("username"):
        ChatParticipant.objects.get_or_create(
            conversation=conversation,
            user=manager,
            defaults={"last_seen_at": timezone.now()}
        )
        current_participant_ids.add(manager.id)

    ChatParticipant.objects.filter(conversation=conversation).exclude(user_id__in=current_participant_ids).delete()
    return conversation


def announcement_conversation():
    conversation, _ = Conversation.objects.get_or_create(
        conversation_type=Conversation.ANNOUNCEMENT,
        defaults={"title": "Announcements"}
    )
    for user in User.objects.filter(is_active=True, role__in=["CEO", "HR", "MANAGER", "EMPLOYEE"]):
        ChatParticipant.objects.get_or_create(
            conversation=conversation,
            user=user,
            defaults={"last_seen_at": timezone.now()}
        )
    return conversation


def ensure_chat_conversations(user):
    conversations = [announcement_conversation()]

    for contact in direct_chat_contacts(user):
        conversations.append(direct_conversation_for_users(user, contact))

    if user.role in ["CEO", "MANAGER"]:
        managers_conversation = sync_managers_conversation()
        if managers_conversation:
            conversations.append(managers_conversation)

    if user.role == "MANAGER":
        conversations.append(sync_team_conversation(user))
    elif user.role == "EMPLOYEE" and user.profile.manager_id:
        conversations.append(sync_team_conversation(user.profile.manager))

    return conversations


def user_can_access_conversation(user, conversation):
    if not conversation.participants.filter(id=user.id).exists():
        return False

    if conversation.conversation_type == Conversation.DIRECT:
        other = conversation.participants.exclude(id=user.id).first()
        return bool(other and users_can_direct_chat(user, other))

    return True


def user_can_send_chat_message(user, conversation):
    if not user_can_access_conversation(user, conversation):
        return False

    if conversation.conversation_type == Conversation.ANNOUNCEMENT:
        return user.role in ["CEO", "HR"]

    return True


def conversation_display_title(conversation, user):
    if conversation.conversation_type == Conversation.DIRECT:
        other = conversation.participants.exclude(id=user.id).first()
        return other.username if other else "Direct chat"

    return conversation.title


def conversation_subtitle(conversation, user):
    if conversation.conversation_type == Conversation.DIRECT:
        other = conversation.participants.exclude(id=user.id).select_related("profile").first()
        if not other:
            return "One on one"
        position = other.profile.position or other.get_role_display()
        return f"{other.get_role_display()} - {position}"

    if conversation.conversation_type == Conversation.TEAM:
        return "Team group chat"

    return "Company announcements"


def serialize_chat_message(message, user):
    return {
        "id": message.id,
        "body": message.body,
        "sender": message.sender.username,
        "is_own": message.sender_id == user.id,
        "created_at": localtime(message.created_at).strftime("%b %d, %H:%M"),
    }


def chat_participant_for(user, conversation):
    return ChatParticipant.objects.filter(conversation=conversation, user=user).first()


def unread_count_for_conversation(conversation, user):
    participant = chat_participant_for(user, conversation)
    if not participant:
        return 0

    unread_messages = conversation.messages.exclude(sender=user)
    if participant.last_seen_at:
        unread_messages = unread_messages.filter(created_at__gt=participant.last_seen_at)
    return unread_messages.count()


def mark_conversation_seen(conversation, user):
    ChatParticipant.objects.filter(
        conversation=conversation,
        user=user
    ).update(last_seen_at=timezone.now())


def user_chat_conversations(user):
    ensure_chat_conversations(user)
    conversations = list(
        Conversation.objects.filter(participants=user)
        .prefetch_related("participants")
        .order_by("-last_message_at", "conversation_type", "title")
        .distinct()
    )
    return [
        conversation for conversation in conversations
        if user_can_access_conversation(user, conversation)
    ]


def unread_chat_count(user):
    return sum(
        1 for conversation in user_chat_conversations(user)
        if unread_count_for_conversation(conversation, user) > 0
    )


def chat_last_message_payload(conversation, user):
    last_message = conversation.messages.select_related("sender").order_by("-created_at").first()
    if not last_message:
        return {
            "sender": "",
            "body": "No messages yet",
            "preview": "No messages yet",
        }

    preview = f"{last_message.sender.username}: {' '.join(last_message.body.split())}"
    return {
        "sender": last_message.sender.username,
        "body": last_message.body,
        "preview": preview[:39] + "..." if len(preview) > 42 else preview,
    }


def apply_approved_leave_request(leave_request):
    leave_end = leave_request.end_date or leave_request.date
    holidays = set(
        Holiday.objects.filter(
            date__gte=leave_request.date,
            date__lte=leave_end
        ).values_list("date", flat=True)
    )
    cursor = leave_request.date
    attendance_rows = []

    while cursor <= leave_end:
        if cursor.weekday() < 5 and cursor not in holidays:
            attendance, _ = Attendance.objects.get_or_create(
                user=leave_request.user,
                date=cursor
            )
            attendance.status = "LEAVE"
            attendance.is_anomaly = False
            attendance.anomaly_reason = ""
            attendance.save()
            attendance_rows.append(attendance)

        cursor += timedelta(days=1)

    return attendance_rows


def leave_period_display(leave_request, date_format="%b %d, %Y"):
    leave_end = leave_request.end_date or leave_request.date
    start = leave_request.date.strftime(date_format)
    end = leave_end.strftime(date_format)

    if leave_request.date == leave_end:
        return start

    return f"{start} - {end}"


def leave_calendar_event(leave_request, title):
    leave_end = leave_request.end_date or leave_request.date
    return {
        "title": title,
        "start": leave_request.date.strftime("%Y-%m-%d"),
        "end": (leave_end + timedelta(days=1)).strftime("%Y-%m-%d"),
        "allDay": True,
        "color": "#3B82F6",
        "extendedProps": {
            "title": title,
            "status": leave_period_display(leave_request),
        },
    }


@login_required
def chat_view(request):
    conversations = user_chat_conversations(request.user)

    selected_conversation = None
    selected_id = request.GET.get("conversation")
    if selected_id:
        selected_conversation = next(
            (conversation for conversation in conversations if str(conversation.id) == selected_id),
            None
        )
    if not selected_conversation and conversations:
        selected_conversation = next(
            (conversation for conversation in conversations if user_can_send_chat_message(request.user, conversation)),
            conversations[0]
        )

    messages = []
    if selected_conversation:
        mark_conversation_seen(selected_conversation, request.user)
        messages = selected_conversation.messages.select_related("sender").order_by("created_at")

    conversation_rows = []
    for conversation in conversations:
        last_message = conversation.messages.select_related("sender").order_by("-created_at").first()
        conversation_rows.append({
            "conversation": conversation,
            "title": conversation_display_title(conversation, request.user),
            "subtitle": conversation_subtitle(conversation, request.user),
            "last_message": last_message,
            "is_selected": selected_conversation and conversation.id == selected_conversation.id,
            "unread_count": unread_count_for_conversation(conversation, request.user),
        })

    return render(request, "chat.html", {
        "conversation_rows": conversation_rows,
        "selected_conversation": selected_conversation,
        "selected_title": conversation_display_title(selected_conversation, request.user) if selected_conversation else "",
        "selected_subtitle": conversation_subtitle(selected_conversation, request.user) if selected_conversation else "",
        "messages": messages,
        "can_send": user_can_send_chat_message(request.user, selected_conversation) if selected_conversation else False,
    })


@login_required
def chat_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not user_can_access_conversation(request.user, conversation):
        return JsonResponse({"error": "You cannot access this chat."}, status=403)

    mark_conversation_seen(conversation, request.user)
    messages = conversation.messages.select_related("sender").order_by("created_at")
    return JsonResponse({
        "messages": [serialize_chat_message(message, request.user) for message in messages],
        "can_send": user_can_send_chat_message(request.user, conversation),
    })


@login_required
def chat_unread_status(request):
    conversations = user_chat_conversations(request.user)
    conversation_payload = []
    total_unread = 0

    for conversation in conversations:
        unread_count = unread_count_for_conversation(conversation, request.user)
        if unread_count:
            total_unread += 1

        last_message = chat_last_message_payload(conversation, request.user)
        conversation_payload.append({
            "id": conversation.id,
            "unread_count": unread_count,
            "last_message": last_message,
        })

    return JsonResponse({
        "total_unread": total_unread,
        "conversations": conversation_payload,
    })


@login_required
@require_POST
def chat_send_message(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not user_can_send_chat_message(request.user, conversation):
        return JsonResponse({"error": "You cannot send messages in this chat."}, status=403)

    body = request.POST.get("body", "").strip()
    if not body:
        return JsonResponse({"error": "Message cannot be empty."}, status=400)

    message = ChatMessage.objects.create(
        conversation=conversation,
        sender=request.user,
        body=body
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at"])
    mark_conversation_seen(conversation, request.user)

    return JsonResponse({
        "message": serialize_chat_message(message, request.user),
    })


def calculate_salary_adjustment(user, attendance, month_start, month_end):
    salary = float(user.profile.salary or 0)
    join_date = user.date_joined.date()
    rate_month_end = date(
        month_start.year,
        month_start.month,
        calendar.monthrange(month_start.year, month_start.month)[1]
    )
    holiday_dates = set(
        Holiday.objects.filter(
            date__gte=month_start,
            date__lte=rate_month_end
        ).values_list("date", flat=True)
    )
    leave_dates = set(
        attendance.filter(status="LEAVE").values_list("date", flat=True)
    )

    working_days = 0
    cursor = month_start
    while cursor <= rate_month_end:
        if cursor.weekday() < 5 and cursor not in holiday_dates and cursor not in leave_dates:
            working_days += 1
        cursor += timedelta(days=1)

    daily_rate = salary / working_days if salary and working_days else 0
    hourly_rate = daily_rate / 7 if daily_rate else 0

    pre_join_days = 0
    if month_start < join_date <= rate_month_end:
        cursor = month_start
        while cursor < join_date:
            if cursor.weekday() < 5 and cursor not in holiday_dates and cursor not in leave_dates:
                pre_join_days += 1
            cursor += timedelta(days=1)

    pre_join_deduction = pre_join_days * daily_rate
    absence_days = attendance.filter(status="ABSENT").count()
    absence_deduction = absence_days * daily_rate

    today = timezone.now().date()
    short_hours = 0
    for row in attendance.exclude(status__in=["ABSENT", "HOLIDAY", "WORKING_HOLIDAY", "LEAVE"]).exclude(date=today):
        worked_hours = row.worked_hours or 0
        short_hours += max(7 - worked_hours, 0)

    short_hours_deduction = short_hours * hourly_rate
    holiday_overtime_hours = attendance.filter(
        status__in=["WORKING_HOLIDAY", "LEAVE"]
    ).aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0
    holiday_overtime_addition = holiday_overtime_hours * hourly_rate
    bonus_total = PayrollAdjustment.objects.filter(
        user=user,
        adjustment_type=PayrollAdjustment.BONUS,
        month=month_start
    ).aggregate(Sum("amount"))["amount__sum"] or 0
    bonus_total = float(bonus_total)
    payroll_deduction_total = PayrollAdjustment.objects.filter(
        user=user,
        adjustment_type=PayrollAdjustment.DEDUCTION,
        month=month_start
    ).aggregate(Sum("amount"))["amount__sum"] or 0
    payroll_deduction_total = abs(float(payroll_deduction_total))

    deductions = pre_join_deduction + absence_deduction + short_hours_deduction + payroll_deduction_total
    additions = holiday_overtime_addition + bonus_total
    net_adjustment = additions - deductions
    net_pay = salary + net_adjustment

    if salary and net_pay < salary / 2:
        salary_status_class = "danger"
        salary_status_label = "Less than half of monthly salary"
    elif salary and net_pay < salary:
        salary_status_class = "warning"
        salary_status_label = "Below monthly salary"
    else:
        salary_status_class = "positive"
        salary_status_label = "Salary intact or above"

    return {
        "salary_monthly": round(salary, 2),
        "net_pay": round(net_pay, 2),
        "net_pay_display": f"${net_pay:.2f}",
        "salary_deductions": round(deductions, 2),
        "pre_join_deduction": round(pre_join_deduction, 2),
        "salary_additions": round(additions, 2),
        "holiday_overtime_addition": round(holiday_overtime_addition, 2),
        "bonus_total": round(bonus_total, 2),
        "payroll_deduction_total": round(payroll_deduction_total, 2),
        "salary_adjustment_total": round(net_adjustment, 2),
        "salary_adjustment_display": f"{'+' if net_adjustment >= 0 else '-'}${abs(net_adjustment):.2f}",
        "salary_adjustment_class": salary_status_class,
        "salary_adjustment_label": salary_status_label,
        "absence_days": absence_days,
        "short_hours": round(short_hours, 2),
        "holiday_overtime_hours": round(holiday_overtime_hours, 2),
        "daily_rate": round(daily_rate, 2),
        "hourly_rate": round(hourly_rate, 2),
        "expected_working_days": working_days,
        "pre_join_days": pre_join_days,
    }


def build_month_choices(join_date, today):
    month_cursor = date(today.year, today.month, 1)
    join_month = date(join_date.year, join_date.month, 1)
    months = []

    while month_cursor >= join_month:
        months.append({
            "value": month_cursor.strftime("%Y-%m"),
            "label": month_cursor.strftime("%B %Y"),
        })

        if month_cursor.month == 1:
            month_cursor = date(month_cursor.year - 1, 12, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month - 1, 1)

    return months, join_month


def parse_selected_month(request, join_month, today):
    selected_month = request.GET.get("month", today.strftime("%Y-%m"))

    try:
        selected_year, selected_month_number = map(int, selected_month.split("-"))
        selected_month_date = date(selected_year, selected_month_number, 1)
    except ValueError:
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")
        selected_month_date = date(selected_year, selected_month_number, 1)

    current_month = date(today.year, today.month, 1)

    if selected_month_date < join_month or selected_month_date > current_month:
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")

    month_start = date(selected_year, selected_month_number, 1)
    last_day = calendar.monthrange(selected_year, selected_month_number)[1]
    month_end = date(selected_year, selected_month_number, last_day)

    if selected_year == today.year and selected_month_number == today.month:
        month_end = today

    return selected_month, month_start, month_end


def month_datetime_bounds(month_start, month_end):
    month_start_datetime = timezone.make_aware(
        datetime.combine(month_start, time.min),
        timezone.get_current_timezone()
    )

    month_end_datetime = timezone.make_aware(
        datetime.combine(month_end, time.max),
        timezone.get_current_timezone()
    )

    return month_start_datetime, month_end_datetime


def format_attendance_time(value):
    return localtime(value).strftime("%H:%M") if value else "-"


def serialize_anomaly(anomaly):
    return {
        "date": anomaly.date.strftime("%b %d, %Y"),
        "status": anomaly.status,
        "status_class": anomaly.status.lower(),
        "check_in": format_attendance_time(anomaly.check_in),
        "check_out": format_attendance_time(anomaly.check_out),
        "worked_hours": round(anomaly.worked_hours or 0, 2),
        "reason": anomaly.anomaly_reason or "No reason provided.",
    }


def local_day_bounds(day=None):
    local_tz = timezone.get_current_timezone()
    day = day or timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(day, time.min), local_tz)
    next_day_start = day_start + timedelta(days=1)

    return day_start, next_day_start

def login_view(request):
    if request.user.is_authenticated:
        return redirect('face_verify')
    
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            request.session['verified'] = False
            auto_fix_attendance(user)
            ensure_holidays_exist()

            if not user.face_encoding:
                return redirect('face_register')
            else:
                return redirect('face_verify')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})

    return render(request, 'login.html')

@login_required
def face_register(request):
    if request.user.role in ['CEO', 'HR', 'ACCOUNTANT']:
        if not request.user.profile.biometric_enabled:
            return redirect('face_verify')

    if request.user.face_encoding:
        return redirect('face_verify')

    if request.method == 'POST':
        data = json.loads(request.body)
        image_data = data['image']
        step = data.get('step', 1)

        format, imgstr = image_data.split(';base64,')
        img_bytes = base64.b64decode(imgstr)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        turn_direction, last_direction = get_head_turn_direction(img)

        if turn_direction is None:
            return JsonResponse({
                'message': 'No face detected',
                'status': 'warning'
            })

        if step == 1:
            direction = random.choice(['LEFT', 'RIGHT'])
            request.session['direction'] = direction

            return JsonResponse({
                'message': f'Turn your head to the {direction}',
                'next_step': 2,
                'status': 'instruction'
            })

        elif step == 2:
            direction = request.session.get('direction')

            moved = (direction == turn_direction)
            if not moved:
                if last_direction == direction:
                    return JsonResponse({
                        'message': f'Hold still, the system is verifying...',
                        'next_step': 2,
                        'status': 'success'
                    })
                elif last_direction == 'CENTER': 
                    return JsonResponse({
                        'message': f'Turn your head to the {direction}',
                        'next_step': 2,
                        'status': 'instruction'
                    })
                else:
                    return JsonResponse({
                        'message': f'Please turn your head to the {direction}',
                        'next_step': 2,
                        'status': 'warning'
                    })

            try:
                base_image_data = data['base_image']

                format, imgstr = base_image_data.split(';base64,')
                img_bytes = base64.b64decode(imgstr)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                base_img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                embedding = DeepFace.represent(base_img, model_name='Facenet')[0]['embedding']

                user = request.user
                user.face_encoding = str(embedding)
                user.save()

                request.session.pop('direction', None)
                return JsonResponse({
                    'success': True,
                    'message': 'Face registered successfully!',
                    'status': 'success'
                })

            except:
                return JsonResponse({
                    'message': 'Face processing failed',
                    'status': 'error'
                })
    
    return render(request, 'face_register.html')

@login_required
def face_verify(request):
    mode = request.GET.get('mode') or request.session.get('mode')
    request.session['mode'] = mode

    if request.user.role in ['CEO', 'HR', 'ACCOUNTANT']:
        if not request.user.profile.biometric_enabled:
            if mode == 'logout':
                from django.contrib.auth import logout
                logout(request)
                request.session.flush()
                return redirect('login')
            else:
                request.session['verified'] = True
                return redirect('dashboard')

    if not request.user.face_encoding:
        return redirect('face_register')

    if request.session.get('verified') and mode != 'logout':
        return redirect('dashboard')

    if request.method == 'POST':
        data = json.loads(request.body)
        image_data = data['image']
        step = data.get('step', 1)

        format, imgstr = image_data.split(';base64,')
        img_bytes = base64.b64decode(imgstr)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        turn_direction, last_direction = get_head_turn_direction(img)

        if turn_direction is None:
            return JsonResponse({
                'message': 'No face detected',
                'status': 'warning'
        })

        if step == 1:
            try:
                new_embedding = DeepFace.represent(img, model_name='Facenet')[0]['embedding']

                stored_embedding = ast.literal_eval(request.user.face_encoding)

                distance = np.linalg.norm(np.array(new_embedding) - np.array(stored_embedding))

                if distance < 10:
                    direction = random.choice(['LEFT', 'RIGHT'])
                    request.session['direction'] = direction

                    return JsonResponse({
                        'message': f'Turn your head to the {direction}',
                        'next_step': 2,
                        'status': 'instruction'
                    })
                else:
                    return JsonResponse({
                        'message': 'Face not recognized',
                        'status': 'warning'    
                    })

            except Exception as e:
                return JsonResponse({
                    'message': 'Error detecting face',
                    'status': 'error'
                })

        elif step == 2:
            direction = request.session.get('direction')

            moved = (direction == turn_direction)
            if not moved:
                if last_direction == direction:
                    return JsonResponse({
                        'message': f'Hold still, the system is verifying...',
                        'next_step': 2,
                        'status': 'success'
                    })
                elif last_direction == 'CENTER': 
                    return JsonResponse({
                        'message': f'Turn your head to the {direction}',
                        'next_step': 2,
                        'status': 'instruction'
                    })
                else:
                    return JsonResponse({
                        'message': f'Please turn your head to the {direction}',
                        'next_step': 2,
                        'status': 'warning'
                    })

            mode = request.session.get('mode')
            request.session.pop('direction', None)
            request.session.pop('mode', None)
            request.session['verified'] = True

            if mode == 'logout' and request.session.get('verified'):
                from django.contrib.auth import logout
                handle_check_out(request.user)
                logout(request)
                request.session.flush()

                return JsonResponse({
                    'success': True,
                    'message': 'Face verified successfully!',
                    'redirect': '/',
                    'status': 'success'
                })

            else:
                request.session['verified'] = True
                handle_check_in(request.user)

                return JsonResponse({
                    'success': True,
                    'message': 'Face verified successfully!',
                    'redirect': '/dashboard/',
                    'status': 'success'
                })

    return render(request, 'face_verify.html')

@login_required
def dashboard(request):
    if not request.session.get('verified'):
        return redirect('face_verify')

    if request.user.role == 'CEO':
        return redirect('ceo_dashboard')
    if request.user.role == 'HR':
        return redirect('hr_dashboard')
    
    user = request.user
    today = timezone.now().date()

    attendance = Attendance.objects.filter(
        user=user,
        date=today
    ).first()

    selected_status = selected_task_status_filter(request)
    tasks = Task.objects.filter(
        assigned_to=user
    ).order_by('deadline', '-created_at')

    raw_status = attendance.status if attendance else "OFFLINE"
    status = STATUS_DISPLAY.get(raw_status, raw_status)
    alerts = attendance.anomaly_reason if attendance and attendance.is_anomaly else None

    context = {
        "status": status,
        "tasks": tasks,
        "tasks_count": tasks.count(),
        "task_status_options": task_status_filter_options(selected_status),
        "selected_task_status": selected_status,
        "alert": alerts,
        "show_manager_portal": user.role == "MANAGER",
        "unread_chat_count": unread_chat_count(user),
    }

    return render(request, "dashboard.html", context)


@login_required
def leave_request_view(request):
    if request.user.role not in ["EMPLOYEE", "MANAGER"]:
        return redirect("dashboard")

    form = LeaveRequestForm(user=request.user)
    success_message = ""

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            success_message = "Leave request sent to HR."
            form = LeaveRequestForm(user=request.user)

    today_start, tomorrow_start = local_day_bounds()
    leave_requests = LeaveRequest.objects.filter(user=request.user).filter(
        models.Q(status=LeaveRequest.PENDING) |
        models.Q(
            status=LeaveRequest.APPROVED,
            reviewed_at__gte=today_start,
            reviewed_at__lt=tomorrow_start
        )
    ).order_by("-date")

    return render(request, "leave_request.html", {
        "form": form,
        "leave_requests": leave_requests,
        "success_message": success_message,
    })


def manager_dashboard(request):
    if request.user.role != 'MANAGER':
        return redirect('dashboard')

    user = request.user
    today = timezone.now().date()
    team_profiles = manager_team_queryset(user)
    team_users = [profile.user for profile in team_profiles]

    task_form = ManagerTaskForm(manager=user)

    if request.method == "POST":
        task_form = ManagerTaskForm(request.POST, manager=user)

        if task_form.is_valid():
            task = task_form.save(commit=False)
            task.assigned_by = user
            task.save()
            for image in request.FILES.getlist("initial_images"):
                if not image.content_type or image.content_type.startswith("image/"):
                    TaskImage.objects.create(task=task, image=image, uploaded_by=user)
            return redirect('manager_dashboard')

    attendance_rows = []
    member_rows = []
    for profile in team_profiles:
        attendance = Attendance.objects.filter(
            user=profile.user,
            date=today
        ).first()

        raw_status = attendance.status if attendance else "OFFLINE"
        display_status = STATUS_DISPLAY.get(raw_status, raw_status)
        is_online = bool(attendance and attendance.check_in and not attendance.check_out)

        attendance_rows.append({
            "employee": profile.user,
            "position": profile.position,
            "status": display_status,
            "is_online": is_online,
            "check_in": attendance.check_in if attendance else None,
            "check_out": attendance.check_out if attendance else None,
            "worked_hours": attendance.worked_hours if attendance else 0,
            "alert": attendance.anomaly_reason if attendance and attendance.is_anomaly else None,
        })
        member_rows.append({
            "profile": profile,
            "status": display_status,
            "is_online": is_online,
        })

    all_team_tasks = Task.objects.filter(
        assigned_to__in=team_users
    ).select_related('assigned_to', 'assigned_by').order_by('deadline', '-created_at')
    selected_status = selected_task_status_filter(request)
    team_tasks = all_team_tasks
    active_team_tasks = all_team_tasks.exclude(status='DONE')

    open_tasks = active_team_tasks.count()
    ready_tasks = active_team_tasks.filter(status='READY').count()
    online_count = sum(1 for row in attendance_rows if row["is_online"])
    anomaly_count = sum(1 for row in attendance_rows if row["alert"])

    return render(request, "manager_dashboard.html", {
        "task_form": task_form,
        "member_rows": member_rows,
        "attendance_rows": attendance_rows,
        "team_tasks": team_tasks,
        "task_status_options": task_status_filter_options(selected_status),
        "selected_task_status": selected_status,
        "team_count": len(team_users),
        "open_tasks": open_tasks,
        "ready_tasks": ready_tasks,
        "online_count": online_count,
        "anomaly_count": anomaly_count,
        "unread_chat_count": unread_chat_count(user),
    })


@login_required
def manager_edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not user_can_manage_task(request.user, task):
        return redirect('manager_dashboard')

    if request.method == "POST":
        form = ManagerTaskForm(request.POST, instance=task, manager=request.user)

        if form.is_valid():
            form.save()
            return redirect('manager_dashboard')
    else:
        form = ManagerTaskForm(instance=task, manager=request.user)

    return render(request, "manager_task_form.html", {
        "form": form,
        "task": task,
        "mode": "Edit",
    })


@require_POST
@login_required
def manager_delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not user_can_manage_task(request.user, task):
        return JsonResponse({"success": False, "error": "Not allowed"}, status=403)

    task.delete()
    return JsonResponse({"success": True})


@login_required
def ceo_dashboard(request):
    if request.user.role != 'CEO':
        return redirect('dashboard')

    user = request.user
    today = timezone.now().date()
    managers = list(manager_users_queryset())

    task_form = CEOTaskForm()

    if request.method == "POST":
        task_form = CEOTaskForm(request.POST)

        if task_form.is_valid():
            task = task_form.save(commit=False)
            task.assigned_by = user
            task.save()
            for image in request.FILES.getlist("initial_images"):
                if not image.content_type or image.content_type.startswith("image/"):
                    TaskImage.objects.create(task=task, image=image, uploaded_by=user)
            return redirect('ceo_dashboard')

    attendance_rows = []
    member_rows = []
    for manager in managers:
        attendance = Attendance.objects.filter(
            user=manager,
            date=today
        ).first()

        raw_status = attendance.status if attendance else "OFFLINE"
        display_status = STATUS_DISPLAY.get(raw_status, raw_status)
        is_online = bool(attendance and attendance.check_in and not attendance.check_out)

        attendance_rows.append({
            "manager": manager,
            "position": manager.profile.position,
            "status": display_status,
            "is_online": is_online,
            "check_in": attendance.check_in if attendance else None,
            "check_out": attendance.check_out if attendance else None,
            "worked_hours": attendance.worked_hours if attendance else 0,
            "alert": attendance.anomaly_reason if attendance and attendance.is_anomaly else None,
        })
        member_rows.append({
            "manager": manager,
            "profile": manager.profile,
            "status": display_status,
            "is_online": is_online,
        })

    all_manager_tasks = Task.objects.filter(
        assigned_to__in=managers
    ).select_related('assigned_to', 'assigned_by').order_by('deadline', '-created_at')
    selected_status = selected_task_status_filter(request)
    manager_tasks = all_manager_tasks
    active_manager_tasks = all_manager_tasks.exclude(status='DONE')

    open_tasks = active_manager_tasks.count()
    ready_tasks = active_manager_tasks.filter(status='READY').count()
    online_count = sum(1 for row in attendance_rows if row["is_online"])
    anomaly_count = sum(1 for row in attendance_rows if row["alert"])

    return render(request, "ceo_dashboard.html", {
        "task_form": task_form,
        "member_rows": member_rows,
        "attendance_rows": attendance_rows,
        "manager_tasks": manager_tasks,
        "task_status_options": task_status_filter_options(selected_status),
        "selected_task_status": selected_status,
        "manager_count": len(managers),
        "open_tasks": open_tasks,
        "ready_tasks": ready_tasks,
        "online_count": online_count,
        "anomaly_count": anomaly_count,
        "unread_chat_count": unread_chat_count(user),
    })


@login_required
def ceo_staff_management(request):
    if request.user.role != 'CEO':
        return redirect('dashboard')

    form = HRCreationForm()
    success_message = ""

    if request.method == "POST":
        action = request.POST.get("action")
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if action == "create_hr":
            form = HRCreationForm(request.POST)
            if form.is_valid():
                created_user = form.save()
                success_message = f"HR account created for {created_user.username}."
                form = HRCreationForm()
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": success_message,
                        "hr": staff_user_payload(created_user),
                        "hr_count": User.objects.filter(role="HR").count(),
                    })
            elif is_ajax:
                return JsonResponse({
                    "success": False,
                    "error": form_error_text(form),
                }, status=400)

        elif action == "update_hr":
            hr_user = get_object_or_404(User, id=request.POST.get("hr_id"), role="HR")
            edit_form = HRUpdateForm(request.POST, user=hr_user)

            if edit_form.is_valid():
                updated_user = edit_form.save()
                success_message = f"Updated HR account for {updated_user.username}."
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": success_message,
                        "hr": staff_user_payload(updated_user),
                    })
            elif is_ajax:
                return JsonResponse({
                    "success": False,
                    "error": form_error_text(edit_form),
                }, status=400)

        elif action == "toggle_hr":
            hr_user = get_object_or_404(User, id=request.POST.get("hr_id"), role="HR")
            hr_user.is_active = not hr_user.is_active
            hr_user.save(update_fields=["is_active"])
            state = "activated" if hr_user.is_active else "suspended"
            success_message = f"{hr_user.username} has been {state}."
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "message": success_message,
                    "hr": staff_user_payload(hr_user),
                })

        elif action == "delete_hr":
            hr_user = get_object_or_404(User, id=request.POST.get("hr_id"), role="HR")
            hr_id = hr_user.id
            username = hr_user.username
            hr_user.delete()
            success_message = f"Deleted HR account for {username}."
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "message": success_message,
                    "hr_id": hr_id,
                    "hr_count": User.objects.filter(role="HR").count(),
                })

    hr_users = User.objects.filter(role='HR').select_related('profile').order_by('username')

    return render(request, "ceo_staff_management.html", {
        "form": form,
        "success_message": success_message,
        "hr_users": hr_users,
        "hr_count": hr_users.count(),
    })


def staff_user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "No email",
        "is_active": user.is_active,
    }


def form_error_text(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]

    return "Please check the form and try again."


@login_required
def hr_dashboard(request):
    if request.user.role != "HR":
        return redirect("dashboard")

    today = timezone.now().date()
    staff_users = list(hr_managed_users_queryset())
    attendance_today = Attendance.objects.filter(user__in=staff_users, date=today).select_related("user")
    attendance_by_user = {row.user_id: row for row in attendance_today}

    attendance_rows = []
    for user in staff_users:
        attendance = attendance_by_user.get(user.id)
        raw_status = attendance.status if attendance else "OFFLINE"
        if raw_status == "ABSENT":
            raw_status = "OFFLINE"
        display_status = STATUS_DISPLAY.get(raw_status, raw_status)
        status_class = {
            "PRESENT": "active",
            "LOW_HOURS": "short",
            "OFFLINE": "offline",
            "WORKING_HOLIDAY": "overtime",
            "HOLIDAY": "holiday",
            "LEAVE": "leave",
        }.get(raw_status, "offline")
        is_online = bool(attendance and attendance.check_in and not attendance.check_out)
        attendance_rows.append({
            "user": user,
            "status": display_status,
            "status_code": raw_status,
            "status_class": status_class,
            "is_online": is_online,
            "check_in": attendance.check_in if attendance else None,
            "check_out": attendance.check_out if attendance else None,
            "worked_hours": attendance.worked_hours if attendance else 0,
            "alert": attendance.anomaly_reason if attendance and attendance.is_anomaly else None,
        })

    return render(request, "hr_dashboard.html", {
        "staff_count": len(staff_users),
        "manager_count": sum(1 for user in staff_users if user.role == "MANAGER"),
        "employee_count": sum(1 for user in staff_users if user.role == "EMPLOYEE"),
        "online_count": sum(1 for row in attendance_rows if row["is_online"]),
        "anomaly_count": sum(1 for row in attendance_rows if row["alert"]),
        "pending_leave_count": LeaveRequest.objects.filter(status=LeaveRequest.PENDING).count(),
        "unread_chat_count": unread_chat_count(request.user),
        "attendance_rows": attendance_rows,
    })


@login_required
def hr_leave_requests(request):
    if request.user.role != "HR":
        return redirect("dashboard")

    if request.method == "POST":
        leave_request = get_object_or_404(
            LeaveRequest.objects.select_related("user", "user__profile"),
            id=request.POST.get("leave_id"),
            status=LeaveRequest.PENDING
        )
        action = request.POST.get("action")

        if action == "approve":
            leave_request.status = LeaveRequest.APPROVED
            leave_request.reviewed_by = request.user
            leave_request.reviewed_at = timezone.now()
            leave_request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            apply_approved_leave_request(leave_request)
            message = f"Approved leave for {leave_request.user.username}."
            approved_payload = {
                "id": leave_request.id,
                "username": leave_request.user.username,
                "period": leave_period_display(leave_request),
                "reviewed_by": request.user.username,
            }
        elif action == "reject":
            username = leave_request.user.username
            leave_request.delete()
            message = f"Rejected leave for {username}."
            approved_payload = None
        else:
            return JsonResponse({"success": False, "error": "Invalid action."}, status=400)

        return JsonResponse({
            "success": True,
            "message": message,
            "leave_id": request.POST.get("leave_id"),
            "pending_count": LeaveRequest.objects.filter(status=LeaveRequest.PENDING).count(),
            "approved": approved_payload,
        })

    pending_requests = LeaveRequest.objects.filter(
        status=LeaveRequest.PENDING
    ).select_related("user", "user__profile").order_by("date", "end_date", "created_at")
    today_start, tomorrow_start = local_day_bounds()
    approved_requests = LeaveRequest.objects.filter(
        status=LeaveRequest.APPROVED,
        reviewed_at__gte=today_start,
        reviewed_at__lt=tomorrow_start
    ).select_related("user", "user__profile", "reviewed_by").order_by("-reviewed_at")[:20]

    return render(request, "hr_leave_requests.html", {
        "pending_requests": pending_requests,
        "approved_requests": approved_requests,
    })


@login_required
def hr_staff_management(request):
    if request.user.role != "HR":
        return redirect("dashboard")

    form = HRStaffCreationForm()
    success_message = ""

    if request.method == "POST":
        action = request.POST.get("action")
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if action == "create_staff":
            form = HRStaffCreationForm(request.POST)
            if form.is_valid():
                user = form.save()
                success_message = f"{user.get_role_display()} account created for {user.username}."
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": success_message,
                        "user": hr_staff_payload(user),
                        "staff_count": hr_managed_users_queryset().count(),
                    })
            elif is_ajax:
                return JsonResponse({"success": False, "error": form_error_text(form)}, status=400)

        elif action == "update_staff":
            user = get_object_or_404(User, id=request.POST.get("user_id"), role__in=["MANAGER", "EMPLOYEE"])
            update_form = HRStaffUpdateForm(request.POST, user=user)
            if update_form.is_valid():
                user = update_form.save()
                success_message = f"Updated account for {user.username}."
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": success_message,
                        "user": hr_staff_payload(user),
                    })
            elif is_ajax:
                return JsonResponse({"success": False, "error": form_error_text(update_form)}, status=400)

        elif action == "toggle_staff":
            user = get_object_or_404(User, id=request.POST.get("user_id"), role__in=["MANAGER", "EMPLOYEE"])
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            state = "activated" if user.is_active else "suspended"
            success_message = f"{user.username} has been {state}."
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "message": success_message,
                    "user": hr_staff_payload(user),
                })

        elif action == "delete_staff":
            user = get_object_or_404(User, id=request.POST.get("user_id"), role__in=["MANAGER", "EMPLOYEE"])
            user_id = user.id
            username = user.username
            user.delete()
            success_message = f"Deleted account for {username}."
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "message": success_message,
                    "user_id": user_id,
                    "staff_count": hr_managed_users_queryset().count(),
                })

    users = hr_managed_users_queryset()

    return render(request, "hr_staff_management.html", {
        "form": form,
        "users": users,
        "staff_count": users.count(),
        "managers": User.objects.filter(role="MANAGER", is_active=True).order_by("username"),
        "success_message": success_message,
    })


def hr_staff_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "role": user.role,
        "role_label": user.get_role_display(),
        "phone": user.phone or "",
        "department": user.profile.department or "",
        "position": user.profile.position or "",
        "salary": str(user.profile.salary or ""),
        "manager_id": user.profile.manager_id or "",
        "manager_name": user.profile.manager.username if user.profile.manager else "No manager",
        "is_active": user.is_active,
    }


@login_required
def hr_analytics(request):
    if request.user.role != "HR":
        return redirect("employee_analytics")

    today = timezone.now().date()
    users = list(hr_managed_users_queryset())
    start_date = min((user.date_joined.date() for user in users), default=today)
    months, join_month = build_month_choices(start_date, today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)
    month_start_datetime, month_end_datetime = month_datetime_bounds(month_start, month_end)

    attendance = Attendance.objects.filter(user__in=users, date__gte=month_start, date__lte=month_end)
    tasks = Task.objects.filter(assigned_to__in=users, updated_at__gte=month_start_datetime, updated_at__lte=month_end_datetime)

    working_days = attendance.filter(status__in=["PRESENT", "WORKING_HOLIDAY", "LOW_HOURS"]).count()
    total_hours = attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0
    total_tasks = tasks.count()
    completed = tasks.filter(status="DONE").count()
    rows = []
    for user in users:
        user_attendance = attendance.filter(user=user)
        user_tasks = tasks.filter(assigned_to=user)
        rows.append({
            "user": user,
            "hours": round(user_attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0, 2),
            "anomalies": user_attendance.filter(is_anomaly=True).count(),
            "absences": user_attendance.filter(status="ABSENT").count(),
            "completed": user_tasks.filter(status="DONE").count(),
            "total_tasks": user_tasks.count(),
        })

    data = {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "staff_count": len(users),
        "total_hours": round(total_hours, 2),
        "avg_hours": round(total_hours / working_days, 2) if working_days else 0,
        "absences": attendance.filter(status="ABSENT").count(),
        "anomalies": attendance.filter(is_anomaly=True).count(),
        "total_tasks": total_tasks,
        "completed": completed,
        "completion_rate": round((completed / total_tasks * 100), 1) if total_tasks else 0,
        "rows": rows,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **{key: value for key, value in data.items() if key not in ["months", "rows"]},
            "rows": [{
                "name": row["user"].username,
                "role": row["user"].get_role_display(),
                "hours": row["hours"],
                "completed": row["completed"],
                "total_tasks": row["total_tasks"],
                "absences": row["absences"],
                "anomalies": row["anomalies"],
                "search": f"{row['user'].username} {row['user'].get_role_display()}",
            } for row in rows],
        })

    return render(request, "hr_analytics.html", data)


@login_required
def hr_accountant(request):
    if request.user.role != "HR":
        return redirect("dashboard")

    today = timezone.now().date()
    users = list(hr_managed_users_queryset())
    start_date = min((user.date_joined.date() for user in users), default=today)
    months, join_month = build_month_choices(start_date, today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)
    if selected_month == today.strftime("%Y-%m"):
        month_end = today

    rows = []
    for user in users:
        attendance = Attendance.objects.filter(user=user, date__gte=month_start, date__lte=month_end)
        salary = calculate_salary_adjustment(user, attendance, month_start, month_end)
        rows.append({
            "user": user,
            "salary": salary,
            "net_pay": salary["net_pay"],
        })

    return render(request, "hr_accountant.html", {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "rows": rows,
    })


@login_required
def hr_add_bonus(request):
    if request.user.role != "HR":
        return redirect("dashboard")

    initial = {}
    user_id = request.GET.get("user")
    month = request.GET.get("month") or request.POST.get("month")

    if user_id:
        initial["user"] = user_id

    selected_month = month or timezone.now().date().strftime("%Y-%m")

    initial["month"] = selected_month

    if request.method == "POST":
        form = PayrollBonusForm(request.POST)

        if form.is_valid():
            adjustment = form.save(created_by=request.user)
            return redirect(f"{reverse('hr_accountant')}?month={adjustment.month.strftime('%Y-%m')}")
    else:
        form = PayrollBonusForm(initial=initial)

    return render(request, "hr_bonus_form.html", {
        "form": form,
        "mode": "Add Adjustment",
        "selected_month": selected_month,
    })


@login_required
def hr_attendance_calendar(request):
    if request.user.role != "HR":
        return redirect("calendar")

    events = []
    for attendance in Attendance.objects.filter(user__role__in=["MANAGER", "EMPLOYEE"]).exclude(status="LEAVE").select_related("user"):
        status = STATUS_DISPLAY.get(attendance.status, attendance.status or "Attendance")
        anomaly_reason = attendance.anomaly_reason or "Attendance anomaly detected."
        base_color = {
            "ABSENT": "#EF4444",
            "LOW_HOURS": "#F59E0B",
            "WORKING_HOLIDAY": "#6366F1",
            "PRESENT": "#10B981",
        }.get(attendance.status, "#3B82F6")
        highlight_anomaly = attendance.is_anomaly and attendance.status in ["PRESENT", "WORKING_HOLIDAY"]
        color = "#A855F7" if highlight_anomaly else base_color
        events.append({
            "title": f"{attendance.user.username}: {status}",
            "start": attendance.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": color,
            "classNames": ["attendance-anomaly"] if highlight_anomaly else ["attendance-normal"],
            "extendedProps": {
                "is_anomaly": attendance.is_anomaly,
                "anomaly_reason": anomaly_reason if attendance.is_anomaly else "",
                "user": attendance.user.username,
                "status": status,
            },
        })

    for leave in LeaveRequest.objects.filter(
        user__role__in=["MANAGER", "EMPLOYEE"],
        status=LeaveRequest.APPROVED
    ).select_related("user"):
        events.append(leave_calendar_event(leave, f"{leave.user.username}: Leave"))

    for holiday in Holiday.objects.all():
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745",
        })

    return render(request, "hr_attendance_calendar.html", {
        "events_json": json.dumps(events)
    })


@login_required
def ceo_edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not user_can_manage_manager_task(request.user, task):
        return redirect('ceo_dashboard')

    if request.method == "POST":
        form = CEOTaskForm(request.POST, instance=task)

        if form.is_valid():
            form.save()
            return redirect('ceo_dashboard')
    else:
        form = CEOTaskForm(instance=task)

    return render(request, "ceo_task_form.html", {
        "form": form,
        "task": task,
        "mode": "Edit",
    })


@require_POST
@login_required
def ceo_delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not user_can_manage_manager_task(request.user, task):
        return JsonResponse({"success": False, "error": "Not allowed"}, status=403)

    task.delete()
    return JsonResponse({"success": True})

@csrf_exempt
@login_required
def update_task_status(request):
    if request.method == "POST":
        data = json.loads(request.body)

        task_id = data.get("task_id")
        new_status = data.get("status")

        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return JsonResponse({"error": "Task not found"}, status=404)

        user = request.user

        if user == task.assigned_to:
            allowed = {
                "PENDING": ["IN_PROGRESS"],
                "IN_PROGRESS": ["READY", "PENDING"],
                "READY": ["IN_PROGRESS"]
            }

            if task.status in allowed and new_status in allowed[task.status]:
                task.status = new_status
                task.save()
                return JsonResponse({"success": True})

        if user_can_review_task(user, task):
            allowed = {
                "READY": ["REVIEW", "DONE", "IN_PROGRESS"],
                "REVIEW": ["DONE", "IN_PROGRESS"],
                "PENDING": ["IN_PROGRESS"],
                "IN_PROGRESS": ["READY", "PENDING"],
                "DONE": ["REVIEW"]
            }

            if task.status in allowed and new_status in allowed[task.status]:
                task.status = new_status
                if new_status == "DONE":
                    task.completed_at = timezone.now()
                elif task.completed_at and new_status != "DONE":
                    task.completed_at = None
                task.save()
                return JsonResponse({"success": True})

        return JsonResponse({"error": "Not allowed"}, status=403)
    
@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if task.assigned_to != request.user and not user_can_review_task(request.user, task):
        return redirect('dashboard')

    commits = task.commits.select_related('user').order_by('-created_at')
    images = task.images.select_related('uploaded_by').order_by('-uploaded_at')
    assigner_images = images.filter(uploaded_by=task.assigned_by)
    assignee_images = images.filter(uploaded_by=task.assigned_to)

    can_edit = (
        task.assigned_to == request.user and
        task.status == "IN_PROGRESS"
    )
    can_manage = user_can_review_task(request.user, task)
    can_manage_manager_task = user_can_manage_manager_task(request.user, task)
    edit_task_url_name = "ceo_edit_task" if can_manage_manager_task else "manager_edit_task"
    review_subject = "manager" if can_manage_manager_task else "employee"
    can_upload_images = user_can_upload_task_image(request.user, task)
    image_upload_role = ""
    if request.user == task.assigned_by:
        image_upload_role = "assigner"
    elif request.user == task.assigned_to:
        image_upload_role = "assignee"

    role = request.user.role
    opened_as_manager = role == "MANAGER" and request.GET.get("role") == "manager"
    if role == "CEO":
        back_url = "/ceo/dashboard/"
    elif opened_as_manager:
        back_url = "/manager/dashboard/"
    else:
        back_url = "/dashboard/"

    return render(request, "task_detail.html", {
        "task": task,
        "commits": commits,
        "assigner_images": assigner_images,
        "assignee_images": assignee_images,
        "can_edit": can_edit,
        "can_manage": can_manage,
        "can_upload_images": can_upload_images,
        "image_upload_role": image_upload_role,
        "edit_task_url_name": edit_task_url_name,
        "review_subject": review_subject,
        "user_role": role,
        "back_url": back_url,
    })


@require_POST
@login_required
def add_task_images(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not user_can_upload_task_image(request.user, task):
        return JsonResponse({
            "success": False,
            "error": "You cannot upload images for this task right now."
        }, status=403)

    files = request.FILES.getlist("images")

    if not files:
        return JsonResponse({
            "success": False,
            "error": "Please choose at least one image."
        }, status=400)

    uploaded_images = []
    for image in files:
        if image.content_type and not image.content_type.startswith("image/"):
            continue

        task_image = TaskImage.objects.create(
            task=task,
            image=image,
            uploaded_by=request.user
        )
        uploaded_images.append({
            "id": task_image.id,
            "url": task_image.image.url,
            "uploaded_by": task_image.uploaded_by.username,
            "uploaded_at": localtime(task_image.uploaded_at).strftime("%b %d, %Y - %H:%M"),
        })

    if not uploaded_images:
        return JsonResponse({
            "success": False,
            "error": "Only image files can be uploaded."
        }, status=400)

    return JsonResponse({
        "success": True,
        "images": uploaded_images,
    })


@require_POST
@login_required
def delete_task_image(request, image_id):
    task_image = get_object_or_404(TaskImage, id=image_id)

    if not user_can_delete_task_image(request.user, task_image):
        return JsonResponse({
            "success": False,
            "error": "You cannot delete this image."
        }, status=403)

    task_image.image.delete(save=False)
    task_image.delete()
    return JsonResponse({"success": True})


@require_POST
@login_required
def add_task_commit(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if task.assigned_to != request.user or task.status != "IN_PROGRESS":
        return JsonResponse({
            "success": False,
            "error": "You cannot add commits to this task."
        }, status=403)

    message = request.POST.get("message", "").strip()

    if not message:
        return JsonResponse({
            "success": False,
            "error": "Commit message cannot be empty."
        }, status=400)

    commit = TaskCommit.objects.create(
        task=task,
        user=request.user,
        message=message
    )

    return JsonResponse({
        "success": True,
        "commit": {
            "id": commit.id,
            "user": commit.user.username,
            "message": commit.message,
            "updated_at": localtime(commit.updated_at).strftime("%b %d, %Y - %H:%M"),
            "edited": commit.is_edited,
        }
    })

@login_required
def delete_commit(request, commit_id):
    try:
        commit = TaskCommit.objects.get(id=commit_id)

        if commit.user != request.user:
            return JsonResponse({
                "success": False,
                "error": "You cannot delete this commit."
            }, status=403)
        
        if commit.task.status != "IN_PROGRESS":
            return JsonResponse({
                "success": False,
                "error": "You can only delete commits while the task is in progress."
            }, status=403)

        commit.delete()

        return JsonResponse({"success": True})

    except TaskCommit.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Commit not found."
        }, status=404)
    
@require_POST
@login_required
def edit_commit(request, commit_id):
    try:
        commit = TaskCommit.objects.get(id=commit_id)

        if commit.user != request.user:
            return JsonResponse({
                "success": False,
                "error": "You cannot edit this commit."
            }, status=403)

        if commit.task.status != "IN_PROGRESS":
            return JsonResponse({
                "success": False,
                "error": "You can only edit commits while the task is in progress."
            }, status=403)

        message = request.POST.get("message", "").strip()

        if not message:
            return JsonResponse({
                "success": False,
                "error": "Commit message cannot be empty."
            }, status=400)

        commit.message = message
        commit.save()

        return JsonResponse({
            "success": True,
            "commit": {
                "id": commit.id,
                "message": commit.message,
                "updated_at": localtime(commit.updated_at).strftime("%b %d, %Y - %H:%M"),
                "edited": commit.is_edited,
            }
        })

    except TaskCommit.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Commit not found."
        }, status=404)

@login_required
def calendar_view(request):
    tasks = Task.objects.filter(assigned_to=request.user)

    events = []
    for task in tasks:
        if task.deadline:
            events.append(task_calendar_event(task, task.title))
    
    holidays = Holiday.objects.all()

    for holiday in holidays:
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

    for leave in LeaveRequest.objects.filter(user=request.user, status=LeaveRequest.APPROVED):
        events.append(leave_calendar_event(leave, "Leave"))

    return render(request, "calendar.html", {
        "events_json": json.dumps(events)
    })


@login_required
def manager_calendar_view(request):
    if request.user.role != 'MANAGER':
        return redirect('calendar')

    team_users = manager_team_users(request.user)
    tasks = Task.objects.filter(assigned_to__in=team_users).select_related('assigned_to')

    events = []
    for task in tasks:
        if task.deadline:
            events.append(task_calendar_event(task, f"{task.assigned_to.username}: {task.title}"))

    for holiday in Holiday.objects.all():
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

    for leave in LeaveRequest.objects.filter(
        user__in=team_users,
        status=LeaveRequest.APPROVED
    ).select_related("user"):
        events.append(leave_calendar_event(leave, f"{leave.user.username}: Leave"))

    return render(request, "manager_calendar.html", {
        "events_json": json.dumps(events)
    })


@login_required
def ceo_calendar_view(request):
    if request.user.role != 'CEO':
        return redirect('calendar')

    managers = list(manager_users_queryset())
    tasks = Task.objects.filter(assigned_to__in=managers).select_related('assigned_to')

    events = []
    for task in tasks:
        if task.deadline:
            events.append(task_calendar_event(task, f"{task.assigned_to.username}: {task.title}"))

    for holiday in Holiday.objects.all():
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

    for leave in LeaveRequest.objects.filter(
        user__in=managers,
        status=LeaveRequest.APPROVED
    ).select_related("user"):
        events.append(leave_calendar_event(leave, f"{leave.user.username}: Leave"))

    return render(request, "ceo_calendar.html", {
        "events_json": json.dumps(events)
    })


@login_required
def ceo_analytics(request):
    if request.user.role != 'CEO':
        return redirect('employee_analytics')

    today = timezone.now().date()
    managers = list(manager_users_queryset())
    start_date = min((manager.date_joined.date() for manager in managers), default=today)
    months, join_month = build_month_choices(start_date, today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)
    month_start_datetime, month_end_datetime = month_datetime_bounds(month_start, month_end)

    attendance = Attendance.objects.filter(
        user__in=managers,
        date__gte=month_start,
        date__lte=month_end
    )

    working_days = attendance.filter(
        status__in=["PRESENT", "WORKING_HOLIDAY", "LOW_HOURS"]
    ).count()
    total_hours = attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0
    avg_hours = total_hours / working_days if working_days else 0
    absences = attendance.filter(status="ABSENT").count()
    anomalies = attendance.filter(is_anomaly=True).count()

    tasks = Task.objects.filter(
        assigned_to__in=managers,
        updated_at__gte=month_start_datetime,
        updated_at__lte=month_end_datetime
    )

    total_tasks = tasks.count()
    completed = tasks.filter(status="DONE").count()
    ready = tasks.filter(status="READY").count()
    in_progress = tasks.filter(status="IN_PROGRESS").count()
    pending = tasks.filter(status="PENDING").count()
    completion_rate = (completed / total_tasks * 100) if total_tasks else 0

    finished_tasks = tasks.filter(
        status="DONE",
        completed_at__isnull=False,
        estimated_hours__isnull=False
    )

    completion_ratios = []
    for task in finished_tasks:
        actual_hours = (task.completed_at - task.created_at).total_seconds() / 3600
        if task.estimated_hours:
            completion_ratios.append(actual_hours / task.estimated_hours)

    avg_completion_ratio = sum(completion_ratios) / len(completion_ratios) if completion_ratios else 0

    manager_rows = []
    for manager in managers:
        manager_attendance = attendance.filter(user=manager)
        manager_tasks = tasks.filter(assigned_to=manager)
        manager_rows.append({
            "manager": manager,
            "hours": round(manager_attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0, 2),
            "anomalies": manager_attendance.filter(is_anomaly=True).count(),
            "absences": manager_attendance.filter(status="ABSENT").count(),
            "completed": manager_tasks.filter(status="DONE").count(),
            "total_tasks": manager_tasks.count(),
        })

    data = {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "manager_count": len(managers),
        "total_hours": round(total_hours, 2),
        "avg_hours": round(avg_hours, 2),
        "absences": absences,
        "anomalies": anomalies,
        "total_tasks": total_tasks,
        "completed": completed,
        "ready": ready,
        "in_progress": in_progress,
        "pending": pending,
        "completion_rate": round(completion_rate, 1),
        "avg_completion_ratio": round(avg_completion_ratio, 2),
        "manager_rows": manager_rows,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **{key: value for key, value in data.items() if key not in ["months", "manager_rows"]},
            "rows": [{
                "name": row["manager"].username,
                "hours": row["hours"],
                "completed": row["completed"],
                "total_tasks": row["total_tasks"],
                "absences": row["absences"],
                "anomalies": row["anomalies"],
                "search": row["manager"].username,
            } for row in manager_rows],
        })

    return render(request, "ceo_analytics.html", data)


@login_required
def ceo_anomalies(request):
    if request.user.role != 'CEO':
        return redirect('employee_anomalies')

    today = timezone.now().date()
    managers = list(manager_users_queryset().select_related('profile'))
    start_date = min((manager.date_joined.date() for manager in managers), default=today)
    months, join_month = build_month_choices(start_date, today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)

    grouped_anomalies = []
    total_anomalies = 0
    affected_managers = 0

    for manager in managers:
        anomalies = list(Attendance.objects.filter(
            user=manager,
            date__gte=month_start,
            date__lte=month_end,
            is_anomaly=True
        ).order_by("-date"))

        total_anomalies += len(anomalies)

        if anomalies:
            affected_managers += 1
            grouped_anomalies.append({
                "manager": manager,
                "profile": manager.profile,
                "anomalies": anomalies,
                "count": len(anomalies),
                "hours": round(sum(a.worked_hours or 0 for a in anomalies), 2),
            })

    manager_summaries = []
    for manager in managers:
        manager_count = Attendance.objects.filter(
            user=manager,
            date__gte=month_start,
            date__lte=month_end,
            is_anomaly=True
        ).count()

        manager_summaries.append({
            "manager": manager,
            "profile": manager.profile,
            "count": manager_count,
        })

    data = {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "manager_count": len(managers),
        "total_anomalies": total_anomalies,
        "affected_managers": affected_managers,
        "clear_managers": len(managers) - affected_managers,
        "grouped_anomalies": grouped_anomalies,
        "manager_summaries": manager_summaries,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **{key: value for key, value in data.items() if key not in ["months", "grouped_anomalies", "manager_summaries"]},
            "summaries": [{
                "name": row["manager"].username,
                "position": row["profile"].position or "Manager",
                "count": row["count"],
                "search": f"{row['manager'].username} {row['profile'].position or 'Manager'}",
            } for row in manager_summaries],
            "groups": [{
                "name": group["manager"].username,
                "position": group["profile"].position or "Manager",
                "department": group["profile"].department or "",
                "count": group["count"],
                "hours": group["hours"],
                "anomalies": [serialize_anomaly(anomaly) for anomaly in group["anomalies"]],
            } for group in grouped_anomalies],
        })

    return render(request, "ceo_anomalies.html", data)


@login_required
def profile_view(request):
    profile = request.user.profile
    can_manage_own_biometrics = request.user.role in ['CEO', 'HR']
    can_upload_own_cv = request.user.role in ['MANAGER', 'EMPLOYEE']
    can_edit_own_identity = request.user.role == 'CEO'

    if request.method == "POST":
        form = EmployeeProfileForm(request.POST, instance=profile)
        action = request.POST.get("action")

        if can_manage_own_biometrics and action == "toggle_biometrics":
            profile.biometric_enabled = not profile.biometric_enabled
            profile.save(update_fields=["biometric_enabled"])

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "biometric_enabled": profile.biometric_enabled,
                })

            return redirect('profile')
        elif can_upload_own_cv and action == "upload_cv":
            cv_file = request.FILES.get("cv")

            if not cv_file or not is_valid_cv_file(cv_file):
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "success": False,
                        "error": "Please upload a valid CV document (.pdf, .doc, or .docx)."
                    }, status=400)
                return redirect('profile')

            if profile.cv:
                profile.cv.delete(save=False)

            profile.cv = cv_file
            profile.save(update_fields=["cv"])

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "cv_url": reverse("profile_cv"),
                    "cv_name": Path(profile.cv.name).name,
                })

            return redirect('profile')
        elif action in [None, "save_profile"] and form.is_valid():
            phone = request.POST.get("phone", "").strip()

            if len(phone) > 15:
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "success": False,
                        "error": "Phone number must be 15 characters or fewer.",
                    }, status=400)
                return redirect('profile')

            request.user.phone = phone
            user_update_fields = ["phone"]

            if can_edit_own_identity:
                username = request.POST.get("username", "").strip()
                email = request.POST.get("email", "").strip()

                if not username:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({
                            "success": False,
                            "error": "Username cannot be empty.",
                        }, status=400)
                    return redirect('profile')

                if not email:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({
                            "success": False,
                            "error": "Email cannot be empty.",
                        }, status=400)
                    return redirect('profile')

                try:
                    validate_email(email)
                except ValidationError:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({
                            "success": False,
                            "error": "Please enter a valid email address.",
                        }, status=400)
                    return redirect('profile')

                if User.objects.exclude(pk=request.user.pk).filter(username=username).exists():
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({
                            "success": False,
                            "error": "That username is already taken.",
                        }, status=400)
                    return redirect('profile')

                if User.objects.exclude(pk=request.user.pk).filter(email=email).exists():
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({
                            "success": False,
                            "error": "That email address is already used.",
                        }, status=400)
                    return redirect('profile')

                request.user.username = username
                request.user.email = email
                user_update_fields.extend(["username", "email"])

            request.user.save(update_fields=user_update_fields)

            form.save()

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "address": profile.address or "",
                    "username": request.user.username,
                    "email": request.user.email,
                    "phone": request.user.phone or "",
                })

        elif request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "success": False,
                "errors": form.errors,
            }, status=400)
    else:
        form = EmployeeProfileForm(instance=profile)

    return render(request, "profile.html", {
        "form": form,
        "profile": profile,
        "is_high_priority_role": request.user.role in ['CEO', 'HR'],
        "can_manage_own_biometrics": can_manage_own_biometrics,
        "can_upload_own_cv": can_upload_own_cv,
        "can_edit_own_identity": can_edit_own_identity,
    })


@login_required
def profile_cv(request):
    profile = request.user.profile

    if not profile.cv:
        raise Http404("CV not found.")

    content_type, _ = mimetypes.guess_type(profile.cv.name)
    filename = Path(profile.cv.name).name

    return FileResponse(
        profile.cv.open("rb"),
        as_attachment=False,
        filename=filename,
        content_type=content_type or "application/octet-stream",
    )


@login_required
def manager_analytics(request):
    if request.user.role != 'MANAGER':
        return redirect('employee_analytics')

    today = timezone.now().date()
    team_users = manager_team_users(request.user)
    months, join_month = build_month_choices(manager_team_start_date(request.user, today), today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)
    month_start_datetime, month_end_datetime = month_datetime_bounds(month_start, month_end)

    attendance = Attendance.objects.filter(
        user__in=team_users,
        date__gte=month_start,
        date__lte=month_end
    )

    working_days = attendance.filter(
        status__in=["PRESENT", "WORKING_HOLIDAY", "LOW_HOURS"]
    ).count()
    total_hours = attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0
    avg_hours = total_hours / working_days if working_days else 0
    absences = attendance.filter(status="ABSENT").count()
    anomalies = attendance.filter(is_anomaly=True).count()

    tasks = Task.objects.filter(
        assigned_to__in=team_users,
        updated_at__gte=month_start_datetime,
        updated_at__lte=month_end_datetime
    )

    total_tasks = tasks.count()
    completed = tasks.filter(status="DONE").count()
    ready = tasks.filter(status="READY").count()
    in_progress = tasks.filter(status="IN_PROGRESS").count()
    pending = tasks.filter(status="PENDING").count()
    completion_rate = (completed / total_tasks * 100) if total_tasks else 0

    finished_tasks = tasks.filter(
        status="DONE",
        completed_at__isnull=False,
        estimated_hours__isnull=False
    )

    completion_ratios = []
    for task in finished_tasks:
        actual_hours = (task.completed_at - task.created_at).total_seconds() / 3600
        if task.estimated_hours:
            completion_ratios.append(actual_hours / task.estimated_hours)

    avg_completion_ratio = sum(completion_ratios) / len(completion_ratios) if completion_ratios else 0

    member_rows = []
    for employee in team_users:
        employee_attendance = attendance.filter(user=employee)
        employee_tasks = tasks.filter(assigned_to=employee)
        member_rows.append({
            "employee": employee,
            "hours": round(employee_attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0, 2),
            "anomalies": employee_attendance.filter(is_anomaly=True).count(),
            "absences": employee_attendance.filter(status="ABSENT").count(),
            "completed": employee_tasks.filter(status="DONE").count(),
            "total_tasks": employee_tasks.count(),
        })

    data = {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "team_count": len(team_users),
        "total_hours": round(total_hours, 2),
        "avg_hours": round(avg_hours, 2),
        "absences": absences,
        "anomalies": anomalies,
        "total_tasks": total_tasks,
        "completed": completed,
        "ready": ready,
        "in_progress": in_progress,
        "pending": pending,
        "completion_rate": round(completion_rate, 1),
        "avg_completion_ratio": round(avg_completion_ratio, 2),
        "member_rows": member_rows,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **{key: value for key, value in data.items() if key not in ["months", "member_rows"]},
            "rows": [{
                "name": row["employee"].username,
                "hours": row["hours"],
                "completed": row["completed"],
                "total_tasks": row["total_tasks"],
                "absences": row["absences"],
                "anomalies": row["anomalies"],
                "search": row["employee"].username,
            } for row in member_rows],
        })

    return render(request, "manager_analytics.html", data)


@login_required
def manager_anomalies(request):
    if request.user.role != 'MANAGER':
        return redirect('employee_anomalies')

    today = timezone.now().date()
    team_profiles = manager_team_queryset(request.user)
    team_users = [profile.user for profile in team_profiles]
    months, join_month = build_month_choices(manager_team_start_date(request.user, today), today)
    selected_month, month_start, month_end = parse_selected_month(request, join_month, today)

    grouped_anomalies = []
    total_anomalies = 0
    affected_employees = 0

    for profile in team_profiles:
        anomalies = list(Attendance.objects.filter(
            user=profile.user,
            date__gte=month_start,
            date__lte=month_end,
            is_anomaly=True
        ).order_by("-date"))

        total_anomalies += len(anomalies)

        if anomalies:
            affected_employees += 1
            grouped_anomalies.append({
                "profile": profile,
                "anomalies": anomalies,
                "count": len(anomalies),
                "hours": round(sum(a.worked_hours or 0 for a in anomalies), 2),
            })

    employee_summaries = []
    for profile in team_profiles:
        employee_count = Attendance.objects.filter(
            user=profile.user,
            date__gte=month_start,
            date__lte=month_end,
            is_anomaly=True
        ).count()

        employee_summaries.append({
            "profile": profile,
            "count": employee_count,
        })

    data = {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "team_count": len(team_users),
        "total_anomalies": total_anomalies,
        "affected_employees": affected_employees,
        "clear_employees": len(team_users) - affected_employees,
        "grouped_anomalies": grouped_anomalies,
        "employee_summaries": employee_summaries,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **{key: value for key, value in data.items() if key not in ["months", "grouped_anomalies", "employee_summaries"]},
            "summaries": [{
                "name": row["profile"].user.username,
                "position": row["profile"].position or "Employee",
                "count": row["count"],
                "search": f"{row['profile'].user.username} {row['profile'].position or 'Employee'}",
            } for row in employee_summaries],
            "groups": [{
                "name": group["profile"].user.username,
                "position": group["profile"].position or "Employee",
                "department": group["profile"].department or "",
                "count": group["count"],
                "hours": group["hours"],
                "anomalies": [serialize_anomaly(anomaly) for anomaly in group["anomalies"]],
            } for group in grouped_anomalies],
        })

    return render(request, "manager_anomalies.html", data)

@login_required
def employee_analytics(request):
    user = request.user

    today = timezone.now().date()

    join_date = user.date_joined.date()
    month_cursor = date(today.year, today.month, 1)
    join_month = date(join_date.year, join_date.month, 1)

    months = []

    while month_cursor >= join_month:
        months.append({
            "value": month_cursor.strftime("%Y-%m"),
            "label": month_cursor.strftime("%B %Y"),
        })

        if month_cursor.month == 1:
            month_cursor = date(month_cursor.year - 1, 12, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month - 1, 1)

    selected_month = request.GET.get("month", today.strftime("%Y-%m"))

    try:
        selected_year, selected_month_number = map(int, selected_month.split("-"))
    except ValueError:
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")

    selected_month_date = date(selected_year, selected_month_number, 1)

    if selected_month_date < join_month or selected_month_date > date(today.year, today.month, 1):
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")
        selected_month_date = date(selected_year, selected_month_number, 1)

    month_start = date(selected_year, selected_month_number, 1)
    last_day = calendar.monthrange(selected_year, selected_month_number)[1]
    month_end = date(selected_year, selected_month_number, last_day)

    if selected_year == today.year and selected_month_number == today.month:
        month_end = today

    month_start_datetime = timezone.make_aware(
        datetime.combine(month_start, time.min),
        timezone.get_current_timezone()
    )

    month_end_datetime = timezone.make_aware(
        datetime.combine(month_end, time.max),
        timezone.get_current_timezone()
    )

    attendance = user.attendance_set.filter(
        date__gte=month_start,
        date__lte=month_end
    )

    total_working_days = attendance.filter(
        status__in=["PRESENT", "WORKING_HOLIDAY", "LOW_HOURS"]
    ).count()

    total_hours = attendance.aggregate(Sum("worked_hours"))["worked_hours__sum"] or 0
    avg_hours = total_hours / total_working_days if total_working_days else 0
    anomalies = attendance.filter(is_anomaly=True).count()
    salary_adjustment = calculate_salary_adjustment(user, attendance, month_start, month_end)

    tasks = user.tasks.filter(
        updated_at__gte=month_start_datetime,
        updated_at__lte=month_end_datetime
    )

    completed = tasks.filter(status="DONE").count()
    in_progress = tasks.filter(status="IN_PROGRESS").count()
    pending = tasks.filter(status="PENDING").count()

    total_tasks = tasks.count()

    completion_rate = (completed / total_tasks * 100) if total_tasks else 0
    in_progress_rate = (in_progress / total_tasks * 100) if total_tasks else 0
    pending_rate = (pending / total_tasks * 100) if total_tasks else 0

    commits = user.taskcommit_set.filter(
        created_at__gte=month_start_datetime,
        created_at__lte=month_end_datetime
    )

    total_commits = commits.count()

    active_days = len({
        commit.created_at.date()
        for commit in commits
    })

    commits_per_day = total_commits / active_days if active_days else 0

    if avg_hours > 6:
        trend = "strong"
        trend_class = "positive"
    elif avg_hours > 4:
        trend = "moderate"
        trend_class = "moderate"
    else:
        trend = "needs attention"
        trend_class = "low"

    data = {
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),

        "total_days": total_working_days,
        "total_hours": round(total_hours, 2),
        "avg_hours": round(avg_hours, 2),
        "anomalies": anomalies,

        "total_tasks": total_tasks,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "completion_rate": round(completion_rate, 1),
        "in_progress_rate": round(in_progress_rate, 1),
        "pending_rate": round(pending_rate, 1),

        "total_commits": total_commits,
        "commits_per_day": round(commits_per_day, 2),
        "active_days": active_days,

        "trend": trend,
        "trend_class": trend_class,
        **salary_adjustment,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(data)

    return render(request, "analytics.html", {
        **data,
        "months": months,
    })

@login_required
def employee_anomalies(request):
    user = request.user
    today = timezone.now().date()

    join_date = user.date_joined.date()
    month_cursor = date(today.year, today.month, 1)
    join_month = date(join_date.year, join_date.month, 1)

    months = []

    while month_cursor >= join_month:
        months.append({
            "value": month_cursor.strftime("%Y-%m"),
            "label": month_cursor.strftime("%B %Y"),
        })

        if month_cursor.month == 1:
            month_cursor = date(month_cursor.year - 1, 12, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month - 1, 1)

    selected_month = request.GET.get("month", today.strftime("%Y-%m"))

    try:
        selected_year, selected_month_number = map(int, selected_month.split("-"))
    except ValueError:
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")

    selected_month_date = date(selected_year, selected_month_number, 1)

    if selected_month_date < join_month or selected_month_date > date(today.year, today.month, 1):
        selected_year = today.year
        selected_month_number = today.month
        selected_month = today.strftime("%Y-%m")
        selected_month_date = date(selected_year, selected_month_number, 1)

    month_start = date(selected_year, selected_month_number, 1)
    last_day = calendar.monthrange(selected_year, selected_month_number)[1]
    month_end = date(selected_year, selected_month_number, last_day)

    if selected_year == today.year and selected_month_number == today.month:
        month_end = today

    anomalies = user.attendance_set.filter(
        date__gte=month_start,
        date__lte=month_end,
        is_anomaly=True
    ).order_by("-date")

    data = {
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "anomalies_count": anomalies.count(),
        "anomalies": anomalies,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            **data,
            "anomalies": [serialize_anomaly(anomaly) for anomaly in anomalies],
        })

    return render(request, "anomalies.html", {
        **data,
        "months": months,
    })
