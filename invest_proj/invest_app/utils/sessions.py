from functools import wraps
from django.http import JsonResponse
import json


# Helper to extract customer_id from body if needed
def get_data_customer_id(request):
    try:
        if request.content_type == 'application/json':
            body = json.loads(request.body)
            return body.get("customer_id")
        return request.POST.get("customer_id") or request.GET.get("customer_id")
    except:
        return None


# Customer Login Required Decorator
def customer_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        customer_id = request.session.get("customer_id")
        if not customer_id:
            return JsonResponse({"error": "Customer login required"}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# Admin Login Required Decorator
def admin_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        admin_id = request.session.get("admin_id")
        if not admin_id:
            return JsonResponse({"error": "Admin login required"}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# Role-Based Access Decorator (for trainers, managers, superadmin, etc.)
def role_required(required_role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            role = request.session.get("role")
            if not role or role != required_role:
                return JsonResponse({"error": f"Access denied: '{required_role}' role required"}, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
