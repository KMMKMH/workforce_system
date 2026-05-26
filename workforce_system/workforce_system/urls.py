"""
URL configuration for workforce_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.urls import path
from core.views import add_task_commit, add_task_images, calendar_view, ceo_analytics, ceo_anomalies, ceo_calendar_view, ceo_dashboard, ceo_delete_task, ceo_edit_task, ceo_staff_management, chat_messages, chat_send_message, chat_unread_status, chat_view, dashboard, delete_task_image, edit_commit, delete_commit, employee_analytics, employee_anomalies, hr_accountant, hr_add_bonus, hr_analytics, hr_attendance_calendar, hr_dashboard, hr_leave_requests, hr_staff_management, leave_request_view, login_view, face_verify, face_register, manager_analytics, manager_anomalies, manager_calendar_view, manager_dashboard, manager_delete_task, manager_edit_task, profile_cv, task_detail, update_task_status, profile_view
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', login_view, name='login'),
    path('face/register/', face_register, name='face_register'),
    path('face/verify/', face_verify, name='face_verify'),
    path('dashboard/', dashboard, name='dashboard'),
    path('ceo/dashboard/', ceo_dashboard, name='ceo_dashboard'),
    path('ceo/analytics/', ceo_analytics, name='ceo_analytics'),
    path('ceo/anomalies/', ceo_anomalies, name='ceo_anomalies'),
    path('ceo/calendar/', ceo_calendar_view, name='ceo_calendar'),
    path('ceo/staff/', ceo_staff_management, name='ceo_staff_management'),
    path('ceo/tasks/<int:task_id>/edit/', ceo_edit_task, name='ceo_edit_task'),
    path('ceo/tasks/<int:task_id>/delete/', ceo_delete_task, name='ceo_delete_task'),
    path('hr/dashboard/', hr_dashboard, name='hr_dashboard'),
    path('hr/staff/', hr_staff_management, name='hr_staff_management'),
    path('hr/analytics/', hr_analytics, name='hr_analytics'),
    path('hr/accountant/', hr_accountant, name='hr_accountant'),
    path('hr/accountant/bonus/add/', hr_add_bonus, name='hr_add_bonus'),
    path('hr/attendance-calendar/', hr_attendance_calendar, name='hr_attendance_calendar'),
    path('hr/leave-requests/', hr_leave_requests, name='hr_leave_requests'),
    path('leave/request/', leave_request_view, name='leave_request'),
    path('chat/', chat_view, name='chat'),
    path('chat/<int:conversation_id>/messages/', chat_messages, name='chat_messages'),
    path('chat/<int:conversation_id>/send/', chat_send_message, name='chat_send_message'),
    path('chat/unread-status/', chat_unread_status, name='chat_unread_status'),
    path('tasks/update/', update_task_status, name='update_task_status'),
    path('manager/dashboard/', manager_dashboard, name='manager_dashboard'),
    path('manager/tasks/<int:task_id>/edit/', manager_edit_task, name='manager_edit_task'),
    path('manager/tasks/<int:task_id>/delete/', manager_delete_task, name='manager_delete_task'),
    path('manager/calendar/', manager_calendar_view, name='manager_calendar'),
    path('calendar/', calendar_view, name='calendar'),
    path("tasks/<int:task_id>/", task_detail, name="task_detail"),
    path("tasks/<int:task_id>/commit/", add_task_commit, name="add_task_commit"),
    path("tasks/<int:task_id>/images/", add_task_images, name="add_task_images"),
    path("tasks/images/<int:image_id>/delete/", delete_task_image, name="delete_task_image"),
    path("commits/<int:commit_id>/delete/", delete_commit, name="delete_commit"),
    path("commits/<int:commit_id>/edit/", edit_commit, name="edit_commit"),
    path("profile/", profile_view, name="profile"),
    path("profile/cv/", profile_cv, name="profile_cv"),
    path("analytics/", employee_analytics, name="employee_analytics"),
    path("manager/analytics/", manager_analytics, name="manager_analytics"),
    path("manager/anomalies/", manager_anomalies, name="manager_anomalies"),
    path("analytics/anomalies/", employee_anomalies, name="employee_anomalies"),
    path('password/change/', PasswordChangeView.as_view(
        template_name='registration/password_change_form.html'
    ), name='password_change'),

    path('password/change/done/', PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'
    ), name='password_change_done'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
