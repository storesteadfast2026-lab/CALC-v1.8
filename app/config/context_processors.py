from django.conf import settings


def software_version(request):
    """Expose the configured software version to every rendered interface."""
    return {'software_version': settings.APP_VERSION}
