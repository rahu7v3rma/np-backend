import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    get_password_validators,
    validate_password,
)
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from services.email import send_reset_password_email
from user_management.models import ResetPasswordToken
from user_management.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    ResetPasswordConfirmSerializer,
    ResetPasswordRequestSerializer,
    ResetPasswordVerifySerializer,
    SignUpSerializer,
    UserSerializer,
)
from user_management.utils import InnerIsAuthenticated, hash_user_id
from user_profile.models import Profile


logger = logging.getLogger(__name__)

UserModel = get_user_model()


class UserLoginView(APIView):
    """
    Login and send token
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # parse request
        request_serializer = LoginSerializer(data=request.data)

        # make sure request data is valid
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # find user by email
        request_email = request_serializer.validated_data['email']
        try:
            user = UserModel.objects.get(email=request_email.lower())
        except UserModel.DoesNotExist:
            logger.info(
                'login attempt with non-existing email: %s',
                request_email,
            )
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials.',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # validate user password
        if not user.check_password(request_serializer['password'].value):
            logger.info(
                'login attempt with bad password for email: %s',
                request_email,
            )
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials.',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # create new token or get existing one for user (will be related to
        # the user instance)
        Token.objects.get_or_create(user=user)

        # signal that user has logged in (will update last_login value)
        user_logged_in.send(sender=user.__class__, request=request, user=user)

        # respond with user data and token
        response_serializer = UserSerializer(user)
        return Response(
            {
                'success': True,
                'message': 'User logged in successfully.',
                'status': status.HTTP_200_OK,
                'data': response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class SignUpView(APIView):
    """
    Sign up new user
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # parse request
        request_serializer = SignUpSerializer(data=request.data)

        # make sure request data is valid
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # get user request
        request_email = request_serializer.validated_data['email']
        request_first_name = request_serializer.validated_data['first_name']
        request_last_name = request_serializer.validated_data['last_name']
        request_password = request_serializer.validated_data['password']

        try:
            validate_password(
                request_password,
                password_validators=get_password_validators(
                    settings.AUTH_PASSWORD_VALIDATORS
                ),
            )
        except ValidationError as ex:
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'password_does_not_conform',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {
                        'password': ex.messages,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # create the new user
        try:
            user = UserModel.objects.create_user(
                email=request_email.lower(),
                password=request_password,
                last_name=request_last_name,
                first_name=request_first_name,
                username=request_email.lower(),
                profile=Profile(),
            )
            user.profile.save()
        except IntegrityError:
            return Response(
                {
                    'success': False,
                    'message': 'Email already exists.',
                    'code': 'email_already_exists',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # no welcome email for now
        # # send password email
        # send_password_response = send_password_email(
        #     request_email,
        #     {
        #         'name': f'{request_first_name}',
        #         'password': user_password,
        #     },
        # )

        # if not send_password_response:
        #     logger.error(
        #         "the password email couldn't be sent to : %s", request_email
        #     )

        # create new token or get existing one for user (will be related to
        # the user instance)
        Token.objects.get_or_create(user=user)

        # signal that user has logged in (will update last_login value)
        user_logged_in.send(sender=user.__class__, request=request, user=user)

        # respond with user data and token
        response_serializer = UserSerializer(user)

        return Response(
            {
                'success': True,
                'message': 'User successfully created.',
                'status': status.HTTP_200_OK,
                'data': response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UserLogoutView(APIView):
    """
    Logout an active session
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # delete auth token
        request.user.auth_token.delete()

        # signal that user has logged out
        user_logged_out.send(
            sender=request.user.__class__, request=request, user=request.user
        )

        return Response(
            {
                'success': True,
                'message': 'User logged out successfully.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordRequestView(APIView):
    """
    Request a password reset with an account email
    """

    permission_classes = [AllowAny]

    def post(self, request):
        request_serializer = ResetPasswordRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_email = request_serializer.validated_data['email']

        # query for a user, email if found and always return 200
        try:
            user = UserModel.objects.get(email=request_email.lower())
        except UserModel.DoesNotExist:
            logger.info(
                'reset password request attempt with non-existing email: %s',
                request_email,
            )
        else:
            # generate a new token and save it
            request_ip_address = request.META.get('REMOTE_ADDR')
            request_user_agent = request.META.get('HTTP_USER_AGENT')
            reset_password_token = ResetPasswordToken(
                user=user,
                ip_address=request_ip_address,
                user_agent=request_user_agent,
            )
            reset_password_token.save()

            reset_password_link = (
                f'{settings.BASE_RESET_PASSWORD_URL}'
                f'?code={reset_password_token.token}'
            )
            response = send_reset_password_email(
                email=request_email, reset_password_link=reset_password_link
            )
            if not response:
                return Response(
                    {
                        'success': False,
                        'message': 'Server error.',
                        'code': 'server_error',
                        'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                        'data': {},
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {
                'success': True,
                'message': 'Reset password token requested successfully.',
                'status': status.HTTP_200_OK,
                'data': {},
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordVerifyView(APIView):
    """
    Verify a reset password token
    """

    permission_classes = [AllowAny]

    def post(self, request):
        request_serializer = ResetPasswordVerifySerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_token = request_serializer.validated_data['token']

        try:
            reset_password_token = ResetPasswordToken.objects.get(token=request_token)

            if reset_password_token.verify():
                return Response(
                    {
                        'success': True,
                        'message': 'Token verified successfully.',
                        'status': status.HTTP_200_OK,
                        'data': {},
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                logger.info(
                    'reset password verify attempt with expired token: %s',
                    request_token,
                )

                # delete expired tokens
                reset_password_token.delete()
        except ResetPasswordToken.DoesNotExist:
            logger.info(
                'reset password verify attempt with non-existing token: %s',
                request_token,
            )

        return Response(
            {
                'success': False,
                'message': 'Invalid or expired token.',
                'code': 'bad_token',
                'status': status.HTTP_400_BAD_REQUEST,
                'data': {},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ResetPasswordConfirmView(APIView):
    """
    Request a password reset with an account email
    """

    permission_classes = [AllowAny]

    def post(self, request):
        request_serializer = ResetPasswordConfirmSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_token = request_serializer.validated_data['token']
        request_password = request_serializer.validated_data['password']

        try:
            reset_password_token = ResetPasswordToken.objects.get(token=request_token)

            if reset_password_token.verify():
                # validate password
                try:
                    validate_password(
                        request_password,
                        user=reset_password_token.user,
                        password_validators=get_password_validators(
                            settings.AUTH_PASSWORD_VALIDATORS
                        ),
                    )
                except ValidationError as ex:
                    return Response(
                        {
                            'success': False,
                            'message': 'Request is invalid.',
                            'code': 'password_does_not_conform',
                            'status': status.HTTP_400_BAD_REQUEST,
                            'data': {
                                'password': ex.messages,
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                reset_password_token.user.set_password(request_password)
                reset_password_token.user.save()

                # delete used token
                reset_password_token.delete()

                return Response(
                    {
                        'success': True,
                        'message': 'Password changed successfully.',
                        'status': status.HTTP_200_OK,
                        'data': {},
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                logger.info(
                    'reset password confirm attempt with expired token: %s',
                    request_token,
                )

                # delete expired tokens
                reset_password_token.delete()
        except ResetPasswordToken.DoesNotExist:
            logger.info(
                'reset password confirm attempt with non-existing token: %s',
                request_token,
            )

        return Response(
            {
                'success': False,
                'message': 'Invalid or expired token.',
                'code': 'bad_token',
                'status': status.HTTP_400_BAD_REQUEST,
                'data': {},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ChangePasswordView(APIView):
    """
    Change user password
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_serializer = ChangePasswordSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'request_invalid',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': request_serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_new_password = request_serializer.validated_data['new_password']
        request_old_password = request_serializer.validated_data['old_password']

        # find user by authentication token
        try:
            user = UserModel.objects.get(auth_token=request.user.auth_token.key)
        except UserModel.DoesNotExist:
            logger.info(
                'change password attempt for unknown token: %s',
                request.user.auth_token.key,
            )
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials.',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # validate user password
        if not user.check_password(request_old_password):
            logger.info(
                'change password attempt with bad password for user: %s',
                user.email,
            )
            return Response(
                {
                    'success': False,
                    'message': 'Bad credentials.',
                    'code': 'bad_credentials',
                    'status': status.HTTP_401_UNAUTHORIZED,
                    'data': {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # validate password
        try:
            validate_password(
                request_new_password,
                user=user,
                password_validators=get_password_validators(
                    settings.AUTH_PASSWORD_VALIDATORS
                ),
            )
        except ValidationError as ex:
            return Response(
                {
                    'success': False,
                    'message': 'Request is invalid.',
                    'code': 'password_does_not_conform',
                    'status': status.HTTP_400_BAD_REQUEST,
                    'data': {
                        'password': ex.messages,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(request_new_password)
        user.save()

        # create new token and delete the existing token
        # to close all existing sessions
        Token.objects.filter(user=user).all().delete()
        Token.objects.create(user=user)

        return Response(
            {
                'success': True,
                'message': 'Password changed successfully.',
                'status': status.HTTP_200_OK,
                'data': {'new_token': user.auth_token.key},
            },
            status=status.HTTP_200_OK,
        )


class InnerAuthView(APIView):
    """
    Logout an active session
    """

    permission_classes = [InnerIsAuthenticated]

    def get(self, request):
        hashed_username = hash_user_id(request.user.username)

        return Response(
            {
                'success': True,
                'message': 'Inner authentication valid.',
                'status': status.HTTP_200_OK,
                'data': {
                    'username': request.user.username,
                    'hashed_username': hashed_username,
                },
            },
            status=status.HTTP_200_OK,
        )
