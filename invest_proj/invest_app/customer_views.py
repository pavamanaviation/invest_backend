from invest_app.utils.shared_imports import *
from .models import Admin, CustomerRegister,PaymentDetails, KYCDetails, CustomerMoreDetails, NomineeDetails, Role
from invest_app.utils.msg91 import send_bulk_sms
from invest_app.utils.idfy_verification import (
   
    verify_aadhar_sync,
    verify_bank_account_sync
)
from .utils.s3_helper import upload_to_s3, generate_presigned_url
from .utils.idfy_verification import check_idfy_status_by_request_id, submit_idfy_aadhar_ocr, submit_idfy_pan_ocr, check_idfy_task_status, submit_idfy_pan_verification


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
        otp = None

        # 🔹 Google Signup Flow
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

        # 🔹 Check for existing customer (optimized with exists())
        exists = False
        if email and CustomerRegister.objects.filter(email=email).exists():
            exists = True
        elif mobile_no and CustomerRegister.objects.filter(mobile_no=mobile_no).exists():
            exists = True

        if exists:
            return JsonResponse({"error": "Customer already registered. Please login."}, status=409)

        # 🔹 Get admin (lightweight query with only())
        admin = Admin.objects.only("id").order_by("id").first()
        if not admin:
            return JsonResponse({"error": "No admin found for assignment."}, status=500)

        # 🔹 Create Customer
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

            # 🔹 Send OTP via email/SMS
            if email:
                send_otp_email(email, first_name or '', otp)
            if mobile_no:
                send_bulk_sms([mobile_no], otp)

        return JsonResponse({
            "message": "Google account registered successfully." if is_google_signup else "OTP sent. Please verify to continue.",
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

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        #Optimize by limiting fields (use .only)
        customer_qs = None
        if email and mobile_no:
            customer_qs = CustomerRegister.objects.filter(email=email, mobile_no=mobile_no).only(
                "id", "email", "mobile_no", "first_name", "last_name", "otp", "account_status", "register_status", "otp_send_type"
            )
        elif email:
            customer_qs = CustomerRegister.objects.filter(email=email).only(
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

        # # Final stage: login after full verification
        # if customer.register_status == 1 and customer.account_status == 1:
        #     request.session['customer_id'] = customer.id
        #     request.session.save()
        #     return JsonResponse({
        #         "message": "OTP verified and login successful.",
        #         "customer_id": customer.id,
        #         "email": customer.email,
        #         "register_status": customer.register_status,
        #         "account_status": customer.account_status,
        #         "session_id": request.session.session_key
        #     }, status=200)

        # Partial verification response
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

        # Limit fields to optimize query
        try:
            customer = CustomerRegister.objects.only(
                "id", "email", "mobile_no", "first_name", "last_name", 
                "otp", "changed_on", "register_status", "account_status", "otp_send_type"
            ).get(id=customer_id)
        except CustomerRegister.DoesNotExist:
            return JsonResponse({"error": "Customer not found."}, status=404)

        if customer.register_status != 1:
            return JsonResponse({"error": "First phase registration incomplete."}, status=400)

        # Prevent redundant OTP phase
        if customer.mobile_no and not customer.email and not email:
            return JsonResponse({"error": "Mobile already verified. Provide email to continue."}, status=400)
        if customer.email and not customer.mobile_no and not mobile_no:
            return JsonResponse({"error": "Email already verified. Provide mobile to continue."}, status=400)

        customer.clear_expired_otp()

        # Generate OTP
        otp = generate_otp()
        otp_sent = False
        otp_send_type = None
        update_fields = []

        # Handle new mobile number
        if not customer.mobile_no and mobile_no:
            if CustomerRegister.objects.filter(mobile_no=mobile_no).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Mobile number already in use."}, status=400)

            customer.mobile_no = mobile_no
            otp_send_type = 'Mobile'
            send_bulk_sms([mobile_no], otp)
            otp_sent = True
            update_fields.append('mobile_no')

        # Handle new email
        elif not customer.email and email:
            if CustomerRegister.objects.filter(email=email).exclude(id=customer.id).exists():
                return JsonResponse({"error": "Email already in use."}, status=400)

            customer.email = email
            otp_send_type = 'Email'
            send_otp_email(email, first_name or customer.first_name, otp)
            otp_sent = True
            update_fields.append('email')

        # Resend OTP (if applicable)
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
                return JsonResponse({"error": "No email/mobile found for OTP resend."}, status=400)

        # Update optional fields
        if first_name and customer.first_name != first_name:
            customer.first_name = first_name
            update_fields.append('first_name')
        if last_name and customer.last_name != last_name:
            customer.last_name = last_name
            update_fields.append('last_name')

        # Save OTP in both DB & cache (2 mins)
        customer.otp = otp
        customer.otp_send_type = otp_send_type or customer.otp_send_type
        customer.changed_on = timezone.now()
        update_fields.extend(['otp', 'changed_on', 'otp_send_type'])

        customer.save(update_fields=update_fields)

        # Save in cache for fast verify (email or mobile-based key)
        cache_key = f"otp_{email or mobile_no}"
        cache.set(cache_key, otp, timeout=120)  # 2 mins

        return JsonResponse({
            "message": "OTP sent. Please verify to complete your profile.",
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

        # Try Customer
        user = fetch_user_by_email_or_mobile(CustomerRegister, email, mobile_no)
        if user:
            user_type = "customer"
            user_id = user.id
            send_and_store_otp(user, user.first_name or first_name, email, mobile_no)

        else:
            # Try Admin
            user = fetch_user_by_email_or_mobile(Admin, email, mobile_no)
            if user:
                user_type = "admin"
                user_id = user.id
                send_and_store_otp(user, user.name, email, mobile_no)

            else:
                # Try Role
                user = fetch_user_by_email_or_mobile(Role, email, mobile_no)
                if user:
                    user_type = "role"
                    user_id = user.id
                    full_name = f"{user.first_name} {user.last_name}".strip()
                    send_and_store_otp(user, full_name, email, mobile_no)

        # Final Response
        if user:
            return JsonResponse({
                "message": "OTP sent. It is valid for 2 minutes.",
                "user_type": user_type,
                "user_id": user_id,
                "status_code": 200
            }, status=200)

        return JsonResponse({"error": "Account not found or not verified."}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

@csrf_exempt
def customer_profile_view(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        # Load request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        customer_id = data.get('customer_id')
        action = str(data.get('action', 'view')).strip().lower()

        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Login required."}, status=403)

        # Fetch customer efficiently with only needed fields
        customer = CustomerRegister.objects.only(
            "id", "first_name", "last_name", "email", "mobile_no",
            "register_status", "account_status", "kyc_accept_status", "payment_accept_status"
        ).filter(id=session_customer_id).first()

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

        # Response
        return JsonResponse({
            "customer_id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "mobile_no": customer.mobile_no,
            "register_status": customer.register_status,
            "account_status": customer.account_status,
            "kyc_accept_status": customer.kyc_accept_status,
            "payment_accept_status": customer.payment_accept_status,
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

        # Fetch customer using only required fields
        customer = CustomerRegister.objects.only(
            "id", "first_name", "last_name", "email", "mobile_no",
            "register_status", "account_status"
        ).filter(id=customer_id).first()

        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)

        # Check if details already submitted
        more = CustomerMoreDetails.objects.filter(customer=customer).first()

        if more and more.personal_status == 1:
            return JsonResponse({
                "action": "view_only",
                "message": "Personal details already submitted. Please proceed for next.",
                "customer_readonly_info": {
                    "customer_id": customer.id,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "personal_status": more.personal_status
                }
            }, status=200)

        # Allow update if not yet submitted
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

        # Safe date parsing
        dob = parsedate(dob_str) if dob_str else None

        # Get location info
        location = get_location_by_pincode(pincode) or {}

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

# -----------------------------------------



@csrf_exempt
def verify_pan_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    customer_id = request.POST.get('customer_id')
    session_customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Invalid or missing customer ID'}, status=403)

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
        # file_name = pan_file.name
        # mime_type, _ = mimetypes.guess_type(file_name)
        # file_ext = os.path.splitext(file_name)[1].lower()

        # allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        # allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']
        # if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
        #     return JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed.'}, status=400)

        # # Generate file key and related info
        # file_key, customer_name, customer_folder, file_ext = generate_customer_file_key(
        #     pan_file, customer=customer, doc_type='pan', prefix='customerdoc')

        # # Upload to S3
        # upload_to_s3(pan_file, file_key)
        # file_url = generate_presigned_url(file_key, expires_in=300)

        status_code, response_json, task_id = submit_idfy_pan_ocr(file_url)
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


# def get_customer_pan_path(customer_id, first_name, last_name):
#     s3 = boto3.client(
#         's3',
#         aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#         aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#         region_name=settings.AWS_S3_REGION_NAME
#     )

#     bucket_name = settings.AWS_STORAGE_BUCKET_NAME
#     customer_folder = f'customerdoc/{customer_id}_{first_name.lower()}{last_name.lower()}/'

#     response = s3.list_objects_v2(Bucket=bucket_name, Prefix=customer_folder)
#     if 'Contents' not in response:
#         return None

#     for obj in response['Contents']:
#         key = obj['Key']
#         if 'pan_' in key.lower():
#             return key  # Return PAN path
#     return None
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

@csrf_exempt
def get_pan_verification_status(request):
    import traceback

    try:
        request_id = request.GET.get('request_id')
        customer_id = request.GET.get('customer_id')

        if not request_id or not customer_id:
            return JsonResponse({'error': 'Both request_id and customer_id are required'}, status=400)

        # Fetch customer
        customer = CustomerRegister.objects.get(id=customer_id)

        # Get OCR result by request_id
        status_code, result = check_idfy_status_by_request_id(request_id)
        print("🧠 IDfy raw result:", result)

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

        print("🔍 Using extracted PAN data:", pan_number, pan_name, pan_dob)

        # ✅ Submit source verification without file
        verify_status_code, verify_response, verify_task_id, verify_request_id = submit_idfy_pan_verification(
            name=pan_name,
            dob=pan_dob,
            pan_number=pan_number
        )

        print("✅ Submission response:", verify_status_code)
        print("📦 API response body:", verify_response)

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
        print("🔥 Exception occurred during PAN verification submission")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    
@csrf_exempt
def get_pan_source_verification_status(request):
    request_id = request.GET.get("request_id")
    customer_id = request.GET.get("customer_id")

    if not request_id or not customer_id:
        return JsonResponse({'error': 'Missing request_id or customer_id'}, status=400)

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

        source_output = result.get("result", {}).get("source_output", {})
        name_match = source_output.get("name_match")
        dob_match = source_output.get("dob_match")
        pan_status = source_output.get("pan_status")

        if not (name_match and dob_match and pan_status == "Existing and Valid. PAN is Operative"):
            return JsonResponse({
                'status': 'failed',
                'message': 'Source verification mismatch',
                'details': source_output,
                'raw_result': result
            }, status=422)

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

# @csrf_exempt
# def get_pan_verification_status(request):
#     request_id = request.GET.get('request_id')
#     customer_id = request.GET.get('customer_id')

#     if not request_id or not customer_id:
#         return JsonResponse({'error': 'Both request_id and customer_id are required'}, status=400)

#     try:
#         customer = CustomerRegister.objects.get(id=customer_id)
#     except CustomerRegister.DoesNotExist:
#         return JsonResponse({'error': 'Customer not found'}, status=404)

#     try:
#         customer = CustomerRegister.objects.get(id=customer_id)

#         # Fetch pan_path from S3
#         pan_path = get_customer_document_path(customer.id, customer.first_name, customer.last_name,'pan')

#         status_code, result = check_idfy_status_by_request_id(request_id)
#         print("Raw IDfy result:", result)

#         if isinstance(result, list):
#             if not result:
#                 return JsonResponse({'error': 'No result found for this request ID'}, status=404)
#             result = result[0]

#         status = result.get("status")
#         extraction = result.get("result", {}).get("extraction_output", {})

#         if status == "completed":
#             KYCDetails.objects.update_or_create(
#                 customer=customer,
#                 defaults={
#                     "pan_number": extraction.get("id_number"),
#                     "pan_name": extraction.get("name_on_card"),
#                     "pan_dob": extraction.get("date_of_birth"),
#                     "pan_task_id": result.get("task_id", ""),
#                     "pan_group_id": settings.IDFY_GROUP_ID,
#                     "pan_request_id": request_id,
#                     "idfy_pan_status": status,
#                     "pan_status": 1,
#                     "pan_path": pan_path

#                 }
#             )

#             return JsonResponse({
#                 'status': 'completed',
#                 'result': extraction,
#                 'message': 'KYC details updated successfully.'
#             })

#         return JsonResponse({
#             'status': status,
#             'result': extraction,
#             'message': 'PAN verification not yet completed.'
#         })

#     except Exception as e:
#         # import traceback
#         # traceback.print_exc()
#         return JsonResponse({'error': f'Error fetching status: {str(e)}'}, status=500)

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

@csrf_exempt
def verify_aadhar_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    customer_id = request.POST.get('customer_id')
    session_customer_id = request.session.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Invalid or missing customer ID'}, status=403)

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
                # 🧠 Fetch verified PAN details
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

                # Match aadhar with PAN
                if aadhar_name != pan_name or aadhar_dob != pan_dob:
                    return JsonResponse({
                        "status": "failed",
                        "message": "aadhar and PAN details do not match. Please verify your PAN number correctly.",
                        "pan_name": kyc_pan.pan_name,
                        "aadhar_name": aadhar_data.get("name_on_card"),
                        "pan_dob": pan_dob,
                        "aadhar_dob": aadhar_dob
                    }, status=422)

                # ✅ Store aadhar data after match
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
    
@csrf_exempt
def get_aadhar_verification_status(request):
    request_id = request.GET.get('request_id')
    customer_id = request.GET.get('customer_id')

    if not request_id or not customer_id:
        return JsonResponse({'error': 'Both request_id and customer_id are required'}, status=400)

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

        # ✅ Match Aadhaar name/DOB with PAN
        kyc_pan = KYCDetails.objects.filter(customer=customer, pan_status=1).first()
        if not kyc_pan:
            return JsonResponse({
                "status": "failed",
                "message": "PAN verification is required before Aadhaar verification."
            }, status=400)

        pan_name = kyc_pan.pan_name.strip().lower()
        pan_dob = str(kyc_pan.pan_dob)

        if aadhar_name != pan_name or aadhar_dob != pan_dob:
            return JsonResponse({
                "status": "failed",
                "message": "Aadhaar and PAN details do not match.",
                "pan_name": kyc_pan.pan_name,
                "aadhar_name": extraction.get("name_on_card"),
                "pan_dob": pan_dob,
                "aadhar_dob": aadhar_dob
            }, status=422)

        # ✅ Aadhaar name/DOB matched, now verify Aadhaar number
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

        # ✅ Save verified Aadhaar info
        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found"}, status=500)

        KYCDetails.objects.update_or_create(
            customer=customer,
            defaults={
                "aadhar_number": extracted_aadhar_number,
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

# @csrf_exempt
# def get_aadhar_verification_status(request):
#     request_id = request.GET.get('request_id')
#     customer_id = request.GET.get('customer_id')

#     if not request_id or not customer_id:
#         return JsonResponse({'error': 'Both request_id and customer_id are required'}, status=400)

#     try:
#         customer = CustomerRegister.objects.get(id=customer_id)
#     except CustomerRegister.DoesNotExist:
#         return JsonResponse({'error': 'Customer not found'}, status=404)

#     try:
#         # Get aadhar file path from S3
#         aadhar_path = get_customer_document_path(customer.id, customer.first_name, customer.last_name, 'aadhar')

#         # Fetch OCR result from IDfy
#         status_code, result = check_idfy_status_by_request_id(request_id)
#         print("Raw IDfy aadhar result:", result)

#         if isinstance(result, list):
#             if not result:
#                 return JsonResponse({'error': 'No result found for this request ID'}, status=404)
#             result = result[0]

#         status = result.get("status")
#         extraction = result.get("result", {}).get("extraction_output", {})
#         admin = Admin.objects.only("id").first()
#         if not admin:
#             return JsonResponse({"error": "Admin not found."}, status=500)

#         if status == "completed":
#             KYCDetails.objects.update_or_create(
#                 customer=customer,
#                 defaults={
#                     "aadhar_number": extraction.get("id_number"),
#                     "aadhar_name": extraction.get("name_on_card"),
#                     "aadhar_dob": extraction.get("date_of_birth"),
#                     "aadhar_gender": extraction.get("gender"),
#                     "aadhar_status": 1,  # mark verified
#                     "aadhar_request_id": request_id,
#                     "idfy_aadhar_status": status,
#                     "aadhar_task_id": result.get("task_id", ""),
#                     "aadhar_path": aadhar_path,
#                     "admin": admin,
#                 }
#             )

#             return JsonResponse({
#                 'status': 'completed',
#                 'result': extraction,
#                 'message': 'aadhar KYC details updated successfully.'
#             })

#         return JsonResponse({
#             'status': status,
#             'result': extraction,
#             'message': 'aadhar verification not yet completed.'
#         })

#     except Exception as e:
#         return JsonResponse({'error': f'Error fetching status: {str(e)}'}, status=500)


# ----------------------------------------
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
        bank_status = 1 if idfy_bank_status == "completed" else 0
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

    customer_id = None
    doc_type = None
    file = None

    # 1. Handle JSON status-check requests (no file required)
    if request.content_type.startswith('application/json'):
        try:
            data = json.loads(request.body)
            customer_id = data.get('customer_id')
            doc_type = data.get('doc_type')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        # Session validation
        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        if not customer_id or not doc_type:
            return JsonResponse({'error': 'Customer ID, doc_type required'}, status=400)

        if doc_type not in ['selfie', 'signature']:
            return JsonResponse({'error': "Status check only supported for 'selfie' or 'signature'"}, status=400)

        # View-only status check
        customer = get_object_or_404(CustomerRegister, id=customer_id)
        more, _ = CustomerMoreDetails.objects.get_or_create(customer=customer)

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

    else:
        customer_id = request.POST.get('customer_id')
        doc_type = request.POST.get('doc_type')
        file = request.FILES.get('kyc_file')

        # Session validation
        session_customer_id = request.session.get('customer_id')
        if not customer_id or not session_customer_id or int(customer_id) != int(session_customer_id):
            return JsonResponse({"error": "Unauthorized: Customer ID mismatch."}, status=403)

        if not customer_id or not doc_type or not file:
            return JsonResponse({'error': 'Customer ID, doc_type, and file are required.'}, status=400)

        if doc_type not in ['aadhar', 'pan', 'selfie', 'signature']:
            return JsonResponse({'error': "Invalid doc_type."}, status=400)

        customer = get_object_or_404(CustomerRegister, id=customer_id)
        kyc, _ = KYCDetails.objects.get_or_create(customer=customer)
        more, _ = CustomerMoreDetails.objects.get_or_create(customer=customer)

        file_name = file.name
        mime_type, _ = mimetypes.guess_type(file_name)
        file_ext = os.path.splitext(file_name)[1].lower()

        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        allowed_mime_types = ['application/pdf', 'image/jpeg', 'image/png']

        if file_ext not in allowed_extensions or mime_type not in allowed_mime_types:
            return JsonResponse({'error': 'Only PDF, JPG, JPEG, PNG files are allowed.'}, status=400)

        customer_name = f"{customer.first_name}{customer.last_name}".replace(" ", "").lower()
        customer_folder = f"{customer.id}_{customer_name}"
        s3_filename = f"{customer_folder}/{doc_type}_{customer_name}{file_ext}"

        try:
            s3_url = upload_file_to_s3(file, s3_filename)

            if doc_type == 'aadhar':
                kyc.aadhar_path = s3_filename
            elif doc_type == 'pan':
                kyc.pan_path = s3_filename
            elif doc_type == 'selfie':
                more.selfie_path = s3_filename
                more.selfie_status = 1
            elif doc_type == 'signature':
                more.signature_path = s3_filename
                more.signature_status = 1

            kyc.save()
            more.save()

            return JsonResponse({
                "status": "success",
                "message": f"{doc_type.capitalize()} uploaded successfully.",
                "file_url": s3_url,
                "selfie_status": more.selfie_status,
                "signature_status": more.signature_status
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        
# -------------------------------------------------------
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


@csrf_exempt
def initiate_nominee_registration(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=405)
    try:
        data, files = request.POST, request.FILES
        customer_id = data.get("customer_id")
        mode = data.get("mode", "create").lower()
        session_customer_id = request.session.get("customer_id")

        # if not customer_id or int(customer_id) != int(session_customer_id):
        #     return JsonResponse({"error": "Customer ID mismatch."}, status=403)

        if mode == "edit":
            required_fields = ["nominee_id", "first_name", "last_name", "relation"]
            file_upload_required = False
        else:
            required_fields = ["first_name", "last_name", "relation", "dob", "address_proof", "share"]
            file_fields = ["address_proof_file", "id_proof_file"]
            file_upload_required = True

        missing_fields = [f for f in required_fields if not data.get(f)]
        missing_files = [f for f in file_fields if f not in files] if file_upload_required else []

        if missing_fields or missing_files:
            return JsonResponse({"error": f"{', '.join(missing_fields + missing_files)} is required for {mode}."}, status=400)

        nominee_data = {k: data[k] for k in required_fields}
        cache_key_prefix = f"{mode}_nominee_{customer_id}"
        cache.set(f"{cache_key_prefix}_data", nominee_data, timeout=600)

        if file_upload_required:
            address_file = files["address_proof_file"]
            id_file = files["id_proof_file"]

            addr_ext = os.path.splitext(address_file.name)[1].lower()
            id_ext = os.path.splitext(id_file.name)[1].lower()

            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.svg']
            if addr_ext not in allowed_extensions or id_ext not in allowed_extensions:
                return JsonResponse({'error': 'Invalid file extension for uploaded files.'}, status=400)

            cache.set(f"{cache_key_prefix}_addr_ext", addr_ext, timeout=600)
            cache.set(f"{cache_key_prefix}_id_ext", id_ext, timeout=600)

            cache.set(f"{cache_key_prefix}_files", {
                "address_proof_file": address_file.read(),
                "id_proof_file": id_file.read()
            }, timeout=600)

        customer = CustomerRegister.objects.only("id", "mobile_no").get(id=customer_id)
        otp = generate_otp()
        customer.otp = otp
        customer.changed_on = timezone_now()
        customer.save(update_fields=["otp", "changed_on"])

        send_bulk_sms([str(customer.mobile_no)], otp)

        return JsonResponse({"message": f"OTP sent to registered mobile for nominee {mode}."})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@csrf_exempt
def verify_and_update_nominee(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=405)

    try:
        data = request.POST
        otp = data.get("otp")
        customer_id = data.get("customer_id")
        mode = "edit"

        session_customer_id = request.session.get("customer_id")
        # if not customer_id or int(customer_id) != int(session_customer_id):
        #     return JsonResponse({"error": "Unauthorized request."}, status=403)

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        if str(customer.otp) != otp:
            return JsonResponse({"error": "Invalid OTP."}, status=400)
        if not customer.is_otp_valid():
            return JsonResponse({"error": "OTP expired."}, status=400)

        customer.otp = None
        customer.changed_on = None
        customer.save(update_fields=["otp", "changed_on"])

        key_prefix = f"{mode}_nominee_{customer_id}"
        nominee_data = cache.get(f"{key_prefix}_data")

        if not nominee_data or "nominee_id" not in nominee_data:
            return JsonResponse({"error": "Session expired or missing nominee_id."}, status=400)

        nominee = NomineeDetails.objects.filter(id=nominee_data["nominee_id"], customer=customer).first()
        if not nominee:
            return JsonResponse({"error": "Nominee not found."}, status=404)

        # Optional file updates
        files_data = cache.get(f"{key_prefix}_files")
        addr_ext = cache.get(f"{key_prefix}_addr_ext")
        id_ext = cache.get(f"{key_prefix}_id_ext")

        if files_data:
            if "address_proof_file" in files_data:
                address_file = BytesIO(files_data["address_proof_file"].encode("latin1"))
                address_file.name = f"address{addr_ext}"
                address_key, _, _, _ = generate_customer_file_key(address_file, customer, "nominee_address_proof")
                upload_file_to_s3(address_file, address_key)
                nominee.address_proof_path = address_key

            if "id_proof_file" in files_data:
                id_file = BytesIO(files_data["id_proof_file"].encode("latin1"))
                id_file.name = f"id{id_ext}"
                id_key, _, _, _ = generate_customer_file_key(id_file, customer, "nominee_id_proof")
                upload_file_to_s3(id_file, id_key)
                nominee.id_proof_path = id_key

        # Update fields
        nominee.first_name = nominee_data["first_name"]
        nominee.last_name = nominee_data["last_name"]
        nominee.relation = nominee_data["relation"]
        nominee.save()

        # Clean cache
        for suffix in ["data", "files", "addr_ext", "id_ext"]:
            cache.delete(f"{key_prefix}_{suffix}")

        return JsonResponse({"message": "Nominee updated successfully.", "nominee_id": nominee.id})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def verify_and_save_nominee(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=405)

    try:
        data = request.POST
        otp = data.get("otp")
        customer_id = data.get("customer_id")
        mode = "create"

        session_customer_id = request.session.get("customer_id")
        # if not customer_id or int(customer_id) != int(session_customer_id):
        #     return JsonResponse({"error": "Unauthorized request."}, status=403)

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        customer = CustomerRegister.objects.get(id=customer_id)
        if str(customer.otp) != otp:
            return JsonResponse({"error": "Invalid OTP."}, status=400)
        if not customer.is_otp_valid():
            return JsonResponse({"error": "OTP expired."}, status=400)

        customer.otp = None
        customer.changed_on = None
        customer.save(update_fields=["otp", "changed_on"])

        # Load cached data
        key_prefix = f"{mode}_nominee_{customer_id}"
        nominee_data = cache.get(f"{key_prefix}_data")
        files_data = cache.get(f"{key_prefix}_files")

        if not all([nominee_data, files_data]):
            return JsonResponse({"error": "Session expired or incomplete data."}, status=400)

        # Upload files
        address_file = BytesIO(files_data["address_proof_file"].encode("latin1"))
        address_file.name = "address_proof.jpg"
        id_file = BytesIO(files_data["id_proof_file"].encode("latin1"))
        id_file.name = "id_proof.jpg"

        addr_key, _, _, _ = generate_customer_file_key(address_file, customer, "nominee_address_proof")
        id_key, _, _, _ = generate_customer_file_key(id_file, customer, "nominee_id_proof")
        upload_file_to_s3(address_file, addr_key)
        upload_file_to_s3(id_file, id_key)

        # Check for duplicate
        if NomineeDetails.objects.filter(
            customer=customer,
            first_name=nominee_data["first_name"],
            last_name=nominee_data["last_name"],
            relation=nominee_data["relation"],
            nominee_status=1
        ).exists():
            return JsonResponse({"error": "This nominee already exists for the customer."}, status=409)

        dob = datetime.strptime(nominee_data["dob"], "%Y-%m-%d").date()
        admin = Admin.objects.only("id").first()
        if not admin:
            return JsonResponse({"error": "Admin not found."}, status=500)

        nominee = NomineeDetails.objects.create(
            customer=customer,
            first_name=nominee_data["first_name"],
            last_name=nominee_data["last_name"],
            relation=nominee_data["relation"],
            dob=dob,
            share=nominee_data["share"],
            address_proof=nominee_data["address_proof"],
            address_proof_path=addr_key,
            id_proof_path=id_key,
            admin=admin,
            nominee_status=1
        )

        for suffix in ["data", "files"]:
            cache.delete(f"{key_prefix}_{suffix}")

        return JsonResponse({"message": "Nominee saved successfully.", "nominee_id": nominee.id})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
# ----------------`------------------------
# `
def get_s3_url(path):
    if path:
        return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{path}"
    return None

@csrf_exempt
def preview_customer_details(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        session_customer_id = request.session.get('customer_id')
        if not session_customer_id or int(session_customer_id) != int(customer_id):
            return JsonResponse({"error": "Unauthorized: Session customer ID mismatch."}, status=403)

        customer = CustomerRegister.objects.only("id", "first_name", "last_name", "email", "mobile_no").filter(id=session_customer_id).first()
        kyc = KYCDetails.objects.only("id", "pan_number", "aadhar_number", "banck_account_number",
        "ifsc_code", "banck_name","aadhar_path", "pan_path").filter(customer_id=session_customer_id,status=1).first()
        more = CustomerMoreDetails.objects.only(
            "address", "city", "state", "country", "pincode", "mandal",
            "district", "dob", "gender", "profession", "designation", "personal_status",
            "selfie_path", "signature_path"
        ).filter(customer_id=session_customer_id,status=1).first()
        nominee = NomineeDetails.objects.only(
            "first_name", "last_name", "relation", "dob", "address_proof",
            "address_proof_path", "id_proof_path","share"
        ).filter(customer_id=session_customer_id,status=1).first()

        if not customer:
            return JsonResponse({"error": "Customer not found."}, status=404)
        if not kyc:
            return JsonResponse({"error": "KYC details not found."}, status=404)
        if not more:
            return JsonResponse({"error": "Personal details not found."}, status=404)
        if not nominee:
            return JsonResponse({"error": "Nominee details not found."}, status=404)

        return JsonResponse({
            "message": "All customer data retrieved successfully.",
            "customer": {
                "customer_id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "mobile_no": customer.mobile_no,
            },
            "kyc": {
                "pan_number": kyc.pan_number,
                "aadhar_number": kyc.aadhar_number,
                "banck_account_number": kyc.banck_account_number,
                "ifsc_code": kyc.ifsc_code,
                "banck_name": kyc.banck_name,
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
            "nominee": {
                "first_name": nominee.first_name,
                "last_name": nominee.last_name,
                "relation": nominee.relation,
                "dob": str(nominee.dob),
                "share":nominee.share,
                "address_proof": nominee.address_proof,
                "address_proof_url": get_s3_url(nominee.address_proof_path),
                "id_proof_url": get_s3_url(nominee.id_proof_path),
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def create_drone_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        email = data.get('email')
        current_payment = float(data.get('price'))  # what customer wants to pay now

        session_customer_id = request.session.get('customer_id')
        if not session_customer_id or int(session_customer_id) != int(customer_id):
            return JsonResponse({"error": "Unauthorized: Session customer ID mismatch."}, status=403)
        if not all([customer_id, email, current_payment]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        customer = CustomerRegister.objects.filter(id=customer_id, email=email).first()
        if not customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        total_required = 1200000  # ₹12,00,000 fixed total

        # Total paid so far
        total_paid = PaymentDetails.objects.filter(
            customer=customer,
            drone_payment_status='paid'
        ).aggregate(total_paid=Sum('amount'))['total_paid'] or 0

        # Remaining amount
        remaining = total_required - total_paid

        if remaining <= 0:
            return JsonResponse({'error': 'Full payment of ₹12L already completed.'}, status=400)

        if current_payment > remaining:
            return JsonResponse({'error': f'Maximum remaining amount is ₹{remaining}. Please enter valid amount.'}, status=400)

        # Determine next part number
        last_part = PaymentDetails.objects.filter(customer=customer).aggregate(
            last_part=Max('part_number')
        )['last_part'] or 0
        next_part = last_part + 1

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        amount_paise = int(current_payment * 100)

        order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'customer_id': str(customer_id),
                'email': email,
                'part': str(next_part)
            }
        })

        PaymentDetails.objects.create(
            customer=customer,
            razorpay_order_id=order['id'],
            amount=current_payment,
            part_number=next_part,
            drone_payment_status='created'
        )

        return JsonResponse({
            'message': f'Order for part {next_part} created.',
            'orders': [{
                'order_id': order['id'],
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'amount': current_payment,
                'currency': 'INR',
                'email': email,
                'part_number': next_part
            }]
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def razorpay_callback(request):
    try:
        payload = request.body
        signature = request.headers.get('X-Razorpay-Signature')

        # Verify signature
        expected_signature = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        print("Signature:", signature)
        print("Expected Signature:", expected_signature)

        if signature != expected_signature:
            return JsonResponse({'error': 'Invalid signature'}, status=400)

        data = json.loads(payload)
        event = data.get('event')
        print("Webhook Event Received:", event)

        if event == 'payment.captured':
            payment_entity = data['payload']['payment']['entity']
            razorpay_order_id = payment_entity['order_id']
            payment_id = payment_entity['id']

            print("Order ID:", razorpay_order_id)
            print("Payment ID:", payment_id)

            payment = PaymentDetails.objects.filter(razorpay_order_id=razorpay_order_id).first()
            if payment and payment.drone_payment_status != 'paid':
                payment.drone_payment_status = 'paid'
                payment.razorpay_payment_id = payment_id
                payment.save()
                print(f"Payment part {payment.part_number} marked as PAID.")

                all_paid = PaymentDetails.objects.filter(
                    customer=payment.customer, drone_payment_status='paid'
                ).count()

                if all_paid == 3:
                    print("Full ₹12L drone payment completed.")

        return HttpResponse(status=200)

    except Exception as e:
        print("Webhook error:", str(e))
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def payment_status_check(request):
    try:
        customer_id = request.GET.get('customer_id')

        if not customer_id:
            return JsonResponse({'error': 'customer_id is required'}, status=400)

        customer = CustomerRegister.objects.filter(id=customer_id).first()
        if not customer:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        total_paid = PaymentDetails.objects.filter(
            customer=customer,
            drone_payment_status='paid'
        ).aggregate(total_paid=Sum('amount'))['total_paid'] or 0

        completed = total_paid >= 1200000

        return JsonResponse({
            'completed': completed,
            'total_paid': total_paid,
            'remaining': max(0, 1200000 - total_paid)
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

