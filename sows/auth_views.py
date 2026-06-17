from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect


class SecureLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if self._should_redirect_to_https(request):
            return redirect(self._build_https_url(request))
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _should_redirect_to_https(request) -> bool:
        return (
            not settings.DEBUG
            and not getattr(settings, 'TESTING', False)
            and not request.is_secure()
        )

    @staticmethod
    def _build_https_url(request) -> str:
        current_url = urlsplit(request.build_absolute_uri())
        return urlunsplit(('https', current_url.netloc, current_url.path, current_url.query, current_url.fragment))
