import random
import json
import pytz
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db import IntegrityError
from django.utils import timezone
import requests
from .models import CustomerRegister
from .sms_utils import send_otp_sms
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

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
        email = data.get('email')
        mobile_no = data.get('mobile_no')

        first_name = ''
        last_name = ''

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
        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number."}, status=400)
        customer = None
        if email:
            customer = CustomerRegister.objects.filter(email=email).first()
        if not customer and mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

        otp = generate_otp()

        if customer:
            if customer.register_status == 1:
                return JsonResponse({
                    "message": "Account already verified. Please login.",
                    "customer_id": customer.id,
                    "email": customer.email,
                    "mobile_no": customer.mobile_no,
                }, status=200)

            # resend OTP if not verified
            customer.otp = otp
            customer.save(update_fields=['otp'])
        else:
            customer = CustomerRegister.objects.create(
                email=email or '',
                mobile_no=mobile_no or '',
                first_name=first_name or '',
                last_name=last_name or '',
                otp=otp,
                register_type="Google" if token else "Email" if email else "Mobile",
                
            )
        if email:
            send_otp_email(email,first_name, otp)
        if mobile_no:
            send_otp_sms([mobile_no], f"Hi,This is your OTP for password reset on Pavaman Aviation: {otp}. It is valid for 2 minutes. Do not share it with anyone.")

        return JsonResponse({
            "message": "OTP sent. Please verify to continue.",
            "customer_id": customer.id,
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

        else:
            return JsonResponse({"error": "User is already fully verified."}, status=400)

        # Clear otp_send_type after verification
        customer.otp_send_type = None
        update_fields.append('otp_send_type')

        customer.save(update_fields=update_fields)

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

        otp = generate_otp()
        otp_sent = False
        otp_send_type = None
        if not customer.mobile_no and mobile_no:
            if CustomerRegister.objects.filter(mobile_no=mobile_no).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Mobile number already in use."}, status=400)
            customer.mobile_no = mobile_no
            send_otp_sms([mobile_no], f"Hi, This is your OTP for profile verification on Pavaman Aviation: {otp}. Valid for 2 minutes.")
            otp_sent = True
            otp_send_type = 'Mobile'
        if not customer.email and email:
            if CustomerRegister.objects.filter(email=email).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Email already in use."}, status=400)
            customer.email = email
            send_otp_email(email, first_name or customer.first_name, otp)
            otp_sent = True
            otp_send_type = 'Email'
        if first_name:
            customer.first_name = first_name
        if last_name:
            customer.last_name = last_name

        if not otp_sent:
            return JsonResponse({"error": "No new field to verify (mobile/email) or already provided."}, status=400)

        customer.otp = otp
        customer.save(update_fields=['otp_send_type','mobile_no','email','first_name', 'last_name', 'otp'])

        return JsonResponse({
            "message": "OTP sent. Please verify to complete your profile.",
            "customer_id": customer.id
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

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
