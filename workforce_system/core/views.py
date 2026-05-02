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
from core.models import Attendance, Task, Holiday, TaskCommit
from core.data.display import STATUS_DISPLAY
from core.forms import EmployeeProfileForm

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
    
    user = request.user
    today = timezone.now().date()

    attendance = Attendance.objects.filter(
        user=user,
        date=today
    ).first()

    tasks = Task.objects.filter(
        assigned_to=user
    )

    raw_status = attendance.status if attendance else "OFFLINE"
    status = STATUS_DISPLAY.get(raw_status, raw_status)
    alerts = attendance.anomaly_reason if attendance and attendance.is_anomaly else None

    context = {
        "status": status,
        "tasks": tasks,
        "tasks_count": tasks.count(),
        "alert": alerts,
    }

    return render(request, "dashboard.html", context)

@csrf_exempt
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

        return JsonResponse({"error": "Not allowed"}, status=403)
    
@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    commits = task.commits.select_related('user').order_by('-created_at')
    images = task.images.all().order_by('-uploaded_at')

    can_edit = (
        task.assigned_to == request.user and
        task.status == "IN_PROGRESS"
    )

    return render(request, "task_detail.html", {
        "task": task,
        "commits": commits,
        "images": images,
        "can_edit": can_edit,
    })


@require_POST
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
            events.append({
                "title": task.title,
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