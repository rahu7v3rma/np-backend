from django.db.models import Aggregate


class StringAgg(Aggregate):
    """
    STRING_AGG is compatible with sqlite (which we use for development) and
    postgresql (which we use for deployed environments). it will not
    necessarily work with any other databases
    """

    # sqlite note: don't change this to GROUP_CONCAT, make sure your sqlite
    # version is up-to-date as STRING_AGG is supported since version 3.44
    function = 'STRING_AGG'
    template = '%(function)s(%(expressions)s)'
    allow_distinct = False

    def __init__(self, *expressions, **extra):
        super().__init__(*expressions, **extra)
