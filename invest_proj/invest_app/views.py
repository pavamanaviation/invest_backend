from datetime import timedelta
import random
import pytz
import json

from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import Admin, CustomerRegister,Role,CustomerMoreDetails,KYCDetails,NomineeDetails
from .sms_utils import send_otp_sms
from django.contrib.auth.hashers import check_password
from django.conf import settings
from django.db.models import Q, Value
from django.db.models.functions import Concat


@csrf_exempt
def verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get('email')
        mobile_no = data.get('mobile_no')
        otp = data.get('otp')

        if not otp:
            return JsonResponse({"error": "OTP is required."}, status=400)

        # --- 1. Try Customer --- #
        customer = None
        if email:
            customer = CustomerRegister.objects.filter(email=email).first()
        if not customer and mobile_no:
            customer = CustomerRegister.objects.filter(mobile_no=mobile_no).first()

        if customer:
            # Check OTP expiry (2 minutes)
            if not customer.changed_on or timezone.now() > customer.changed_on + timedelta(minutes=2):
                return JsonResponse({"error": "OTP has expired. Please request a new one."}, status=400)

            if not customer.otp or not str(customer.otp).isdigit():
                return JsonResponse({"error": "OTP is invalid or missing. Please request a new one."}, status=400)

            try:
                if int(customer.otp) != int(otp):
                    return JsonResponse({"error": "Invalid OTP."}, status=400)
            except:
                return JsonResponse({"error": "Invalid OTP format."}, status=400)

            if customer.register_status == 1 and customer.account_status == 1:
                customer.otp = None
                customer.save()
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
            else:
                return JsonResponse({"error": "Account is not active or verified."}, status=403)

        # --- 2. Try Admin --- #
        admin = None
        if email:
            admin = Admin.objects.filter(email=email).first()
        if not admin and mobile_no:
            admin = Admin.objects.filter(mobile_no=mobile_no).first()

        if admin:
            if not admin.changed_on or timezone.now() > admin.changed_on + timedelta(minutes=2):
                return JsonResponse({"error": "OTP has expired. Please request a new one."}, status=400)

            if not admin.otp or not str(admin.otp).isdigit():
                return JsonResponse({"error": "OTP is invalid or missing. Please request a new one."}, status=400)

            try:
                if int(admin.otp) != int(otp):
                    return JsonResponse({"error": "Invalid OTP."}, status=400)
            except:
                return JsonResponse({"error": "Invalid OTP format."}, status=400)
            admin.otp = None
            admin.save()
            request.session['admin_id'] = admin.id
            request.session.save()

            return JsonResponse({
                "message": "OTP verified and login successful (Admin).",
                "admin_id": admin.id,
                "email": admin.email,
                "session_id": request.session.session_key
            }, status=200)

        # --- 3. Try Employee (Role) --- #
        role = None
        if email:
            role = Role.objects.filter(email=email).first()
        if not role and mobile_no:
            role = Role.objects.filter(mobile_no=mobile_no).first()

        if role:
            if not role.changed_on or timezone.now() > role.changed_on + timedelta(minutes=2):
                return JsonResponse({"error": "OTP has expired. Please request a new one."}, status=400)

            if not role.otp or not str(role.otp).isdigit():
                return JsonResponse({"error": "OTP is invalid or missing. Please request a new one."}, status=400)

            try:
                if int(role.otp) != int(otp):
                    return JsonResponse({"error": "Invalid OTP."}, status=400)
            except:
                return JsonResponse({"error": "Invalid OTP format."}, status=400)
            role.otp = None
            role.save()
            request.session['role_id'] = role.id
            request.session.save()

            return JsonResponse({
                "message": "OTP verified and login successful (Employee).",
                "role_id": role.id,
                "email": role.email,
                "session_id": request.session.session_key
            }, status=200)

        return JsonResponse({"error": "Account not found."}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)


@csrf_exempt
def register_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)

        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        email = data.get('email', '').strip().lower()
        mobile_no = data.get('mobile_no', '').strip()
        company_name = data.get('company_name', '').strip()
        role_type = data.get('role_type', '').strip()
       

        if not all([first_name, last_name, email, mobile_no, company_name, role_type]):
            return JsonResponse({'error': 'All fields including admin_id are required'}, status=400)

        if Role.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists'}, status=400)
        if Role.objects.filter(mobile_no=mobile_no).exists():
            return JsonResponse({'error': 'Mobile number already exists'}, status=400)

        try:
            admin = Admin.objects.order_by('id').first()  # 💡 Cast to int
        except Admin.DoesNotExist:
            return JsonResponse({'error': 'Admin not found'}, status=404)

        role = Role.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile_no=mobile_no,
            company_name=company_name,
            role_type=role_type,
            changed_on=timezone.now(),
            admin=admin
        )

        return JsonResponse({
            'message': 'Role registered successfully',
            'role_id': role.id
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



@csrf_exempt
def view_roles(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')

        if not admin_id:
            return JsonResponse({'error': 'admin_id is required'}, status=400)

        roles = Role.objects.filter(admin_id=admin_id).order_by('-id')
        roles_data = []

        for role in roles:
            roles_data.append({
                'id': role.id,
                'first_name': role.first_name,
                'last_name': role.last_name,
                'email': role.email,
                'mobile_no': role.mobile_no,
                'company_name': role.company_name,
                'role_type': role.role_type,
                'status': role.status,  
                'changed_on': role.changed_on.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return JsonResponse({'roles': roles_data}, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    
@csrf_exempt
def delete_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')

        if not role_id:
            return JsonResponse({'error': 'role_id is required'}, status=400)

        role = Role.objects.get(id=role_id)
        role.status = 0  # Set as Inactive
        role.save()

        return JsonResponse({'message': 'Role disabled successfully'}, status=200)

    except Role.DoesNotExist:
        return JsonResponse({'error': 'Role not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')

        if not role_id:
            return JsonResponse({'error': 'role_id is required'}, status=400)

        role = Role.objects.get(id=role_id)

        # Update fields if they are sent
        role.first_name = data.get('first_name', role.first_name)
        role.last_name = data.get('last_name', role.last_name)
        role.email = data.get('email', role.email)
        role.mobile_no = data.get('mobile_no', role.mobile_no)
        role.company_name = data.get('company_name', role.company_name)
        role.role_type = data.get('role_type', role.role_type)
        role.save()

        return JsonResponse({'message': 'Role updated successfully'}, status=200)

    except Role.DoesNotExist:
        return JsonResponse({'error': 'Role not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def format_customer_data(customer):
    more = CustomerMoreDetails.objects.filter(customer=customer).first()

    address_parts = [more.address, more.city, more.mandal, more.district, more.state, more.pincode] if more else []
    address = ", ".join(part for part in address_parts if part)

    return {
        "customer_id": customer.id,
        "name": f"{customer.first_name} {customer.last_name}".strip(),
        "email": customer.email,
        "mobile_no": customer.mobile_no,
        "register_type": customer.register_type,
        "register_status": customer.register_status,
        "account_status": customer.account_status,
        "created_at": customer.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "dob": more.dob.strftime("%Y-%m-%d") if more and more.dob else "",
        "gender": more.gender if more else "",
        "profession": more.profession if more else "",
        "designation": more.designation if more else "",
        "address": address,
        "selfie": f"{settings.AWS_S3_BUCKET_URL}/{more.selfie_path}" if more and more.selfie_path else "",
        "signature": f"{settings.AWS_S3_BUCKET_URL}/{more.signature_path}" if more and more.signature_path else "",
    }


# @csrf_exempt
# def admin_customer_details(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST method allowed"}, status=405)

#     try:
#         data = json.loads(request.body)
#         admin_id = data.get('admin_id')
#         action = data.get('action', 'view')
#         customer_id = data.get('customer_id')

#         if not admin_id:
#             return JsonResponse({'error': 'admin_id is required'}, status=400)

#         if action == "view":
#             customers = CustomerRegister.objects.filter(admin_id=admin_id).order_by("-created_at")
#             customer_details = [format_customer_data(customer) for customer in customers]

#             return JsonResponse({
#                 "status": "success",
#                 "status_code": 200,
#                 "admin_id": admin_id,
#                 "total_count": len(customer_details),
#                 "customers": customer_details
#             }, status=200)

#         elif action == "view_more" and customer_id:
#             try:
#                 customer = CustomerRegister.objects.get(id=customer_id, admin_id=admin_id)
#                 customer_data = format_customer_data(customer)

#                 return JsonResponse({
#                     "status": "success",
#                     "status_code": 200,
#                     "admin_id": admin_id,
#                     "customer": customer_data
#                 }, status=200)
#             except CustomerRegister.DoesNotExist:
#                 return JsonResponse({"error": "Customer not found"}, status=404)

#         else:
#             return JsonResponse({'error': 'Invalid action or missing customer_id'}, status=400)

#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)

from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

@csrf_exempt
def admin_customer_details(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')
        action = data.get('action', 'view')
        customer_id = data.get('customer_id')

        if not admin_id:
            return JsonResponse({'error': 'admin_id is required'}, status=400)

        # Handle viewing all customers
        if action == "view":
            customers = CustomerRegister.objects.filter(admin_id=admin_id).order_by("-created_at")
            customer_details = [format_customer_data(customer) for customer in customers]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": len(customer_details),
                "customers": customer_details
            }, status=200)

        # Handle view_more
        elif action == "view_more" and customer_id:
            try:
                customer = CustomerRegister.objects.get(id=customer_id, admin_id=admin_id)
                customer_data = format_customer_data(customer)

                return JsonResponse({
                    "status": "success",
                    "status_code": 200,
                    "admin_id": admin_id,
                    "customer": customer_data
                }, status=200)
            except CustomerRegister.DoesNotExist:
                return JsonResponse({"error": "Customer not found"}, status=404)

        # 🔍 Handle search
        elif action == "search":
            name = data.get('name', '').strip()
            email = data.get('email', '').strip()
            mobile_no = data.get('mobile_no', '').strip()
            account_status = data.get('account_status', '').strip()

            customers = CustomerRegister.objects.filter(admin_id=admin_id)

            if name:
                customers = customers.annotate(
                    full_name=Concat('first_name', Value(' '), 'last_name')
                ).filter(
                    Q(first_name__icontains=name) |
                    Q(last_name__icontains=name) |
                    Q(full_name__icontains=name)
                )

            if email:
                customers = customers.filter(email__icontains=email)

            if mobile_no:
                customers = customers.filter(mobile_no__icontains=mobile_no)

            if account_status != "":
                customers = customers.filter(account_status=int(account_status))

            customers = customers.order_by("-created_at")
            customer_details = [format_customer_data(customer) for customer in customers]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": len(customer_details),
                "customers": customer_details
            }, status=200)

        else:
            return JsonResponse({'error': 'Invalid action or missing customer_id'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



def format_kyc_data(kyc):
    s3_base_url = settings.AWS_S3_BUCKET_URL

    return {
        "customer_id": kyc.customer.id,
        "customer_fname": kyc.customer.first_name,
        "customer_lname": kyc.customer.last_name,
        "email": kyc.customer.email,
        "mobile":kyc.customer.mobile_no,
        "pan_number": kyc.pan_number,
        "pan_status": kyc.pan_status,
        "pan_path": f"{s3_base_url}/{kyc.pan_path}" if kyc.pan_path else "",

        "aadhar_number": kyc.aadhar_number,
        "aadhar_status": kyc.aadhar_status,
        "aadhar_path": f"{s3_base_url}/{kyc.aadhar_path}" if kyc.aadhar_path else "",

        "bank_account_number": kyc.banck_account_number,
        "ifsc_code": kyc.ifsc_code,
        "bank_status": kyc.bank_status,

        "created_at": kyc.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }

from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt
def admin_customer_kyc_details(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        action = data.get("action", "view")
        admin_id = data.get("admin_id")  # required
        customer_id = data.get("customer_id")

        if not admin_id:
            return JsonResponse({"error": "admin_id is required"}, status=400)

        if action == "view":
            kyc_records = KYCDetails.objects.all().order_by("-created_at")
            kyc_list = [format_kyc_data(kyc) for kyc in kyc_records]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": len(kyc_list),
                "kyc_list": kyc_list
            }, status=200)

        elif action == "view_more" and customer_id:
            try:
                kyc = KYCDetails.objects.get(customer_id=customer_id)
                return JsonResponse({
                    "status": "success",
                    "status_code": 200,
                    "admin_id": admin_id,
                    "customer_id": customer_id,
                    "kyc": format_kyc_data(kyc)
                }, status=200)
            except KYCDetails.DoesNotExist:
                return JsonResponse({"error": "KYC not found for the given customer"}, status=404)

        elif action == "search":
            name = data.get("name", "").strip()
            mobile = data.get("mobile", "").strip()
            pan = data.get("pan", "").strip()
            aadhar = data.get("aadhar", "").strip()
            bank_no = data.get("bank_account_number", "").strip()

            kyc_records = KYCDetails.objects.select_related("customer")

            if name:
                kyc_records = kyc_records.annotate(
                    full_name=Concat("customer__first_name", Value(" "), "customer__last_name")
                ).filter(
                    Q(customer__first_name__icontains=name) |
                    Q(customer__last_name__icontains=name) |
                    Q(full_name__icontains=name)
                )

            if mobile:
                kyc_records = kyc_records.filter(customer__mobile_no__icontains=mobile)

            if pan:
                kyc_records = kyc_records.filter(pan_number__icontains=pan)

            if aadhar:
                kyc_records = kyc_records.filter(aadhar_number__icontains=aadhar)

            if bank_no:
                kyc_records = kyc_records.filter(banck_account_number__icontains=bank_no)

            kyc_records = kyc_records.order_by("-created_at")
            kyc_list = [format_kyc_data(kyc) for kyc in kyc_records]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": len(kyc_list),
                "kyc_list": kyc_list
            }, status=200)

        else:
            return JsonResponse({"error": "Invalid action or missing customer_id"}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def admin_nominee_details(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Only POST method is allowed."}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get("admin_id")
        action = data.get("action")

        if not admin_id or not action:
            return JsonResponse({"status": "error", "error": "Missing required fields."}, status=400)

        # Base queryset
        queryset = NomineeDetails.objects.select_related("customer").filter(admin_id=admin_id)

        if action == "view":
            nominees = queryset

        elif action == "view_more":
            nominee_id = data.get("nominee_id")
            if not nominee_id:
                return JsonResponse({"status": "error", "error": "nominee_id is required."}, status=400)

            nominee = queryset.filter(id=nominee_id).first()
            if not nominee:
                return JsonResponse({"status": "error", "error": "Nominee not found."}, status=404)

            return JsonResponse({
                "status": "success",
                "nominee": {
                    "id": nominee.id,
                    "first_name": nominee.first_name,
                    "last_name": nominee.last_name,
                    "relation": nominee.relation,
                    "dob": nominee.dob,
                    "address_proof": nominee.address_proof,
                    "address_proof_path": nominee.address_proof_path,
                    "id_proof": nominee.id_proof,
                    "id_proof_path": nominee.id_proof_path,
                    "nominee_status": nominee.nominee_status,
                    "created_at": nominee.created_at,
                    "customer_name": f"{nominee.customer.first_name or ''} {nominee.customer.last_name or ''}".strip(),
                    "customer_email": nominee.customer.email,
                    "customer_mobile": nominee.customer.mobile_no,
                }
            })

        elif action == "search":
            filters = Q(admin_id=admin_id)
            if data.get("name"):
                filters &= (Q(first_name__icontains=data["name"]) | Q(last_name__icontains=data["name"]))
            if data.get("email"):
                filters &= Q(customer__email__icontains=data["email"])
            if data.get("mobile_no"):
                filters &= Q(customer__mobile_no__icontains=data["mobile_no"])
            if data.get("relation"):
                filters &= Q(relation__icontains=data["relation"])

            nominees = queryset.filter(filters)

        else:
            return JsonResponse({"status": "error", "error": "Invalid action provided."}, status=400)

        nominee_list = [
            {
                "id": n.id,
                "first_name": n.first_name,
                "last_name": n.last_name,
                "relation": n.relation,
                "dob": n.dob,
                "address_proof": n.address_proof,
                "id_proof": n.id_proof,
                "nominee_status": n.nominee_status,
                "created_at": n.created_at,
                "customer_name": f"{n.customer.first_name or ''} {n.customer.last_name or ''}".strip(),
                "customer_email": n.customer.email,
                "customer_mobile": n.customer.mobile_no
            }
            for n in nominees
        ]

        return JsonResponse({
            "status": "success",
            "nominees": nominee_list,
            "total_count": len(nominee_list)
        })

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
