from rest_framework.permissions import SAFE_METHODS, BasePermission


class StaffWritePermission(BasePermission):
    """
    Allow anyone to read products/categories.
    Only allow staff (X-User-Role: staff) to create/update/delete.
    """

    def has_permission(self, request, view):  # noqa: ANN001
        if request.method in SAFE_METHODS:
            return True
        role = (request.headers.get("X-User-Role") or "").strip().lower()
        return role == "staff"

