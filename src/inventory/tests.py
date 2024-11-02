from django.contrib.admin.options import ModelAdmin
from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from inventory.models import Category


class MockRequest:
    pass


class MockSuperUser:
    def has_perm(self, perm, obj=None):
        return True


class CategoryAdminTest(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.category_admin = ModelAdmin(Category, self.site)
        self.request = MockRequest()
        self.request.user = MockSuperUser()

    def test_category_name_he_required(self):
        category_admin = ModelAdmin(Category, self.site)
        CategoryForm = category_admin.get_form(self.request)
        form = CategoryForm(data={'name': 'name en', 'name_en': 'name en'})
        self.assertFalse(form.is_valid())

    def test_category_name_en_required(self):
        category_admin = ModelAdmin(Category, self.site)
        CategoryForm = category_admin.get_form(self.request)
        form = CategoryForm(data={'name': 'name en', 'name_he': 'name he'})
        self.assertFalse(form.is_valid())

    def test_category_valid_name_en_name_he(self):
        category_admin = ModelAdmin(Category, self.site)
        CategoryForm = category_admin.get_form(self.request)
        form = CategoryForm(
            data={'name': 'name en', 'name_en': 'name en', 'name_he': 'name he'}
        )
        self.assertTrue(form.is_valid())
