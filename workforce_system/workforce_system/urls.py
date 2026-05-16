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
from django.contrib import admin
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.urls import path
from core.views import add_task_commit, calendar_view, ceo_analytics, ceo_calendar_view, ceo_dashboard, ceo_delete_task, ceo_edit_task, dashboard, edit_commit, delete_commit, employee_analytics, employee_anomalies, login_view, face_verify, face_register, manager_analytics, manager_anomalies, manager_calendar_view, manager_dashboard, manager_delete_task, manager_edit_task, task_detail, update_task_status, profile_view
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', login_view, name='login'),
    path('face/register/', face_register, name='face_register'),
    path('face/verify/', face_verify, name='face_verify'),
    path('dashboard/', dashboard, name='dashboard'),
    path('ceo/dashboard/', ceo_dashboard, name='ceo_dashboard'),
    path('ceo/analytics/', ceo_analytics, name='ceo_analytics'),
    path('ceo/calendar/', ceo_calendar_view, name='ceo_calendar'),
    path('ceo/tasks/<int:task_id>/edit/', ceo_edit_task, name='ceo_edit_task'),
    path('ceo/tasks/<int:task_id>/delete/', ceo_delete_task, name='ceo_delete_task'),
    path('tasks/update/', update_task_status, name='update_task_status'),
    path('manager/dashboard/', manager_dashboard, name='manager_dashboard'),
    path('manager/tasks/<int:task_id>/edit/', manager_edit_task, name='manager_edit_task'),
    path('manager/tasks/<int:task_id>/delete/', manager_delete_task, name='manager_delete_task'),
    path('manager/calendar/', manager_calendar_view, name='manager_calendar'),
    path('calendar/', calendar_view, name='calendar'),
    path("tasks/<int:task_id>/", task_detail, name="task_detail"),
    path("tasks/<int:task_id>/commit/", add_task_commit, name="add_task_commit"),
    path("commits/<int:commit_id>/delete/", delete_commit, name="delete_commit"),
    path("commits/<int:commit_id>/edit/", edit_commit, name="edit_commit"),
    path("profile/", profile_view, name="profile"),
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
