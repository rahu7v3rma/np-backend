class ActiveObjectsAdminMixin:
    """
    Mixin to display active objects for staff users and all objects for superusers
    in the Django Admin.
    """

    def get_queryset(self, request):
        """
        Override the default queryset to show active objects for staff users
        and all objects for superusers.
        """
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return self.model.all_objects.all()
        else:
            return queryset
