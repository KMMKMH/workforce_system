from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import Holiday, LeaveRequest, PayrollAdjustment, Profile, Task, User

PASSWORD_FIELD_ATTRS = {
    "autocomplete": "new-password",
    "readonly": "readonly",
    "onfocus": "this.removeAttribute('readonly')",
}

class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['address']


class HRCreationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS))

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")

        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("That email address is already used.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        if password:
            try:
                validate_password(password)
            except forms.ValidationError as error:
                self.add_error("password", error)

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            role="HR",
            is_staff=False,
            is_superuser=False,
        )
        user.profile.position = "Human Resources"
        user.profile.department = "HR"
        user.profile.save(update_fields=["position", "department"])
        return user


class HRUpdateForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS), required=False)
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if User.objects.exclude(pk=self.user.pk).filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")

        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()

        if User.objects.exclude(pk=self.user.pk).filter(email=email).exists():
            raise forms.ValidationError("That email address is already used.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password or confirm_password:
            if password != confirm_password:
                self.add_error("confirm_password", "Passwords do not match.")

            if password:
                try:
                    validate_password(password, user=self.user)
                except forms.ValidationError as error:
                    self.add_error("password", error)

        return cleaned_data

    def save(self):
        self.user.username = self.cleaned_data["username"]
        self.user.email = self.cleaned_data["email"]

        update_fields = ["username", "email"]
        if self.cleaned_data.get("password"):
            self.user.set_password(self.cleaned_data["password"])
            update_fields.append("password")

        self.user.save(update_fields=update_fields)
        return self.user


class HRStaffCreationForm(forms.Form):
    ROLE_CHOICES = [
        ("EMPLOYEE", "Employee"),
        ("MANAGER", "Manager"),
    ]

    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    phone = forms.CharField(max_length=15, required=False)
    department = forms.CharField(max_length=100, required=False)
    position = forms.CharField(max_length=100, required=False)
    salary = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    manager = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = User.objects.filter(role="MANAGER", is_active=True).order_by("username")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("That email address is already used.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        manager = cleaned_data.get("manager")
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if role == "EMPLOYEE" and not manager:
            self.add_error("manager", "Employees must be assigned to a manager.")

        if role == "MANAGER":
            cleaned_data["manager"] = None

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        if password:
            try:
                validate_password(password)
            except forms.ValidationError as error:
                self.add_error("password", error)

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            role=self.cleaned_data["role"],
            phone=self.cleaned_data.get("phone") or "",
            is_staff=False,
            is_superuser=False,
        )
        profile = user.profile
        profile.department = self.cleaned_data.get("department")
        profile.position = self.cleaned_data.get("position")
        profile.salary = self.cleaned_data.get("salary")
        profile.manager = self.cleaned_data.get("manager")
        profile.biometric_enabled = 1
        profile.save(update_fields=["department", "position", "salary", "manager" ,"biometric_enabled"])
        return user


class HRStaffUpdateForm(HRStaffCreationForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS), required=False)
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=PASSWORD_FIELD_ATTRS), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.exclude(pk=self.user.pk).filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.exclude(pk=self.user.pk).filter(email=email).exists():
            raise forms.ValidationError("That email address is already used.")
        return email

    def save(self):
        self.user.username = self.cleaned_data["username"]
        self.user.email = self.cleaned_data["email"]
        self.user.role = self.cleaned_data["role"]
        self.user.phone = self.cleaned_data.get("phone") or ""

        update_fields = ["username", "email", "role", "phone"]
        if self.cleaned_data.get("password"):
            self.user.set_password(self.cleaned_data["password"])
            update_fields.append("password")

        self.user.save(update_fields=update_fields)

        profile = self.user.profile
        profile.department = self.cleaned_data.get("department")
        profile.position = self.cleaned_data.get("position")
        profile.salary = self.cleaned_data.get("salary")
        profile.manager = self.cleaned_data.get("manager") if self.user.role == "EMPLOYEE" else None
        profile.save(update_fields=["department", "position", "salary", "manager"])
        return self.user


class PayrollBonusForm(forms.ModelForm):
    month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
    )

    class Meta:
        model = PayrollAdjustment
        fields = ["user", "amount", "reason", "month"]
        labels = {
            "amount": "Adjustment Amount",
        }
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_month = timezone.now().date().replace(day=1)
        self.fields["user"].queryset = User.objects.filter(
            role__in=["MANAGER", "EMPLOYEE"],
            is_active=True
        ).order_by("username")
        self.fields["user"].empty_label = "Select staff member"
        self.fields["month"].widget.attrs["min"] = current_month.strftime("%Y-%m")

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_month(self):
        month = self.cleaned_data["month"].replace(day=1)
        current_month = timezone.now().date().replace(day=1)

        if month < current_month:
            raise forms.ValidationError("Adjustments can only be added for the current month or future months.")

        return month

    def clean_amount(self):
        amount = self.cleaned_data["amount"]

        if amount == 0:
            raise forms.ValidationError("Adjustment amount cannot be zero.")

        return amount

    def save(self, commit=True, created_by=None):
        adjustment = super().save(commit=False)
        adjustment.adjustment_type = (
            PayrollAdjustment.DEDUCTION
            if adjustment.amount < 0
            else PayrollAdjustment.BONUS
        )

        if created_by:
            adjustment.created_by = created_by

        if commit:
            adjustment.save()

        return adjustment


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["date", "end_date", "reason"]
        labels = {
            "date": "Start Date",
            "end_date": "End Date",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 4, "placeholder": "Reason for leave"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        tomorrow = timezone.now().date() + timezone.timedelta(days=1)
        self.fields["date"].widget.attrs["min"] = tomorrow.strftime("%Y-%m-%d")
        self.fields["end_date"].widget.attrs["min"] = tomorrow.strftime("%Y-%m-%d")

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("date")
        end_date = cleaned_data.get("end_date") or start_date
        tomorrow = timezone.now().date() + timezone.timedelta(days=1)

        if not start_date:
            return cleaned_data

        range_is_valid = True
        if start_date < tomorrow:
            self.add_error("date", "Leave requests can only be made for tomorrow or future dates.")
            range_is_valid = False

        if end_date < start_date:
            self.add_error("end_date", "End date cannot be before the start date.")
            range_is_valid = False

        if (end_date - start_date).days > 30:
            self.add_error("end_date", "Leave requests can be at most 1 month long.")
            range_is_valid = False

        if range_is_valid:
            holidays = set(
                Holiday.objects.filter(
                    date__gte=start_date,
                    date__lte=end_date
                ).values_list("date", flat=True)
            )
            cursor = start_date
            has_working_day = False
            while cursor <= end_date:
                if cursor.weekday() < 5 and cursor not in holidays:
                    has_working_day = True
                    break
                cursor += timezone.timedelta(days=1)

            if not has_working_day:
                raise forms.ValidationError("The selected period is already non-working days.")

        if self.user and range_is_valid:
            overlaps = LeaveRequest.objects.filter(
                user=self.user,
                date__lte=end_date,
                end_date__gte=start_date,
            )
            if overlaps.exists():
                raise forms.ValidationError("You already have a leave request overlapping this period.")

        cleaned_data["end_date"] = end_date
        return cleaned_data

    def save(self, commit=True):
        leave_request = super().save(commit=False)

        if self.user:
            leave_request.user = self.user

        if commit:
            leave_request.save()

        return leave_request


class ManagerTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'status', 'deadline', 'estimated_hours']
        widgets = {
            'deadline': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].input_formats = ['%Y-%m-%dT%H:%M']
        employee_only_statuses = ['IN_PROGRESS', 'READY']
        self.fields['status'].choices = [
            choice for choice in self.fields['status'].choices
            if choice[0] not in employee_only_statuses
        ]

        if self.instance.pk and self.instance.status in employee_only_statuses:
            self.fields['status'].choices = [
                (self.instance.status, self.instance.get_status_display())
            ] + list(self.fields['status'].choices)
            self.fields['status'].disabled = True
            self.fields['status'].help_text = "This status is controlled by the employee workflow."

        if manager:
            self.fields['assigned_to'].queryset = User.objects.filter(
                profile__manager=manager,
                role='EMPLOYEE'
            ).order_by('username')

        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class CEOTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'status', 'deadline', 'estimated_hours']
        widgets = {
            'deadline': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].input_formats = ['%Y-%m-%dT%H:%M']
        manager_only_statuses = ['IN_PROGRESS', 'READY']
        self.fields['status'].choices = [
            choice for choice in self.fields['status'].choices
            if choice[0] not in manager_only_statuses
        ]

        if self.instance.pk and self.instance.status in manager_only_statuses:
            self.fields['status'].choices = [
                (self.instance.status, self.instance.get_status_display())
            ] + list(self.fields['status'].choices)
            self.fields['status'].disabled = True
            self.fields['status'].help_text = "This status is controlled by the manager's personal workflow."

        self.fields['assigned_to'].queryset = User.objects.filter(
            role='MANAGER'
        ).order_by('username')

        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
