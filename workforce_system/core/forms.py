from django import forms
from .models import Profile, Task, User

class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['address']


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
