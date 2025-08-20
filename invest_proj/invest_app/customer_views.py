from datetime import date
from decimal import Decimal
import string

import num2words
from invest_app.utils.shared_imports import *
from invest_app.utils.sessions import customer_login_required
from invest_app.utils.indiantime import format_datetime_ist 
from .models import (Admin, CompanyDroneModelInfo, CustomerRegister,
 InvoiceDetails,PaymentDetails, KYCDetails, CustomerMoreDetails, NomineeDetails, Role,AgreementDetails)
from invest_app.utils.msg91 import send_bulk_sms
from invest_app.utils.idfy_verification import (
    verify_aadhar_sync,
    verify_bank_account_sync
)
from .utils.s3_helper import ( delete_all_kyc_files,
upload_to_s3, generate_presigned_url)

from .utils.idfy_verification import (check_idfy_status_by_request_id, 
submit_idfy_aadhar_ocr, submit_idfy_pan_ocr, check_idfy_task_status,
 submit_idfy_pan_verification)

from django.template.loader import render_to_string
from weasyprint import HTML
from io import BytesIO
from django.core.mail import EmailMessage
from django.utils import timezone
from datetime import date
from django.utils.timezone import localtime
from num2words import num2words
from dateutil.relativedelta import relativedelta
# --------------
def get_indian_time():
    india_tz = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(india_tz)

def generate_otp():
    return random.randint(100000, 999999)
@csrf_exempt
def customer_register(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        token = data.get('token')
        email = data.get('email', '').strip().lower()
        mobile_no = data.get('mobile_no', '').strip()

        first_name = ''
        last_name = ''
        is_google_signup = False
        otp = None
        customer = None

        #Google Signup Flow
        if token:
            google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            response = requests.get(google_url)

            if response.status_code != 200:
                return JsonResponse({"error": "Google token invalid."}, status=400)

            google_data = response.json()
            if "error" in google_data:
                return JsonResponse({"error": "Invalid Token"}, status=400)

            email = google_data.get("email", "").strip().lower()
            first_name = google_data.get("given_name", "")
            last_name = google_data.get("family_name", "")
            is_google_signup = True

        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number."}, status=400)

        # 🔹 Admin assignment
        admin = Admin.objects.only("id").order_by("id").first()
        if not admin:
            return JsonResponse({"error": "No admin found for assignment."}, status=500)

        # 🔹 Check if customer already exists
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

            # 🔹 Existing user - update phase 1
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
            # 🔹 New Customer
            if is_google_signup:
                customer = CustomerRegister.objects.create(
                    email=email or '',
                    mobile_no=mobile_no or '',
                    first_name=first_name or '',
                    last_name=last_name or '',
                    register_status=1,
                    register_type="Google",
                    admin=admin
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
                    register_type="Email" if email else "Mobile",
                    admin=admin
                )

        # 🔹 Send OTP if non-Google
        if not is_google_signup:
            if email:
                send_otp_email(email, first_name or '', otp)
            if mobile_no:
                send_bulk_sms([mobile_no], otp)

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
        first_name = data.get('first_name', '').lower()
        last_name = data.get('last_name', '').lower()
        email = data.get('email', '').lower().strip()
        mobile_no = data.get('mobile_no', '').strip()


        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        #Optimize by limiting fields (use .only)
        customer_qs = None
        if email and mobile_no:
            customer_qs = CustomerRegister.objects.filter(email__iexact=email, mobile_no=mobile_no).only(
                "id", "email", "mobile_no", "first_name", "last_name", "otp", "account_status", "register_status", "otp_send_type"
            )
        elif email:
            customer_qs = CustomerRegister.objects.filter(email__iexact=email).only(
                "id", "email", "first_name", "last_name", "otp", "account_status", "register_status", "otp_send_type"
            )
        elif mobile_no:
            customer_qs = CustomerRegister.objects.filter(mobile_no=mobile_no).only(
                "id", "mobile_no", "first_name", "last_name", "otp", "account_status", "register_status", "otp_send_type"
            )

        customer = customer_qs.first() if customer_qs else None

        if not customer:
            return JsonResponse({"error": "customer not found with the provided email or mobile number"}, status=404)

        customer.clear_expired_otp()

        # Use caching if OTP was stored via cache.set() earlier
        cache_key = f"otp_{email or mobile_no}"
        cached_otp = cache.get(cache_key)

        if cached_otp and str(cached_otp) != str(otp):
            return JsonResponse({"error": "Invalid OTP."}, status=400)
        elif not cached_otp and (not customer.otp or int(customer.otp) != int(otp)):
            return JsonResponse({"error": "Invalid or expired OTP."}, status=400)

        update_fields = ['otp']  # clear otp
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
            # Handle based on OTP send type
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

        # Clear otp_send_type after verification
        customer.otp_send_type = None
        update_fields.append('otp_send_type')

        customer.save(update_fields=update_fields)

        # Cleanup OTP from cache
        cache.delete(cache_key)

        if customer.register_status == 1 and customer.account_status == 1:
            request.session['customer_id'] = customer.id
            request.session.save()
            return JsonResponse({
                "message": "OTP verified and login successful.",
                "customer_id": customer.id,
                "email": customer.email,
                "register_status": customer.register_status,
                "account_status": customer.account_status,
                "session_id": request.session.session_key
            }, status=200)
        
        request.session['customer_id'] = customer.id
        request.session.save()
        response_data = {
            "message": "OTP verified successfully.",
            "customer_id": customer.id,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
            "session_id": request.session.session_key,
        }

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
        customer_id = request.session.get('customer_id')
        email = data.get('email')
        mobile_no = data.get('mobile_no')
        first_name = data.get('first_name')
        last_name = data.get('last_name')

        if not customer_id:
            return JsonResponse({"error": "Customer ID not found in session or request."}, status=400)
        try:
            customer = CustomerRegister.objects.get(id=customer_id)
        except CustomerRegister.DoesNotExist:
            return JsonResponse({"error": "Customer not found."}, status=404)

        if customer.register_status != 1:
            return JsonResponse({"error": "First phase registration incomplete."}, status=400)

        if customer.mobile_no and not customer.email and not email:
            return JsonResponse({"error": "Mobile already verified in first phase. Please provide email to continue."}, status=400)

        if customer.email and not customer.mobile_no and not mobile_no:
            return JsonResponse({"error": "Email already verified in first phase. Please provide mobile to continue."}, status=400)

        customer.clear_expired_otp()
        otp = generate_otp()
        otp_sent = False
        otp_send_type = None
        update_fields = []

        # New mobile provided
        if not customer.mobile_no and mobile_no:
            if CustomerRegister.objects.filter(mobile_no=mobile_no).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Mobile number already in use."}, status=400)
            customer.mobile_no = mobile_no
            otp_send_type = 'Mobile'
            send_bulk_sms([mobile_no], otp)
            otp_sent = True
            update_fields.append('mobile_no')

        # New email provided
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
                send_bulk_sms([customer.mobile_no], otp)
                otp_send_type = 'Mobile'
                otp_sent = True
            else:
                return JsonResponse({"error": "No verified email or mobile to resend OTP."}, status=400)

        # Update name if changed
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
            "otp":otp,
            "customer_id": customer.id,
            "status_code": 200,
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

def send_otp_email(email, first_name, otp):
    subject = "[Pavaman] Please Verify Your Email"
    logo_url = f"{settings.AWS_S3_BUCKET_URL}/aviation-logo.png"

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

# ---------- Helper: Fetch User with Model-based Filters ----------
def fetch_user_by_email_or_mobile(model, email=None, mobile_no=None, extra_filter=None):
    """
    Search for user (customer/admin/role) by email or mobile with auto filters.
    """
    if model.__name__ == 'CustomerRegister':
        filters = {"account_status": 1, "register_status": 1}
    elif model.__name__ == 'Role':
        filters = {"status": 1, "delete_status": False}
    else:  # Admin
        filters = {"status": 1}

    if extra_filter:
        filters.update(extra_filter)

    query = model.objects.filter(**filters)
    if email and mobile_no:
        return query.filter(Q(email=email) | Q(mobile_no=mobile_no)).first()
    elif email:
        return query.filter(email=email).first()
    elif mobile_no:
        return query.filter(mobile_no=mobile_no).first()
    return None


# ---------- Helper: Generate, Save & Send OTP ----------
def send_and_store_otp(user, name, email=None, mobile_no=None):
    otp = generate_otp()
    user.otp = otp
    user.changed_on = timezone.now()
    print(user.otp)
    print(otp)

    if hasattr(user, 'otp_send_type'):
        user.otp_send_type = 'email' if email else 'mobile'
        user.save(update_fields=['otp', 'changed_on', 'otp_send_type'])
    else:
        user.save(update_fields=['otp', 'changed_on'])

    if email:
        send_otp_email(email, name, otp)
        cache.set(f"otp_{email}", otp, timeout=120)
    if mobile_no:
        send_bulk_sms([mobile_no], otp)
        cache.set(f"otp_{mobile_no}", otp, timeout=120)

    return otp

# ---------- Main View: Customer/Admin/Role Login ----------
@csrf_exempt
def customer_login(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        mobile_no = data.get('mobile_no', '').strip()
        token = data.get('token')

        first_name = ''
        last_name = ''
        user = None
        user_type = None
        user_id = None

        # ---------- Google Login ----------
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

            customer = fetch_user_by_email_or_mobile(CustomerRegister, email=email)
            if not customer:
                return JsonResponse({"error": "Account not found or not verified."}, status=404)

            request.session['customer_id'] = customer.id
            request.session.modified = True
            request.session.save()

            return JsonResponse({
                "message": "Login successful via Google.",
                "user_type": "customer",
                "user_id": customer.id,
                "email": customer.email,
                "mobile_no": customer.mobile_no,
                "first_name": customer.first_name or first_name,
                "last_name": customer.last_name or last_name,
                "register_status": customer.register_status,
                "account_status": customer.account_status,
                "session_id": request.session.session_key
            }, status=200)

        # ---------- OTP Login ----------
        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number or valid Google token."}, status=400)

        user = fetch_user_by_email_or_mobile(CustomerRegister, email, mobile_no)
        if user:
            user_type = "customer"
            user_id = user.id
            send_and_store_otp(user, user.first_name or first_name, email, mobile_no)

        else:
            partial_user = CustomerRegister.objects.filter(
                Q(email=email) | Q(mobile_no=mobile_no),
                register_status=1,
                account_status=0
            ).first()

            if partial_user:
                return JsonResponse({
                    "error": "Your account is not fully verified. Please complete your registration or signup process.",
                    "user_type": "customer",
                    "user_id": partial_user.id,
                    "register_status": partial_user.register_status,
                    "account_status": partial_user.account_status
                }, status=403)
            else:
                user = fetch_user_by_email_or_mobile(Admin, email, mobile_no)
                if user:
                    user_type = "admin"
                    user_id = user.id
                    send_and_store_otp(user, user.name, email, mobile_no)

                else:
                    user = fetch_user_by_email_or_mobile(Role, email, mobile_no)
                    if user:
                        user_type = "role"
                        user_id = user.id
                        full_name = f"{user.first_name} {user.last_name}".strip()
                        send_and_store_otp(user, full_name, email, mobile_no)
                    
        if user:
            return JsonResponse({
                "message": "OTP sent. It is valid for 2 minutes.",
                "user_type": user_type,
                "user_id": user_id,
                "status_code": 200,
            }, status=200)

        return JsonResponse({"error": "Account not found or not verified."}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

@customer_login_required 
@csrf_exempt
def customer_profile_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        action = str(data.get('action', 'view')).strip().lower()
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({"error": "Unauthorized: Login required."}, status=403)
        # session_customer_id = request.session.get('customer_id')
        # if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
        #     return JsonResponse({"error": "Unauthorized: Login required."}, status=403)

        customer = CustomerRegister.objects.only(
            "id", "first_name", "last_name", "email", "mobile_no",
            "register_status", "account_status", "kyc_accept_status", "payment_accept_status"
        ).filter(id=customer_id).first()

        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)

        update_fields = []

        if action == 'save_kyc_accept_status' and str(data.get('kyc_accept_status')) == '1':
            customer.kyc_accept_status = 1
            update_fields.append('kyc_accept_status')

        if action == 'save_payment_accept_status' and str(data.get('payment_accept_status')) == '1':
            customer.payment_accept_status = 1
            update_fields.append('payment_accept_status')

        if update_fields:
            customer.save(update_fields=update_fields)
        kyc= KYCDetails.objects.filter(customer=customer, pan_status=1).only("pan_name","pan_dob","aadhar_gender").first()
        full_name = kyc.pan_name if kyc and kyc.pan_name else f"{customer.first_name} {customer.last_name}"
        dob = kyc.pan_dob if kyc else None
        gender = kyc.aadhar_gender if kyc else None

        return JsonResponse({
            "customer_id": customer.id,
            "full_name": full_name,
            # "first_name": customer.first_name,
            # "last_name": customer.last_name,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
            "kyc_accept_status": customer.kyc_accept_status,
            "payment_accept_status": customer.payment_accept_status,
            "dob":dob,
            "gender":gender
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
    
def get_location_by_pincode(pincode):
    try:
        url = f"https://api.postalpincode.in/pincode/{pincode}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data[0]['Status'] == 'Success':
                post_office = data[0]['PostOffice'][0]
                return {
                    "district": post_office.get("District"),
                    "state": post_office.get("State"),
                    "country": post_office.get("Country"),
                    "city": post_office.get("Name"),
                    "block": post_office.get("Block", ""),
                }
    except:
        pass
    return {}
# ---------------------------------
# @customer_login_required
# @csrf_exempt
# def customer_more_details(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)

#     try:
#         data = json.loads(request.body)
#         customer_id = request.session.get('customer_id')
#         if not customer_id:
#             return JsonResponse({"error": "Unauthorized: Login required."}, status=403)

#         customer = CustomerRegister.objects.filter(id=customer_id).first()
#         if not customer:
#             return JsonResponse({"error": "Customer not found."}, status=404)

#         existing = CustomerMoreDetails.objects.filter(customer=customer).first()
#         if existing and existing.personal_status == 1:
#             return JsonResponse({
#                 "action": "view_only",
#                 "message": "Personal details already submitted.",
#                 "customer_readonly_info": {
#                     "customer_id": customer.id,
#                     "first_name": customer.first_name,
#                     "last_name": customer.last_name,
#                     "email": customer.email,
#                     "personal_status": existing.personal_status
#                 }
#             })

#         required = ["mobile_no", "email", "address", "pincode", "designation", "profession","gender","dob","fullname",]
#         for field in required:
#             if not data.get(field):
#                 return JsonResponse({"error": f"{field} is required."}, status=400)

#         location = get_location_by_pincode(data["pincode"]) or {}

#         more = CustomerMoreDetails.objects.create(
#             customer=customer,
#             address=data["address"],
#             pincode=data["pincode"],
#             designation=data["designation"],
#             profession=data["profession"],
#             district=location.get("district", ""),
#             state=location.get("state", ""),
#             country=location.get("country", ""),
#             city=location.get("city", ""),
#             mandal=location.get("block", ""),
#             personal_status=1
#         )

#         return JsonResponse({
#             "message": "Customer details saved successfully.",
#             "action": "add_details",
#             "customer_details": {
#                 "customer_id": customer.id,
#                 "first_name": customer.first_name,
#                 "last_name": customer.last_name,
#                 "email": customer.email,
#                 "mobile_no": customer.mobile_no,
#                 "address": more.address,
#                 "pincode": more.pincode,
#                 "designation": more.designation,
#                 "profession": more.profession,
#                 "district": more.district,
#                 "state": more.state,
#                 "country": more.country,
#                 "city": more.city,
#                 "mandal": more.mandal,
#                 "personal_status": more.personal_status,
#             }
#         })

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

# -----------------------------------------
@csrf_exempt
def customer_more_details(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')

        if not customer_id:
            return JsonResponse({"error": "Unauthorized: Login required."}, status=403)

        customer = CustomerRegister.objects.filter(id=customer_id).first()
        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)

        # Prevent resubmission
        existing = CustomerMoreDetails.objects.filter(customer=customer, status=1).order_by('-id').first()
        if existing and existing.personal_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Personal details already submitted.",
                "customer_readonly_info": {
                    "customer_id": customer.id,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "personal_status": existing.personal_status
                }
            })

        # Required fields
        required_fields = ["designation", "profession", "address", "pincode", "same_address","guardian_name","guardian_relation"]
        for field in required_fields:
            if field not in data:
                return JsonResponse({"error": f"{field} is required."}, status=400)

        same_address = data.get("same_address", False)

        if not same_address:
            if not data.get("present_address") or not data.get("present_pincode"):
                return JsonResponse({"error": "present_address and present_pincode are required."}, status=400)
            if not data.get("address") or not data.get("pincode"):
                return JsonResponse({"error": "address and pincode are required when addresses are different."}, status=400)

            present_location = get_location_by_pincode(data["present_pincode"]) or {}
            permanent_location = get_location_by_pincode(data["pincode"]) or {}

            address_data = {
                "present_address": data["present_address"],
                "present_pincode": data["present_pincode"],
                "present_city": present_location.get("city", ""),
                "present_district": present_location.get("district", ""),
                "present_state": present_location.get("state", ""),
                "present_country": present_location.get("country", ""),
                "present_mandal": present_location.get("block", ""),
                "address": data["address"],
                "pincode": data["pincode"],
                "city": permanent_location.get("city", ""),
                "district": permanent_location.get("district", ""),
                "state": permanent_location.get("state", ""),
                "country": permanent_location.get("country", ""),
                "mandal": permanent_location.get("block", "")
            }
        else:
            location = get_location_by_pincode(data["pincode"]) or {}
            address_data = {
                "present_address": data["address"],
                "present_pincode": data["pincode"],
                "present_city": location.get("city", ""),
                "present_district": location.get("district", ""),
                "present_state": location.get("state", ""),
                "present_country": location.get("country", ""),
                "present_mandal": location.get("block", ""),
                "address": data["address"],
                "pincode": data["pincode"],
                "city": location.get("city", ""),
                "district": location.get("district", ""),
                "state": location.get("state", ""),
                "country": location.get("country", ""),
                "mandal": location.get("block", "")
            }

        # Save to DB
        more = CustomerMoreDetails.objects.create(
            customer=customer,
            guardian_name=data["guardian_name"],
            guardian_relation=data["guardian_relation"],
            same_address=same_address,
            designation=data["designation"],
            profession=data["profession"],
            personal_status=1,
            status=1,  # Important to fetch correctly later
            **address_data
        )

        return JsonResponse({
            "message": "Customer details saved successfully.",
            "action": "add_details",
            "customer_details": {
                "customer_id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "guardian_name":more.guardian_name,
                "guardian_relation":more.guardian_relation,
                "present_address": more.present_address,
                "permanent_address": more.address,
                "same_address": more.same_address,
                "present_city": more.present_city,
                "city": more.city,
                "profession": more.profession,
                "designation": more.designation,
                "state": more.state,
                "present_state": more.present_state,
                "country": more.country,
                "present_country": more.present_country,
                "pincode": more.pincode,
                "present_pincode": more.present_pincode
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: '{str(e)}'"}, status=500)
    
@customer_login_required
@csrf_exempt
def verify_pan_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)
    pan_file = request.FILES.get('pan_doc')
    if not pan_file:
        return JsonResponse({'error': 'PAN document is required'}, status=400)

    try:
        from .models import KYCDetails, CustomerRegister
        customer = CustomerRegister.objects.get(id=customer_id)
        # Use shared helper
        file_key, file_url, error_response = validate_and_upload_document(pan_file, customer, doc_type='pan')
        if error_response:
            return error_response
    
        status_code, response_json, task_id = submit_idfy_pan_ocr(file_url)
        print("IDfy OCR response:", response_json)

        if status_code not in [200, 202]:
            return JsonResponse({
                'error': 'Failed to submit to IDfy',
                'status_code': status_code,
                'submitted_url': file_url,
                'details': response_json
            }, status=500)

        # if status_code != 200:
        #     return JsonResponse({'error': 'Failed to submit to IDfy', 'details': response_json}, status=500)

        for _ in range(5):
            time.sleep(2)
            status_code, result = check_idfy_task_status(task_id)
            print("Polling OCR result:", result)
            if result.get("status") == "completed":
                pan_data = result.get("result", {})

                kyc, created = KYCDetails.objects.update_or_create(
                    customer=customer,
                    defaults={
                        "pan_number": pan_data.get("pan_number"),
                        "pan_name": pan_data.get("full_name"),
                        "pan_dob": pan_data.get("dob"),
                        "pan_task_id": task_id,
                        "pan_group_id": settings.IDFY_GROUP_ID,
                        "pan_request_id": result.get("request_id"),
                        "idfy_pan_status": result.get("status"),
                        "pan_status": 1,
                        "pan_path": file_key,
                    }
                )

                return JsonResponse({
                    'status': 'success',
                    'pan_data': pan_data,
                    'request_id': result.get("request_id"),
                    'task_id': task_id,
                    'file_key': file_key,
                    'file_url': file_url,
                    'pan_path': file_key
                })

        return JsonResponse({
            'status': 'pending',
            'message': 'Verification in progress',
            'request_id': response_json.get("request_id"),
            'task_id': task_id,
            'file_key': file_key,
            'file_url': file_url,
            'pan_path': file_key
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_customer_document_path(customer_id, first_name, last_name, doc_type):
    """
    Fetch the S3 key/path of the specified document type (PAN or Aadhar) for a customer.
    :param customer_id: int
    :param first_name: str
    :param last_name: str
    :param doc_type: str ("pan" or "aadhar")
    :return: str or None (S3 key)
    """
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )

    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    customer_folder = f'customerdoc/{customer_id}_{first_name.lower()}{last_name.lower()}/'

    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=customer_folder)
    if 'Contents' not in response:
        return None

    for obj in response['Contents']:
        key = obj['Key']
        if f'{doc_type.lower()}_' in key.lower():
            return key  # Return PAN or Aadhar path

    return None

@customer_login_required
@csrf_exempt
def get_pan_verification_status(request):
    import traceback

    try:
        customer_id = request.session.get('customer_id')
        request_id = request.GET.get('request_id')
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)
        if not request_id:
            return JsonResponse({'error': 'Request_id is required'}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)

        # Get OCR result by request_id
        status_code, result = check_idfy_status_by_request_id(request_id)
        print("IDfy raw result:", result)

        # If list, take the first item
        if isinstance(result, list) and result:
            result = result[0]

        extraction = result.get("result", {}).get("extraction_output", {})
        pan_number = extraction.get("id_number")
        pan_name = extraction.get("name_on_card")
        pan_dob = extraction.get("date_of_birth")

        if not all([pan_name, pan_dob, pan_number]):
            return JsonResponse({
                'status': 'ocr_failed',
                'message': 'Missing extracted data',
                'ocr_data': extraction
            }, status=422)

        print("Using extracted PAN data:", pan_number, pan_name, pan_dob)

        # Submit source verification without file
        verify_status_code, verify_response, verify_task_id, verify_request_id = submit_idfy_pan_verification(
            name=pan_name,
            # dob="1990-01-01",
            dob = extraction.get("date_of_birth") or "1990-01-01",
            pan_number=pan_number
        )

        print("Submission response:", verify_status_code)
        print("API response body:", verify_response)

        if verify_status_code not in [200, 202]:
            return JsonResponse({
                'error': 'Source verification submission failed',
                'ocr_data': extraction,
                'response': verify_response
            }, status=500)
        
        return JsonResponse({
            'status': 'submitted',
            'message': 'Pan number verification started',
            'source_task_id': verify_task_id,
            'request_id': verify_request_id,
            'ocr_data': extraction
        })

    except Exception as e:
        print("Exception occurred during PAN verification submission")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    
@customer_login_required
@csrf_exempt
def get_pan_source_verification_status(request):
    customer_id = request.session.get('customer_id')
    request_id = request.GET.get("request_id")

    if not request_id:
        return JsonResponse({'error': 'Missing request_id'}, status=400)

    try:
        customer = CustomerRegister.objects.get(id=customer_id)

        # Resolve task_id using request_id
        status_code, results = check_idfy_status_by_request_id(request_id)
        if isinstance(results, list) and results:
            result = results[0]
        else:
            result = results

        task_id = result.get("task_id")
        status = result.get("status")

        if status != "completed":
            return JsonResponse({'status': 'pending', 'message': 'Source verification still pending'}, status=202)
        print("🔍 Full raw result from IDfy:", json.dumps(result, indent=2))

        result_data = result.get("result", {})
        if not result_data:
            return JsonResponse({
                "status": "failed",
                "message": "Missing result from IDfy",
                "raw_result": result
            }, status=422)

        source_output = result_data.get("source_output")
        if not source_output:
            return JsonResponse({
                "status": "failed",
                "message": "Missing source_output from IDfy result",
                "raw_result": result
            }, status=422)

        name_match = source_output.get("name_match")
        dob_match = source_output.get("dob_match")
        pan_status = source_output.get("pan_status")
        print("source_output from IDfy:", source_output)

        if not (name_match and dob_match and pan_status == "Existing and Valid. PAN is Operative"):

            matched_data = {
            "id_number": source_output.get("input_details", {}).get("input_pan_number"),
            "name": source_output.get("input_details", {}).get("input_name"),
            "dob": source_output.get("input_details", {}).get("input_dob")
        }
            

        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found."}, status=500)

        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "pan_number": matched_data.get("id_number"),
                "pan_name": matched_data.get("name"),
                "pan_dob": matched_data.get("dob"),
                "pan_task_id": task_id,
                "pan_group_id": settings.IDFY_GROUP_ID,
                "idfy_pan_status": status,
                "pan_request_id": request_id,
                "pan_status": 1,
                "admin":admin,
                "pan_path": get_customer_document_path(customer.id, customer.first_name, customer.last_name, "pan"),
            }
        )
        
        return JsonResponse({
            'status': 'verified',
            'message': 'Source verification successful',
            'verified_data': matched_data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    



def generate_customer_file_key(file_obj, customer, doc_type='pan', prefix='customerdoc'):
    customer_name = f"{customer.first_name}{customer.last_name}".replace(" ", "").lower()
    customer_folder = f"{prefix}/{customer.id}_{customer_name}"
    file_ext = file_obj.name.split('.')[-1].lower()
    file_key = f"{customer_folder}/{doc_type}_{customer_name}_{uuid.uuid4()}.{file_ext}"
    return file_key, customer_name, customer_folder, file_ext

def validate_and_upload_document(file_obj, customer, doc_type='aadhar'):
    file_name = file_obj.name
    mime_type, _ = mimetypes.guess_type(file_name)
    file_ext = os.path.splitext(file_name)[1].lower()
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']

    if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
        return None, None, JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed.'}, status=400)

    # Use generate_customer_file_key
    file_key, _, _, _ = generate_customer_file_key(file_obj, customer, doc_type)
    upload_to_s3(file_obj, file_key)
    file_url = generate_presigned_url(file_key, expires_in=300)

    return file_key, file_url, None
@customer_login_required
@csrf_exempt
def verify_aadhar_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)
    aadhar_file = request.FILES.get('aadhar_doc')
    if not aadhar_file:
        return JsonResponse({'error': 'aadhar document is required'}, status=400)

    try:
        from .models import KYCDetails, CustomerRegister
        customer = CustomerRegister.objects.get(id=customer_id)
        file_key, file_url, error_response = validate_and_upload_document(aadhar_file, customer, doc_type='aadhar')
        if error_response:
            return error_response

        # file_name = aadhar_file.name
        # mime_type, _ = mimetypes.guess_type(file_name)
        # file_ext = os.path.splitext(file_name)[1].lower()

        # allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        # allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']
        # if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
        #     return JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed.'}, status=400)

        # file_key = upload_to_s3(aadhar_file, customer=customer, doc_type='aadhar')
        # file_url = generate_presigned_url(file_key, expires_in=300)

        # Submit to IDfy aadhar OCR
        status_code, response_json, task_id = submit_idfy_aadhar_ocr(file_url)
        if status_code not in [200, 202]:
            return JsonResponse({
                'error': 'Failed to submit to IDfy',
                'status_code': status_code,
                'details': response_json
            }, status=500)
        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found."}, status=500)

        # Poll for result
        for _ in range(5):
            time.sleep(2)
            status_code, result = check_idfy_task_status(task_id)
            if result.get("status") == "completed":

                aadhar_data = result.get("result", {})
                # Fetch verified PAN details
                kyc_pan = KYCDetails.objects.filter(customer=customer, pan_status=1).first()
                if not kyc_pan:
                    return JsonResponse({
                        "status": "failed",
                        "message": "PAN verification is required before aadhar verification."
                    }, status=400)

                # Normalize names and dob
                aadhar_name = aadhar_data.get("name_on_card", "").strip().lower()
                aadhar_dob = str(aadhar_data.get("date_of_birth"))
                pan_name = kyc_pan.pan_name.strip().lower()
                pan_dob = str(kyc_pan.pan_dob)
                aadhar_gender= aadhar_data.get("gender","").strip().lower()
                # Match aadhar with PAN
                if aadhar_name != pan_name or aadhar_dob != pan_dob:
                    #Delete Aadhaar document from S3
                     delete_all_kyc_files(customer.id, customer.first_name, customer.last_name, 'pan')
                     return JsonResponse({
                        "status": "failed",
                        "message": "aadhar and PAN details do not match. Please verify your PAN number correctly.",
                        "pan_name": kyc_pan.pan_name,
                        "aadhar_name": aadhar_data.get("name_on_card"),
                        "pan_dob": pan_dob,
                        "aadhar_dob": aadhar_dob
                    }, status=422)

                # Store aadhar data after match
                kyc, created = KYCDetails.objects.update_or_create(
                    customer=customer,
                    defaults={
                        "aadhar_number": aadhar_data.get("id_number"),
                        "aadhar_name": aadhar_data.get("name_on_card"),
                        "aadhar_dob": aadhar_data.get("date_of_birth"),
                        "aadhar_gender": aadhar_data.get("gender"),            
                        "aadhar_task_id": task_id,
                        "aadhar_request_id": result.get("request_id"),
                        "idfy_aadhar_status": result.get("status"),
                        "aadhar_status": 1,
                        "aadhar_path": file_key,
                        "admin": admin,
                    }
                )
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'aadhar KYC matched with PAN and saved successfully.',
                    'aadhar_data': aadhar_data,
                    'request_id': result.get("request_id"),
                    'task_id': task_id,
                    'file_key': file_key,
                    'file_url': file_url
                })

        # If timeout, return pending status
        return JsonResponse({
            'status': 'pending',
            'message': 'Verification in progress',
            'request_id': response_json.get("request_id"),
            'task_id': task_id,
            'file_key': file_key,
            'file_url': file_url
        }, status=202)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
@customer_login_required    
@csrf_exempt
def get_aadhar_verification_status(request):
    customer_id = request.session.get('customer_id')
    request_id = request.GET.get('request_id')
    if not customer_id:
        return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)
    if not request_id:
        return JsonResponse({'error': 'Request_id is required'}, status=400)

    try:
        customer = CustomerRegister.objects.get(id=customer_id)
    except CustomerRegister.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)

    try:
        # Aadhaar document path
        aadhar_path = get_customer_document_path(customer.id, customer.first_name, customer.last_name, 'aadhar')

        # Fetch from IDfy
        status_code, result = check_idfy_status_by_request_id(request_id)
        if isinstance(result, list):
            if not result:
                return JsonResponse({'error': 'No result found for this request ID'}, status=404)
            result = result[0]

        status = result.get("status")
        extraction = result.get("result", {}).get("extraction_output", {})
        extracted_aadhar_number = extraction.get("id_number")
        aadhar_name = extraction.get("name_on_card", "").strip().lower()
        aadhar_dob = str(extraction.get("date_of_birth"))
        aadhar_gender= extraction.get("gender")
        if status != "completed":
            return JsonResponse({
                'status': status,
                'message': 'Aadhaar OCR still in progress.',
                'extracted_data': extraction
            }, status=202)

        if not extracted_aadhar_number:
            return JsonResponse({
                "status": "failed",
                "message": "Aadhaar number could not be extracted from the document."
            }, status=400)

        # Match Aadhaar name/DOB with PAN
        kyc_pan = KYCDetails.objects.filter(customer=customer, pan_status=1).first()
        if not kyc_pan:
            return JsonResponse({
                "status": "failed",
                "message": "PAN verification is required before Aadhaar verification."
            }, status=400)

        pan_name = kyc_pan.pan_name.strip().lower()
        pan_dob = str(kyc_pan.pan_dob)

        if aadhar_name != pan_name or aadhar_dob != pan_dob:
            delete_all_kyc_files(customer.id, customer.first_name, customer.last_name, 'pan')

            return JsonResponse({
                "status": "failed",
                "message": "Aadhaar and PAN details do not match.",
                "pan_name": kyc_pan.pan_name,
                "aadhar_name": extraction.get("name_on_card"),
                "pan_dob": pan_dob,
                "aadhar_dob": aadhar_dob,
                "aadhar_gender": aadhar_gender
            }, status=422)

        # Aadhaar name/DOB matched, now verify Aadhaar number
        task_id = str(uuid.uuid4())
        result = verify_aadhar_sync(extracted_aadhar_number, task_id)
        idfy_aadhar_status = result.get("status", None)
        aadhar_status = 1 if idfy_aadhar_status == "completed" else 0

        if aadhar_status != 1:
            return JsonResponse({
                "status": "failed",
                "message": "Aadhaar number verification failed.",
                "idfy_aadhar_status": idfy_aadhar_status,
                "aadhar_number": extracted_aadhar_number,
                "response": result.get("result")
            }, status=422)

        #Save verified Aadhaar info
        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found"}, status=500)

        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "aadhar_number": extracted_aadhar_number,
                "aadhar_gender": aadhar_gender,
                "aadhar_status": aadhar_status,
                "idfy_aadhar_status": idfy_aadhar_status,
                "aadhar_task_id": task_id,
                "aadhar_request_id": request_id,
                "aadhar_path": aadhar_path,
                "admin": admin,
            }
        )
      
        return JsonResponse({
            "status": "completed",
            "message": "Aadhaar KYC verified successfully after name and DOB matched with PAN.",
            "aadhar_number": extracted_aadhar_number,
            "idfy_aadhar_status": idfy_aadhar_status,
            "task_id": task_id
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Error verifying Aadhaar: {str(e)}'}, status=500)
@customer_login_required
@csrf_exempt
def bank_account_verification_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

        account_number = data.get("account_number")
        ifsc = data.get("ifsc")

        if not account_number or not ifsc:
            return JsonResponse({'error': 'account_number and ifsc are required'}, status=400)

        customer = get_object_or_404(CustomerRegister, id=customer_id)
        kyc = KYCDetails.objects.filter(customer=customer).first()

        # If already verified, return early
        if kyc and kyc.bank_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Bank account already verified. Please proceed to the next step.",
                "bank_status": kyc.bank_status,
                "idfy_bank_status": kyc.idfy_bank_status
            }, status=200)

        # Call sync function and parse
        task_id, result = verify_bank_account_sync(account_number, ifsc)
        idfy_bank_status = result.get("status", "")
        result_data = result.get("result", {})

        # Extract holder name properly
        bank_holder_name = (
            result_data.get("name_at_bank") or
            result_data.get("account_holder_name") or
            result_data.get("customer_name") or
            ""
        ).strip()

        bank_name = (
            result_data.get("bank_name") or
            result_data.get("bank") or
            result_data.get("branch_bank") or
            result_data.get("bank_details", {}).get("bank_name") or
            ""
        ).strip()
        
        verified = result_data.get("status", "") == "id_found"
        bank_name = result_data.get("bank_name", "") or bank_holder_name
        pan_name = kyc.pan_name.strip() if kyc and kyc.pan_name else ""

        if not bank_holder_name:
            return JsonResponse({
                "action": "manual_review",
                "message": "Bank holder name not found. Cannot perform name match.",
                "bank_holder_name": "",
                "pan_name": pan_name,
                "verified": verified,
                "idfy_bank_status": idfy_bank_status,
                "raw_response": result
            }, status=400)
        

        # Compare PAN and Bank Holder Name (case-insensitive)
        is_name_matched = pan_name.lower() == bank_holder_name.lower()

        if not is_name_matched:
            return JsonResponse({
                "action": "manual_review",
                "message": "Name mismatch between PAN and bank account holder.",
                "bank_holder_name": bank_holder_name,
                "pan_name": pan_name,
                "verified": verified,
                "idfy_bank_status": idfy_bank_status,
                "raw_response": result
            }, status=400)

        # ✅ Save only if name matched AND IDfy status is 'completed'
        print("Bank Holder Name:", bank_holder_name)
        print("Bank Name:", bank_name)

        if is_name_matched and idfy_bank_status == "completed":
            KYCDetails.objects.update_or_create(
                customer=customer,
                defaults={
                    "bank_account_number": account_number,
                    "ifsc_code": ifsc,
                    "bank_name": bank_name,
                    "bank_task_id": task_id,
                    "idfy_bank_status": idfy_bank_status,
                    "bank_status": 1,
                    "bank_holder_name": bank_holder_name,
                    "bank_pan_name_match": True
                }
            )

        return JsonResponse({
            "action": "verify",
            "message": "Bank verification successful. Details saved." if idfy_bank_status == "completed" else "Name matched. Awaiting completion from IDfy.",
            "verified": verified,
            "bank_status": 1 if idfy_bank_status == "completed" else 0,
            "idfy_bank_status": idfy_bank_status,
            "task_id": task_id,
            "bank_holder_name": bank_holder_name,
            "pan_name": pan_name,
            "name_matched": True,
            "raw_response": result,
            "bank_name": bank_name,
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@customer_login_required
@csrf_exempt
def upload_pdf_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

    customer = get_object_or_404(CustomerRegister, id=customer_id)
    kyc, _ = KYCDetails.objects.get_or_create(customer=customer)
    # more, _ = CustomerMoreDetails.objects.get_or_create(customer=customer)
    more = CustomerMoreDetails.objects.filter(customer=customer, status=1).order_by('-id').first()
    if not more:
        more = CustomerMoreDetails.objects.create(customer=customer, status=1)


    # Handle JSON status-check request
    if request.content_type.startswith('application/json'):
        try:
            data = json.loads(request.body)
            doc_type = data.get('doc_type')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        if not doc_type or doc_type not in ['selfie', 'signature']:
            return JsonResponse({'error': "Status check only supported for 'selfie' or 'signature'"}, status=400)

        if doc_type == 'selfie':
            return JsonResponse({
                "action": "view_only" if more.selfie_status == 1 else "not_uploaded",
                "selfie_status": more.selfie_status,
                "file_path": more.selfie_path if more.selfie_status == 1 else None,
            })
        elif doc_type == 'signature':
            return JsonResponse({
                "action": "view_only" if more.signature_status == 1 else "not_uploaded",
                "signature_status": more.signature_status,
                "file_path": more.signature_path if more.signature_status == 1 else None,
            })

    # Handle file upload (FormData)
    else:
        doc_type = request.POST.get('doc_type')
        file = request.FILES.get('kyc_file')

        if not doc_type or not file:
            return JsonResponse({'error': 'doc_type and file are required.'}, status=400)

        if doc_type not in ['aadhar', 'pan', 'selfie', 'signature']:
            return JsonResponse({'error': "Invalid doc_type."}, status=400)

        file_key, file_url, error_response = validate_and_upload_document(file, customer, doc_type)
        if error_response:
            return error_response

        if doc_type == 'selfie':
            more.selfie_path = file_key
            more.selfie_status = 1
        elif doc_type == 'signature':
            more.signature_path = file_key
            more.signature_status = 1

        more.save()

        return JsonResponse({
            "status": "success",
            "message": f"{doc_type.capitalize()} uploaded successfully.",
            "file_url": file_url,
            "selfie_status": more.selfie_status,
            "signature_status": more.signature_status
        })

def get_s3_url(path):
    if path:
        return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{path}"
    return None

@csrf_exempt
def preview_customer_details(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        # data = json.loads(request.body)
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)
       
        customer = CustomerRegister.objects.only("id", "email", "mobile_no").filter(id=customer_id).first()
        kyc = KYCDetails.objects.only("id", "pan_number","pan_name","pan_dob", "aadhar_number","aadhar_gender", "bank_account_number",
        "ifsc_code", "bank_name","aadhar_path", "pan_path").filter(customer_id=customer_id,status=1).first()
        more = CustomerMoreDetails.objects.only(
            "address", "city", "state", "country", "pincode", "mandal",
            "district","gender", "profession", "designation", "personal_status",
            "selfie_path", "signature_path"
        ).filter(customer_id=customer_id,status=1).first()
        nominee = NomineeDetails.objects.only(
            "first_name", "last_name", "relation", "dob", "address_proof",
            "address_proof_path", "id_proof_path","share"
        ).filter(customer_id=customer_id,status=1).first()

        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)
        if not kyc:
            return JsonResponse({"error": "KYC details not found."}, status=404)
        if not more:
            return JsonResponse({"error": "Personal details not found."}, status=404)
        # if not nominee:
        #     return JsonResponse({"error": "Nominee details not found."}, status=404)

        return JsonResponse({
            "message": "All customer data retrieved successfully.",
            "customer": {
                "customer_id": customer.id,
                "email": customer.email,
                "mobile_no": customer.mobile_no,
            },
            "kyc": {
                "pan_number": kyc.pan_number,
                "pan_name": kyc.pan_name,
                "pan_dob": str(kyc.pan_dob),
                "aadhar_number": kyc.aadhar_number,
                "aadhar_gender":kyc.aadhar_gender,
                "bank_account_number": kyc.bank_account_number,
                "ifsc_code": kyc.ifsc_code,
                "bank_name": kyc.bank_name,
                "pan_doc_url": get_s3_url(kyc.pan_path),
                "aadhar_doc_url": get_s3_url(kyc.aadhar_path),
            },
            "personal_details": {
                "address": more.address,
                "city": more.city,
                "state": more.state,
                "country": more.country,
                "pincode": more.pincode,
                "mandal": more.mandal,
                "district": more.district,
                "dob": str(more.dob),
                "gender": more.gender,
                "profession": more.profession,
                "designation": more.designation,
                "personal_status": more.personal_status,
                "selfie_url": get_s3_url(more.selfie_path),
                "signature_url": get_s3_url(more.signature_path),
            },
            # "nominee": {
            #     "first_name": nominee.first_name,
            #     "last_name": nominee.last_name,
            #     "relation": nominee.relation,
            #     "dob": str(nominee.dob),
            #     "share":nominee.share,
            #     "address_proof": nominee.address_proof,
            #     "address_proof_url": get_s3_url(nominee.address_proof_path),
            #     "id_proof_url": get_s3_url(nominee.id_proof_path),
            # }
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@customer_login_required
@csrf_exempt
def completed_status(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

        customer = CustomerRegister.objects.filter(id=customer_id, status=1).first()
        if not customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        kyc = KYCDetails.objects.filter(customer=customer, status=1).first()
        pan_complete = kyc.pan_status == 1 if kyc else False
        aadhar_complete = kyc.aadhar_status == 1 if kyc else False

        # more = CustomerMoreDetails.objects.filter(customer=customer, status=1).order_by('-id').first()
        # more = CustomerMoreDetails.objects.filter(customer=customer).order_by('-id').first()

        # personal_complete = more.personal_status == 1 if more else False
        # selfie_complete = more.selfie_status == 1 if more else False
        # signature_complete = more.signature_status == 1 if more else False

        more = CustomerMoreDetails.objects.filter(customer=customer, status=1).order_by('-id').first()

        personal_complete = more.personal_status == 1 if more else False
        selfie_complete = more.selfie_status == 1 if more else False
        signature_complete = more.signature_status == 1 if more else False




        kyc_completed = all([
            pan_complete,
            aadhar_complete,
            personal_complete,
            selfie_complete,
            signature_complete
        ])

        if kyc_completed:
            return JsonResponse({'message': 'All KYC details are completed.'}, status=200)
        else:
            return JsonResponse({
                'message': 'KYC details are incomplete.',
                'pan_status': pan_complete,
                'aadhar_status': aadhar_complete,
                'personal_status': personal_complete,
                'selfie_status': selfie_complete,
                'signature_status': signature_complete,
            }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

#part wise payment 
@customer_login_required
@csrf_exempt
def create_drone_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = request.session.get('customer_id')
        email = data.get('email')
        quantity = int(data.get('quantity') or 1)
        # current_payment = float(data.get('price') or 0)
        total_amount = Decimal(data.get('total_amount') or 0)
        payment_type = data.get('payment_type', 'fullpayment').lower()  # full or partial
        
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

        if not all([email, quantity, total_amount]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        if payment_type not in ["fullpayment", "insatallment"]:
            return JsonResponse({'error': 'Invalid payment type'}, status=400)

        if quantity > 10:
            return JsonResponse({'error': 'You can purchase a maximum of 10 drones.'}, status=400)

        customer = CustomerRegister.objects.filter(id=customer_id, email=email,status=1).first()
        if not customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        unit_price = 1200000
        total_required = unit_price * quantity
        
        if total_amount > total_required:
            return JsonResponse({
                'error': f'Maximum amount is ₹{total_required:,}. Please enter valid amount.'
            }, status=400)

        # Get latest drone_order_id
        latest_order = PaymentDetails.objects.filter(customer=customer,status=1).order_by('-created_at').first()
        if latest_order:
            latest_order_id = latest_order.drone_order_id
            latest_order_status = PaymentDetails.objects.filter(
                customer=customer,
                drone_order_id=latest_order_id
            ).values_list('payment_status', flat=True).first()

            # If the previous order is unpaid (status not 1), delete it
            if latest_order_status != 1 and latest_order.drone_payment_status != 'captured':
                PaymentDetails.objects.filter(
                    customer=customer,
                    drone_order_id=latest_order_id
                ).delete()

        # Razorpay per-order limit (₹5,00,000)
        MAX_RZP_ORDER_LIMIT = 500000

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        orders = []
        drone_order_id = f"OD{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
        admin = Admin.objects.filter(id=1).first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)

        next_part = 1

        amount_remaining = total_amount
        while amount_remaining > 0:
            split_amount = min(amount_remaining, MAX_RZP_ORDER_LIMIT)
            amount_paise = int(split_amount * 100)

            order = client.order.create({
                'amount': amount_paise,
                'currency': 'INR',
                'payment_capture': 1,
                'notes': {
                    'customer_id': str(customer_id),
                    'email': email,
                    'drone_order_id': drone_order_id,
                    'part': str(next_part),
                    'quantity': str(quantity),
                    'unit_price': str(unit_price),
                }
            })

            PaymentDetails.objects.create(
                customer=customer,
                razorpay_order_id=order['id'],
                amount=split_amount,
                total_amount=total_amount,
                part_number=next_part,
                drone_payment_status='created',
                quantity=quantity,
                drone_order_id=drone_order_id,
                payment_type=payment_type,
                admin=admin
            )

            orders.append({
                'order_id': order['id'],
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'amount': float(split_amount),
                'currency': 'INR',
                'email': email,
                'part_number': next_part,
                'quantity': quantity,
                
            })

            amount_remaining -= split_amount
            next_part += 1

        return JsonResponse({
            'message': f'{len(orders)} order(s) created.',
            'drone_order_id': drone_order_id,
            'customer_id': customer_id,
            'payment_type':payment_type,
            'orders': orders
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

#combine status 
#    
@customer_login_required
@csrf_exempt
def payment_status_check(request):
    try:
        data = json.loads(request.body)
        customer_id=data.get("customer_id") or request.session.get("customer_id")
        # customer_id = request.session.get("customer_id")
        payment_type = data.get("payment_type", "installment")
        drone_order_id = data.get("drone_order_id")

        if not customer_id:
            return JsonResponse({"error": "Unauthorized: Login required"}, status=403)

        # Step 1: Get latest drone_order_id if not provided
        if not drone_order_id:
            latest = PaymentDetails.objects.filter(
                customer_id=customer_id,
                payment_type=payment_type
            ).order_by('-id').first()

            if latest:
                drone_order_id = latest.drone_order_id
            else:
                return JsonResponse({
                    "paid": False,
                    "message": f"No {payment_type} orders found yet.",
                    "payment_status": 0
                })

        # Step 2: Get all parts of the order
        all_parts = PaymentDetails.objects.filter(
            customer_id=customer_id,
            drone_order_id=drone_order_id,
            payment_type=payment_type
        )
        
        if not all_parts.exists():
            return JsonResponse({
                "paid": False,
                "message": "Order not found for this payment type.",
                "payment_status": 0
            })
        # -----------
        # Get all invoices related to this drone_order_id
        invoice_qs = InvoiceDetails.objects.filter(
            payment__drone_order_id=drone_order_id,
            payment__customer_id=customer_id,
            status=1
        )

        total_invoices = invoice_qs.count()
        # Separate total amounts for each type
        drone_amount = invoice_qs.filter(invoice_type='drone').aggregate(
            total=Sum('total_invoice_amount'))['total'] or Decimal('0.00')


        accessory_amounts = invoice_qs.filter(invoice_type='accessory') \
            .values_list('total_invoice_amount', flat=True).distinct()

        # If there are any accessory invoices, take only one unique amount
        accessory_amount = accessory_amounts[0] if accessory_amounts else Decimal('0.00')

        amc_amount = invoice_qs.filter(invoice_type='amc').aggregate(
            total=Sum('total_invoice_amount'))['total'] or Decimal('0.00')

        # Deduplicate drone + accessory if same
        if drone_amount == accessory_amount and drone_amount > 0:
            total_invoice_amount = drone_amount + amc_amount
        else:
            total_invoice_amount = drone_amount + accessory_amount + amc_amount
        invoice_status_sum = invoice_qs.aggregate(total=Sum('total_invoice_status'))['total'] or 0
        total_invoice_status = 1 if invoice_status_sum == 5 else 0
        # -------------
        total_parts = all_parts.count()
        paid_parts = all_parts.filter(drone_payment_status='captured').count()  

        # For both installment and fullpayment, use same fields ,  captured
        total_amount = all_parts.first().total_amount or 0
        total_paid = all_parts.filter(drone_payment_status='captured').aggregate(
            total=Sum('amount')
        )['total'] or 0

        remaining_amount = max(total_amount - total_paid, 0)
        payment_status = all_parts.first().payment_status

        # Step 3: Days left (for installment only)
        days_left = None
        if payment_type == "installment":
            first_payment = all_parts.order_by('created_at').first()
            start_date = first_payment.created_at.date() if first_payment else timezone.now().date()
            today = timezone.now().date()
            days_left = max(0, 2 - (today - start_date).days)
  
        # Final paid status check
        paid = total_paid >= total_amount and total_amount > 0

        return JsonResponse({
            "paid": paid,
            "message": "✅ Fully paid. You can proceed with a new order." if paid else f"⚠️ Payment still pending ({paid_parts}/{total_parts})",
            "payment_status": payment_status,
            "drone_order_id": drone_order_id,
            "payment_type": payment_type,
            "total_amount": str(total_amount),
            "paid_amount": str(total_paid),
            "remaining_amount": str(remaining_amount),
            "days_left": days_left,
            "total_invoices": total_invoices,
            "total_invoice_amount": str(total_invoice_amount),
            # "total_invoice_status":1
            "total_invoice_status": total_invoice_status,

        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@customer_login_required
@csrf_exempt
def create_drone_installment_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = request.session.get('customer_id')

        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

        customer = CustomerRegister.objects.filter(id=customer_id, status=1).first()
        if not customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        email = data.get('email')
        quantity = int(data.get('quantity') or 1)
        amount = Decimal(data.get('amount') or 0)  # installment_amount
        total_amount = Decimal(data.get('total_amount') or 0)

        if not all([email, quantity, amount, total_amount]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        if quantity > 10:
            return JsonResponse({'error': 'You can purchase a maximum of 10 drones.'}, status=400)
        unit_price = 1200000
        total_required = unit_price * quantity
        order_amount = total_required
                
        admin = Admin.objects.filter(id=1).first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)
        existing_order = None
        orders = PaymentDetails.objects.filter(
            customer=customer,
            payment_type='installment'
        ).order_by('-created_at').values_list('drone_order_id', flat=True).distinct()

        for order_id in orders:
            total_paid = PaymentDetails.objects.filter(
                customer=customer,
                drone_order_id=order_id,
                payment_type='installment',
                drone_payment_status='captured'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
            order_amount = PaymentDetails.objects.filter(
                customer=customer,
                drone_order_id=order_id,
                payment_type='installment'
            ).first().total_amount
            if total_paid < order_amount:
                existing_order = order_id
                break

        if existing_order:
            drone_order_id = existing_order
            previous_payments = PaymentDetails.objects.filter(
                customer=customer,
                drone_order_id=drone_order_id,
                payment_type='installment'
            )
            order_amount = previous_payments.first().total_amount
           
        else:
            drone_order_id = f"OD{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
            previous_payments = PaymentDetails.objects.none()
            order_amount = total_required
     
        if previous_payments.exists():
            order_amount = previous_payments.first().total_amount
        else:
            order_amount = total_amount
        total_paid_installments = previous_payments.filter(
            drone_payment_status='captured'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

    
        remaining_amount = max(Decimal('0.0'), order_amount - total_paid_installments)

        if total_paid_installments >= order_amount:
            return JsonResponse({'error': 'You have already paid the full amount for this order. No further payments are accepted.'}, status=400)
        if amount > remaining_amount:
            return JsonResponse({
                'error': f'Installment exceeds remaining payable amount. You have already paid ₹{total_paid_installments:.2f}, remaining: ₹{remaining_amount:.2f}'
            }, status=400)
        unpaid_payment = previous_payments.filter(
            drone_payment_status__in=['created', 'failed', 'pending','cancelled']
        ).order_by('-part_number').first()

        if unpaid_payment:
            installment_number = unpaid_payment.part_number
        else:
            installment_number = (previous_payments.aggregate(max_part=Max('part_number'))['max_part'] or 0) + 1

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order = client.order.create({
            'amount': int(amount * 100),
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'customer_id': str(customer_id),
                'email': email,
                'drone_order_id': drone_order_id,
                'part': str(installment_number),
                'quantity': str(quantity)
            }
        })
        payment = PaymentDetails.objects.create(
            customer=customer,
            razorpay_order_id=order['id'],
            total_amount=order_amount,
            amount=amount,
            part_number=installment_number,
            drone_payment_status='created',
            quantity=quantity,
            drone_order_id=drone_order_id,
            payment_type='installment',
            admin=admin
        )
        first_payment = previous_payments.order_by('created_at').first()
        start_date = first_payment.created_at.date() if first_payment else timezone.now().date()
        today = timezone.now().date()
        days_left = max(0, 2 - (today - start_date).days)

        return JsonResponse({
            'message': 'Installment order created.',
            'drone_order_id': drone_order_id,
            'installment_number': installment_number,
            'days_left': days_left,
            'total_amount': order_amount,
            'total_paid_amount': total_paid_installments,
            'remaining_amount': remaining_amount,
            'order': {
                'razorpay_order_id': order['id'],
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'amount': amount,
                'currency': 'INR',
                'email': email,
                'quantity': quantity
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
from django.db import transaction

@csrf_exempt
def razorpay_callback(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        payload = request.body
        received_signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE")
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

        # Verify Signature
        generated_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_signature, generated_signature):
            return HttpResponseBadRequest("Invalid signature")

        data = json.loads(payload)
        payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})

        razorpay_order_id = payment_entity.get("order_id")
        razorpay_payment_id = payment_entity.get("id")
        status = payment_entity.get("status")       # created | authorized | captured | failed
        method = payment_entity.get("method")
        amount = int(payment_entity.get("amount", 0))   # in paise

        if not razorpay_order_id:
            return JsonResponse({"error": "Invalid payload"}, status=400)

        payment = PaymentDetails.objects.filter(razorpay_order_id=razorpay_order_id).first()
        if not payment:
            return JsonResponse({"error": "Payment record not found"}, status=404)

        # Handle Payment Status
        with transaction.atomic():
            if status == "authorized":
                # ✅ Capture immediately in production
                try:
                    capture_res = client.payment.capture(razorpay_payment_id, amount)
                    status = capture_res.get("status", "failed")
                    print(f"Payment Authorized & Captured: {razorpay_payment_id}")
                except Exception as e:
                    print(f"Capture failed: {str(e)}")
                    # If already captured, treat as success
                    if "already been captured" in str(e).lower():
                        status = "captured"
                    else:
                        status = "authorized"
            # Always update DB with the latest Razorpay status
            payment.razorpay_payment_id = razorpay_payment_id
            payment.drone_payment_status = status   # captured | failed | authorized | refunded
            payment.payment_mode = method
            payment.save()

            # Run business logic only when captured
            if status == "captured":
                if payment.payment_type == "installment":
                    kyc = KYCDetails.objects.filter(customer=payment.customer).first()

                    context = {
                        "payment_type": payment.payment_type,
                        "part_number": payment.part_number,
                        "full_name": kyc.pan_name if kyc else "Customer",
                        "payment_mode": payment.payment_mode,
                        "amount": payment.amount,
                    }
                    pdf_file = generate_receipt_pdf(context, "receipt_pdf.html")
                    send_receipt_email(payment.customer, payment, kyc, pdf_file)

                    # check all installments
                    all_parts = PaymentDetails.objects.filter(
                        customer=payment.customer,
                        drone_order_id=payment.drone_order_id,
                        payment_type="installment"
                    )

                    total_paid = all_parts.filter(
                        drone_payment_status="captured"
                    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.0")

                    expected_total = all_parts.first().total_amount if all_parts.exists() else Decimal("0.0")

                    if total_paid >= expected_total:
                        all_parts.update(payment_status=1)
                        print(f"✅ Installment fully paid. Order complete: {payment.drone_order_id}")

                elif payment.payment_type == "fullpayment":
                    payment.payment_status = 1
                    payment.save()
                    print(f"✅ Full payment completed for Order: {payment.drone_order_id}")

        return JsonResponse({"status": "Webhook handled successfully"}, status=200)

    except Exception as e:
        print(f"Webhook Error: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


# @customer_login_required
# @csrf_exempt
# def create_drone_installment_order(request):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Only POST allowed'}, status=405)

#     try:
#         data = json.loads(request.body)
#         customer_id = request.session.get('customer_id')

#         if not customer_id:
#             return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)

#         customer = CustomerRegister.objects.filter(id=customer_id, status=1).first()
#         if not customer:
#             return JsonResponse({'error': 'Customer not found'}, status=404)

#         email = data.get('email')
#         quantity = int(data.get('quantity') or 1)
#         amount = Decimal(data.get('amount') or 0) #installment_amount
#         total_amount = Decimal(data.get('total_amount') or 0)

#         if not all([email, quantity, amount, total_amount]):
#             return JsonResponse({'error': 'Missing required fields'}, status=400)

#         if quantity > 10:
#             return JsonResponse({'error': 'You can purchase a maximum of 10 drones.'}, status=400)

#         admin = Admin.objects.filter(id=1).first()
#         if not admin:
#             return JsonResponse({'error': 'Admin not found'}, status=500)
#         # Clean up unpaid previous orders
#         latest_order = PaymentDetails.objects.filter(customer=customer, status=1).order_by('-created_at').first()
#         if latest_order:
#             latest_order_id = latest_order.drone_order_id
#             latest_order_status = PaymentDetails.objects.filter(
#                 customer=customer,
#                 drone_order_id=latest_order_id
#             ).values_list('payment_status', flat=True).first()

#             # SAFE: Deletes only unpaid "created" installment or full order if nothing paid
#             if latest_order_status != 1 and latest_order.drone_payment_status == 'created':
#                 if not PaymentDetails.objects.filter(
#                     customer=customer,
#                     drone_order_id=latest_order_id,
#                     drone_payment_status='paid'
#                 ).exists():
#                     # If no part is paid, it's safe to delete whole order
#                     PaymentDetails.objects.filter(
#                         customer=customer,
#                         drone_order_id=latest_order_id
#                     ).delete()
#                 else:
#                     # Just delete the latest created installment only
#                     latest_order.delete()


#         # Step: Check if there's any previous unpaid installment by this customer
#         # Step 1: Check if there is any unpaid order (reuse it)
#         existing_unpaid = PaymentDetails.objects.filter(
#             customer=customer,
#             payment_type='installment',
#             drone_payment_status__in=['created', 'failed']
#         ).order_by('-created_at').first()

#         if existing_unpaid:
#             # Reuse existing unpaid drone_order_id
#             drone_order_id = existing_unpaid.drone_order_id
#             order_amount = existing_unpaid.amount
#             previous_payments = PaymentDetails.objects.filter(
#                 customer=customer,
#                 drone_order_id=drone_order_id,
#                 payment_type='installment'
#             )
#         else:
#             # Step 2: Check latest completed or in-progress order
#             latest_order = PaymentDetails.objects.filter(
#                 customer=customer,
#                 payment_type='installment'
#             ).order_by('-created_at').first()

#             if latest_order:
#                 drone_order_id = latest_order.drone_order_id
#                 order_amount = latest_order.total_amount
#                 previous_payments = PaymentDetails.objects.filter(
#                     customer=customer,
#                     drone_order_id=drone_order_id,
#                     payment_type='installment'
#                 )
#                 total_paid = previous_payments.filter(
#                     drone_payment_status='paid'
#                 ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

#                 if total_paid >= order_amount:
#                     # Full paid, start fresh order
#                     drone_order_id = f"OD{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
#                     order_amount = total_amount
#                     previous_payments = PaymentDetails.objects.none()
#             else:
#                 # First order ever
#                 drone_order_id = f"OD{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
#                 order_amount = total_amount
#                 previous_payments = PaymentDetails.objects.none() 

#         total_paid_installments = previous_payments.filter(
#             drone_payment_status='paid'
#         ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

#         order_amount = previous_payments.first().total_amount if previous_payments.exists() else total_amount

#         remaining_amount = max(Decimal('0.0'), order_amount - total_paid_installments)

#         if remaining_amount <= 0:
#             return JsonResponse({'error': 'You have already paid the full amount.'}, status=400)

#         if total_paid_installments + amount > order_amount:
#             return JsonResponse({
#                 'error': f'Installment exceeds remaining payable amount. You have already paid ₹{total_paid_installments:.2f}, remaining: ₹{remaining_amount:.2f}'
#             }, status=400)

#         installment_number = (previous_payments.aggregate(max_part=Max('part_number'))['max_part'] or 0) + 1

#         # Create Razorpay order
#         client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
#         order = client.order.create({
#             'amount': int(amount * 100),
#             'currency': 'INR',
#             'payment_capture': 1,
#             'notes': {
#                 'customer_id': str(customer_id),
#                 'email': email,
#                 'drone_order_id': drone_order_id,
#                 'part': str(installment_number),
#                 'quantity': str(quantity)
#             }
#         })

#         # Save to DB
#         payment = PaymentDetails.objects.create(
#             customer=customer,
#             razorpay_order_id=order['id'],
#             total_amount=order_amount,
#             amount=amount,
#             part_number=installment_number,
#             drone_payment_status='created',
#             quantity=quantity,
#             drone_order_id=drone_order_id,
#             payment_type='installment',
#             admin=admin
#         )

#         # Calculate days left from first payment date
#         first_payment = previous_payments.order_by('created_at').first()
#         start_date = first_payment.created_at.date() if first_payment else timezone.now().date()
#         today = timezone.now().date()
#         days_left = max(0, 2 - (today - start_date).days)

#         return JsonResponse({
#             'message': 'Installment order created.',
#             'drone_order_id': drone_order_id,
#             'installment_number': installment_number,
#             'days_left': days_left,
#             'total_amount': order_amount,
#             'total_paid_amount': total_paid_installments,
#             'remaining_amount': remaining_amount,
#             'order': {
#                 'razorepay_order_id': order['id'],
#                 'razorpay_key': settings.RAZORPAY_KEY_ID,
#                 'amount': amount,
#                 'currency': 'INR',
#                 'email': email,
#                 'quantity': quantity
#             }
#         }, status=200)

#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)
# #combile call back
# @csrf_exempt
# def razorpay_callback(request):
#     try:
#         payload = request.body
#         signature = request.headers.get('X-Razorpay-Signature')

#         # Verify Razorpay signature
#         expected_signature = hmac.new(
#             settings.RAZORPAY_WEBHOOK_SECRET.encode(),
#             msg=payload,
#             digestmod=hashlib.sha256
#         ).hexdigest()

#         if signature != expected_signature:
#             return JsonResponse({'error': 'Invalid signature'}, status=400)

#         data = json.loads(payload)
#         event = data.get('event')

#         if event == 'payment.captured':
#             payment_entity = data['payload']['payment']['entity']
#             razorpay_order_id = payment_entity['order_id']
#             payment_id = payment_entity['id']

#             payment = PaymentDetails.objects.filter(razorpay_order_id=razorpay_order_id).first()

#             if payment and payment.drone_payment_status != 'paid':
#                 payment.drone_payment_status = 'paid'
#                 payment.razorpay_payment_id = payment_id
#                 payment.payment_mode = payment_entity.get('method')
#                 payment.save()

#                 print(f"✅ Payment Captured - Razorpay Order ID: {razorpay_order_id}, Payment ID: {payment_id}")
#                 print(f"🧾 Type: {payment.payment_type} | Part: {payment.part_number} | Drone Order: {payment.drone_order_id}")

#                 if payment.payment_type == 'installment':
#                     kyc = KYCDetails.objects.filter(customer=payment.customer).first()

#                     context = {
#                         "payment_type": payment.payment_type,
#                         "part_number": payment.part_number,
#                         "full_name": kyc.pan_name if kyc else "Customer",
#                         "payment_mode": payment.payment_mode,
#                         "amount": payment.amount,
#                     }
#                     pdf_file = generate_receipt_pdf(context,"receipt_pdf.html")
#                     send_receipt_email(payment.customer, payment,kyc, pdf_file)
                    
#                     all_parts = PaymentDetails.objects.filter(
#                         customer=payment.customer,
#                         drone_order_id=payment.drone_order_id,
#                         payment_type='installment'
#                     )

#                     total_paid = all_parts.filter(
#                         drone_payment_status='paid'
#                     ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

#                     expected_total = all_parts.first().total_amount if all_parts.exists() else Decimal('0.0')

#                     if total_paid >= expected_total:
#                         all_parts.update(payment_status=1)
#                         print(f"✅ Installment fully paid. All parts marked as complete for Order: {payment.drone_order_id}")

#                 elif payment.payment_type == 'fullpayment':
#                     # For full payment, just mark status
#                     payment.payment_status = 1
#                     payment.save()
#                     print(f"✅ Full payment completed for Order: {payment.drone_order_id}")

#         elif event == 'payment.failed':
#             payment_entity = data['payload']['payment']['entity']
#             razorpay_order_id = payment_entity['order_id']
#             payment_id = payment_entity['id']

#             payment = PaymentDetails.objects.filter(razorpay_order_id=razorpay_order_id).first()
#             if payment and payment.drone_payment_status != 'failed':
#                 payment.drone_payment_status = 'failed'
#                 payment.razorpay_payment_id = payment_id
#                 payment.payment_mode = payment_entity.get('method')
#                 payment.save()

#                 print(f"❌ Payment Failed - Order ID: {payment.drone_order_id}, Part: {payment.part_number}")

#         return HttpResponse(status=200)

#     except Exception as e:
#         print("Webhook Error:", str(e))
#         return JsonResponse({'error': str(e)}, status=500)

def generate_receipt_pdf(context, template_name):
    html_string = render_to_string(template_name, context)
    pdf_file = BytesIO()
    HTML(string=html_string).write_pdf(target=pdf_file)
    pdf_file.seek(0)
    return pdf_file

def send_receipt_email(customer, payment,kyc, pdf_file):
    subject = "Installment Receipt from Pavaman Aviation"
    logo_url = f"{settings.AWS_S3_BUCKET_URL}/aviation-logo.png"

    text_content = f"""
    Dear {kyc.pan_name},

    Thank you for your installment payment (Part {payment.part_number}).

    Amount Paid: ₹{payment.amount}
    Paid On: {payment.created_at.strftime('%d %b %Y, %I:%M %p')}

    Your receipt is attached with this email.
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
                <h2 style="margin-top: 0; color: #222;">Installment Receipt</h2>
            </div>

            <p style="margin: 0 0 10px; color: #555; font-size: 15px;">
                Dear {kyc.pan_name},
            </p>

            <p style="color: #555; font-size: 15px; line-height: 1.6;">
                Thank you for your installment payment. Your receipt is attached below.
            </p>

            <table style="width: 100%; margin-top: 20px; border-collapse: collapse;">
               
                <tr>
                    <td style="font-weight: bold; padding: 8px 0;">Installment No:</td>
                    <td>{payment.part_number}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; padding: 8px 0;">Amount Paid:</td>
                    <td>₹{payment.amount}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; padding: 8px 0;">Paid On:</td>
                    <td>{payment.created_at.strftime('%d %b %Y, %I:%M %p')}</td>
                </tr>
            </table>

            <p style="color: #888; font-size: 13px; margin-top: 30px;">
                If you have any questions, please reach out to us at support@pavaman.com.
            </p>

            <p style="margin-top: 20px; font-size: 13px; color: #888;">
                Disclaimer: This is an automated email. Please do not reply.
            </p>
        </div>
    </body>
    </html>
    """

    email_message = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [customer.email]
    )
    email_message.attach_alternative(html_content, "text/html")
    email_message.attach(
        f"Receipt_{payment.drone_order_id}_Part{payment.part_number}.pdf",
        pdf_file.read(),
        'application/pdf'
    )
    email_message.send()
def upload_file_to_s3(file_obj, file_key):
    s3 = boto3.client('s3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )

    mime_type, _ = mimetypes.guess_type(file_key)
    extra_args = {'ContentType': mime_type} if mime_type else {}

    s3.upload_fileobj(file_obj, settings.AWS_STORAGE_BUCKET_NAME, file_key, ExtraArgs=extra_args)
    # return file_key
    return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{file_key}"

@customer_login_required
@csrf_exempt
def stage_nominees(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        customer_id = request.session.get("customer_id")
        customer = CustomerRegister.objects.only("id", "mobile_no").get(id=customer_id)

        nominee_list = json.loads(request.POST.get('nominees', '[]'))
        files = request.FILES

        if not nominee_list:
            return JsonResponse({"error": "No nominees provided."}, status=400)

        # Get already saved nominees and sum their shares
        existing_nominees = NomineeDetails.objects.filter(customer=customer)
        existing_share_total = sum(float(n.share or 0) for n in existing_nominees)

        # Get staged nominees from cache if any
        staged_nominees_cache = cache.get(f"cached_nominees_{customer_id}") or []
        staged_share_total = sum(float(n["data"]["share"]) for n in staged_nominees_cache)

        # Sum all existing + staged + new
        new_nominee_share_total = existing_share_total + staged_share_total

        for nominee in nominee_list:
            new_nominee_share_total += float(nominee.get("share", 0))

        if new_nominee_share_total > 100:
            return JsonResponse({
                "error": f"Total nominee share cannot exceed 100%. Current total: {existing_share_total + staged_share_total}%"
            }, status=400)

        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.svg']
        staged_nominees = []

        for index, nominee in enumerate(nominee_list):
            required_fields = [
                "first_name", "last_name", "dob", "relation", "share",
                "address",  # New field for address
                "address_proof", "address_proof_file",
                "id_proof_file"
            ]
            if not all(nominee.get(f) for f in required_fields):
                return JsonResponse({"error": f"Missing fields in nominee {index + 1}."}, status=400)

            addr_file_key = nominee["address_proof_file"]
            id_file_key = nominee["id_proof_file"]

            address_file = files.get(addr_file_key)
            id_file = files.get(id_file_key)

            if not address_file or not id_file:
                return JsonResponse({"error": f"Missing files for nominee {index + 1}."}, status=400)

            if os.path.splitext(address_file.name)[1].lower() not in allowed_extensions or \
               os.path.splitext(id_file.name)[1].lower() not in allowed_extensions:
                return JsonResponse({"error": f"Invalid file extension in nominee {index + 1}."}, status=400)

            staged_nominees.append({
                "data": nominee,
                "address_proof_file": address_file.read().decode("latin1"),
                "id_proof_file": id_file.read().decode("latin1"),
                "address_name": address_file.name,
                "id_name": id_file.name
            })

        cache.set(f"cached_nominees_{customer_id}", staged_nominees, timeout=900)

        otp = generate_otp()
        customer.otp = otp
        customer.changed_on = timezone_now()
        customer.save(update_fields=["otp", "changed_on"])

        send_bulk_sms([str(customer.mobile_no)], otp)
        cache.set(f"otp_verified_{customer_id}", False, timeout=900)

        return JsonResponse({"message": "OTP sent for Nominee verification.","otp":otp})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@customer_login_required
@csrf_exempt
def verify_nominee(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        customer_id = request.session.get("customer_id")

        if request.content_type == 'application/json':
            data = json.loads(request.body)
            otp = data.get("otp")
        else:
            otp = request.POST.get("otp")

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        if str(customer.otp) != otp or not customer.is_otp_valid():
            return JsonResponse({"error": "Invalid or expired OTP."}, status=400)

        customer.otp = None
        customer.changed_on = None
        customer.save(update_fields=["otp", "changed_on"])

        cache.set(f"otp_verified_{customer_id}", True, timeout=900)

        return JsonResponse({"message": "OTP verified. You can now save nominees."})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@customer_login_required
@csrf_exempt
def save_staged_nominees(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        customer_id = request.session.get("customer_id")
        customer = CustomerRegister.objects.get(id=customer_id)

        if not cache.get(f"otp_verified_{customer_id}", False):
            return JsonResponse({"error": "OTP verification required."}, status=403)

        nominees = cache.get(f"cached_nominees_{customer_id}")
        if not nominees:
            return JsonResponse({"error": "No nominees staged or session expired."}, status=400)

        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found."}, status=500)

        created_ids = []

        for nominee in nominees:
            nominee_data = nominee["data"]

            # Convert files from cached latin1
            addr_file = BytesIO(nominee["address_proof_file"].encode("latin1"))
            addr_file.name = nominee["address_name"]
            id_file = BytesIO(nominee["id_proof_file"].encode("latin1"))
            id_file.name = nominee["id_name"]

            dob = datetime.strptime(nominee_data["dob"], "%Y-%m-%d").date()

            nominee_obj = NomineeDetails.objects.create(
                    customer=customer,
                    first_name=nominee_data["first_name"],
                    last_name=nominee_data["last_name"],
                    relation=nominee_data["relation"],
                    dob=dob,
                    share=nominee_data["share"],
                    address_proof=nominee_data.get("address_proof", "Aadhar"),  # or set default
                    admin=admin,
                    address=nominee_data["address"],
            )
 
            nominee_id = nominee_obj.id
            nominee_name = f"{nominee_data['first_name']}{nominee_data['last_name']}".replace(" ", "").lower()
            customer_name = f"{customer.first_name}{customer.last_name}".replace(" ", "").lower()
            folder_path = f"customerdoc/{customer.id}_{customer_name}"
            suffix = uuid.uuid4().hex[-6:]

            addr_ext = os.path.splitext(addr_file.name)[1].lower()
            id_ext = os.path.splitext(id_file.name)[1].lower()

            addr_key = f"{folder_path}/nominee_address_proof_{nominee_id}_{nominee_name}_{suffix}{addr_ext}"
            id_key = f"{folder_path}/nominee_id_proof_{nominee_id}_{nominee_name}_{suffix}{id_ext}"

            # Upload to S3
            upload_file_to_s3(addr_file, addr_key)
            upload_file_to_s3(id_file, id_key)

            # Update nominee record with paths
            nominee_obj.address_proof_path = addr_key
            nominee_obj.id_proof_path = id_key
            nominee_obj.save()

            created_ids.append(nominee_id)

        cache.delete(f"cached_nominees_{customer_id}")
        cache.delete(f"otp_verified_{customer_id}")

        return JsonResponse({"message": "All nominees saved successfully.", "nominee_ids": created_ids})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

from datetime import date

def generate_invoice_number(created_at):
    invoice_date = timezone.localtime(created_at).date()
    year = invoice_date.year
    month = invoice_date.month

    # Determine financial year
    if month < 4:
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1

    fy_start = str(start_year)[-2:]
    fy_end = str(end_year)[-2:]
    month_str = f"{month:02d}"
    financial_year = f"{fy_start}-{fy_end}"

    start_date = date(start_year, 4, 1)
    end_date = date(end_year, 3, 31)

    # GLOBAL SERIAL NUMBER — across all invoice types
    latest_invoice = InvoiceDetails.objects.filter(
        created_at__range=(start_date, end_date)
    ).order_by('-created_at').first()

    if latest_invoice:
        try:
            last_serial = int(latest_invoice.invoice_number.split("/")[-1])
        except:
            last_serial = 0
    else:
        last_serial = 0

    next_serial = last_serial + 1
    serial_str = f"{next_serial:04d}"

    return f"PAV-INV-{financial_year}/{month_str}/{serial_str}"
@csrf_exempt
def create_invoice(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        drone_order_id = data.get('drone_order_id')
        address_type = data.get('address_type', 'permanent')

        if not customer_id or not drone_order_id:
            return JsonResponse({'error': 'Customer ID and drone order ID are required'}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        customer_more = CustomerMoreDetails.objects.filter(customer_id=customer_id).first()
        admin = Admin.objects.first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)

        # Check for existing invoice
        existing_invoice = InvoiceDetails.objects.filter(
            customer=customer,
            invoice_status=1,
            invoice_type="Drone",
            payment__drone_order_id=drone_order_id
        ).first()
        if existing_invoice:
            return JsonResponse({
                "message": "Invoice already exists for this customer.",
                "invoice_id": existing_invoice.id,
                "invoice_number": existing_invoice.invoice_number,
                "invoice_date": existing_invoice.created_at.strftime("%Y-%m-%d"),
            }, status=200)

        payment = PaymentDetails.objects.filter(
            customer=customer,
            drone_order_id=drone_order_id,
            drone_payment_status__in=['captured', 'paid'],
            # drone_payment_status='captured',
            status=1
        ).first()
        if not payment:
            return JsonResponse({'error': 'No paid payment found for this customer'}, status=404)

        # Address logic
        if customer_more.same_address:
            state = customer_more.state or ""
        elif address_type == 'present':
            state = customer_more.present_state or ""
        else:
            state = customer_more.state or ""

        company_state = "Telangana"
        is_intrastate = state.strip().lower() == company_state.lower()

        required_quantity = payment.quantity
        available_drones = CompanyDroneModelInfo.objects.filter(assign_status=0)[:required_quantity]

        if len(available_drones) < required_quantity:
            return JsonResponse({'error': f'Only {len(available_drones)} drones available, but {required_quantity} required.'}, status=400)

        # === GST Calculations ===
        rate_per_unit = Decimal('310000')
        base_amount = rate_per_unit * required_quantity
        GST_PERCENTAGE = Decimal('5.0')
        gst_amount = base_amount * (GST_PERCENTAGE / 100)

        if is_intrastate:
            cgst = sgst = gst_amount / 2
            igst = Decimal('0.00')
        else:
            cgst = sgst = Decimal('0.00')
            igst = gst_amount

        total_invoice_amount = base_amount + cgst + sgst + igst
        rounded_amount = int(round(total_invoice_amount))
        try:
            total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"
        except:
            total_in_words = ""

        # Generate invoice number
        invoice_number = generate_invoice_number(timezone.now())

        # Assign drones and get UINs
        uin_list = []
        drone_model_ids = [drone.id for drone in available_drones]
        uin_list = [drone.uin_number for drone in available_drones]
        for drone in available_drones:
            drone.assign_status = 1
            drone.save()
        # Create single invoice row
        invoice = InvoiceDetails.objects.create(
            customer=customer,
            customer_more=customer_more,
            admin=admin,
            payment=payment,
            drone_model_ids=drone_model_ids,
            invoice_number=invoice_number,
            serial_no=1,
            parts_quantity=required_quantity,
            hsn_sac_code="88062300",
            uom="No",
            rate_per_unit=rate_per_unit,
            total_amount=base_amount,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            total_taxable_amount=base_amount,
            total_invoice_amount=total_invoice_amount,
            total_invoice_amount_words=total_in_words,
            address_type=address_type,
            description="TEJA-S (UIN Drone)",
            uin_no=", ".join([d.uin_number for d in available_drones]),
            invoice_type="Drone",
            invoice_status=1
        )

        return JsonResponse({
            "message": "Drone invoice created successfully",
            "invoice_number": invoice_number,
            "total_invoice_amount": float(total_invoice_amount),
            "total_invoice_amount_words": total_in_words,
            "rows": [
                {
                    "serial_no": 1,
                    "uin_no": ", ".join(uin_list),
                    "quantity": required_quantity,
                    "rate": float(rate_per_unit),
                    "total": float(base_amount),
                    "cgst": float(cgst),
                    "sgst": float(sgst),
                    "igst": float(igst),
                    "invoice_id": invoice.id,
                    "invoice_status": invoice.invoice_status
                }
            ]
        }, status=201)

    except CustomerRegister.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def create_accessory_invoice(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        drone_order_id = data.get('drone_order_id')
        uin_list = data.get('uin_list', [])
        address_type = data.get('address_type', 'permanent')

        if not customer_id or not drone_order_id or not uin_list:
            return JsonResponse({'error': 'Customer ID, Drone Order ID, and UIN list are required'}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        customer_more = CustomerMoreDetails.objects.filter(customer_id=customer_id).first()
        admin = Admin.objects.first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)

        payment = PaymentDetails.objects.filter(
            customer_id=customer_id,
            drone_order_id=drone_order_id,
            drone_payment_status='paid',
            status=1
        ).first()
       
        if not payment:
            return JsonResponse({'error': 'No paid payment found for this customer and drone order.'}, status=404)
        # Check for existing accessory invoice
        existing_invoice = InvoiceDetails.objects.filter(
            customer=customer,
            invoice_status=1,
            invoice_type="accessory",
            payment__drone_order_id=drone_order_id
        ).first()

        if existing_invoice:
            return JsonResponse({
                "message": "Accessory invoice already exists for this customer.",
                "invoice_id": existing_invoice.id,
                "invoice_number": existing_invoice.invoice_number,
                "invoice_date": existing_invoice.created_at.strftime("%Y-%m-%d"),
            }, status=200)

        if customer_more.same_address:
            state = customer_more.state or ""
        elif address_type == 'present':
            state = customer_more.present_state or ""
        else:
            state = customer_more.state or ""

        company_state = "Telangana"
        is_intrastate = state.strip().lower() == company_state.lower()
        drone_count = len(uin_list)

        # Accessory items per total drone count
        accessory_items = [
            {"description": "Batteries (8 Nos) - 1 Set = 2 Batteries", "qty": 4 * drone_count, "rate": Decimal('29000'), "hsn": "8806", "uom": "Set"},
            {"description": "DG Set", "qty": 1 * drone_count, "rate": Decimal('110000'), "hsn": "8502", "uom": "No"},
            {"description": "Water Tank", "qty": 1 * drone_count, "rate": Decimal('6627'), "hsn": "3925", "uom": "No"}
        ]

        total_taxable_amount = sum(item['qty'] * item['rate'] for item in accessory_items)
        GST_PERCENTAGE = Decimal('18.0')
        gst_amount = total_taxable_amount * (GST_PERCENTAGE / 100)

        if is_intrastate:
            cgst = sgst = gst_amount / 2
            igst = Decimal('0.00')
        else:
            cgst = sgst = Decimal('0.00')
            igst = gst_amount

        total_invoice_amount = total_taxable_amount + cgst + sgst + igst
        rounded_amount = int(round(total_invoice_amount))

        try:
            total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"
        except Exception as e:
            print("Num2words Error:", e)
            total_in_words = ""

        #Generate invoice number once
        invoice_number = generate_invoice_number(timezone.now())
        drones = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_list)
        drone_model_ids = [d.id for d in drones]

        serial_no = 1
        created_rows = []

        for item in accessory_items:
            line_total = item['qty'] * item['rate']
            invoice_status = 1 if serial_no == 1 else 0

            invoice = InvoiceDetails.objects.create(
                customer=customer,
                customer_more=customer_more,
                admin=admin,
                payment=payment,
                drone_model_ids=drone_model_ids,
                invoice_number=invoice_number,
                serial_no=serial_no,
                uin_no=", ".join(uin_list),  # Optional: or uin_list[0], or leave blank
                invoice_type="accessory",
                invoice_status=invoice_status,
                parts_quantity=item['qty'],
                hsn_sac_code=item['hsn'],
                uom=item['uom'],
                rate_per_unit=item['rate'],
                total_amount=line_total,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_taxable_amount=total_taxable_amount,
                total_invoice_amount=total_invoice_amount,
                total_invoice_amount_words=total_in_words,
                address_type=address_type,
                description=item['description'],
                status=1
            )

            created_rows.append({
                "serial_no": serial_no,
                "description": item['description'],
                "quantity": item['qty'],
                "rate": float(item['rate']),
                "total": float(line_total),
                "cgst": float(cgst),
                "sgst": float(sgst),
                "igst": float(igst),
                "invoice_status": invoice.invoice_status
            })

            serial_no += 1
        return JsonResponse({
            "message": "Accessory invoice created successfully",
            "invoice_number": invoice_number,
            "total_invoice_amount": float(total_invoice_amount),
            "total_invoice_amount_words": total_in_words,
            "rows": created_rows
        }, status=201)

    except CustomerRegister.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def create_amc_invoice(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        drone_order_id = data.get('drone_order_id')
        address_type = data.get('address_type', 'permanent')
        uin_list = data.get('uin_list', [])

        if not customer_id or not drone_order_id or not uin_list:
            return JsonResponse({'error': 'Customer ID, Drone Order ID, and UIN list are required'}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        customer_more = CustomerMoreDetails.objects.filter(customer_id=customer_id).first()
        admin = Admin.objects.first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)

        payment = PaymentDetails.objects.filter(
            customer=customer,
            drone_order_id=drone_order_id,
            drone_payment_status='paid',
            status=1
        ).first()
        if not payment:
            return JsonResponse({'error': 'No paid payment found for this customer'}, status=404)

        # Determine state
        if customer_more.same_address:
            state = customer_more.state or ""
        elif address_type == 'present':
            state = customer_more.present_state or ""
        else:
            state = customer_more.state or ""

        company_state = "Telangana"
        is_intrastate = state.strip().lower() == company_state.lower()

        # Drone details
        drones = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_list)
        drone_model_ids = [d.id for d in drones]

        if len(drones) != len(uin_list):
            return JsonResponse({'error': 'Some UINs not found in system'}, status=400)

        quantity = len(drones)
        rate_per_unit = Decimal('508475')
        base_amount = rate_per_unit * quantity
        GST_PERCENTAGE = Decimal('18.0')
        gst_amount = base_amount * (GST_PERCENTAGE / 100)

        if is_intrastate:
            cgst = sgst = gst_amount / 2
            igst = Decimal('0.00')
        else:
            cgst = sgst = Decimal('0.00')
            igst = gst_amount

        total_invoice_amount = base_amount + cgst + sgst + igst
        rounded_amount = int(round(total_invoice_amount))
        try:
            total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"
        except:
            total_in_words = ""

        invoice_number = generate_invoice_number(timezone.now())
        
        invoice = InvoiceDetails.objects.create(
            customer=customer,
            customer_more=customer_more,
            admin=admin,
            payment=payment,
            drone_model_ids=drone_model_ids,
            invoice_number=invoice_number,
            serial_no=1,
            parts_quantity=quantity,
            hsn_sac_code="9987",
            uom="No",
            rate_per_unit=rate_per_unit,
            total_amount=base_amount,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            total_taxable_amount=base_amount,
            total_invoice_amount=total_invoice_amount,
            total_invoice_amount_words=total_in_words,
            address_type=address_type,
            description="AMC for 5.5 Years",
            uin_no=", ".join(uin_list),
            invoice_type="amc",
            invoice_status=1
        )

        return JsonResponse({
            "message": "AMC invoice created successfully",
            "invoice_number": invoice_number,
            "total_invoice_amount": float(total_invoice_amount),
            "total_invoice_amount_words": total_in_words,
            "rows": [
                {
                    "serial_no": 1,
                    "uin_no": ", ".join(uin_list),
                    "quantity": quantity,
                    "rate": float(rate_per_unit),
                    "total": float(base_amount),
                    "cgst": float(cgst),
                    "sgst": float(sgst),
                    "igst": float(igst),
                    "invoice_id": invoice.id,
                    "invoice_status": invoice.invoice_status
                }
            ]
        }, status=201)

    except CustomerRegister.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
# @customer_login_required
@csrf_exempt
def create_invoice_combined(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id=data.get('customer_id')
        # customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({'error': 'Unauthorized: Login required'}, status=403)


        drone_order_id = data.get('drone_order_id')
        address_type = data.get('address_type', 'permanent')
        uin_list = data.get('uin_list', [])
        invoice_for = data.get('invoice_for', 'drone').lower()

        if not customer_id or not drone_order_id or (invoice_for != 'drone' and not uin_list):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        customer_more = CustomerMoreDetails.objects.filter(customer_id=customer_id).first()
        admin = Admin.objects.first()
        if not admin:
            return JsonResponse({'error': 'Admin not found'}, status=500)

        payment = PaymentDetails.objects.filter(
            customer_id=customer_id,
            drone_order_id=drone_order_id,
            drone_payment_status='captured',
            status=1
        ).first()
        if not payment:
            return JsonResponse({'error': 'No paid payment found for this customer and drone order.'}, status=404)

        if customer_more.same_address:
            state = customer_more.state or ""
        elif address_type == 'present':
            state = customer_more.present_state or ""
        else:
            state = customer_more.state or ""

        is_intrastate = state.strip().lower() == "telangana"
        invoice_number = generate_invoice_number(timezone.now())
        created_rows = []
        serial_no = 1
 
        # ---------------- DRONE INVOICE ----------------
        if invoice_for == 'drone':
            existing = InvoiceDetails.objects.filter(
                customer=customer,
                invoice_type="drone",
                invoice_status=1,
                payment__drone_order_id=drone_order_id
            ).first()
            if existing:
                return JsonResponse({
                    "message": "Drone invoice already exists.",
                    "invoice_number": existing.invoice_number,
                    "invoice_status":existing.invoice_status,
                    "invoice_id":existing.id,
                    "uni_no":existing.uin_no,
                    "total_invoice_status":existing.total_invoice_status,
                }, status=200)

            required_quantity = payment.quantity
            available_drones = CompanyDroneModelInfo.objects.filter(assign_status=0)[:required_quantity]

            if len(available_drones) < required_quantity:
                return JsonResponse({'error': f'Only {len(available_drones)} drones available, but {required_quantity} required.'}, status=400)

            rate_per_unit = Decimal('310000')
            base_amount = rate_per_unit * required_quantity
            GST_PERCENTAGE = Decimal('5.0')
            gst_amount = base_amount * (GST_PERCENTAGE / 100)

            if is_intrastate:
                cgst = sgst = gst_amount / 2
                igst = Decimal('0.00')
            else:
                cgst = sgst = Decimal('0.00')
                igst = gst_amount

            total_invoice_amount = base_amount + cgst + sgst + igst
            rounded_amount = int(round(total_invoice_amount))

            try:
                total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"
            except:
                total_in_words = ""

            drone_model_ids = [drone.id for drone in available_drones]
            uin_list = [drone.uin_number for drone in available_drones]

            for drone in available_drones:
                drone.assign_status = 1
                drone.save()

            invoice = InvoiceDetails.objects.create(
                customer=customer,
                customer_more=customer_more,
                admin=admin,
                payment=payment,
                drone_model_ids=drone_model_ids,
                invoice_number=invoice_number,
                serial_no=1,
                parts_quantity=required_quantity,
                hsn_sac_code="88062300",
                uom="No",
                rate_per_unit=rate_per_unit,
                total_amount=base_amount,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_taxable_amount=base_amount,
                total_invoice_amount=total_invoice_amount,
                total_invoice_amount_words=total_in_words,
                address_type=address_type,
                description="TEJA-S (UIN Drone)",
                uin_no=", ".join(uin_list),
                invoice_type="drone",
                invoice_status=1
            )

            created_rows.append({
                "serial_no": 1,
                "uin_no": ", ".join(uin_list),
                "quantity": required_quantity,
                "rate_per_unit": float(rate_per_unit),
                "total_amount": float(base_amount),
                "total_taxable_amount": float(base_amount),
                "cgst": float(cgst),
                "sgst": float(sgst),
                "igst": float(igst),
                "total_invoice_amount": float(total_invoice_amount),
                "invoice_id": invoice.id,
                "invoice_status": invoice.invoice_status,
                # "total_invoice_status":invoice.total_invoice_status
            })

        # ---------------- AMC INVOICE ----------------
        elif invoice_for == 'amc':
            existing = InvoiceDetails.objects.filter(
                customer=customer, invoice_type="amc", invoice_status=1, payment__drone_order_id=drone_order_id
            ).first()
            if existing:
                return JsonResponse({
                    "message": "AMC invoice already exists.",
                    "invoice_number": existing.invoice_number,
                    "invoice_status":existing.invoice_status,
                    "invoice_id":existing.id,
                    "uni_no":existing.uin_no,
                    "total_invoice_status":existing.total_invoice_status,
                }, status=200)
            
            drones = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_list)
            if len(drones) != len(uin_list):
                return JsonResponse({'error': 'Some UINs not found'}, status=400)

            drone_model_ids = [d.id for d in drones]
            quantity = len(drones)
            rate_per_unit = Decimal('508475')
            base_amount = rate_per_unit * quantity
            GST_PERCENTAGE = Decimal('18.0')
            gst_amount = base_amount * (GST_PERCENTAGE / 100)
            cgst = sgst = igst = Decimal('0.00')
            if is_intrastate:
                cgst = sgst = gst_amount / 2
            else:
                igst = gst_amount

            total_invoice_amount = base_amount + cgst + sgst + igst
            rounded_amount = int(round(total_invoice_amount))
            try:
                total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"
            except:
                total_in_words = ""

            invoice = InvoiceDetails.objects.create(
                customer=customer,
                customer_more=customer_more,
                admin=admin,
                payment=payment,
                drone_model_ids=drone_model_ids,
                invoice_number=invoice_number,
                serial_no=1,
                parts_quantity=quantity,
                hsn_sac_code="9987",
                uom="No",
                rate_per_unit=rate_per_unit,
                total_amount=base_amount,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_taxable_amount=base_amount,
                total_invoice_amount=total_invoice_amount,
                total_invoice_amount_words=total_in_words,
                address_type=address_type,
                description="AMC for 5.5 Years",
                uin_no=", ".join(uin_list),
                invoice_type="amc",
                invoice_status=1
            )

            created_rows.append({
                "serial_no": 1,
                "uin_no": ", ".join(uin_list),
                "quantity": quantity,
                "rate_per_unit": float(rate_per_unit),
                "total_amount": float(base_amount),
                "total_taxable_amount":float(base_amount),
                "cgst": float(cgst),
                "sgst": float(sgst),
                "igst": float(igst),
                "total_invoice_amount":float(total_invoice_amount),
                "invoice_status": invoice.invoice_status,
                # "total_invoice_status":invoice.total_invoice_status,
                "invoice_id":invoice.id,
            })

        # ---------------- ACCESSORY INVOICE ----------------
        elif invoice_for == 'accessory':
            existing = InvoiceDetails.objects.filter(
                customer=customer, invoice_type="accessory", invoice_status=1, payment__drone_order_id=drone_order_id
            ).first()
            if existing:
                return JsonResponse({
                    "message": "Accessory invoice already exists.",
                    "invoice_number": existing.invoice_number,
                    "invoice_status":existing.invoice_status,
                    "invoice_id":existing.id,
                    "uni_no":existing.uin_no,
                    "total_invoice_status":existing.total_invoice_status,
                }, status=200)
            

            drones = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_list)
            drone_model_ids = [d.id for d in drones]
            drone_count = len(uin_list)

            accessories = [
                {"description": "Batteries (8 Nos)", "qty": 4 * drone_count, "rate": Decimal('29000'), "hsn": "8806", "uom": "Set"},
                {"description": "DG Set", "qty": 1 * drone_count, "rate": Decimal('110000'), "hsn": "8502", "uom": "No"},
                {"description": "Water Tank", "qty": 1 * drone_count, "rate": Decimal('6627'), "hsn": "3925", "uom": "No"},
            ]

            total_taxable_amount = sum(x['qty'] * x['rate'] for x in accessories)
            gst_amount = total_taxable_amount * Decimal('0.18')
            cgst = sgst = gst_amount / 2 if is_intrastate else Decimal('0')
            igst = gst_amount if not is_intrastate else Decimal('0')
            total_invoice_amount = total_taxable_amount + cgst + sgst + igst
            rounded_amount = int(round(total_invoice_amount))
            total_in_words = num2words(rounded_amount, lang='en_IN').title() + " Rupees Only"

            serial_no = 1
            created_rows = []
            created_invoice_objs = []

            for item in accessories:
                line_total = item['qty'] * item['rate']
                invoice = InvoiceDetails.objects.create(
                    customer=customer,
                    customer_more=customer_more,
                    admin=admin,
                    payment=payment,
                    drone_model_ids=drone_model_ids,
                    invoice_number=invoice_number,
                    serial_no=serial_no,
                    parts_quantity=item['qty'],
                    hsn_sac_code=item['hsn'],
                    uom=item['uom'],
                    rate_per_unit=item['rate'],
                    total_amount=line_total,
                    cgst=cgst,
                    sgst=sgst,
                    igst=igst,
                    total_taxable_amount=total_taxable_amount,
                    total_invoice_amount=total_invoice_amount,
                    total_invoice_amount_words=total_in_words,
                    address_type=address_type,
                    description=item['description'],
                    uin_no=", ".join(uin_list),
                    invoice_type="accessory",
                    invoice_status=0
                )
                created_invoice_objs.append(invoice)
                created_rows.append({
                    "serial_no": serial_no,
                    "description": item['description'],
                    "quantity": item['qty'],
                    "rate_per_unit": float(item['rate']),
                    "total_amount": float(line_total),
                    "cgst": float(cgst),
                    "sgst": float(sgst),
                    "igst": float(igst),
                    # "invoice_status": 0,
                    "total_taxable_amount": float(total_taxable_amount),
                    "total_invoice_amount": float(total_invoice_amount),
                    "invoice_id": invoice.id,
                    "invoice_status": invoice.invoice_status,
                    # "total_invoice_status":invoice.total_invoice_status
                })
                serial_no += 1

            if len(created_invoice_objs) == 3:
                for inv in created_invoice_objs:
                    inv.invoice_status = 1
                    inv.save()
                for row in created_rows:
                    row["invoice_status"] = 1

        # ---------------- RETURN ----------------
        # ---------------- CHECK AND UPDATE TOTAL INVOICE STATUS ----------------
        if uin_list:
            for uin in uin_list:
                all_types = ['drone', 'amc', 'accessory']
                invoice_statuses = InvoiceDetails.objects.filter(
                    uin_no__icontains=uin,
                    invoice_type__in=all_types,
                    invoice_status=1
                ).values_list('invoice_type', flat=True).distinct()

                if set(invoice_statuses) == set(all_types):
                    InvoiceDetails.objects.filter(
                        uin_no__icontains=uin,
                        invoice_type__in=all_types
                    ).update(total_invoice_status=1)
         # Check if all UINs of this drone_order_id are fully invoiced, then send mail
        try:
            all_invoices = InvoiceDetails.objects.filter(
                customer=customer,
                payment__drone_order_id=drone_order_id
            )

            uin_set = set()
            for inv in all_invoices:
                uins = [x.strip() for x in inv.uin_no.split(",") if x.strip()]
                uin_set.update(uins)

            eligible_uins = []
            for uin in uin_set:
                completed_types = InvoiceDetails.objects.filter(
                    uin_no__icontains=uin,
                    invoice_type__in=['drone', 'amc', 'accessory'],
                    total_invoice_status=1
                ).values_list('invoice_type', flat=True).distinct()

                if set(completed_types) == {'drone', 'amc', 'accessory'}:
                    eligible_uins.append(uin)

            if set(uin_set) == set(eligible_uins):
                completed_invoices = InvoiceDetails.objects.filter(
                    customer=customer,
                    payment__drone_order_id=drone_order_id,
                    invoice_type__in=['drone', 'amc', 'accessory'],
                    total_invoice_status=1
                ).order_by('serial_no')
                template_map = {
                    "drone": "invoice_1.html",
                    "amc": "invoice_2.html",
                    "accessory": "invoice_3.html"
                }
                pdf_attachments = []
                contexts = build_invoice_contexts(completed_invoices, customer)
                for context in contexts:
                    template_name = template_map.get(context["invoice_type"].lower(), "invoice_1.html")
                # for inv in completed_invoices:
                    # template_name = template_map.get(inv.invoice_type, "invoice_1.html")
                    # address = get_customer_address(customer.id, inv.address_type)
                    # context = {
                    #     "invoice_type": inv.invoice_type.title(),
                    #     "invoice_number": inv.invoice_number,
                    #     "invoice_date": inv.created_at.strftime("%Y-%m-%d"),
                    #     "invoice_status": inv.invoice_status,
                    #     "serial_no": inv.serial_no,
                    #     "description": inv.description,
                    #     "parts_quantity": inv.parts_quantity,
                    #     "rate_per_unit": float(inv.rate_per_unit),
                    #     "hsn_sac_code": inv.hsn_sac_code,
                    #     "uom": inv.uom,
                    #     "total_amount": float(inv.total_amount),
                    #     "cgst": float(inv.cgst),
                    #     "sgst": float(inv.sgst),
                    #     "igst": float(inv.igst),
                    #     "total_taxable_amount": float(inv.total_taxable_amount),
                    #     "total_invoice_amount": float(inv.total_invoice_amount),
                    #     "total_invoice_amount_words": inv.total_invoice_amount_words,
                    #     "uin_no": inv.uin_no,
                    #     "address_type": inv.address_type,
                    #     "customer": {
                    #         "id": customer.id,
                    #         "full_name": customer.kyc.pan_name if hasattr(customer, 'kyc') and customer.kyc else "Customer",
                    #         "name": f"{customer.first_name} {customer.last_name}",
                    #         "email": customer.email,
                    #         "mobile_no": customer.mobile_no,
                    #     },
                    #     "address": address,
                    #     "payment": {
                    #         "id": inv.payment.id,
                    #         "amount": float(inv.payment.amount),
                    #         "total_amount": float(inv.payment.total_amount),
                    #         "quantity": inv.payment.quantity,
                    #         "drone_order_id": inv.payment.drone_order_id,
                    #         "payment_status": inv.payment.payment_status,
                    #         "drone_payment_status": inv.payment.drone_payment_status,
                    #         "payment_type": inv.payment.payment_type,
                    #         "payment_mode": inv.payment.payment_mode,
                    #         "created_at": localtime(inv.payment.created_at).strftime("%Y-%m-%d"),
                    #     }
                    # }
                 
                    # # template_name = template_map.get(inv.invoice_type, "invoice_1.html")

                    pdf_file = generate_receipt_pdf(context, template_name)
                    pdf_attachments.append({
                        "filename": f"{context['invoice_type']}_Invoice_{context['invoice_number']}.pdf",
                        "file": pdf_file
                    })
                    # pdf_attachments.append({
                    #     "filename": f"{inv.invoice_type.title()}_Invoice_{inv.invoice_number}.pdf",
                    #     "file": pdf_file
                    # })

                send_invoice_bundle_email(customer, pdf_attachments)
        except Exception as e:
            print("Error while checking total invoice status for email:", e)

        return JsonResponse({
            "message": f"{invoice_for.title()} invoice created successfully",
            "invoice_number": invoice_number,
            "total_invoice_amount": float(total_invoice_amount),
            "total_invoice_amount_words": total_in_words,
            "total_invoice_status": invoice.total_invoice_status,
            "rows": created_rows,
        }, status=201)

    except CustomerRegister.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
from django.utils.timezone import localtime

def build_invoice_contexts(invoices, customer):
    """
    Create a reusable list of context dictionaries for multiple invoices.
    Can be used for both viewing and PDF generation.
    """
    contexts = []
    for inv in invoices:
        address = get_customer_address(customer.id, inv.address_type)
        context = {
            "invoice_type": inv.invoice_type.title(),
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.created_at.strftime("%Y-%m-%d"),
            "invoice_status": inv.invoice_status,
            "serial_no": inv.serial_no,
            "description": inv.description,
            "parts_quantity": inv.parts_quantity,
            "rate_per_unit": float(inv.rate_per_unit),
            "hsn_sac_code": inv.hsn_sac_code,
            "uom": inv.uom,
            "total_amount": float(inv.total_amount),
            "cgst": float(inv.cgst),
            "sgst": float(inv.sgst),
            "igst": float(inv.igst),
            "total_taxable_amount": float(inv.total_taxable_amount),
            "total_invoice_amount": float(inv.total_invoice_amount),
            "total_invoice_amount_words": inv.total_invoice_amount_words,
            "uin_no": inv.uin_no,
            "address_type": inv.address_type,
            "customer": {
                "id": customer.id,
                "full_name": getattr(getattr(customer, 'kyc', None), 'pan_name', "Customer"),
                "name": f"{customer.first_name} {customer.last_name}",
                "email": customer.email,
                "mobile_no": customer.mobile_no,
            },
            "address": address,
            "payment": {
                "id": inv.payment.id,
                "amount": float(inv.payment.amount),
                "total_amount": float(inv.payment.total_amount),
                "quantity": inv.payment.quantity,
                "drone_order_id": inv.payment.drone_order_id,
                "payment_status": inv.payment.payment_status,
                "drone_payment_status": inv.payment.drone_payment_status,
                "payment_type": inv.payment.payment_type,
                "payment_mode": inv.payment.payment_mode,
                "created_at": localtime(inv.payment.created_at).strftime("%Y-%m-%d"),
            }
        }
        contexts.append(context)
    return contexts
    
def send_invoice_bundle_email(customer, attachments):
    subject = "All Invoices from Pavaman Aviation"
    text_content = f"Dear {customer.full_name},\n\nPlease find attached all invoices for your drone order."

    html_content = f"""
    <p>Dear {customer.full_name},</p>
    <p>Thank you for completing your purchase with Pavaman Aviation. All three invoices (Drone, AMC, and Accessories) are attached below.</p>
    <p>If you have any questions, please contact support@pavaman.com.</p>
    <p>Regards,<br>Pavaman Aviation</p>
    """

    email_message = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [customer.email]
    )
    email_message.attach_alternative(html_content, "text/html")

    for attachment in attachments:
        email_message.attach(attachment["filename"], attachment["file"].read(), 'application/pdf')

    email_message.send()
# @customer_login_required
@csrf_exempt
def view_invoices(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)
    try:
        data = json.loads(request.body)
        customer_id = data.get("customer_id")       
        # customer_id = request.session.get('customer_id')
        if not customer_id:
            return JsonResponse({"error": "Unauthorized"}, status=403)

        drone_order_id = data.get("drone_order_id")
        if not drone_order_id:
            return JsonResponse({"error": "drone_order_id is required"}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        invoices = InvoiceDetails.objects.filter(
            customer_id=customer_id,
            payment__drone_order_id=drone_order_id
        ).order_by('serial_no')

        if not invoices.exists():
            return JsonResponse({"error": "No invoices found"}, status=404)

        contexts = build_invoice_contexts(invoices, customer)
        return JsonResponse({"invoices": contexts}, status=200)

    except CustomerRegister.DoesNotExist:
        return JsonResponse({"error": "Customer not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def view_installment_receipt(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)
    try:
        data = json.loads(request.body)
        customer_id = data.get("customer_id")

        if not customer_id:
            return JsonResponse({"error": "customer_id is required as GET parameter"}, status=400)

        payments = PaymentDetails.objects.filter(
            customer_id=customer_id,
            drone_payment_status='captured',
            payment_type='installment',
            status=1
        ).order_by('-id')

        if not payments.exists():
            return JsonResponse({"error": "No paid payments found for this customer."}, status=404)

        kyc = KYCDetails.objects.filter(customer_id=customer_id).first()
        full_name = kyc.pan_name if kyc else "Customer"

        receipts = []
        for payment in payments:
            receipts.append({
                "payment_type": payment.payment_type,
                "installment_number": payment.part_number,
                "full_name": full_name,
                "payment_mode": payment.payment_mode,
                "amount": float(payment.amount),
                "payment_status": payment.payment_status,
                "drone_order_id": payment.drone_order_id,
                "razorpay_payment_id": payment.razorpay_payment_id,
                "created_at": format_datetime_ist(payment.created_at),
            })

        return JsonResponse({"receipts": receipts}, status=200)

    except Exception as e:
        print("View Customer Receipt Error:", str(e))
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def payment_history(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get("customer_id")

        if not customer_id:
            return JsonResponse({"error": "customer_id is required"}, status=400)

        payments = PaymentDetails.objects.filter(customer_id=customer_id).order_by("-id")

        if not payments.exists():
            return JsonResponse({"error": "No payment history found for this customer."}, status=404)

        kyc = KYCDetails.objects.filter(customer_id=customer_id).first()
        full_name = kyc.pan_name if kyc else "Customer"

        history = []
        for payment in payments:
            history.append({
                "payment_type": payment.payment_type,
                "part_number": payment.part_number,
                "full_name": full_name,
                "payment_mode": payment.payment_mode,
                "amount": float(payment.amount),
                "payment_status": payment.payment_status,
                "drone_order_id": payment.drone_order_id,
                "razorpay_payment_id": payment.razorpay_payment_id,
                "created_at": payment.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(payment, "created_at") else None
            })

        return JsonResponse({"payment_history": history}, status=200, safe=False)

    except Exception as e:
        print("Payment History Error:", str(e))
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt 
def get_invoice_details(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    customer_id = data.get('customer_id')
    invoice_id = data.get('invoice_id')

    if not customer_id:
        return JsonResponse({'error': 'Unauthorized, session expired or not logged in'}, status=401)

    if not invoice_id:
        return JsonResponse({'error': 'invoice_id is required'}, status=400)

    try:
        invoice = InvoiceDetails.objects.select_related(
            'customer', 'customer_more', 'payment', 'drone_model', 'admin'
        ).get(id=invoice_id)

        if str(invoice.customer.id) != str(customer_id):
            return JsonResponse({'error': 'You are not authorized to view this invoice'}, status=403)

        customer = invoice.customer
        customer_more = invoice.customer_more
        payment = invoice.payment
        drone_model = invoice.drone_model
        admin = invoice.admin
        address =get_customer_address(customer_id, invoice.address_type)

        return JsonResponse({
            "invoice": {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "invoice_date": localtime(invoice.created_at).strftime("%Y-%m-%d"),
                "invoice_status": invoice.invoice_status,
                "invoice_type": invoice.invoice_type,
                "description": invoice.description,
                "parts_quantity": invoice.parts_quantity,
                "rate_per_unit": float(invoice.rate_per_unit),
                "hsn_sac_code": invoice.hsn_sac_code,
                "uom": invoice.uom,
                "total_amount": float(invoice.total_amount),
                "cgst": float(invoice.cgst),
                "sgst": float(invoice.sgst),
                "igst": float(invoice.igst),
                "total_taxable_amount": float(invoice.total_taxable_amount),
                "total_invoice_amount": float(invoice.total_invoice_amount),
                "total_invoice_amount_words": invoice.total_invoice_amount_words,
                "uin_no": invoice.uin_no,
                "address_type": invoice.address_type,
            },
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}",
                "email": customer.email,
                "mobile_no": customer.mobile_no,
            } if customer else None,
            "address": address,
            "payment": {
                "id": payment.id,
                "amount": float(payment.amount),
                "total_amount": float(payment.total_amount),
                "quantity": payment.quantity,
                "drone_order_id": payment.drone_order_id,
                "payment_status": payment.payment_status,
                "drone_payment_status": payment.drone_payment_status,
                "payment_type": payment.payment_type,
                "created_at": localtime(payment.created_at).strftime("%Y-%m-%d"),
            } if payment else None,
            "drone_model": {
                "id": drone_model.id,
                "uin_number": drone_model.uin_number,
                "assign_status": drone_model.assign_status,
            } if drone_model else None,
          
        }, status=200)

    except InvoiceDetails.DoesNotExist:
        return JsonResponse({'error': 'Invoice not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
def get_customer_address(customer_id, address_type="permanent"):
    try:
        more_details = CustomerMoreDetails.objects.get(customer_id=customer_id)

        if address_type == "permanent":
            return {
                "address": more_details.address,
                "district": more_details.district,
                "mandal": more_details.mandal,
                "city": more_details.city,
                "state": more_details.state,
                "country": more_details.country,
                "pincode": more_details.pincode,
            }

        elif address_type == "present":
            if more_details.same_address:
                # Use permanent details
                return {
                    "address": more_details.address,
                    "district": more_details.district,
                    "mandal": more_details.mandal,
                    "city": more_details.city,
                    "state": more_details.state,
                    "country": more_details.country,
                    "pincode": more_details.pincode,
                }
            else:
                # Use present details
                return {
                    "address": more_details.present_address,
                    "district": more_details.present_district,
                    "mandal": more_details.present_mandal,
                    "city": more_details.present_city,
                    "state": more_details.present_state,
                    "country": more_details.present_country,
                    "pincode": more_details.present_pincode,
                }

        return None

    except CustomerMoreDetails.DoesNotExist:
        return None
  

def calculate_age(dob):
    from datetime import date
    if not dob:
        return ""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# @csrf_exempt
# def generate_agreement_by_order(request):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Only POST method allowed'}, status=405)

#     try:
#         data = json.loads(request.body)
#         drone_order_id = data.get('drone_order_id')
#         customer_id = data.get('customer_id')

#         if not drone_order_id:
#             return JsonResponse({'error': 'drone_order_id is required'}, status=400)

#         payments = PaymentDetails.objects.filter(drone_order_id=drone_order_id).order_by('created_at')
#         if not payments.exists():
#             return JsonResponse({'error': 'No payments found for this drone_order_id'}, status=404)

#         payment = payments.first()
#         invoices = InvoiceDetails.objects.filter(payment=payment)
#         if not invoices.exists():
#             return JsonResponse({'error': 'Invoice not found for this payment'}, status=404)

#         invoice = invoices.first()
#         customer = invoice.customer

#         if customer_id and str(customer.id) != str(customer_id):
#             return JsonResponse({'error': 'Unauthorized access'}, status=403)

#         try:
#             kyc = KYCDetails.objects.get(customer=customer)
#         except KYCDetails.DoesNotExist:
#             kyc = None

#         nominees = NomineeDetails.objects.filter(customer=customer)
#         more_details = CustomerMoreDetails.objects.filter(customer=customer).first()

#         uin_numbers = invoice.uin_no.split(',') if invoice.uin_no else []
#         uin_numbers = [u.strip() for u in uin_numbers if u.strip()]
#         drone_infos = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_numbers)

#         drone_names = [d.model_name for d in drone_infos]
#         drone_uins = [d.uin_number for d in drone_infos]

#         unique_names = list(dict.fromkeys(drone_names))
#         unique_uins = list(dict.fromkeys(drone_uins))

#         drone_name = ', '.join(unique_names)
#         drone_unique_code = ', '.join(unique_uins)

#         today = localtime().date()
#         agreement_no = f"PAV-AGRI-{today.strftime('%Y%m%d')}{str(customer.id).zfill(3)}"
#         from_date = today
#         to_date = today + relativedelta(months=66)

#         unique_invoice_map = {}
#         for inv in invoices:
#             inv_number = inv.invoice_number.strip().replace('\n', '').replace('\r', '')
#             if inv_number and inv_number not in unique_invoice_map:
#                 unique_invoice_map[inv_number] = inv
#         unique_invoices = list(unique_invoice_map.values())
#         unique_invoices.sort(key=lambda x: x.created_at)

#         invoice_number_str = ','.join(unique_invoice_map.keys())
#         invoice_date_str = unique_invoices[0].created_at.strftime("%Y-%m-%d") if unique_invoices else ''
#         total_invoice_amount = sum(inv.total_invoice_amount for inv in unique_invoices)

#         resident_of = ""
#         address_type = getattr(invoice, 'address_type', 'permanent')
#         if more_details:
#             if more_details.same_address:
#                 resident_of = f"{more_details.address or ''}, {more_details.city or ''}, " \
#                               f"{more_details.district or ''}, {more_details.mandal or ''}, " \
#                               f"{more_details.country or ''} - {more_details.pincode or ''}"
#             else:
#                 if address_type == "present":
#                     resident_of = f"{more_details.present_address or ''}, {more_details.present_city or ''}, " \
#                                       f"{more_details.present_district or ''}, {more_details.present_mandal or ''}, " \
#                                       f"{more_details.present_country or ''} - {more_details.present_pincode or ''}"
#                 else:
#                     resident_of = f"{more_details.address or ''}, {more_details.city or ''}, " \
#                                   f"{more_details.district or ''}, {more_details.mandal or ''}, " \
#                                   f"{more_details.country or ''} - {more_details.pincode or ''}"
#             signature_url = ""
#             if more_details and more_details.signature_path:
#                 signature_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{more_details.signature_path}"

#             context = {
#                 "preview": {
#                     "agreement_no": agreement_no,
#                     "agreement_date": today.strftime("%Y-%m-%d"),
#                     "agreement_day": today.strftime('%d'),
#                     "agreement_month": today.strftime('%m'),
#                     "agreement_year_full": today.year,
#                     "agreement_year_short": str(today.year)[-2:],
#                     "from_date": from_date.strftime("%Y-%m-%d"),
#                     "to_date": to_date.strftime("%Y-%m-%d"),
#                     "drone_name": drone_name,
#                     "drone_unique_code": drone_unique_code,
#                     "invoice_number_str": invoice_number_str,
#                     "invoice_date_str": invoice_date_str,
#                     "total_invoice_amount": total_invoice_amount
#                 },
#                 "lessor": {
#                     "name": kyc.pan_name if kyc else f"{customer.first_name} {customer.last_name}",
#                     "guardian_name": "",  # If you have father/spouse name, put here
#                     "age": calculate_age(kyc.pan_dob) if kyc and kyc.pan_dob else "",
#                     "resident_of": resident_of,
#                     "pan_number": kyc.pan_number if kyc else "",
#                     "aadhaar_number": kyc.aadhar_number if kyc else "",
#                     "signature_url": signature_url
#                 },
#                 "bank_details": {
#                     "account_number": kyc.bank_account_number if kyc else "",
#                     "account_holder_name": kyc.pan_name if kyc else "",
#                     "bank_name": kyc.bank_name if kyc else "",
#                     "ifsc_code": kyc.ifsc_code if kyc else ""
#                 },
#                 "nominees": [
#                     {
#                         "sno": idx + 1,
#                         "nominee_name": f"{n.first_name} {n.last_name}",
#                         "nominee_relation": n.relation,
#                         "nominee_address": "",  # If available
#                         "nominee_share": n.share
#                     }
#                     for idx, n in enumerate(nominees)
#                 ],
#                 "company_details": {
#                     "signature": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Sign.png",
#                     "stamp": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Stamp.png"
#                 }
#             }



#         html_string = render_to_string('agreement.html', context)
#         pdf_buffer = BytesIO()
#         HTML(string=html_string).write_pdf(target=pdf_buffer)
#         pdf_content = pdf_buffer.getvalue()

#         s3 = boto3.client(
#             's3',
#             aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#             aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#             region_name=settings.AWS_S3_REGION_NAME
#         )

#         bucket_name = settings.AWS_STORAGE_BUCKET_NAME
#         first_name = customer.first_name or ''
#         last_name = customer.last_name or ''
#         customer_folder = f"customerdoc/{customer.id}_{first_name.lower()}{last_name.lower()}/"
#         timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
#         s3_filename = f"{customer_folder}agreement_{agreement_no}_{timestamp_str}.pdf"

#         s3.upload_fileobj(
#             BytesIO(pdf_content),
#             bucket_name,
#             s3_filename,
#             ExtraArgs={'ContentType': 'application/pdf'}
#         )

#         s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_filename}"

#         agreement_obj = AgreementDetails.objects.create(
#             agreement_no=agreement_no,
#             agreement_date=today,
#             agreement_day=today.strftime('%d'),
#             agreement_month=today.strftime('%m'),
#             agreement_year_full=today.year,
#             agreement_year_short=str(today.year)[-2:],
#             from_date=from_date,
#             to_date=to_date,
#             drone_name=drone_name,
#             drone_unique_code=drone_unique_code,
#             invoice_number=invoice_number_str,
#             invoice_date=invoice.created_at.date(),
#             witness_leassor="Leassor Name",
#             witness_lessee="Lessee Name",
#             customer=customer
#         )

#         # email = EmailMessage(
#         #     subject=f"Agreement Document - {agreement_no}",
#         #     body=f"Dear {customer.first_name},\n\nPlease find attached the agreement document.\n\nRegards,\nTeam",
#         #     from_email=settings.DEFAULT_FROM_EMAIL,
#         #     #to=[customer.email, 'saralkumar28@gmail.com'],
#         #     to=['saralkumar28@gmail.com']
#         # )
#         # email.attach(f"Agreement_{agreement_no}.pdf", pdf_content, "application/pdf")
#         # email.send(fail_silently=False)

#         # Send to WhatsApp
#         # whatsapp_response = send_agreement_on_whatsapp(
#         #     # mobile_number=customer.mobile,
#         #     mobile_number="7981956619",
#         #     agreement_url=s3_url,
#         #     agreement_no=agreement_no
#         # )

#         return JsonResponse({
#             "message": "Agreement generated, uploaded to S3, emailed, and sent via WhatsApp successfully",
#             "agreement_pdf_url": s3_url,
#             "agreement_no": agreement_obj.agreement_no,
#             # "whatsapp_status": whatsapp_response
#         })

#     except json.JSONDecodeError:
#         return JsonResponse({'error': 'Invalid JSON'}, status=400)
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def generate_agreement_by_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        drone_order_id = data.get('drone_order_id')
        customer_id = data.get('customer_id')

        if not drone_order_id:
            return JsonResponse({'error': 'drone_order_id is required'}, status=400)

        payments = PaymentDetails.objects.filter(drone_order_id=drone_order_id).order_by('created_at')
        if not payments.exists():
            return JsonResponse({'error': 'No payments found for this drone_order_id'}, status=404)

        payment = payments.first()
        invoices = InvoiceDetails.objects.filter(payment=payment)
        if not invoices.exists():
            return JsonResponse({'error': 'Invoice not found for this payment'}, status=404)

        invoice = invoices.first()
        customer = invoice.customer

        if customer_id and str(customer.id) != str(customer_id):
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        try:
            kyc = KYCDetails.objects.get(customer=customer)
        except KYCDetails.DoesNotExist:
            kyc = None

        nominees = NomineeDetails.objects.filter(customer=customer)

        # ✅ Get the same signature record logic as preview
        customer_more = (
            CustomerMoreDetails.objects
            .filter(customer=customer, status=1)
            .exclude(signature_path__isnull=True)
            .exclude(signature_path__exact="")
            .order_by("-id")
            .first()
        )

        signature_url = ""
        if customer_more and customer_more.signature_path:
            signature_url = f"{settings.AWS_S3_BUCKET_URL}/{customer_more.signature_path}"

        if not (customer_more and customer_more.guardian_name and customer_more.guardian_relation):
            guardian_source = (
                CustomerMoreDetails.objects
                .filter(customer=customer)
                .exclude(guardian_name__isnull=True)
                .exclude(guardian_name__exact="")
                .exclude(guardian_relation__isnull=True)
                .exclude(guardian_relation__exact="")
                .order_by("-id")
                .first()
            )
            if guardian_source:
                guardian_name = guardian_source.guardian_name
                guardian_relation = guardian_source.guardian_relation
            else:
                guardian_name = ""
                guardian_relation = ""
        else:
            guardian_name = customer_more.guardian_name
            guardian_relation = customer_more.guardian_relation

        # Address
        resident_of = ""
        address_type = getattr(invoice, 'address_type', 'permanent')
        if customer_more:
            if customer_more.same_address:
                resident_of = f"{customer_more.address or ''}, {customer_more.city or ''}, " \
                              f"{customer_more.district or ''}, {customer_more.mandal or ''}, " \
                              f"{customer_more.country or ''} - {customer_more.pincode or ''}"
            else:
                if address_type == "present":
                    resident_of = f"{customer_more.present_address or ''}, {customer_more.present_city or ''}, " \
                                  f"{customer_more.present_district or ''}, {customer_more.present_mandal or ''}, " \
                                  f"{customer_more.present_country or ''} - {customer_more.present_pincode or ''}"
                else:
                    resident_of = f"{customer_more.address or ''}, {customer_more.city or ''}, " \
                                  f"{customer_more.district or ''}, {customer_more.mandal or ''}, " \
                                  f"{customer_more.country or ''} - {customer_more.pincode or ''}"

        # Drone details
        uin_numbers = invoice.uin_no.split(',') if invoice.uin_no else []
        uin_numbers = [u.strip() for u in uin_numbers if u.strip()]
        drone_infos = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_numbers)

        unique_names = list(dict.fromkeys([d.model_name for d in drone_infos]))
        unique_uins = list(dict.fromkeys([d.uin_number for d in drone_infos]))

        drone_name = ', '.join(unique_names)
        drone_unique_code = ', '.join(unique_uins)

        today = localtime().date()
        agreement_no = f"PAV-AGRI-{today.strftime('%Y%m%d')}{str(customer.id).zfill(3)}"
        from_date = today
        to_date = today + relativedelta(months=66)

        unique_invoice_map = {}
        for inv in invoices:
            inv_number = inv.invoice_number.strip().replace('\n', '').replace('\r', '')
            if inv_number and inv_number not in unique_invoice_map:
                unique_invoice_map[inv_number] = inv
        unique_invoices = list(unique_invoice_map.values())
        unique_invoices.sort(key=lambda x: x.created_at)

        invoice_number_str = ','.join(unique_invoice_map.keys())
        invoice_date_str = unique_invoices[0].created_at.strftime("%Y-%m-%d") if unique_invoices else ''
        total_invoice_amount = sum(inv.total_invoice_amount for inv in unique_invoices)

        # Context for template
        context = {
            "preview": {
                "agreement_no": agreement_no,
                "agreement_date": today.strftime("%Y-%m-%d"),
                "agreement_day": today.strftime('%d'),
                "agreement_month": today.strftime('%m'),
                "agreement_year_full": today.year,
                "agreement_year_short": str(today.year)[-2:],
                "from_date": from_date.strftime("%Y-%m-%d"),
                "to_date": to_date.strftime("%Y-%m-%d"),
                "drone_name": drone_name,
                "drone_unique_code": drone_unique_code,
                "invoice_number_str": invoice_number_str,
                "invoice_date_str": invoice_date_str,
                "total_invoice_amount": total_invoice_amount,

            },
            "lessor": {
                "name": kyc.pan_name if kyc else f"{customer.first_name} {customer.last_name}",
                "age": calculate_age(kyc.pan_dob) if kyc and kyc.pan_dob else "",
                "resident_of": resident_of,
                "pan_number": kyc.pan_number if kyc else "",
                "aadhaar_number": kyc.aadhar_number if kyc else "",
                "signature_url": signature_url ,
                "guardian_name": guardian_name,
                "guardian_relation": guardian_relation,
            },
            "bank_details": {
                "account_number": kyc.bank_account_number if kyc else "",
                "account_holder_name": kyc.pan_name if kyc else "",
                "bank_name": kyc.bank_name if kyc else "",
                "ifsc_code": kyc.ifsc_code if kyc else ""
            },
            "nominees": [
                {
                    "sno": idx + 1,
                    "nominee_name": f"{n.first_name} {n.last_name}",
                    "nominee_relation": n.relation,
                    "nominee_address": "",
                    "nominee_share": n.share,
                    "nominee_address":n.address,
                }
                for idx, n in enumerate(nominees)
            ],
            "company_details": {
                "signature": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Sign.png",
                "stamp": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Stamp.png"
            }
        }

        # Render PDF
        html_string = render_to_string('agreement.html', context)
        pdf_buffer = BytesIO()
        HTML(string=html_string).write_pdf(target=pdf_buffer)
        pdf_content = pdf_buffer.getvalue()

        # Upload to S3
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        customer_folder = f"customerdoc/{customer.id}_{(customer.first_name or '').lower()}{(customer.last_name or '').lower()}/"
        timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
        s3_filename = f"{customer_folder}agreement_{agreement_no}_{timestamp_str}.pdf"

        s3.upload_fileobj(
            BytesIO(pdf_content),
            bucket_name,
            s3_filename,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_filename}"

        # Save agreement record
        agreement_obj = AgreementDetails.objects.create(
            agreement_no=agreement_no,
            agreement_date=today,
            agreement_day=today.strftime('%d'),
            agreement_month=today.strftime('%m'),
            agreement_year_full=today.year,
            agreement_year_short=str(today.year)[-2:],
            from_date=from_date,
            to_date=to_date,
            drone_name=drone_name,
            drone_unique_code=drone_unique_code,
            invoice_number=invoice_number_str,
            invoice_date=invoice.created_at.date(),
            witness_leassor="Leassor Name",
            witness_lessee="Lessee Name",
            customer=customer
        )

        return JsonResponse({
            "message": "Agreement generated successfully",
            "agreement_pdf_url": s3_url,
            "agreement_no": agreement_obj.agreement_no
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def preview_agreement_by_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        drone_order_id = data.get('drone_order_id')
        customer_id = data.get('customer_id')

        if not drone_order_id:
            return JsonResponse({'error': 'drone_order_id is required'}, status=400)

        payments = PaymentDetails.objects.filter(drone_order_id=drone_order_id).order_by('created_at')
        if not payments.exists():
            return JsonResponse({'error': 'No payments found for this drone_order_id'}, status=404)

        payment = payments.first()
        invoices = InvoiceDetails.objects.filter(payment=payment)
        if not invoices.exists():
            return JsonResponse({'error': 'Invoice not found for this payment'}, status=404)

        invoice = invoices.first()
        customer = invoice.customer

        if customer_id and str(customer.id) != str(customer_id):
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        try:
            kyc = KYCDetails.objects.get(customer=customer)
        except KYCDetails.DoesNotExist:
            kyc = None


        # Get more details from correct customer object
        # customer_more = CustomerMoreDetails.objects.filter(customer=customer).first()
        # Get latest active details where signature exists
        customer_more = (
            CustomerMoreDetails.objects
            .filter(customer=customer, status=1)  # ensure only active row
            .exclude(signature_path__isnull=True)
            .exclude(signature_path__exact="")
            .order_by("-id")  # latest record first
            .first()
        )

        customer_signature_url = ""
        if customer_more and customer_more.signature_path:
            # Match format_customer_data style
            customer_signature_url = f"{settings.AWS_S3_BUCKET_URL}/{customer_more.signature_path}"

        if not (customer_more and customer_more.guardian_name and customer_more.guardian_relation):
            guardian_source = (
                CustomerMoreDetails.objects
                .filter(customer=customer)
                .exclude(guardian_name__isnull=True)
                .exclude(guardian_name__exact="")
                .exclude(guardian_relation__isnull=True)
                .exclude(guardian_relation__exact="")
                .order_by("-id")
                .first()
            )
            if guardian_source:
                guardian_name = guardian_source.guardian_name
                guardian_relation = guardian_source.guardian_relation
            else:
                guardian_name = ""
                guardian_relation = ""
        else:
            guardian_name = customer_more.guardian_name
            guardian_relation = customer_more.guardian_relation
    
        nominees = NomineeDetails.objects.filter(customer=customer)
        more_details = CustomerMoreDetails.objects.filter(customer=customer).first()

        uin_numbers = invoice.uin_no.split(',') if invoice.uin_no else []
        uin_numbers = [u.strip() for u in uin_numbers if u.strip()]
        drone_infos = CompanyDroneModelInfo.objects.filter(uin_number__in=uin_numbers)

        drone_names = [d.model_name for d in drone_infos]
        drone_uins = [d.uin_number for d in drone_infos]

        unique_names = list(dict.fromkeys(drone_names))
        unique_uins = list(dict.fromkeys(drone_uins))

        drone_name = ', '.join(unique_names)
        drone_unique_code = ', '.join(unique_uins)
        drone_quantity = len(unique_uins)

        today = localtime().date()
        agreement_no = f"PAV-AGRI-{today.strftime('%Y%m%d')}{str(customer.id).zfill(3)}"
        from_date = today
        to_date = today + relativedelta(months=66)

        unique_invoice_map = {}
        for inv in invoices:
            inv_number = inv.invoice_number.strip().replace('\n', '').replace('\r', '')
            if inv_number and inv_number not in unique_invoice_map:
                unique_invoice_map[inv_number] = inv
        unique_invoices = list(unique_invoice_map.values())
        unique_invoices.sort(key=lambda x: x.created_at)

        invoice_number_str = ','.join(unique_invoice_map.keys())
        invoice_date_str = unique_invoices[0].created_at.strftime("%Y-%m-%d") if unique_invoices else ''
        total_invoice_amount = sum(inv.total_invoice_amount for inv in unique_invoices)

        # Address construction
        resident_of = ""
        address_type = getattr(invoice, 'address_type', 'permanent')
        if more_details:
            if more_details.same_address:
                resident_of = f"{more_details.address or ''}, {more_details.city or ''}, " \
                              f"{more_details.district or ''}, {more_details.mandal or ''}, " \
                              f"{more_details.country or ''} - {more_details.pincode or ''}"
            else:
                if address_type == "present":
                    resident_of = f"{more_details.present_address or ''}, {more_details.present_city or ''}, " \
                                  f"{more_details.present_district or ''}, {more_details.present_mandal or ''}, " \
                                  f"{more_details.present_country or ''} - {more_details.present_pincode or ''}"
                else:
                    resident_of = f"{more_details.address or ''}, {more_details.city or ''}, " \
                                  f"{more_details.district or ''}, {more_details.mandal or ''}, " \
                                  f"{more_details.country or ''} - {more_details.pincode or ''}"
        

 
        return JsonResponse({
            "preview": {
                "agreement_no": agreement_no,
                "agreement_date": today.strftime("%Y-%m-%d"),
                "agreement_day": today.strftime('%d'),
                "agreement_month": today.strftime('%m'),
                "agreement_year_full": today.year,
                "from_date": from_date.strftime("%Y-%m-%d"),
                "to_date": to_date.strftime("%Y-%m-%d"),

                "drone_quantity": drone_quantity,
                "drone_name": drone_name,
                "drone_unique_code": drone_unique_code,
                "invoice_number_str": invoice_number_str,
                "invoice_date_str": invoice_date_str,
                "total_invoice_amount": total_invoice_amount,

                "monthly_amount": 25000,
                "lump_sum_amount": 2244000,
                "residual_value": 156000,
                "payment_mode": getattr(payment, 'payment_mode', ''),
                "customer_signature_url": customer_signature_url,
            },
            "lessor": {
                "name": kyc.pan_name if kyc else f"{customer.first_name} {customer.last_name}",
                "guardian_name": guardian_name,
                "guardian_relation": guardian_relation,
                "age": calculate_age(kyc.pan_dob) if kyc and kyc.pan_dob else "",
                "resident_of": resident_of,
                "pan_number": kyc.pan_number if kyc else "",
                "aadhaar_number": kyc.aadhar_number if kyc else ""
            },
            "bank_details": {
                "account_number": kyc.bank_account_number if kyc else "",
                "account_holder_name": kyc.pan_name if kyc else "",
                "bank_name": kyc.bank_name if kyc else "",
                "ifsc_code": kyc.ifsc_code if kyc else ""
            },
            "nominees": [
                {
                    "sno": idx + 1,
                    "nominee_name": f"{n.first_name} {n.last_name}",
                    "nominee_relation": n.relation,
                    "nominee_share": n.share,
                    "nominee_address":n.address,
                } for idx, n in enumerate(nominees)
            ],
            "company_details":{
                "signature": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Sign.png",
                "stamp": "https://pavamaninvestdoc.s3.ap-south-1.amazonaws.com/Pavaman_Stamp.png",
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

import boto3
from django.http import HttpResponseBadRequest, JsonResponse
import json
from botocore.exceptions import ClientError

@csrf_exempt
def download_agreement_by_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        drone_order_id = data.get('drone_order_id')
        customer_id = data.get('customer_id')

        if not drone_order_id:
            return JsonResponse({'error': 'drone_order_id is required'}, status=400)

        payment = PaymentDetails.objects.filter(drone_order_id=drone_order_id).first()
        if not payment:
            return JsonResponse({'error': 'No payment found for this order'}, status=404)

        invoice = InvoiceDetails.objects.filter(payment=payment).first()
        if not invoice:
            return JsonResponse({'error': 'Invoice not found for this payment'}, status=404)

        customer = invoice.customer
        if customer_id and str(customer.id) != str(customer_id):
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        # Get latest agreement
        agreement = AgreementDetails.objects.filter(customer=customer).order_by("-id").first()
        if not agreement:
            return JsonResponse({'error': 'Agreement not found. Please generate it first.'}, status=404)

        first_name = customer.first_name or ''
        last_name = customer.last_name or ''
        customer_folder = f"customerdoc/{customer.id}_{first_name.lower()}{last_name.lower()}/"
        s3_filename_prefix = f"{customer_folder}agreement_{agreement.agreement_no}"

        # S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

        # Find latest file in S3
        s3_objects = s3_client.list_objects_v2(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Prefix=s3_filename_prefix
        )

        if 'Contents' not in s3_objects:
            return JsonResponse({'error': 'Agreement file not found in S3'}, status=404)

        latest_file = max(s3_objects['Contents'], key=lambda x: x['LastModified'])
        s3_key = latest_file['Key']

        # Generate pre-signed URL (valid for 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=3600
        )

        return JsonResponse({"download_url": presigned_url})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except ClientError as e:
        return JsonResponse({'error': f'S3 Error: {str(e)}'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
