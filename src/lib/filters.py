from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.admin.utils import reverse_field_path
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


# much of this code is copied from django-more-admin-filters -
# https://github.com/thomst/django-more-admin-filters/blob/master/more_admin_filters/filters.py


def flatten_used_parameters(used_parameters: dict, keep_list: bool = True):
    # FieldListFilter.__init__ calls prepare_lookup_value,
    # which returns a list if lookup_kwarg ends with '__in'
    for k, v in used_parameters.items():
        if isinstance(v, bool):
            continue
        elif len(v) == 1 and (isinstance(v[0], list) or not keep_list):
            used_parameters[k] = v[0]
        elif (
            k.endswith('__isnull')
            and len(v) == 1
            and isinstance(v, list)
            and isinstance(v[0], bool)
        ):
            used_parameters[k] = v[0]


class MultiSelectMixin(object):
    def queryset(self, request, queryset):
        params = Q()

        for lookup_arg, value in self.used_parameters.items():
            params |= Q(**{lookup_arg: value})
        try:
            return queryset.filter(params)
        except (ValueError, ValidationError) as e:
            # Fields may raise a ValueError or ValidationError when converting
            # the parameters to the correct type.
            raise IncorrectLookupParameters(e)

    def querystring_for_choices(self, val, changelist):
        lookup_vals = self.lookup_vals[:]

        if val in self.lookup_vals:
            lookup_vals.remove(val)
        else:
            lookup_vals.append(val)

        if lookup_vals:
            query_string = changelist.get_query_string(
                {
                    self.lookup_kwarg: ','.join(lookup_vals),
                },
                [],
            )
        else:
            query_string = changelist.get_query_string({}, [self.lookup_kwarg])
        return query_string

    def querystring_for_isnull(self, changelist):
        if self.lookup_val_isnull:
            query_string = changelist.get_query_string({}, [self.lookup_kwarg_isnull])
        else:
            query_string = changelist.get_query_string(
                {
                    self.lookup_kwarg_isnull: 'True',
                },
                [],
            )

        return query_string

    def has_output(self):
        return len(self.lookup_choices) > 1

    def get_facet_counts(self, pk_attname, filtered_qs):
        if not self.lookup_kwarg.endswith('__in'):
            raise NotImplementedError(
                'Facets are only supported for default lookup_kwarg values, '
                f"ending with '__in' (got '{self.lookup_kwarg}')"
            )

        orig_lookup_kwarg = self.lookup_kwarg
        self.lookup_kwarg = self.lookup_kwarg.removesuffix('in') + 'exact'
        counts = super().get_facet_counts(pk_attname, filtered_qs)
        self.lookup_kwarg = orig_lookup_kwarg
        return counts


class MultiSelectFilter(MultiSelectMixin, admin.AllValuesFieldListFilter):
    """
    Multi select filter for all kind of fields.
    """

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg = '%s__in' % field_path
        self.lookup_kwarg_isnull = '%s__isnull' % field_path
        lookup_vals = request.GET.get(self.lookup_kwarg)
        self.lookup_vals = lookup_vals.split(',') if lookup_vals else list()
        self.lookup_val_isnull = request.GET.get(self.lookup_kwarg_isnull)
        self.empty_value_display = model_admin.get_empty_value_display()

        parent_model, reverse_path = reverse_field_path(model, field_path)

        # Obey parent ModelAdmin queryset when deciding which options to show
        if model == parent_model:
            queryset = model_admin.get_queryset(request)
        else:
            queryset = parent_model._default_manager.all()

        self.lookup_choices = self.lookups(request, model_admin)
        if self.lookup_choices is None:
            self.lookup_choices = (
                queryset.distinct()
                .order_by(field.name)
                .values_list(field.name, flat=True)
            )

        super(admin.AllValuesFieldListFilter, self).__init__(
            field, request, params, model, model_admin, field_path
        )

        self.title = getattr(self, 'custom_title', self.title)

        flatten_used_parameters(self.used_parameters)
        self.used_parameters = self.prepare_used_parameters(self.used_parameters)

    def lookups(self, request, model_admin):
        """
        Must be overridden to return a list of tuples (value, verbose value)
        """
        return None

    def prepare_querystring_value(self, value):
        # mask all commas or these values will be used
        # in a comma-seperated-list as get-parameter
        return str(value).replace(',', '%~')

    def prepare_used_parameters(self, used_parameters):
        # remove comma-mask from list-values for __in-lookups
        for key, value in used_parameters.items():
            if not key.endswith('__in'):
                continue

            used_parameters[key] = [v.replace('%~', ',') for v in value]
        return used_parameters

    def choices(self, changelist):
        add_facets = getattr(changelist, 'add_facets', False)
        facet_counts = self.get_facet_queryset(changelist) if add_facets else None

        yield {
            'selected': not self.lookup_vals and self.lookup_val_isnull is None,
            'query_string': changelist.get_query_string(
                {}, [self.lookup_kwarg, self.lookup_kwarg_isnull]
            ),
            'display': _('All'),
        }

        include_none = False
        count = None
        empty_title = self.empty_value_display

        for i, val in enumerate(self.lookup_choices):
            if add_facets:
                count = facet_counts[f'{i}__c']

            if val is None:
                include_none = True
                empty_title = f'{empty_title} ({count})' if add_facets else empty_title
                continue

            # values can be a tuple for enums - query value and display value
            if isinstance(val, tuple):
                qval, val = val
            else:
                qval = val

            val = str(val)
            qval = self.prepare_querystring_value(str(qval))

            yield {
                'selected': qval in self.lookup_vals,
                'query_string': self.querystring_for_choices(qval, changelist),
                'display': f'{val} ({count})' if add_facets else val,
            }

        if include_none:
            yield {
                'selected': bool(self.lookup_val_isnull),
                'query_string': self.querystring_for_isnull(changelist),
                'display': empty_title,
            }
