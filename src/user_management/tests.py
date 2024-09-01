import json
import logging
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.urls import resolve
from rest_framework.test import APIClient

from user_management import views
from user_management.models import ResetPasswordToken


logger = logging.getLogger(__name__)


TEST_USER_EMAIL = 'testmail@test.test'
TEST_USER_WRONG_EMAIL = 'testwrongmail@test.test'
TEST_USER_WRONG_PASSWORD = 'testwrongpassword'
TEST_USER_USERNAME = 'testname'
TEST_USER_PASSWORD = 'testpassword'
TEST_USER_NEW_PASSWORD = 'testnewpassword'


class LoginTestCase(TestCase):
    def tearDown(self):
        get_user_model().objects.get(email=TEST_USER_EMAIL).delete()
        self.user.delete()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()

    def test_root_url_resolves_to_login(self):
        found = resolve('/user/login')
        self.assertEqual(found.func.__name__, views.UserLoginView.as_view().__name__)

    def test_login_authentication_with_succesful_login(self):
        client = APIClient()

        response = client.post(
            '/user/login',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)

        json_string = response.content.decode(encoding='UTF-8')
        user_data = json.loads(json_string)
        self.assertEqual(user_data['data']['username'], TEST_USER_USERNAME)
        self.assertEqual(user_data['data']['email'], TEST_USER_EMAIL)
        self.assertIn('auth_token', user_data['data'])

    def test_login_authentication_with_failed_login(self):
        client = APIClient()

        response = client.post(
            '/user/login',
            format='json',
            data={'email': TEST_USER_EMAIL, 'password': 'wrongpassword'},
        )

        self.assertEqual(response.status_code, 401)

        json_string = response.content.decode(encoding='UTF-8')
        user_data = json.loads(json_string)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(user_data['message'], 'Bad credentials.')

    def test_logout_authentication_with_success(self):
        client = APIClient()

        response = client.post(
            '/user/login',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD,
            },
        )
        user_data = json.loads(response.content.decode(encoding='UTF-8'))

        client = APIClient()
        client.credentials(
            HTTP_X_AUTHORIZATION='Token ' + user_data['data']['auth_token']
        )
        response = client.post('/user/logout')

        self.assertEqual(response.status_code, 200)


class SignUpTestCase(TestCase):
    def tearDown(self):
        self.user.delete()

    def setUp(self):
        self.user = get_user_model().objects.create(
            email='user@test.test',
            username='user@test.test',
            password='user_pass',
        )

    def test_create_new_user(self):
        client = APIClient()
        response = client.post(
            '/user/sign-up',
            format='json',
            data={
                'first_name': 'first_name',
                'last_name': 'last_name',
                'email': 'new_user@test.test',
                'password': 'hzfQvPfG',
            },
        )
        self.assertEqual(response.status_code, 200)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(response_data['message'], 'User successfully created.')
        user1 = get_user_model().objects.get(email='new_user@test.test')
        self.assertEqual(user1.username, 'new_user@test.test')
        self.assertEqual(user1.first_name, 'first_name')
        self.assertEqual(user1.last_name, 'last_name')

    def test_create_user_with_email_already_exists(self):
        client = APIClient()
        with transaction.atomic():
            response = client.post(
                '/user/sign-up',
                format='json',
                data={
                    'first_name': 'first_name',
                    'last_name': 'last_name',
                    'email': 'user@test.test',
                    'password': 'hzfQvPfG',
                },
            )
        self.assertEqual(response.status_code, 401)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(response_data['message'], 'Email already exists.')


class ChangePasswordTestCase(TestCase):
    def tearDown(self):
        get_user_model().objects.get(email=TEST_USER_EMAIL).delete()
        self.user.delete()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()

    def test_change_password_wrong_password(self):
        client = APIClient()

        response = client.post(
            '/user/login',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD,
            },
        )
        user_data = json.loads(response.content.decode(encoding='UTF-8'))
        client.credentials(
            HTTP_X_AUTHORIZATION='Token ' + user_data['data']['auth_token']
        )

        response = client.post(
            '/user/change-password',
            format='json',
            data={
                'new_password': TEST_USER_NEW_PASSWORD,
                'old_password': TEST_USER_WRONG_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 401)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(response_data['message'], 'Bad credentials.')

    def test_change_password(self):
        # check the user password
        self.assertTrue(self.user.check_password(TEST_USER_PASSWORD))
        client = APIClient()
        response = client.post(
            '/user/login',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD,
            },
        )
        user_data = json.loads(response.content.decode(encoding='UTF-8'))
        client.credentials(
            HTTP_X_AUTHORIZATION='Token ' + user_data['data']['auth_token']
        )
        response = client.post(
            '/user/change-password',
            format='json',
            data={
                'new_password': TEST_USER_NEW_PASSWORD,
                'old_password': TEST_USER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(response_data['message'], 'Password changed successfully.')
        # check that the password and the token have been changed
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(TEST_USER_PASSWORD))
        self.assertTrue(self.user.check_password(TEST_USER_NEW_PASSWORD))
        self.assertEqual(
            response_data.get('data').get('new_token'),
            self.user.auth_token.key,
        )


class ResetPasswordTestCase(TestCase):
    def tearDown(self):
        get_user_model().objects.get(email=TEST_USER_EMAIL).delete()
        self.user.delete()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()

    def test_reset_password_with_wrong_email(self):
        client = APIClient()

        with self.assertLogs('user_management.views', level='INFO') as log:
            response = client.post(
                '/user/reset/request',
                format='json',
                data={
                    'email': TEST_USER_WRONG_EMAIL,
                },
            )

            self.assertEqual(response.status_code, 200)

            self.assertIn(
                f'INFO:user_management.views:reset password '
                f'request attempt with non-existing email: {TEST_USER_WRONG_EMAIL}',
                log.output,
            )

    def test_reset_password_with_invalid_request_data(self):
        response = self.client.post(
            '/user/reset/request',
            data=json.dumps({'email': 'not-an-email'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)
        self.assertEqual(response.data['message'], 'Request is invalid.')
        self.assertEqual(response.data['code'], 'request_invalid')

    @mock.patch('user_management.views.send_reset_password_email')
    def test_reset_password_with_unsupported_media_type(self, mock_send_email):
        mock_send_email.return_value = True

        response = self.client.post(
            '/user/reset/request',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
            },
            HTTP_USER_AGENT='TestUserAgent/1.0',
            REMOTE_ADDR='127.0.0.1',
        )

        self.assertEqual(response.status_code, 415)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(
            response_data['detail'],
            'Unsupported media type "multipart/form-data;'
            ' boundary=BoUnDaRyStRiNg" in request.',
        )
        self.assertFalse(mock_send_email.called)

    @mock.patch('user_management.views.logger')
    def test_reset_password_logs_non_existing_email(self, mock_logger):
        response = self.client.post(
            '/user/reset/request',
            format='json',
            data={
                'email': TEST_USER_WRONG_EMAIL,
            },
            content_type='application/json',
            HTTP_USER_AGENT='TestUserAgent/1.0',
            REMOTE_ADDR='127.0.0.1',
        )

        self.assertEqual(response.status_code, 200)
        mock_logger.info.assert_called_with(
            'reset password request attempt with non-existing email: %s',
            TEST_USER_WRONG_EMAIL,
        )

    @mock.patch('user_management.views.send_reset_password_email')
    def test_reset_password_with_valid_email(self, mock_send_email):
        mock_send_email.return_value = True

        response = self.client.post(
            '/user/reset/request',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
            },
            content_type='application/json',
            HTTP_USER_AGENT='TestUserAgent/1.0',
            REMOTE_ADDR='127.0.0.1',
        )

        self.assertEqual(response.status_code, 200)
        json_string = response.content.decode(encoding='UTF-8')
        response_data = json.loads(json_string)
        self.assertEqual(
            response_data['message'],
            'Reset password token requested successfully.',
        )
        self.assertTrue(mock_send_email.called)


class ResetPasswordVerifyTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()
        self.reset_password_token = ResetPasswordToken.objects.create(
            user=self.user,
            token='valid_token',
            ip_address='127.0.0.1',
            user_agent='TestUserAgent/1.0',
        )

    def tearDown(self):
        self.user.delete()
        ResetPasswordToken.objects.all().delete()

    @mock.patch('user_management.views.logger')
    def test_reset_password_verify_invalid_request(self, mock_logger):
        response = self.client.post(
            '/user/reset/verify',
            data=json.dumps({'token': 'test token'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)
        self.assertEqual(response.data['message'], 'Invalid or expired token.')
        mock_logger.info.assert_called_with(
            'reset password verify attempt with non-existing token: %s', 'test token'
        )
        self.assertEqual(response.data['code'], 'bad_token')

    def test_reset_password_verify_without_token(self):
        response = self.client.post(
            '/user/reset/verify',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)
        self.assertEqual(response.data['message'], 'Request is invalid.')
        self.assertEqual(response.data['code'], 'request_invalid')

    def test_reset_password_verify_valid_request(self):
        with mock.patch.object(ResetPasswordToken, 'verify', return_value=True):
            response = self.client.post(
                '/user/reset/verify',
                format='json',
                data={'token': 'valid_token'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['success'], True)
            self.assertEqual(response.data['message'], 'Token verified successfully.')


class ResetPasswordConfirmTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()
        self.reset_password_token = ResetPasswordToken.objects.create(
            user=self.user,
            token='valid_token',
            ip_address='127.0.0.1',
            user_agent='TestUserAgent/1.0',
        )

    def tearDown(self):
        self.user.delete()
        ResetPasswordToken.objects.all().delete()

    @mock.patch('user_management.views.logger')
    def test_reset_password_confirm_invalid_token(self, mock_logger):
        response = self.client.post(
            '/user/reset/confirm',
            format='json',
            data={'token': 'test token', 'password': 'test@test123'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)
        self.assertEqual(response.data['message'], 'Invalid or expired token.')
        mock_logger.info.assert_called_with(
            'reset password confirm attempt with non-existing token: %s', 'test token'
        )
        self.assertEqual(response.data['code'], 'bad_token')

    def test_reset_password_confirm_without_password(self):
        response = self.client.post(
            '/user/reset/confirm',
            format='json',
            data={'token': 'valid_token'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)
        self.assertEqual(response.data['message'], 'Request is invalid.')
        self.assertEqual(response.data['code'], 'request_invalid')

    def test_reset_password_confirm_invalid_password(self):
        with mock.patch.object(ResetPasswordToken, 'verify', return_value=True):
            response = self.client.post(
                '/user/reset/confirm',
                format='json',
                data={'token': 'valid_token', 'password': 'test123'},
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['success'], False)
            self.assertEqual(response.data['message'], 'Request is invalid.')
            self.assertEqual(response.data['code'], 'password_does_not_conform')

    @mock.patch('user_management.views.logger')
    def test_reset_password_confirm_with_invalid_request(self, mock_logger):
        with mock.patch.object(ResetPasswordToken, 'verify', return_value=False):
            response = self.client.post(
                '/user/reset/confirm',
                format='json',
                data={'token': 'valid_token', 'password': 'test@test123'},
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['success'], False)
            self.assertEqual(response.data['message'], 'Invalid or expired token.')
            mock_logger.info.assert_called_with(
                'reset password confirm attempt with expired token: %s', 'valid_token'
            )
            self.assertEqual(response.data['code'], 'bad_token')

    def test_reset_password_confirm_valid_request(self):
        with mock.patch.object(ResetPasswordToken, 'verify', return_value=True):
            response = self.client.post(
                '/user/reset/confirm',
                format='json',
                data={'token': 'valid_token', 'password': 'test@test123'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['success'], True)
            self.assertEqual(response.data['message'], 'Password changed successfully.')


class UserLogoutViewTestCase(TestCase):
    def tearDown(self):
        get_user_model().objects.get(email=TEST_USER_EMAIL).delete()
        self.user.delete()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email=TEST_USER_EMAIL,
            username=TEST_USER_USERNAME,
            password=TEST_USER_PASSWORD,
        )
        self.user.save()

    def test_logout_successfully_logout(self):
        client = APIClient()

        response = client.post(
            '/user/login',
            format='json',
            data={
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD,
            },
        )
        user_data = json.loads(response.content.decode(encoding='UTF-8'))
        client.credentials(
            HTTP_X_AUTHORIZATION='Token ' + user_data['data']['auth_token']
        )
        response = client.post(
            '/user/logout',
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['success'], True)
        self.assertEqual(response.data['message'], 'User logged out successfully.')

    def test_logout_with_unauthenticated_user(self):
        response = self.client.post(
            '/user/logout',
            format='json',
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn(
            'Authentication credentials were not provided.', response.data['detail']
        )
