from multiprocessing.connection import Client
import os
import json
import time
from urllib import response
import uuid
import random
import pytz
import mimetypes
import requests

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404

import boto3

from .models import CustomerRegister, KYCDetails, CustomerMoreDetails, NomineeDetails
from .sms_utils import send_otp_sms
from .idfy_verification import (
    send_pan_verification_request,
    get_pan_verification_result,
    verify_aadhar_sync,
    verify_bank_account_sync
)


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
         # Final unified logic: If fully verified, treat as login
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
        response_data = {
            "message": "OTP verified successfully.",
            "customer_id": customer.id,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
        }
        # return JsonResponse({
        #     "message": "OTP verified successfully.",
        #     "customer_id": customer.id,
        #     "email": customer.email,
        #     "mobile_no": customer.mobile_no,
        #     "first_name": customer.first_name,
        #     "last_name": customer.last_name,
        #     "register_status": customer.register_status,
        #     "account_status": customer.account_status,
        # }, status=200)
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

            request.session['customer_id'] = customer.id  # Set session
            request.session.modified = True
            request.session.save()

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
import json

@csrf_exempt
def customer_profile_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        
        data = json.loads(request.body)
        customer_id = data.get('customer_id')

        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
        # if not session_customer_id:
            return JsonResponse({"error": "Unauthorized: Login required."}, status=403)

        customer = CustomerRegister.objects.filter(id=session_customer_id).first()
        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)

        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        action = str(data.get('action', 'view')).lower()

        if action == 'save_kyc_accept_status' and str(data.get('kyc_accept_status')) == '1':
            customer.kyc_accept_status = 1
            customer.save(update_fields=['kyc_accept_status'])

        if action == 'save_payment_accept_status' and str(data.get('payment_accept_status')) == '1':
            customer.payment_accept_status = 1
            customer.save(update_fields=['payment_accept_status'])

        return JsonResponse({
            "customer_id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
            "kyc_accept_status": customer.kyc_accept_status,
            "payment_accept_status":customer.payment_accept_status
        }, status=200)

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
    

# @csrf_exempt
# def customer_more_details(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)
    
#     try:
#         # customer_id = request.session.get('customer_id')
#         # if not customer_id:
#         #     return JsonResponse({"error": "No customer in session."}, status=401)

        
#         data = json.loads(request.body)
#         customer_id = data.get('customer_id')

#         session_customer_id = request.session.get('customer_id')
#         if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
#         # if not customer_id or not session_customer_id or customer_id != session_customer_id:
#             return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
#         customer = CustomerRegister.objects.filter(id=customer_id).first()
#         if not customer:
#             return JsonResponse({"error": "Customer not found."}, status=404)
#         more = CustomerMoreDetails.objects.filter(customer=customer).first()

#         if more and more.personal_status == 1:
#             return JsonResponse({"error": "Personal details already submitted. Please proceed to next step."}, status=400)

#         mobile_no = data.get('mobile_no')
#         email = data.get('email')
#         dob_str = data.get('dob')
#         gender = data.get('gender')
#         address = data.get('address') #keep flat no,street,area,landmark
#         pincode = data.get('pincode')
#         # mandal = data.get('mandal', '')
#         designation = data.get('designation')
#         profession = data.get('profession')

#         if not (mobile_no and email):
#             return JsonResponse({"error": "Mobile no, and email are required."}, status=400)

#         dob = datetime.strptime(dob_str, "%Y-%m-%d").date() if dob_str else None
#         # more = CustomerMoreDetails.objects.filter(customer=customer).first()

#         # if more and more.personal_status == 1:
#         #     return JsonResponse({"error": "Personal details already submitted. Please proceed to next step."}, status=400)

#         # Get location details
#         location = get_location_by_pincode(pincode)

#         if not more:
#             more = CustomerMoreDetails.objects.create(
#                 customer=customer,
#                 dob=dob,
#                 gender=gender,
#                 address=address,
#                 pincode=pincode,
#                 designation=designation,
#                 profession=profession,
#                 district = location.get("district", ""),
#                 state = location.get("state", ""),
#                 country = location.get("country", ""),
#                 city = location.get("city", ""),
#                 mandal = location.get("block", ""),
#                 personal_status=1
#             )

#         customer_details = {
#             "customer_id": customer.id,
#             "first_name": customer.first_name,
#             "last_name": customer.last_name,
#             "email": customer.email,
#             "mobile_no": customer.mobile_no,
#             "register_status": customer.register_status,
#             "account_status": customer.account_status,
#             "dob": more.dob,
#             "gender": more.gender,
#             "address": more.address,
#             "pincode": more.pincode,
#             "designation": more.designation,
#             "profession": more.profession,
#             "district": location.get("district"),
#             "state": location.get("state"),
#             "country": location.get("country"),
#             "city": location.get("city"),
#             "mandal": more.mandal,
#             "personal_status": more.personal_status,
#         }

#         return JsonResponse({
#             "message": "Customer details updated successfully.",
#             "customer_details": customer_details,
#         }, status=200)

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
@csrf_exempt
def customer_more_details(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        session_customer_id = request.session.get('customer_id')

        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        customer = CustomerRegister.objects.filter(id=customer_id).first()
        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)

        more = CustomerMoreDetails.objects.filter(customer=customer).first()

        # If personal details already submitted, return limited info with view_only action
        if more and more.personal_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Personal details already submitted. Please proceed for next.",
                "customer_readonly_info": {
                    "customer_id": customer.id,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "personal_status":more.personal_status
                }
            }, status=200)

        # If personal_status != 1 (0 or new), allow data entry and save
        mobile_no = data.get('mobile_no')
        email = data.get('email')
        dob_str = data.get('dob')
        gender = data.get('gender')
        address = data.get('address')
        pincode = data.get('pincode')
        designation = data.get('designation')
        profession = data.get('profession')

        if not (mobile_no and email):
            return JsonResponse({"error": "Mobile number and email are required."}, status=400)

        dob = datetime.strptime(dob_str, "%Y-%m-%d").date() if dob_str else None
        location = get_location_by_pincode(pincode)

        if not more:
            more = CustomerMoreDetails.objects.create(
                customer=customer,
                dob=dob,
                gender=gender,
                address=address,
                pincode=pincode,
                designation=designation,
                profession=profession,
                district=location.get("district", ""),
                state=location.get("state", ""),
                country=location.get("country", ""),
                city=location.get("city", ""),
                mandal=location.get("block", ""),
                personal_status=1
            )

        customer_details = {
            "customer_id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
            "dob": more.dob,
            "gender": more.gender,
            "address": more.address,
            "pincode": more.pincode,
            "designation": more.designation,
            "profession": more.profession,
            "district": more.district,
            "state": more.state,
            "country": more.country,
            "city": more.city,
            "mandal": more.mandal,
            "personal_status": more.personal_status,
        }

        return JsonResponse({
            "message": "Customer details saved successfully.",
            "action": "add_details",
            "customer_details": customer_details,
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

# @csrf_exempt
# def pan_verification_request_view(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST allowed."}, status=405)
    
#     data = json.loads(request.body)
#     customer_id = data.get('customer_id')

#     session_customer_id = request.session.get('customer_id')
#     if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
#         # if not customer_id or not session_customer_id or customer_id != session_customer_id:
#             return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
#     pan_number = data.get('pan_number')
#     customer_id = data.get('customer_id')

#     if not all([pan_number, customer_id]):
#         return JsonResponse({"error": "Missing required fields"}, status=400)
#     kyc = KYCDetails.objects.filter(customer__id=customer_id).first()
#     # if kyc and kyc.pan_status == 1:
#     #     return JsonResponse({"error": "PAN verification already completed.Please proceed for next"}, status=400)
#     # Already verified
#     if kyc and kyc.pan_status == 1:
#         return JsonResponse({
#             "action": "view_only",
#             "message": "PAN already verified.",
#             "pan_status": kyc.pan_status,
#         }, status=200)
#     if not pan_number:
#             return JsonResponse({"error": "PAN number is required for verification."}, status=400)

#     customer = get_object_or_404(CustomerRegister, id=customer_id)
#     full_name = f"{customer.first_name} {customer.last_name}".strip()
#     more= CustomerMoreDetails.objects.filter(customer=customer).first()
#     dob = more.dob.strftime("%Y-%m-%d") if more and more.dob else None

#     if not dob:
#         return JsonResponse({"error": "DOB is required for PAN verification."}, status=400)
#     task_id = str(uuid.uuid4())
#     response_data = send_pan_verification_request(pan_number,full_name,dob, task_id)

#     if 'request_id' in response:
#         kyc, _ = KYCDetails.objects.update_or_create(
#             customer=customer,
#             defaults={
#                 "pan_number": pan_number,
#                 "pan_request_id": response["request_id"],
#                 "pan_group_id": settings.IDFY_TEST_GROUP_ID,
#                 "pan_task_id": task_id,
#                 "pan_status": 1  # Request initiated
#             }
#         )

#         return JsonResponse({
#             "action": "verify",
#             "message": "PAN verification initiated.",
#             "request_id": response_data["request_id"],
#             "task_id": task_id,
#             "pan_status": kyc.pan_status,
#             "raw_response": response_data
#         })

#     return JsonResponse({"error": response}, status=500)
@csrf_exempt
def pan_verification_request_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        pan_number = data.get('pan_number')

        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        if not customer_id:
            return JsonResponse({"error": "Customer ID is required."}, status=400)

        customer = get_object_or_404(CustomerRegister, id=customer_id)
        kyc = KYCDetails.objects.filter(customer=customer).first()

        #Already verified
        if kyc and kyc.pan_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "PAN already verified.",
            }, status=200)

        #For new or pending verification, ensure pan_number is provided
        if not pan_number:
            return JsonResponse({"error": "PAN number is required for verification."}, status=400)

        more = CustomerMoreDetails.objects.filter(customer=customer).first()
        dob = more.dob.strftime("%Y-%m-%d") if more and more.dob else None
        if not dob:
            return JsonResponse({"error": "DOB is required for PAN verification."}, status=400)

        full_name = f"{customer.first_name} {customer.last_name}".strip()
        task_id = str(uuid.uuid4())
        response_data = send_pan_verification_request(pan_number, full_name, dob, task_id)

        if 'request_id' in response_data:
            kyc, _ = KYCDetails.objects.update_or_create(
                customer=customer,
                defaults={
                    "pan_number": pan_number,
                    "pan_request_id": response_data["request_id"],
                    "pan_group_id": settings.IDFY_TEST_GROUP_ID,
                    "pan_task_id": task_id,
                    "pan_status": 1  # PAN verified
                }
            )

            return JsonResponse({
                "action": "verify",
                "message": "PAN verification initiated.",
                "request_id": response_data["request_id"],
                "task_id": task_id,
                "pan_status": kyc.pan_status,
                "raw_response": response_data
            }, status=200)

        return JsonResponse({"error": response_data}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

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
            output = result.get("result", {}).get("source_output", {})
            
            # Update KYC fields properly
            kyc.idfy_pan_status = result.get("status")  # e.g. "id_found"
            kyc.pan_status = 1 if result.get("status") == "completed" else 0  # 1: Verified, 2: Rejected
            # kyc.pan_name = output.get("input_details", {}).get("input_name")
            # kyc.pan_dob = output.get("input_details", {}).get("input_dob")
            kyc.save()

        pan_status = kyc.pan_status
    except KYCDetails.DoesNotExist:
        return JsonResponse({"error": "KYC entry not found for this request_id"}, status=404)

    # Return enriched response
    result["pan_status"] = pan_status
    result["message"] = "PAN verification completed successfully."
    return JsonResponse(result, safe=False)
# @csrf_exempt
# def aadhar_lite_verification_view(request):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
#     try:
#         data = json.loads(request.body)
#         customer_id = data.get('customer_id')

#         session_customer_id = request.session.get('customer_id')
#         if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
#             # if not customer_id or not session_customer_id or customer_id != session_customer_id:
#                 return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
#         aadhar_number = data.get("aadhar_number")
#         customer_id = data.get("customer_id")

#         if not aadhar_number or not customer_id:
#             return JsonResponse({'error': 'aadhar_number and customer_id required'}, status=400)
        
#         kyc= KYCDetails.objects.filter(customer_id=customer_id).first()
#         if kyc and kyc.aadhar_status == 1:
#             return JsonResponse({"error": "Aadhaar details already submitted. Please proceed to next step."}, status=400)
#         # Step 1: Call IDfy for verification
#         task_id = str(uuid.uuid4())
#         result = verify_aadhar_sync(aadhar_number, task_id)

#         # Step 2: Extract aadhar status
#         idfy_aadhar_status = result.get("status", None)
#         aadhar_status = 1 if idfy_aadhar_status == "completed" else 0
#         # idfy_aadhar_status = result.get("result", {}).get("source_output", {}).get("status", None)

#         # idfy_aadhar_status = result.get("result", {}).get("output", {}).get("status") or "unknown"
#         # idfy_aadhar_status = result.get("result", {}).get("output", {}).get("status", None)

#         # Step 3: Save to DB
#         customer = get_object_or_404(CustomerRegister, id=customer_id)
#         KYCDetails.objects.update_or_create(
#             customer=customer,
#             defaults={
#                 "aadhar_number": aadhar_number,
#                 "aadhar_status":aadhar_status,
#                 "idfy_aadhar_status": idfy_aadhar_status,  # You should have this field in your model
#                 "aadhar_task_id": task_id
#             }
#         )
#         # Step 4: Return custom response instead of full result
#         return JsonResponse({
#             "message": "Aadhaar verification completed successfully.",
#             "aadhar_status": aadhar_status,
#             "idfy_aadhar_status": idfy_aadhar_status,
#             "task_id": task_id,
#             "result": result
#         })
#         # return JsonResponse(result, safe=False)
    
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def aadhar_lite_verification_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        aadhar_number = data.get('aadhar_number')

        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        if not customer_id:
            return JsonResponse({'error': 'customer_id is required'}, status=400)

        customer = get_object_or_404(CustomerRegister, id=customer_id)
        kyc = KYCDetails.objects.filter(customer=customer).first()

        # Case: Aadhaar already verified
        if kyc and kyc.aadhar_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Aadhaar already verified.",
                "idfy_aadhar_status": kyc.idfy_aadhar_status,
                "aadhar_status": kyc.aadhar_status,
            }, status=200)

        if not aadhar_number:
            return JsonResponse({'error': 'aadhar_number is required for verification'}, status=400)

        task_id = str(uuid.uuid4())
        result = verify_aadhar_sync(aadhar_number, task_id)

        idfy_aadhar_status = result.get("status", None)
        aadhar_status = 1 if idfy_aadhar_status == "completed" else 0

        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "aadhar_number": aadhar_number,
                "aadhar_status": aadhar_status,
                "idfy_aadhar_status": idfy_aadhar_status,
                "aadhar_task_id": task_id
            }
        )
        return JsonResponse({
            "action": "verify",
            "message": "Aadhaar verification completed successfully.",
            "aadhar_status": aadhar_status,
            "idfy_aadhar_status": idfy_aadhar_status,
            "task_id": task_id,
            "result": result
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# @csrf_exempt
# def bank_account_verification_view(request):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Only POST allowed'}, status=405)

#     try:
#         data = json.loads(request.body)
#         customer_id = data.get('customer_id')

#         session_customer_id = request.session.get('customer_id')
#         if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
#             # if not customer_id or not session_customer_id or customer_id != session_customer_id:
#                 return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
#         account_number = data.get("account_number")
#         ifsc = data.get("ifsc")
#         customer_id = data.get("customer_id")

#         if not account_number or not ifsc or not customer_id:
#             return JsonResponse({'error': 'account_number, ifsc, and customer_id required'}, status=400)

#         # Call IDfy sync verification
#         task_id, result = verify_bank_account_sync(account_number, ifsc)

#         # Extract verification result
#         idfy_bank_status = result.get("status", "")
#         source_output = result.get("result", {}).get("source_output", {})
#         verified = source_output.get("verified", False)
#         bank_name = source_output.get("bank_name") or source_output.get("account_holder_name", "")

#         # Determine status: 1 = verified, 2 = failed, 0 = pending
#         bank_status = 1 if idfy_bank_status == "completed" else 0
#         kyc= KYCDetails.objects.filter(customer_id=customer_id).first()
#         if not kyc:
#             return JsonResponse({"error": "KYC details not found for the customer."}, status=404)
#         if kyc.bank_status == 1:
#             return JsonResponse({"error": "Bank details already submitted. Please proceed to next step."}, status=400)

#         # Update or create KYC details
#         customer = get_object_or_404(CustomerRegister, id=customer_id)
#         KYCDetails.objects.update_or_create(
#             customer=customer,
#             defaults={
#                 "banck_account_number": account_number,
#                 "ifsc_code": ifsc,
#                 "bank_name": bank_name,
#                 "bank_task_id": task_id,
#                 "idfy_bank_status": idfy_bank_status,
#                 "bank_status": bank_status
#             }
#         )
#         return JsonResponse({
#             "message": "Bank verification completed",
#             "verified": verified,
#             "bank_status": bank_status,
#             "idfy_bank_status": idfy_bank_status,
#             "task_id": task_id,
#             "raw_response": result
#         })

#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def bank_account_verification_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        account_number = data.get("account_number")
        ifsc = data.get("ifsc")

        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        if not customer_id:
            return JsonResponse({'error': 'customer_id is required'}, status=400)

        customer = get_object_or_404(CustomerRegister, id=customer_id)
        kyc = KYCDetails.objects.filter(customer=customer).first()

        # Action: view_only
        if kyc and kyc.bank_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Bank account already verified.Please proceed for next.",
                "bank_status": kyc.bank_status,
                "idfy_bank_status": kyc.idfy_bank_status
            }, status=200)

        #Action: verify
        if not account_number or not ifsc:
            return JsonResponse({'error': 'account_number and ifsc are required for verification'}, status=400)

        task_id, result = verify_bank_account_sync(account_number, ifsc)
        idfy_bank_status = result.get("status", "")
        source_output = result.get("result", {}).get("source_output", {})
        verified = source_output.get("verified", False)
        bank_name = source_output.get("bank_name") or source_output.get("account_holder_name", "")

        # bank_status = 1 if idfy_bank_status == "completed" and verified else 2 if not verified else 0
        bank_status = 1 if idfy_bank_status == "completed" and verified else 0
        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "banck_account_number": account_number,
                "ifsc_code": ifsc,
                "bank_name": bank_name,
                "bank_task_id": task_id,
                "idfy_bank_status": idfy_bank_status,
                "bank_status": bank_status
            }
        )

        return JsonResponse({
            "action": "verify",
            "message": "Bank verification completed.",
            "verified": verified,
            "bank_status": bank_status,
            "idfy_bank_status": idfy_bank_status,
            "task_id": task_id,
            "raw_response": result
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def upload_pdf_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    # data = json.loads(request.body)
    customer_id = request.POST.get('customer_id')

    session_customer_id = request.session.get('customer_id')
    if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
        # if not customer_id or not session_customer_id or customer_id != session_customer_id:
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
    
    doc_type = request.POST.get('doc_type')  # 'aadhar' or 'pan'
    file = request.FILES.get('kyc_file')

    if not all([customer_id, doc_type, file]):
        return JsonResponse({'error': 'Customer ID, doc_type, and file required'}, status=400)

    if doc_type not in ['aadhar', 'pan', 'selfie', 'signature']:
        return JsonResponse({'error': "doc_type must be 'aadhar', 'pan', 'selfie', or 'signature'"}, status=400)

    file_name = file.name
    mime_type, _ = mimetypes.guess_type(file_name)
    
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']
    
    file_ext = os.path.splitext(file_name)[1]
    if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
        return JsonResponse({'error': 'Only PDF or image files (JPG, PNG) are allowed.'}, status=400)

    customer = get_object_or_404(CustomerRegister, id=customer_id)
    kyc, _ = KYCDetails.objects.get_or_create(customer=customer)
    more,_=CustomerMoreDetails.objects.get_or_create(customer=customer)
    customer_name = f"{customer.first_name}_{customer.last_name}".replace(" ", "_").lower()
    customer_folder = f"{customer_id}_{customer_name}".lower()
    s3_filename = f"{customer_folder}/{doc_type}_{customer_name}{file_ext}"  # e.g., 1234_kapil_dev/aadhar.pdf or pan.jpg

    try:
        s3_url = upload_file_to_s3(file, s3_filename)
       
        if doc_type == 'aadhar':
            kyc.aadhar_path = s3_filename
        elif doc_type == 'pan':
            kyc.pan_path = s3_filename
        elif doc_type == 'selfie':
            more.selfie_path = s3_filename
        elif doc_type == 'signature':
            more.signature_path = s3_filename

        kyc.save()
        return JsonResponse({
            "status": "success",
            "message": f"{doc_type.capitalize()} document uploaded successfully.",
            "file_url": s3_url
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def upload_file_to_s3(file_obj, s3_key):
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )

    s3.upload_fileobj(
        file_obj,
        settings.AWS_STORAGE_BUCKET_NAME,
        s3_key,
        ExtraArgs={
            'ContentType': file_obj.content_type,
        }
    )
    return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

@csrf_exempt
def nominee_details(request):
    if request.method == "POST":
        try:            
            # data = json.loads(request.body)
            customer_id = request.POST.get('customer_id')

            session_customer_id = request.session.get('customer_id')
            if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
                    return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)
    
            # customer_id = request.session.get('customer_id')  # Use session
            # if not customer_id:
            #     return JsonResponse({"error": "Customer not logged in."}, status=401)

            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            relation = request.POST.get('relation')
            dob_str = request.POST.get('dob')
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date() if dob_str else None
            address_proof = request.POST.get('address_proof')
            # id_proof = request.POST.get('id_proof')

            address_proof_file = request.FILES.get('address_proof_file')
            id_proof_file = request.FILES.get('id_proof_file')

            if not all([customer_id, first_name, last_name, relation, dob, address_proof]):
                return JsonResponse({"error": "All fields are required."}, status=400)
            # Allowed formats
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']

            customer = get_object_or_404(CustomerRegister, id=customer_id)
            mobile_no=customer.mobile_no
            nominee_name = f"{first_name}_{last_name}".replace(" ", "_")
            customer_name = f"{customer.first_name}_{customer.last_name}".replace(" ", "_").lower()
            folder_name = f"{customer.id}_{customer_name}"
             # Upload address proof
            if address_proof_file:
                file_name = address_proof_file.name
                file_root, file_ext = os.path.splitext(file_name)
                file_ext = file_ext.lower()
                mime_type, _ = mimetypes.guess_type(file_name)

                if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
                    return JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed for address proof.'}, status=400)

                s3_key = f"{folder_name}/nominee_address_proof_{nominee_name}{file_ext}"
                address_proof_path_s3_url= upload_file_to_s3(address_proof_file, s3_key)
                address_proof_path=s3_key

            # Upload ID proof
            if id_proof_file:
                file_name = id_proof_file.name
                file_root, file_ext = os.path.splitext(file_name)
                file_ext = file_ext.lower()
                mime_type, _ = mimetypes.guess_type(file_name)

                if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
                    return JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed for ID proof.'}, status=400)

                s3_key = f"{folder_name}/nominee_id_proof_{nominee_name}{file_ext}"
                id_proof_path_s3_url=upload_file_to_s3(id_proof_file, s3_key)
                id_proof_path = s3_key

            nominee, created = NomineeDetails.objects.update_or_create(
                customer=customer,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "relation": relation,
                    "dob": dob,
                    "address_proof": address_proof,
                    "address_proof_path": address_proof_path,
                    "id_proof_path": id_proof_path
                }
            )
            #Send SMS inside this function
            try:
                message = f"Dear {customer.first_name}, your nominee {first_name} {last_name} has been successfully registered."
                # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                send_otp_sms(mobile_no,message)
                # print(f"SMS sent: {sms.sid}")
            except Exception as sms_err:
                print("SMS sending failed:", sms_err)

            #Send Email using helper
            # send_nominee_email(customer, f"{first_name} {last_name}", relation)
            send_nominee_email(customer, nominee_name, relation)
            return JsonResponse({
                "message": "Nominee details saved successfully.",
                "nominee_id": nominee.id,
                "first_name": nominee.first_name,
                "last_name": nominee.last_name,
                "relation": nominee.relation,
                "dob": nominee.dob.strftime("%Y-%m-%d") if nominee.dob else None,
                "address_proof": nominee.address_proof,
                "address_proof_path": address_proof_path_s3_url,
                # "id_proof": nominee.id_proof,
                "id_proof_path": id_proof_path_s3_url,
            }, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON."}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
# def send_otp_sms(customer, nominee_name):
#     try:
#         message = f"Dear {customer.first_name}, your nominee {nominee_name} has been successfully registered."
#         mobile_nos = [customer.mobile_no]  # Ensure it's in list form
#         send_otp_sms(mobile_nos, message)
#         return True
#     except Exception as e:
#         print("SMS sending failed:", e)
#         return False

def send_nominee_email(customer, nominee_name, relation):
    try:
        subject = "Nominee Registered Successfully"
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = [customer.email]

        logo_url = f"{settings.AWS_S3_BUCKET_URL}/static/images/aviation-logo.png"
        text_content = f"""
    Hello {customer.first_name},
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
            <img src="{logo_url}" alt="pavaman logo" class="logo" style="max-width: 280px; height: auto; margin-bottom: 20px;" />
            <h2 style="margin-top: 0; color: #222;">Nominee Registration Successful</h2>
        </div>
        <div style="margin-bottom: 10px; color: #555; font-size: 14px;">
            Hello {customer.first_name},
        </div>

        <p style="color: #555; margin-bottom: 20px;">
            Your nominee <strong>{nominee_name}</strong> (<em>{relation}</em>) has been successfully registered.
        </p>

        <p style="color: #888; font-size: 14px;">
            If you did not perform this action, you can safely ignore this email.<br/>
            You're receiving this because you have an account on Pavaman.
        </p>

        <p style="margin-top: 30px; font-size: 14px; color: #888;">Disclaimer: This is an automated email. Please do not reply.</p>
    </div>
</body>
</html>
"""

        email_message = EmailMultiAlternatives(subject, text_content, from_email, to_email)
        email_message.attach_alternative(html_content, "text/html")
        email_message.send()
        return True

    except Exception as e:
        print("Email sending failed:", e)
        return False
