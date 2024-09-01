# Create your tests here.
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


TEST_USERNAME = 'testuser'
TEST_USER_PASSWORD = 'testpassword'
TEST_USER_EMAIL = 'testemail@gmail.com'


@patch('custom_admin.sites.send_otp_token_email', return_value=True)
@override_settings(
    OTP_ADMIN_ENABLED=True,
    OTP_FERNET_KEY='Hl6CtIScGfLXD5ukyIiqLUrGlyNCWKj8cwodOjStgMk=',
)
@override_settings(ALLOWED_HOSTS=['testserver'])
class CmsAdminLogin(TestCase):
    def tearDown(self):
        pass

    def setUp(self):
        self.user = get_user_model().objects.create(
            username=TEST_USERNAME,
            email=TEST_USER_EMAIL,
            is_superuser=True,
            is_staff=True,
        )
        self.user.set_password(TEST_USER_PASSWORD)
        self.user.save()

    def test_correct_login_correct_otp(self, _mock):
        client = Client()
        response = client.post(
            '/admin/login/',
            {'username': TEST_USERNAME, 'password': TEST_USER_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/confirm-2fa/')
        client.get('/admin/confirm-2fa/')
        self.assertEqual(_mock.call_args[0][0], TEST_USER_EMAIL)
        response = client.post('/admin/confirm-2fa/', {'otp': _mock.call_args[0][1]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')
        response = client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome to the Nicklas+ Portal')

    def test_correct_login_wrong_otp(self, _mock):
        client = Client()
        response = client.post(
            '/admin/login/',
            {'username': TEST_USERNAME, 'password': TEST_USER_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/confirm-2fa/')
        client.get('/admin/confirm-2fa/')
        self.assertEqual(_mock.call_args[0][0], TEST_USER_EMAIL)
        response = client.post('/admin/confirm-2fa/', {'otp': '111111'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid 2FA code')

        # check that the user could not visit the protected links
        response = client.get('/admin/password_change/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/login/?next=/admin/password_change/')

    def test_wrong_login(self, _mock):
        client = Client()
        response = client.post(
            '/admin/login/', {'username': TEST_USERNAME, 'password': '123456'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter the correct username and password')
        self.assertEqual(_mock.call_count, 0)
