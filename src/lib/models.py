import logging

from django.db.models import Aggregate


logger = logging.getLogger(__name__)


class StringAgg(Aggregate):
    """
    this is compatible with sqlite (which we use for development) and
    postgresql (which we use for deployed environments). it will not
    necessarily work with any other databases
    """

    function = 'STRING_AGG'
    template = '%(function)s(%(distinct)s%(expressions)s)'
    allow_distinct = True

    def __init__(self, *expressions, **extra):
        super().__init__(*expressions, **extra)

    def as_sqlite(self, compiler, connection, **extra_context):
        # could not avoid this since sqlite's STRING_AGG alias does not support
        # a single expression with a default delimeter as required for the
        # DISTINCT keyword
        self.function = 'GROUP_CONCAT'

        if self.distinct and len(self.source_expressions) > 1:
            logger.warn(
                'sqlite does not support distinct aggregates with more than '
                'one expression. removing and will use default delimeter'
            )
            self.source_expressions = self.source_expressions[:1]

        return self.as_sql(compiler, connection, **extra_context)
