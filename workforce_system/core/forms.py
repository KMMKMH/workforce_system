from django import forms
from .models import Profile

class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['address']