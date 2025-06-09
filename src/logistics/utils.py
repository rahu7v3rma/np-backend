from django.conf import settings
from django.db.models import Q

from inventory.models import Variation


def get_variation_type(variation):
    var_obj = Variation.objects.filter(
        Q(system_name_en=variation)
        | Q(system_name_he=variation)
        | Q(site_name_en=variation)
        | Q(site_name_he=variation)
    ).first()
    return var_obj.variation_kind


def get_variations_string(variations: dict) -> str:
    variations = variations if isinstance(variations, dict) else {}
    variations_text = []
    for key, value in variations.items():
        variation_kind = get_variation_type(variation=key)
        if variation_kind == 'COLOR':
            variations_text.insert(0, str(value[:3]))
        elif variation_kind == 'TEXT':
            variations_text.append(str(value[:3]))
    return ''.join(variations_text)


def exclude_taxes(value):
    """
    return price without taxes
    """
    return round(value / ((100 + settings.TAX_PERCENT) / 100), 2)


def snake_to_title(snake_str_list: list[str]) -> list[str]:
    title_str_list = []
    for snake_str in snake_str_list:
        words = snake_str.split('_')
        title_words = [word.capitalize() for word in words]
        title_str = ' '.join(title_words)
        title_str_list.append(title_str)
    return title_str_list
