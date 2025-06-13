import random
import json
import pytz
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db import IntegrityError
from django.utils import timezone
import requests
from .models import CustomerRegister,KYCDetails
from .sms_utils import send_otp_sms
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
# from .idfy_verification import verify_pan_idfy

def get_indian_time():
    india_tz = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(india_tz)

def generate_otp():
    return random.randint(100000, 999999)

# @csrf_exempt
# def customer_register(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)

#     try:
#         data = json.loads(request.body)
#         token = data.get('token')
#         email = data.get('email')
#         mobile_no = data.get('mobile_no')

#         first_name = ''
#         last_name = ''

#         if token:
#             google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
#             response = requests.get(google_url)

#             if response.status_code != 200:
#                return JsonResponse({"error": "Google token invalid."}, status=400)
        
#             google_data = response.json()
#             if "error" in google_data:
#                     return JsonResponse({"error": "Invalid Token"}, status=400)
#             email = google_data.get("email")
#             first_name = google_data.get("given_name", "")
#             last_name = google_data.get("family_name", "")
#         if not email and not mobile_no:
#             return JsonResponse({"error": "Provide email or mobile number."}, status=400)
#         customer = None
#         if email:
#             customer = CustomerRegister.objects.filter(email=email).first()
#         if not customer and mobile_no:
#             customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

#         otp = generate_otp()

#         if customer:
#             if customer.register_status == 1:
#                 return JsonResponse({
#                     "message": "Account already verified. Please proceed to next step.",
#                     "customer_id": customer.id,
#                     "email": customer.email,
#                     "mobile_no": customer.mobile_no,
#                 }, status=200)

#             # resend OTP if not verified
#             customer.otp = otp
#             customer.changed_on = timezone.now()
#             customer.save(update_fields=['otp', 'changed_on'])
#             # customer.save(update_fields=['otp'])
#         else:
#             customer = CustomerRegister.objects.create(
#                 email=email or '',
#                 mobile_no=mobile_no or '',
#                 first_name=first_name or '',
#                 last_name=last_name or '',
#                 otp=otp,
#                 changed_on=timezone.now(),
#                 register_type="Google" if token else "Email" if email else "Mobile",
                
#             )
#         if email:
#             send_otp_email(email,first_name, otp)
#         if mobile_no:
#             send_otp_sms([mobile_no], f"Hi,This is your OTP for password reset on Pavaman Aviation: {otp}. It is valid for 2 minutes. Do not share it with anyone.")

#         return JsonResponse({
#             "message": "OTP sent. Please verify to continue. The OTP is valid for 2 minutes.",
#             "customer_id": customer.id,
#             "status_code": 200
#         }, status=200)

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
@csrf_exempt
def customer_register(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        token = data.get('token')
        email = data.get('email')
        mobile_no = data.get('mobile_no')

        first_name = ''
        last_name = ''
        is_google_signup = False

        if token:
            google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            response = requests.get(google_url)

            if response.status_code != 200:
                return JsonResponse({"error": "Google token invalid."}, status=400)

            google_data = response.json()
            if "error" in google_data:
                return JsonResponse({"error": "Invalid Token"}, status=400)

            email = google_data.get("email")
            first_name = google_data.get("given_name", "")
            last_name = google_data.get("family_name", "")
            is_google_signup = True

        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number."}, status=400)

        customer = None
        if email:
            customer = CustomerRegister.objects.filter(email=email).first()
        if not customer and mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

        if customer:
            if customer.register_status == 1 and customer.account_status == 1:
                return JsonResponse({
                    "message": "Account already verified. Please login to continue.",
                    "customer_id": customer.id,
                    "email": customer.email,
                    "mobile_no": customer.mobile_no,
                }, status=200)

            if customer.register_status == 1:
                return JsonResponse({
                    "message": "Account already verified. Please proceed to next step.",
                    "customer_id": customer.id,
                    "email": customer.email,
                    "mobile_no": customer.mobile_no,
                }, status=200)
            
            if is_google_signup:
                customer.register_status = 1
                customer.first_name = customer.first_name or first_name
                customer.last_name = customer.last_name or last_name
                customer.save(update_fields=['register_status', 'first_name', 'last_name'])
            else:
                otp = generate_otp()
                customer.otp = otp
                customer.changed_on = timezone.now()
                customer.save(update_fields=['otp', 'changed_on'])
        else:
            if is_google_signup:
                customer = CustomerRegister.objects.create(
                    email=email or '',
                    mobile_no=mobile_no or '',
                    first_name=first_name or '',
                    last_name=last_name or '',
                    register_status=1,
                    register_type="Google"
                )
            else:
                otp = generate_otp()
                customer = CustomerRegister.objects.create(
                    email=email or '',
                    mobile_no=mobile_no or '',
                    first_name=first_name or '',
                    last_name=last_name or '',
                    otp=otp,
                    changed_on=timezone.now(),
                    register_type="Email" if email else "Mobile"
                )

        if not is_google_signup:
            if email:
                send_otp_email(email, first_name, otp)
            if mobile_no:
                send_otp_sms([mobile_no], f"Hi,This is your OTP for password reset on Pavaman Aviation: {otp}. It is valid for 2 minutes. Do not share it with anyone.")

        return JsonResponse({
            "message": "Google account verified successfully." if is_google_signup else "OTP sent. Please verify to continue. The OTP is valid for 2 minutes.",
            "customer_id": customer.id,
            "status_code": 200
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

@csrf_exempt
def verify_customer_otp(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests are allowed."}, status=405)
    try:
        data = json.loads(request.body)
        otp = str(data.get('otp'))
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        mobile_no = data.get('mobile_no', '')
        email = data.get('email', '')
        # if not customer_id:
        #     return JsonResponse({"error": "Customer ID is required."}, status=400)

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)
        customer = None
        if email and mobile_no:
            customer = CustomerRegister.objects.filter(email=email, mobile_no=mobile_no).first()
        elif email:
            customer = CustomerRegister.objects.filter(email=email).first()
        elif mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

        if not customer:
            return JsonResponse({"error": "User not found with the provided email or mobile number"}, status=404)
        
        customer.clear_expired_otp()
        
        if not customer.otp and customer.account_status != 1:
            return JsonResponse({"error": "OTP has expired. Please request a new one."}, status=400)
        if not customer.otp or not str(customer.otp).isdigit():
            return JsonResponse({"error": "OTP is expired or invalid.Please request a new one."}, status=400)

        try:
           
            if int(customer.otp) != int(otp):
                return JsonResponse({"error": "Invalid OTP."}, status=400)
        except:
            return JsonResponse({"error": "Invalid OTP format."}, status=400)
        update_fields = ['otp']  # otp will be cleared after successful verification
        customer.otp = None
        if customer.register_status != 1:
            customer.register_status = 1
            update_fields.append('register_status')
            if first_name:
                customer.first_name = first_name
                update_fields.append('first_name')
            if last_name:
                customer.last_name = last_name
                update_fields.append('last_name')
            if mobile_no:
                customer.mobile_no = mobile_no
                update_fields.append('mobile_no')
        
        elif customer.register_status == 1 and customer.account_status == 0:
            if customer.otp_send_type == 'Mobile':
                if not mobile_no or (customer.mobile_no and customer.mobile_no != mobile_no):
                    return JsonResponse({"error": "Mobile number mismatch or missing for OTP verification."}, status=400)
                if not customer.mobile_no:
                    customer.mobile_no = mobile_no
            elif customer.otp_send_type == 'Email':
                if not email or (customer.email and customer.email != email):
                    return JsonResponse({"error": "Email mismatch or missing for OTP verification."}, status=400)
                if not customer.email:
                    customer.email = email
            else:
                return JsonResponse({"error": "OTP send type is missing. Cannot verify."}, status=400)

            customer.account_status = 1
            update_fields.append('account_status')
        pass
        # else:
        #     return JsonResponse({"error": "User is already fully verified."}, status=400)

        # Clear otp_send_type after verification
        customer.otp_send_type = None
        update_fields.append('otp_send_type')

        customer.save(update_fields=update_fields)
         # ✅ Final unified logic: If fully verified, treat as login
        if customer.register_status == 1 and customer.account_status == 1:
            request.session['customer_id'] = customer.id
            request.session.save()
            return JsonResponse({
                "message": "OTP verified and login successful.",
                "customer_id": customer.id,
                "email": customer.email,
                "mobile_no": customer.mobile_no,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "register_status": customer.register_status,
                "account_status": customer.account_status,
                "session_id": request.session.session_key
            }, status=200)
        return JsonResponse({
            "message": "OTP verified successfully.",
            "customer_id": customer.id,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
        }, status=200)
        # If both phases are completed, suggest login
        if customer.register_status == 1 and customer.account_status == 1:
            response_data["next_step"] = "login"
            response_data["login_message"] = "Your profile is verified. Please login to continue."

        return JsonResponse(response_data, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

@csrf_exempt
def customer_register_sec_phase(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed."}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        email = data.get('email')
        mobile_no = data.get('mobile_no')
        first_name = data.get('first_name')
        last_name = data.get('last_name')

        if not customer_id:
            return JsonResponse({"error": "Customer ID is required."}, status=400)

        try:
            customer = CustomerRegister.objects.get(id=customer_id)
        except CustomerRegister.DoesNotExist:
            return JsonResponse({"error": "Customer not found."}, status=404)

        if customer.register_status != 1:
            return JsonResponse({"error": "First phase registration incomplete."}, status=400)

        # Block second mobile OTP if mobile was already used in first phase
        if customer.mobile_no and not customer.email and not email:
            return JsonResponse({"error": "Mobile already verified in first phase. Please provide email to continue."}, status=400)
        if customer.email and not customer.mobile_no and not mobile_no:
            return JsonResponse({"error": "Email already verified in first phase. Please provide mobile to continue."}, status=400)
        # Clear expired OTP
        customer.clear_expired_otp()

        # if customer.is_otp_valid():
        #     return JsonResponse({"error": "OTP already sent. Please wait 2 minutes before requesting again."}, status=400)

        otp = generate_otp()
        otp_sent = False
        otp_send_type = None
        # otp_send_type = None
        if email:
            otp_send_type = 'Email'
        elif mobile_no:
            otp_send_type = 'Mobile'
        print(f"OTP send type:", otp_send_type)
        
        update_fields = []

        # # Validate if already OTP sent via mobile or email
        # if customer.register_status == 1 and customer.account_status == 0:
        #     if customer.otp_send_type == 'Mobile':
        #         if not mobile_no or (customer.mobile_no and customer.mobile_no != mobile_no):
        #             return JsonResponse({"error": "Mobile number mismatch or missing for OTP verification."}, status=400)
        #         if not customer.mobile_no:
        #             customer.mobile_no = mobile_no
        #             update_fields.append('mobile_no')
            
        #     elif customer.otp_send_type == 'Email':
        #         if not email or (customer.email and customer.email != email):
        #             return JsonResponse({"error": "Email mismatch or missing for OTP verification."}, status=400)
        #         if not customer.email:
        #             customer.email = email
        #             update_fields.append('email')
        #     else:
        #         return JsonResponse({"error": "OTP send type is missing. Cannot verify."}, status=400)

        # New email provided
        if not customer.mobile_no and mobile_no:
            if CustomerRegister.objects.filter(mobile_no=mobile_no).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Mobile number already in use."}, status=400)
            customer.mobile_no = mobile_no
            otp_send_type = 'Mobile'
            send_otp_sms([mobile_no], f"Hi, This is your OTP for profile verification on Pavaman Aviation: {otp}. Valid for 2 minutes.")
            otp_sent = True
            update_fields.append('mobile_no')
        # New mobile provided (only if mobile not used in phase 1)
        elif not customer.email and email:
            if CustomerRegister.objects.filter(email=email).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Email already in use."}, status=400)
            customer.email = email
            otp_send_type = 'Email'
            send_otp_email(email, first_name or customer.first_name, otp)
            otp_sent = True
            update_fields.append('email')

        # Resend OTP
        if not otp_sent and customer.account_status == 0:
            if customer.otp_send_type == 'Email' and customer.email:
                send_otp_email(customer.email, customer.first_name or '', otp)
                otp_send_type = 'Email'
                otp_sent = True
            elif customer.otp_send_type == 'Mobile' and customer.mobile_no:
                send_otp_sms([customer.mobile_no], f"Hi, This is your OTP for profile verification on Pavaman Aviation: {otp}. Valid for 2 minutes.")
                otp_send_type = 'Mobile'
                otp_sent = True
            else:
                return JsonResponse({"error": "No verified email or mobile to resend OTP."}, status=400)

        # if first_name:
        #     customer.first_name = first_name
        # if last_name:
        #     customer.last_name = last_name

        # customer.otp = otp
        # customer.changed_on = timezone.now()
        # customer.otp_send_type = otp_send_type
        # customer.save(update_fields=['otp_send_type', 'mobile_no', 'email', 'first_name', 'last_name', 'otp', 'changed_on'])

        # Update name fields
        if first_name and customer.first_name != first_name:
            customer.first_name = first_name
            update_fields.append('first_name')
        if last_name and customer.last_name != last_name:
            customer.last_name = last_name
            update_fields.append('last_name')

        customer.otp = otp
        customer.otp_send_type = otp_send_type or customer.otp_send_type
        customer.changed_on = timezone.now()
        update_fields.extend(['otp', 'changed_on', 'otp_send_type'])

        customer.save(update_fields=update_fields)
        return JsonResponse({
            "message": "OTP sent. Please verify to complete your profile. The OTP is valid for 2 minutes.",
            "customer_id": customer.id,
            "status_code": 200,
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

# @csrf_exempt
# def customer_register_sec_phase(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST method allowed."}, status=405)
#     try:
#         data = json.loads(request.body)
#         customer_id = data.get('customer_id')
#         email = data.get('email')
#         mobile_no = data.get('mobile_no')
#         first_name = data.get('first_name')
#         last_name = data.get('last_name')

#         if not customer_id:
#             return JsonResponse({"error": "Customer ID is required."}, status=400)

#         try:
#             customer = CustomerRegister.objects.get(id=customer_id)
#         except CustomerRegister.DoesNotExist:
#             return JsonResponse({"error": "Customer not found."}, status=404)

#         if customer.register_status != 1:
#             return JsonResponse({"error": "First phase registration incomplete."}, status=400)

#         otp = generate_otp()
#         otp_sent = False
#         otp_send_type = None
#         if not customer.mobile_no and mobile_no:
#             if CustomerRegister.objects.filter(mobile_no=mobile_no).exclude(id=customer.id).exists():
#                 return JsonResponse({"error": "Mobile number already in use."}, status=400)
#             customer.mobile_no = mobile_no
#             send_otp_sms([mobile_no], f"Hi, This is your OTP for profile verification on Pavaman Aviation: {otp}. Valid for 2 minutes.")
#             otp_sent = True
#             otp_send_type = 'Mobile'
#         if not customer.email and email:
#             if CustomerRegister.objects.filter(email=email).exclude(id=customer.id).exists():
#                 return JsonResponse({"error": "Email already in use."}, status=400)
#             customer.email = email
#             send_otp_email(email, first_name or customer.first_name, otp)
#             otp_sent = True
#             otp_send_type = 'Email'
#         if first_name:
#             customer.first_name = first_name
#         if last_name:
#             customer.last_name = last_name

#         if not otp_sent:
#             return JsonResponse({"error": "No new field to verify (mobile/email) or already provided."}, status=400)

#         customer.otp = otp
#         customer.save(update_fields=['otp_send_type','mobile_no','email','first_name', 'last_name', 'otp'])

#         return JsonResponse({
#             "message": "OTP sent. Please verify to complete your profile.",
#             "customer_id": customer.id
#         }, status=200)

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

def send_otp_email(email, first_name, otp):
    subject = "[Pavaman] Please Verify Your Email"
    logo_url = f"{settings.AWS_S3_BUCKET_URL}/static/images/aviation-logo.png"

    text_content = f"""
    Hello {first_name},
    """
    html_content = f"""
    <html>
    <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 90% !important;
                    padding: 20px !important;
                }}
                .logo {{
                    max-width: 180px !important;
                    height: auto !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Inter', sans-serif; background-color: #f5f5f5;">
        <div class="container" style="margin: 40px auto; background-color: #ffffff; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); padding: 40px 30px; max-width: 480px; text-align: left;">
                <div style="text-align: center;">
                <img src="{logo_url}" alt="Pavaman Logo" class="logo" style="max-width: 280px; height: auto; margin-bottom: 20px;" />
                <h2 style="margin-top: 0; color: #222;">Verify your email</h2>
            </div>
            <div style="margin-bottom: 10px; color: #555; font-size: 14px;">
                Hello {first_name},
            </div>
           
             <p style="color: #555; margin-bottom: 30px;">
                Please use the OTP below to verify your email.
            </p>
          
            <p class="otp" style="font-size: 28px; font-weight: bold; color: #4450A2; background: #f2f2f2; display: block; padding: 12px 24px; border-radius: 10px; letter-spacing: 4px; width: fit-content; margin: 0 auto;">
                {otp}
            </p>
            <p style="color: #888; font-size: 14px; margin-top: 20px;">
                If you didn't request this, you can safely ignore this email.<br/>
                You're receiving this because you have an account on Pavaman.
            </p>
            <p style="margin-top: 30px; font-size: 14px; color: #888;">Disclaimer: This is an automated email. Please do not reply.</p>
        </div>
    </body>
    </html>
    """

    email_message = EmailMultiAlternatives(
        subject, text_content, settings.DEFAULT_FROM_EMAIL, [email]
    )
    email_message.attach_alternative(html_content, "text/html")
    email_message.send()

# @csrf_exempt
# def customer_login_request_otp(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)

#     try:
#         data = json.loads(request.body)
#         email = data.get('email')
#         mobile_no = data.get('mobile_no')
#         token = data.get('token')  # Google token, if present

#         first_name = ''
#         last_name = ''

#         # If Google token provided, verify and extract email
#         if token:
#             google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
#             response = requests.get(google_url)
#             if response.status_code != 200:
#                 return JsonResponse({"error": "Google token invalid."}, status=400)

#             google_data = response.json()
#             if "error" in google_data:
#                 return JsonResponse({"error": "Invalid Google token."}, status=400)

#             # email = google_data.get("email")
#             # first_name = google_data.get("given_name", "")
#             # last_name = google_data.get("family_name", "")

#         if not email and not mobile_no:
#             return JsonResponse({"error": "Provide email or mobile number or valid Google token."}, status=400)

#         # Lookup the customer with account_status = 1
#         customer = None
#         if email:
#             customer = CustomerRegister.objects.filter(email=email, account_status=1).first()
#         if not customer and mobile_no:
#             customer = CustomerRegister.objects.filter(mobile_no=mobile_no, account_status=1).first()

#         if not customer:
#             return JsonResponse({"error": "Account not found or not verified."}, status=404)

#         otp = generate_otp()
#         customer.otp = otp
#         customer.changed_on = timezone.now()
#         customer.save(update_fields=['otp', 'changed_on'])

#         if email:
#             send_otp_email(email, customer.first_name or first_name, otp)
#         if mobile_no:
#             send_otp_sms([mobile_no], f"Hi,This is your OTP for login to Pavaman Aviation: {otp}. It is valid for 2 minutes. Do not share it with anyone.")

#         return JsonResponse({
#             "message": "OTP sent for login.",
#             "customer_id": customer.id,
#             "status_code": 200
#         }, status=200)

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
@csrf_exempt
def customer_login(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get('email')
        mobile_no = data.get('mobile_no')
        token = data.get('token')  # Optional: Google token

        first_name = ''
        last_name = ''

        # Case 1: Google Token Login
        if token:
            google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            response = requests.get(google_url)
            if response.status_code != 200:
                return JsonResponse({"error": "Google token invalid."}, status=400)

            google_data = response.json()
            if "error" in google_data:
                return JsonResponse({"error": "Invalid Google token."}, status=400)

            email = google_data.get("email")
            first_name = google_data.get("given_name", "")
            last_name = google_data.get("family_name", "")

            if not email:
                return JsonResponse({"error": "Email not found in Google token."}, status=400)

            customer = CustomerRegister.objects.filter(email=email, account_status=1).first()
            if not customer:
                return JsonResponse({"error": "Account not found or not verified."}, status=404)

            request.session['customer_id'] = customer.id  # ✅ Set session

            return JsonResponse({
                "message": "Login successful via Google.",
                "customer_id": customer.id,
                "email": customer.email,
                "mobile_no": customer.mobile_no,
                "first_name": customer.first_name or first_name,
                "last_name": customer.last_name or last_name,
                "register_status": customer.register_status,
                "account_status": customer.account_status,
                "session_id": request.session.session_key
            }, status=200)

        # Case 2: OTP Login (Email/Mobile)
        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number or valid Google token."}, status=400)

        customer = None
        if email:
            customer = CustomerRegister.objects.filter(email=email, account_status=1).first()
        if not customer and mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no, account_status=1).first()

        if not customer:
            return JsonResponse({"error": "Account not found or not verified."}, status=404)

        otp = generate_otp()
        customer.otp = otp
        customer.changed_on = timezone.now()
        customer.save(update_fields=['otp', 'changed_on'])

        if email:
            send_otp_email(email, customer.first_name or first_name, otp)
        if mobile_no:
            send_otp_sms([mobile_no], f"Hi,This is your OTP for login to Pavaman Aviation: {otp}. It is valid for 2 minutes. Do not share it with anyone.")

        return JsonResponse({
            "message": "OTP sent for login.It is valid for 2 minutes.",
            "customer_id": customer.id,
            "status_code": 200
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

import uuid
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .idfy_verification import send_pan_verification_request, get_pan_verification_result
from .models import KYCDetails, CustomerRegister
from django.shortcuts import get_object_or_404

@csrf_exempt
def pan_verification_request_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    data = json.loads(request.body)
    pan_number = data.get('pan_number')
    customer_id = data.get('customer_id')  # Ensure frontend sends this

    if not all([pan_number, customer_id]):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    task_id = str(uuid.uuid4())
    response = send_pan_verification_request(pan_number, task_id)

    if 'request_id' in response:
        customer = get_object_or_404(CustomerRegister, id=customer_id)
        
        # Only set pan_status = 1 if message is as expected
        # status_value = 1 if response.get("message") == "PAN verification initiated." else 0

        # Manually assign pan_status = 1 when request_id is received
        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "pan_number": pan_number,
                "pan_request_id": response["request_id"],
                "pan_group_id": settings.IDFY_TEST_GROUP_ID,
                "pan_task_id": task_id,
                "pan_status": 1  # Always set to 1 when request_id is present
            }
        )

        return JsonResponse({
            "message": "PAN verification initiated.",
            "request_id": response["request_id"],
            "task_id": task_id
        })
        
    else:
        return JsonResponse({"error": response}, status=500)

@csrf_exempt
def pan_verification_result_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    data = json.loads(request.body)
    request_id = data.get('request_id')

    if not request_id:
        return JsonResponse({"error": "Missing request_id"}, status=400)

    result = get_pan_verification_result(request_id)
    pan_status = None  # Default if not found
    
    try:
        kyc = KYCDetails.objects.get(pan_request_id=request_id)
        if result.get("status") == "completed":
            output = result.get("result", {}).get("output", {})
            kyc.idfy_pan_status = output.get("status")
            # kyc.pan_status = 1 if output.get("status") == "match" else 2  # 1: Approved, 2: Rejected
            kyc.pan_name = output.get("full_name")
            kyc.pan_dob = output.get("dob")
            kyc.save()

        pan_status = kyc.pan_status
    except KYCDetails.DoesNotExist:
        pass  # Handle if needed # Leave pan_status as None

    # Append pan_status to result
    result["pan_status"] = pan_status

    return JsonResponse(result, safe=False)


# @csrf_exempt
# def pan_verification_request_view(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)

#     data = json.loads(request.body)
#     pan_number = data.get('pan_number')
#     # full_name = data.get('full_name')
#     # dob = data.get('dob')

#     if not all([pan_number]):
#         return JsonResponse({"error": "Missing required fields"}, status=400)

#     task_id = str(uuid.uuid4())
#     response = send_pan_verification_request(pan_number, task_id)

#     if 'request_id' in response:
#         return JsonResponse({
#             "message": "PAN verification initiated.",
#             "request_id": response["request_id"],
#             "task_id": task_id
#         })

#     else:
#         return JsonResponse({"error": response}, status=500)


# @csrf_exempt
# def pan_verification_result_view(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)

#     data = json.loads(request.body)
#     request_id = data.get('request_id')

#     if not request_id:
#         return JsonResponse({"error": "Missing request_id"}, status=400)

#     result = get_pan_verification_result(request_id)
#     return JsonResponse(result, safe=False)


import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# IDFY_API_KEY = settings.IDFY_TEST_API_KEY  # Replace with your actual key
# IDFY_RESULT_URL = 'https://eve.idfy.com/v3/tasks?request_id={request_id}'


@csrf_exempt
def fetch_pan_verification_result(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET requests are allowed.'}, status=405)

    request_id = request.GET.get('request_id')
    if not request_id:
        return JsonResponse({'error': 'request_id is required.'}, status=400)

    url = settings.IDFY_RESULT_URL.format(request_id=request_id)
    headers = {
        'Authorization': f'Bearer {settings.IDFY_TEST_API_KEY}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        if response.status_code == 200:
            return JsonResponse({'status': 'success', 'data': data}, status=200)
        else:
            return JsonResponse({'status': 'error', 'message': data}, status=response.status_code)

    except requests.RequestException as e:
        return JsonResponse({'error': f'Request failed: {str(e)}'}, status=500)

