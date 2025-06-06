import random
import json
import pytz
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db import IntegrityError
from django.utils import timezone
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
        token = data.get('google_token')
        email = data.get('email')
        mobile_no = data.get('mobile_no')

        if not any([token, email, mobile_no]):
            return JsonResponse({"error": "Provide Google mail or email or mobile number."}, status=400)

        # admin = PavamanAdminDetails.objects.order_by('id').first()
        # if not admin:
        #     return JsonResponse({"error": "Admin not configured."}, status=500)

        if token:
            google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            response = requests.get(google_url)
            if response.status_code != 200:
                return JsonResponse({"error": "Google token invalid."}, status=400)
            google_data = response.json()
            if "error" in google_data or not google_data.get("email"):
                return JsonResponse({"error": "Invalid Google token."}, status=400)
            email = google_data.get("email")
            first_name = google_data.get("given_name", "")
            last_name = google_data.get("family_name", "")
        else:
            first_name = ''
            last_name = ''

        # Check if user exists by email or mobile
        customer = None
        if email:
            customer = CustomerRegister.objects.filter(email=email).first()
        if not customer and mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

        otp = generate_otp()

        if customer:
            if customer.account_status == 1:
                return JsonResponse({
                    "message": "Account already verified. Please login.",
                    "customer_id": customer.id,
                    "email": customer.email,
                    "mobile_no": customer.mobile_no,
                }, status=200)

            # resend OTP if not verified
            customer.otp = otp
            customer.save(update_fields=['otp'])
            # customer.otp_created_at = timezone.now()
            # customer.save(update_fields=['otp', 'otp_created_at'])

        else:
            customer = CustomerRegister.objects.create(
                email=email or '',
                mobile_no=mobile_no or '',
                otp=otp,
                # otp_created_at=timezone.now(),
                # account_status=0,
                register_status=1,
                register_type="Google" if token else "Email" if email else "Mobile",
                
            )

        # Send OTP
        if email:
            send_otp_email(email,first_name, otp)
        if mobile_no:
            # send_otp_sms(mobile_no, otp)
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
        # customer_id = data.get('customer_id')
        otp = str(data.get('otp'))
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        mobile_no = data.get('mobile_no', '')
        email = data.get('email', '')

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        customer = CustomerRegister.objects.filter(
                email=email
            ).first() or CustomerRegister.objects.filter(
                mobile_no=mobile_no
            ).first()
        if not customer:
                return JsonResponse({"error": "User not found with the provided email or mobile number"}, status=404)
        if not customer.otp:
                return JsonResponse({"error": "OTP has expired or is missing"}, status=400)

        # Google account already verified
        if customer.register_type == "Google" and customer.account_status == 1:
            if not customer.mobile_no and mobile_no:
                customer.mobile_no = mobile_no
                customer.save(update_fields=['mobile_no'])
            
            return JsonResponse({
                "message": "Google account already verified.",
                "customer_id": customer.id,
                "email": customer.email,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "mobile_no": customer.mobile_no,
                "require_mobile": not bool(customer.mobile_no)
            }, status=200)

        if str(customer.otp) != otp:
            return JsonResponse({"error": "Invalid OTP."}, status=400)
        
        # customer.clear_expired_otp()
        # if not customer.otp or str(customer.otp) != str(otp):
        #         return JsonResponse({"error": "Invalid OTP or OTP has expired"}, status=400)
           
        # Mark account as verified
        customer.account_status = 1
        if first_name:
            customer.first_name = first_name
        if last_name:
            customer.last_name = last_name
        if mobile_no:
            customer.mobile_no = mobile_no
        customer.otp = None  # Optional: clear OTP after use
        customer.save(update_fields=['account_status', 'first_name', 'last_name', 'mobile_no', 'otp'])
        
        
        return JsonResponse({
            "message": "OTP verified successfully. Account is now active.",
            "customer_id": customer.id,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

def send_otp_email(email, first_name, otp):
    subject = "[Pavaman] Please Verify Your Email"

    # frontend_url =  settings.FRONTEND_URL
    # full_link = f"{frontend_url}/verify-email/{verification_link}"
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

def send_email_verification_otp_email(customer):
    otp = customer.otp
    email = customer.email
    first_name = customer.first_name or 'Customer'
    logo_url = f"{settings.AWS_S3_BUCKET_URL}/static/images/aviation-logo.png"
    subject = "[Pavaman] OTP to Verify Your Email"
    text_content = f"Hello {first_name},\n\nYour OTP for verifying your email is: {otp}"
    
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
                .otp {{
                    font-size: 24px !important;
                    padding: 10px 20px !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Inter', sans-serif; background-color: #f5f5f5;">
        <div class="container" style="margin: 40px auto; background-color: #ffffff; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); padding: 40px 30px; max-width: 480px; text-align: left;">
            <div style="text-align: center;">
            <img src="{logo_url}" alt="Pavaman Logo" class="logo" style="max-width: 280px; height: auto; margin-bottom: 20px;" />
            <h2 style="margin-top: 0; color: #222;">Verify Your Email</h2>
            </div>

            <p style="color: #555; margin-bottom: 30px; text-align: left;">
            Hello <strong>{first_name}</strong>,
            </p>

            <p style="color: #555; margin-bottom: 30px;">
                Use the OTP below to verify your email.
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
