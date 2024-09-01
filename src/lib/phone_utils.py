import logging

from django.core.exceptions import ValidationError
import phonenumbers


logger = logging.getLogger(__name__)


def validate_phone_number(phone_number: str) -> None:
    try:
        p = phonenumbers.parse(phone_number, region='IL')
        assert phonenumbers.region_code_for_country_code(p.country_code) == 'IL'
    except Exception as _ex:
        raise ValidationError(
            '%(value)s is not a valid phone number',
            params={'value': phone_number},
        )


def convert_phone_number_to_long_form(phone_number: str) -> str | None:
    try:
        p = phonenumbers.parse(phone_number, region='IL')
        return f'+{p.country_code}{p.national_number}'
    except Exception as ex:
        logger.error(
            f'Failed to convert phone number "{phone_number}" to long form '
            f'with error "{str(ex)}"'
        )
        return None
