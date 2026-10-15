from rest_framework.throttling import SimpleRateThrottle


class RegistrationAdminThrottle(SimpleRateThrottle):
    scope = "registration_admin"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class TransferAdminThrottle(SimpleRateThrottle):
    scope = "transfer_admin"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class AdminAccountThrottle(SimpleRateThrottle):
    scope = "admin_account"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
