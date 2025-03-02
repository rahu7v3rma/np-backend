from rest_framework import serializers

from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    first_login = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'
