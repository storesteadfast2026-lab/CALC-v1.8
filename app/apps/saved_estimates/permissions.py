from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.authentication_gateway.models import CalculatorUserProfile
from apps.authentication_gateway.services import (
    allowed_clients_for,
    get_calculator_profile,
)
from apps.clients.models import FreightCalculator

from .models import SavedEstimate


def estimates_for_user(user):
    """Return only the saved quotations the current user is allowed to see.

    Customer users are isolated to quotations they created for their assigned
    client. Internal users see every quotation for their authorised clients,
    regardless of which customer or internal user created it.
    """
    queryset = SavedEstimate.objects.select_related('client', 'created_by')

    if user.is_superuser:
        return queryset

    profile = get_calculator_profile(user)
    if profile.role == CalculatorUserProfile.Role.CUSTOMER_USER:
        return queryset.filter(client=profile.client, created_by=user)

    if profile.role == CalculatorUserProfile.Role.INTERNAL_USER:
        return queryset.filter(
            client__in=allowed_clients_for(user),
        ).distinct()

    # Defensive default: an unknown role never widens quotation access.
    return queryset.none()


def can_export_estimates(user) -> bool:
    if user.is_superuser:
        return True
    profile = get_calculator_profile(user)
    return profile.role == CalculatorUserProfile.Role.INTERNAL_USER


def estimates_in_visible_history(user):
    """Apply each client's configured recent-history window to the list view."""
    queryset = estimates_for_user(user)
    client_ids = list(
        queryset.order_by().values_list('client_id', flat=True).distinct()
    )
    configured_windows = {}
    for calculator in (
        FreightCalculator.objects.filter(client_id__in=client_ids, active=True, archived_at__isnull=True)
        .only('client_id', 'visible_history_days')
    ):
        configured_windows[calculator.client_id] = calculator.visible_history_days
    today = timezone.localdate()
    visible = Q()
    has_clients = False
    for client_id in client_ids:
        has_clients = True
        configured_days = configured_windows.get(client_id, 14)
        days = max(int(configured_days or 1), 1)
        cutoff = today - timedelta(days=days - 1)
        visible |= Q(client_id=client_id, created_at__date__gte=cutoff)
    return queryset.filter(visible) if has_clients else queryset.none()
