from django.utils import timezone
from django.contrib.auth import logout
from django.shortcuts import redirect
from core.models import Attendance
from core.utils.attendance import handle_no_checkout

class AttendanceCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.role in ['CEO', 'HR', 'ACCOUNTANT']:
                return self.get_response(request)

            today = timezone.now().date()

            last_record = (
                Attendance.objects
                .filter(user=request.user)
                .order_by('-date')
                .first()
            )

            if (
                last_record
                and last_record.date < today
                and last_record.check_in
                and not last_record.check_out
            ):

                logout(request)
                request.session.flush()

                return redirect('login')

        return self.get_response(request)