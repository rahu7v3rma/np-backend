from django import forms

from campaign.models import EmployeeGroup


class EmployeeGroupForm(forms.ModelForm):
    class Meta:
        model = EmployeeGroup
        fields = '__all__'
