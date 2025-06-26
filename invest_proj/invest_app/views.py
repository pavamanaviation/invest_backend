from datetime import timedelta
import random
import pytz
import json
import datetime
from django.apps import apps
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from invest_app.models import (Admin, CustomerRegister,Role,CustomerMoreDetails,
                               KYCDetails,Permission)
from .sms_utils import send_otp_sms
from django.contrib.auth.hashers import check_password
from django.conf import settings
from django.db import IntegrityError

MODEL_LABELS = {
                "CustomerRegister": "Customer Registration Details",
                "KYCDetails": "KYC Details",
                "CustomerMoreDetails": "Customer More Details",
                "NomineeDetails": "Nominee Details",
                "PaymentDetails": "Payment Details"
            }

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
def get_models_by_admin(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')

        if not admin_id:
            return JsonResponse({'error': 'admin_id is required'}, status=400)

        excluded_models = {'Admin', 'Role', 'Permission'}

        model_name_map = {
            'CustomerRegister': 'Customer Registration Details',
            'KYCDetails': 'KYC Details',
            'CustomerMoreDetails': 'Customer More Details',
            'NomineeDetails': 'Nominee Details',
            'PaymentDetails': 'Payment Details'
        }

        app_models = apps.get_app_config('invest_app').get_models()

        model_dict = {
            model.__name__: model_name_map.get(model.__name__, model.__name__)
            for model in app_models
            if model.__name__ not in excluded_models and model.__name__ in model_name_map
        }

        return JsonResponse({'models': model_dict}, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
@csrf_exempt
def assign_role_permissions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')
        role_id = data.get('role_id')
        permissions = data.get('permissions', [])

        if not admin_id or not role_id or not permissions:
            return JsonResponse({'error': 'admin_id, role_id, and permissions are required'}, status=400)
        try:
            admin = Admin.objects.get(id=admin_id,status=1)
            role = Role.objects.get(id=role_id,status=1)
        except Admin.DoesNotExist:
            return JsonResponse({'error': 'Admin not found'}, status=404)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)

        allowed_models = [
            model.__name__ for model in apps.get_app_config('invest_app').get_models()
            if model.__name__ not in ['Admin', 'Role', 'Permission']
        ]

        Permission.objects.filter(admin=admin, role=role).delete()

        created_permissions = []

        for perm in permissions:
            model_name = perm.get('model_name')
            if model_name not in allowed_models:
                continue

            obj = Permission.objects.create(
                model_name=model_name,
                can_add=perm.get('can_add', False),
                can_view=perm.get('can_view', False),
                can_edit=perm.get('can_edit', False),
                can_delete=perm.get('can_delete', False),
                admin=admin,
                role=role
            )
            created_permissions.append({
                "model_name": model_name,
                "label": MODEL_LABELS.get(model_name, model_name),
                "can_add": obj.can_add,
                "can_view": obj.can_view,
                "can_edit": obj.can_edit,
                "can_delete": obj.can_delete
            })

        return JsonResponse({
            "message": "Permissions updated successfully",
            "assigned_permissions": created_permissions
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def view_role_permissions_by_admin(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')

        if not admin_id:
            return JsonResponse({'error': 'admin_id is required'}, status=400)

        try:
            admin = Admin.objects.get(id=admin_id)
        except Admin.DoesNotExist:
            return JsonResponse({'error': 'Admin not found'}, status=404)

        roles = Role.objects.filter(permission__admin=admin).distinct()
        result = []

        for role in roles:
            permissions = Permission.objects.filter(admin=admin, role=role)

            perms_list = []
            for perm in permissions:
                perms_list.append({
                    "model_name": perm.model_name,
                    "label": MODEL_LABELS.get(perm.model_name, perm.model_name),
                    "can_add": perm.can_add,
                    "can_view": perm.can_view,
                    "can_edit": perm.can_edit,
                    "can_delete": perm.can_delete
                })

            result.append({
                "role_id": role.id,
                "role_type": role.role_type,
                "name": role.first_name+" "+role.last_name,
                "email": role.email,
                "company_name": role.company_name,
                "permissions": perms_list
            })

        return JsonResponse({"roles_permission_details": result}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def add_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)

        admin_id = data.get('admin_id')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        email = data.get('email', '').strip().lower()
        mobile_no = data.get('mobile_no', '').strip()
        company_name = data.get('company_name', '').strip()
        role_type = data.get('role_type', '').strip()

        if not all([admin_id, first_name, last_name, email, mobile_no, company_name, role_type]):
            return JsonResponse({'error': 'All fields including admin_id are required'}, status=400)
        try:
            admin = Admin.objects.get(id=admin_id)
        except Admin.DoesNotExist:
            return JsonResponse({'error': 'Admin not found with given ID'}, status=404)

        if Role.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists'}, status=400)

        if Role.objects.filter(mobile_no=mobile_no).exists():
            return JsonResponse({'error': 'Mobile number already exists'}, status=400)

        if Role.objects.filter(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile_no=mobile_no,
            company_name=company_name,
            role_type=role_type
        ).exists():
            return JsonResponse({'error': 'This role already exists with the same details'}, status=400)

        role = Role.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile_no=mobile_no,
            company_name=company_name,
            role_type=role_type,
            created_at=datetime.datetime.now(),  # or timezone.now() for UTC
            admin=admin
        )

        return JsonResponse({
            'message': 'Role added successfully',
            'role_id': role.id
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except IntegrityError:
        return JsonResponse({'error': 'A role with the same email or mobile number already exists.'}, status=400)
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

        if not Admin.objects.filter(id=admin_id).exists():
            return JsonResponse({'error': 'Admin not found'}, status=404)

        roles = Role.objects.filter(admin_id=admin_id, status=1).order_by('-id')

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
                'created_on': role.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return JsonResponse({'roles': roles_data}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    
@csrf_exempt
def delete_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')
        admin_id = data.get('admin_id')

        if not role_id or not admin_id:
            return JsonResponse({'error': 'Both role_id and admin_id are required'}, status=400)

        try:
            role = Role.objects.get(id=role_id, admin_id=admin_id)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found for the given admin'}, status=404)

        role.status = 0  # Mark as inactive
        role.save()

        return JsonResponse({'message': 'Role disabled successfully'}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
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

        else:
            return JsonResponse({'error': 'Invalid action or missing customer_id'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def format_kyc_data(kyc):
    s3_base_url = settings.AWS_S3_BUCKET_URL

    return {
        "customer_id": kyc.customer.id,
        "email": kyc.customer.email,
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

        else:
            return JsonResponse({"error": "Invalid action or missing customer_id"}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)