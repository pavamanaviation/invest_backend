import random
import json
import pytz
import re
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db import IntegrityError
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from .models import (CustomerRegister,)
def is_valid_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(char.isdigit() for char in password):
        return "Password must contain at least one digit."
    if not any(char.isupper() for char in password):
        return "Password must contain at least one uppercase letter."
    if not any(char.islower() for char in password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character."
    return None

def match_password(password, re_password):
    if password != re_password:
        return "Passwords must be the same."
    return None

def get_indian_time():
    india_tz = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(india_tz)
print("Current Indian Time:", get_indian_time())

def generate_otp():
    return random.randint(100000, 999999)

@csrf_exempt
def customer_register(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Invalid HTTP method. Only POST allowed.", "status_code": 405}, status=405)

    try:
        data = json.loads(request.body)

        required_fields = ['first_name', 'last_name', 'email', 'mobile_no', 'password', 're_password']
        if not all(data.get(field) for field in required_fields):
            return JsonResponse({"error": "All fields are required.", "status_code": 400}, status=400)

        first_name = data['first_name'].strip()
        last_name = data['last_name'].strip()
        email = data['email'].strip().lower()
        mobile_no = data['mobile_no'].strip()
        password = data['password']
        re_password = data['re_password']

        password_error = is_valid_password(password)
        if password_error:
            return JsonResponse({"error": password_error, "status_code": 400}, status=400)

        mismatch_error = match_password(password, re_password)
        if mismatch_error:
            return JsonResponse({"error": mismatch_error, "status_code": 400}, status=400)

        existing_customer = CustomerRegister.objects.filter(email=email).first()
        if existing_customer:
            if existing_customer.password is None:
                return JsonResponse({"error": "This email was registered using Google Sign-In. Please reset your password.", "status_code": 409}, status=409)
            return JsonResponse({"error": "Email already exists. Please use a different one.", "status_code": 409}, status=409)

        if CustomerRegister.objects.filter(mobile_no=mobile_no).exists():
            return JsonResponse({"error": "Mobile number already exists. Use a different one.", "status_code": 409}, status=409)

        # admin = Admin.objects.order_by('id').first()
        # if not admin:
        #     return JsonResponse({"error": "No admin found in the system.", "status_code": 500}, status=500)

        otp = generate_otp()
        current_time = get_indian_time()

        customer = CustomerRegister.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile_no=mobile_no,
            password=make_password(password),
            status=1,
            register_status=1,
            created_at=current_time,
            # admin=admin,
            otp=otp,
            # otp_send_type="email",
            register_type="Manual"
        )

        # send_otp_to_customer(email, otp)

        return JsonResponse(
            {
                "message": "Account created successfully. OTP sent to your email for Account verification.",
                "customer_id": customer.id,
                "status_code": 200
            }, status=200
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data.", "status_code": 400}, status=400)
    except IntegrityError:
        return JsonResponse({"error": "Database integrity error.", "status_code": 500}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"An unexpected error occurred: {str(e)}", "status_code": 500}, status=500)
