def format_street_line(
    street_name: str, street_number: str, appartment_number: str | None
) -> str:
    line = f'{street_number} {street_name}'

    if appartment_number:
        line = f'{line}, {appartment_number}'

    return line
