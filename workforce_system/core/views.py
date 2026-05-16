from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import localtime
from django.http import JsonResponse
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum
from datetime import datetime, time, date
import json, cv2, base64, ast, random, calendar
import numpy as np

from deepface import DeepFace
from core.utils.helpers import ensure_holidays_exist, get_head_turn_direction
from core.utils.attendance import auto_fix_attendance, handle_check_in, handle_check_out
from core.models import Attendance, Task, Holiday, TaskCommit, User
from core.data.display import STATUS_DISPLAY
from core.forms import EmployeeProfileForm, ManagerTaskForm, CEOTaskForm


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


def manager_users_queryset():
    return User.objects.filter(
        role='MANAGER'
    ).order_by('username')


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
    
    user = request.user
    today = timezone.now().date()

    attendance = Attendance.objects.filter(
        user=user,
        date=today
    ).first()

    tasks = Task.objects.filter(
        assigned_to=user
    ).exclude(status="DONE")

    raw_status = attendance.status if attendance else "OFFLINE"
    status = STATUS_DISPLAY.get(raw_status, raw_status)
    alerts = attendance.anomaly_reason if attendance and attendance.is_anomaly else None

    context = {
        "status": status,
        "tasks": tasks,
        "tasks_count": tasks.count(),
        "alert": alerts,
        "show_manager_portal": user.role == "MANAGER",
    }

    return render(request, "dashboard.html", context)


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
    team_tasks = all_team_tasks.exclude(status='DONE')
    completed_team_tasks = all_team_tasks.filter(status='DONE')

    open_tasks = team_tasks.count()
    ready_tasks = team_tasks.filter(status='READY').count()
    completed_tasks = completed_team_tasks.count()
    online_count = sum(1 for row in attendance_rows if row["is_online"])
    anomaly_count = sum(1 for row in attendance_rows if row["alert"])

    return render(request, "manager_dashboard.html", {
        "task_form": task_form,
        "member_rows": member_rows,
        "attendance_rows": attendance_rows,
        "team_tasks": team_tasks,
        "completed_team_tasks": completed_team_tasks,
        "team_count": len(team_users),
        "open_tasks": open_tasks,
        "ready_tasks": ready_tasks,
        "completed_tasks": completed_tasks,
        "online_count": online_count,
        "anomaly_count": anomaly_count,
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
    manager_tasks = all_manager_tasks.exclude(status='DONE')
    completed_manager_tasks = all_manager_tasks.filter(status='DONE')

    open_tasks = manager_tasks.count()
    ready_tasks = manager_tasks.filter(status='READY').count()
    completed_tasks = completed_manager_tasks.count()
    online_count = sum(1 for row in attendance_rows if row["is_online"])
    anomaly_count = sum(1 for row in attendance_rows if row["alert"])

    return render(request, "ceo_dashboard.html", {
        "task_form": task_form,
        "member_rows": member_rows,
        "attendance_rows": attendance_rows,
        "manager_tasks": manager_tasks,
        "completed_manager_tasks": completed_manager_tasks,
        "manager_count": len(managers),
        "open_tasks": open_tasks,
        "ready_tasks": ready_tasks,
        "completed_tasks": completed_tasks,
        "online_count": online_count,
        "anomaly_count": anomaly_count,
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
    images = task.images.all().order_by('-uploaded_at')

    can_edit = (
        task.assigned_to == request.user and
        task.status == "IN_PROGRESS"
    )
    can_manage = user_can_review_task(request.user, task)
    can_manage_manager_task = user_can_manage_manager_task(request.user, task)
    edit_task_url_name = "ceo_edit_task" if can_manage_manager_task else "manager_edit_task"
    review_subject = "manager" if can_manage_manager_task else "employee"

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
        "images": images,
        "can_edit": can_edit,
        "can_manage": can_manage,
        "edit_task_url_name": edit_task_url_name,
        "review_subject": review_subject,
        "user_role": role,
        "back_url": back_url,
    })


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
            title = task.title
            events.append({
                "title": title,
                "start": task.deadline.strftime("%Y-%m-%dT%H:%M:%S"),
            })
    
    holidays = Holiday.objects.all()

    for holiday in holidays:
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

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
            events.append({
                "title": f"{task.assigned_to.username}: {task.title}",
                "start": task.deadline.strftime("%Y-%m-%dT%H:%M:%S"),
            })

    for holiday in Holiday.objects.all():
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

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
            events.append({
                "title": f"{task.assigned_to.username}: {task.title}",
                "start": task.deadline.strftime("%Y-%m-%dT%H:%M:%S"),
            })

    for holiday in Holiday.objects.all():
        events.append({
            "title": f"🎉 {holiday.name}",
            "start": holiday.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#28a745"
        })

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

    return render(request, "ceo_analytics.html", {
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
    })

@login_required
def profile_view(request):
    profile = request.user.profile

    if request.method == "POST":
        form = EmployeeProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
    else:
        form = EmployeeProfileForm(instance=profile)

    return render(request, "profile.html", {
        "form": form,
        "profile": profile
    })


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

    return render(request, "manager_analytics.html", {
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
    })


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

    return render(request, "manager_anomalies.html", {
        "months": months,
        "selected_month": selected_month,
        "selected_month_label": month_start.strftime("%B %Y"),
        "team_count": len(team_users),
        "total_anomalies": total_anomalies,
        "affected_employees": affected_employees,
        "clear_employees": len(team_users) - affected_employees,
        "grouped_anomalies": grouped_anomalies,
        "employee_summaries": employee_summaries,
    })

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
        anomalies_data = []

        for anomaly in anomalies:
            anomalies_data.append({
                "date": anomaly.date.strftime("%b %d, %Y"),
                "status": anomaly.status,
                "check_in": localtime(anomaly.check_in).strftime("%H:%M") if anomaly.check_in else "—",
                "check_out": localtime(anomaly.check_out).strftime("%H:%M") if anomaly.check_out else "—",
                "worked_hours": round(anomaly.worked_hours or 0, 2),
                "reason": anomaly.anomaly_reason or "No reason provided.",
            })

        return JsonResponse({
            **data,
            "anomalies": anomalies_data,
        })

    return render(request, "anomalies.html", {
        **data,
        "months": months,
    })
