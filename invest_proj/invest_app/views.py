from invest_app.utils.shared_imports import *
from invest_app.utils.s3_helper import upload_to_s3, generate_presigned_url, get_next_folder_and_filename
from django.utils.dateparse import parse_date

from invest_app.customer_views import generate_otp, send_otp_email
from invest_app.utils.msg91 import send_bulk_sms
from .models import (Admin, AgreementDetails, CustomerRegister, DroneOperation, InvoiceDetails, KYCDetails, CustomerMoreDetails,
                      NomineeDetails, PaymentDetails, Permission, Role,CompanyDroneModelInfo)
import pandas as pd
import re
import tempfile
MODEL_LABELS = {
                "CustomerRegister": "Customer Registration Details",
                "KYCDetails": "KYC Details",
                "CustomerMoreDetails": "Customer More Details",
                "NomineeDetails": "Nominee Details",
                "PaymentDetails": "Payment Details"
            }

# def validate_otp_and_expiry(user, otp):
#     print("User OTP:", user.otp, "Provided OTP:", otp)
#     print("User Changed On:", user.changed_on)
#     print("Current Time:", timezone.now())
#     print("Expiry Time:", user.changed_on + timedelta(minutes=2) if user.changed_on else "N/A")
#     print(user)
#     if not user.changed_on or timezone.now() > user.changed_on + timedelta(minutes=2):
#         return "OTP has expired. Please request a new one."

#     if not user.otp or not str(user.otp).isdigit():
#         return "OTP is invalid or missing. Please request a new one."

#     try:
#         if int(user.otp) != int(otp):
#             return "Invalid OTP."
#     except ValueError:
#         return "Invalid OTP format."

#     return None  # OTP is valid

# @csrf_exempt
# def verify_otp(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Only POST method is allowed."}, status=405)

#     try:
#         data = json.loads(request.body)
#         otp = data.get('otp')
#         email = data.get('email', '').strip()
#         mobile_no = data.get('mobile_no', '').strip()

#         if not otp or not (email or mobile_no):
#             return JsonResponse({"error": "OTP and email or mobile number are required."}, status=400)

#         # Define user models and session mappings
#         user_types = [
#             {
#                 "model": CustomerRegister,
#                 "session_key": "customer_id",
#                 "extra_check": lambda u: u.register_status == 1 and u.account_status == 1,
#                 "error": "Account is not active or verified."
#             },
#             {"model": Admin, "session_key": "admin_id"},
#             {"model": Role, "session_key": "role_id"}
#         ]

#         for user_type in user_types:
#             model = user_type["model"]
#             user = model.objects.filter(
#                 Q(email=email) | Q(mobile_no=mobile_no)
#             ).first()

#             if user:
#                 # Validate OTP
#                 error = validate_otp_and_expiry(user, otp)
#                 if error:
#                     return JsonResponse({"error": error}, status=400)

#                 # Extra user-type specific validation
#                 if "extra_check" in user_type and not user_type["extra_check"](user):
#                     return JsonResponse({"error": user_type["error"]}, status=403)

#                 # OTP is valid, clear it and update session
#                 user.otp = None
#                 user.changed_on = None
#                 user.save(update_fields=["otp", "changed_on"])

#                 request.session[user_type["session_key"]] = user.id
#                 request.session.save()

#                 # Construct response
#                 response = {
#                     "message": f"OTP verified and login successful ({user_type['session_key'].split('_')[0].capitalize()}).",
#                     user_type["session_key"]: user.id,
#                     "email": user.email,
#                     "session_id": request.session.session_key
#                 }

#                 if user_type["session_key"] == "customer_id":
#                     response["register_status"] = user.register_status
#                     response["account_status"] = user.account_status

#                 return JsonResponse(response, status=200)

#         return JsonResponse({"error": "Account not found."}, status=404)

#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON format."}, status=400)
#     except Exception as e:
#         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
def validate_otp_and_expiry(user, otp):
    if not user.changed_on or timezone.now() > user.changed_on + timedelta(minutes=2):
        return "OTP has expired. Please request a new one."

    if not user.otp or not str(user.otp).isdigit():
        return "OTP is invalid or missing. Please request a new one."

    try:
        if int(user.otp) != int(otp):
            return "Invalid OTP."
    except ValueError:
        return "Invalid OTP format."
    return None 

@csrf_exempt
def verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method is allowed."}, status=405)
    try:
        data = json.loads(request.body)
        otp = data.get('otp')
        email = data.get('email', '').strip()
        mobile_no = data.get('mobile_no', '').strip()

        if not otp or not (email or mobile_no):
            return JsonResponse({"error": "OTP and email or mobile number are required."}, status=400)

        # ----------------- CUSTOMER -----------------
        customer = CustomerRegister.objects.filter(
            Q(email=email) | Q(mobile_no=mobile_no), account_status=1, register_status=1
        ).first()
        if customer:
            error = validate_otp_and_expiry(customer, otp)
            if error:
                return JsonResponse({"error": error}, status=400)

            customer.otp = None
            customer.changed_on = None
            customer.save(update_fields=["otp", "changed_on"])

            request.session["customer_id"] = customer.id
            request.session.save()

            return JsonResponse({
                "message": "OTP verified and login successful (Customer).",
                "customer_id": customer.id,
                "email": customer.email,
                "register_status": customer.register_status,
                "account_status": customer.account_status,
                "session_id": request.session.session_key
            }, status=200)

        # ----------------- ADMIN -----------------
        admin = Admin.objects.filter(
            Q(email=email) | Q(mobile_no=mobile_no), status=1
        ).first()
        if admin:
            error = validate_otp_and_expiry(admin, otp)
            if error:
                return JsonResponse({"error": error}, status=400)

            admin.otp = None
            admin.changed_on = None
            admin.save(update_fields=["otp", "changed_on"])

            request.session["admin_id"] = admin.id
            request.session.save()

            return JsonResponse({
                "message": "OTP verified and login successful (Admin).",
                "admin_id": admin.id,
                "email": admin.email,
                "name": admin.name,
                "session_id": request.session.session_key
            }, status=200)

        # ----------------- ROLE (EMPLOYEE) -----------------
        role = Role.objects.filter(
            Q(email=email) | Q(mobile_no=mobile_no), status=1, delete_status=False
        ).first()
        if role:
            error = validate_otp_and_expiry(role, otp)
            if error:
                return JsonResponse({"error": error}, status=400)

            role.otp = None
            role.changed_on = None
            role.save(update_fields=["otp", "changed_on"])

            request.session["role_id"] = role.id
            request.session.save()

            return JsonResponse({
                "message": "OTP verified and login successful (Role).",
                "role_id": role.id,
                "email": role.email,
                "full_name": f"{role.first_name} {role.last_name}".strip(),
                "session_id": request.session.session_key
            }, status=200)

        # If none found
        return JsonResponse({"error": "Account not found or not active."}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
@csrf_exempt
def employee_login(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed."}, status=405)
    try:
        data = json.loads(request.body)
        email = data.get('email')
        mobile_no = data.get('mobile_no')

        if not email and not mobile_no:
            return JsonResponse({"error": "Provide email or mobile number."}, status=400)
        admin = None
        if email:
            admin = Admin.objects.filter(email=email, status=1).first()
        if not admin and mobile_no:
            admin = Admin.objects.filter(mobile_no=mobile_no, status=1).first()

        if admin:
            otp = generate_otp()
            admin.otp = otp
            admin.otp_send_type = "email" if email else "mobile"
            admin.changed_on = timezone.now()
            admin.save(update_fields=["otp", "otp_send_type", "changed_on"])

            if email:
                send_otp_email(email, admin.name, otp)
            if mobile_no:
                send_bulk_sms([mobile_no], otp)

            return JsonResponse({
                "message": "OTP sent for admin login. It is valid for 2 minutes.",
                "admin_id": admin.id,
                "status_code": 200
            }, status=200)
        role = None
        if email:
            role = Role.objects.filter(email=email, status=1, delete_status=False).first()
        if not role and mobile_no:
            role = Role.objects.filter(mobile_no=mobile_no, status=1, delete_status=False).first()

        if role:
            otp = generate_otp()
            role.otp = otp
            role.otp_send_type = "email" if email else "mobile"
            role.changed_on = timezone.now()
            role.save(update_fields=["otp", "otp_send_type", "changed_on"])

            full_name = f"{role.first_name} {role.last_name}".strip()

            if email:
                send_otp_email(email, full_name, otp)
            if mobile_no:
                send_bulk_sms([mobile_no], otp)

            return JsonResponse({
                "message": "OTP sent for employee login. It is valid for 2 minutes.",
                "role_id": role.id,
                "status_code": 200
            }, status=200)

        return JsonResponse({"error": "Staff account not found or not verified."}, status=404)
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
        roles = Role.objects.filter(admin_id=admin_id,status = 1).values(
            'id', 'role_type', 'first_name','last_name', 'email', 'company_name'
        )

        return JsonResponse(
            {'models': model_dict,
             'roles': list(roles)
             }, status=200)

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
    
    """
    Securely serve PAN or Aadhar documents via short-lived pre-signed S3 URL.

    We use this endpoint instead of sending raw S3 links in the frontend
    to:
      - Keep S3 objects private (bucket is not public)
      - Prevent hardcoded S3 URLs in frontend (which can be abused)
      - Allow only authorized users (admin/employee/customer) to access docs
      - Generate a new 5-min valid URL each time for better security
    """
@csrf_exempt
def view_kyc_doc(request):
    """
    Securely serve PAN or Aadhar documents via short-lived pre-signed S3 URL.

    We use this endpoint instead of sending raw S3 links in the frontend
    to:
      - Keep S3 objects private (bucket is not public)
      - Prevent hardcoded S3 URLs in frontend (which can be abused)
      - Allow only authorized users (admin/employee/customer) to access docs
      - Generate a new 5-min valid URL each time for better security
    """
    customer_id = request.GET.get("customer_id")
    doc_type = request.GET.get("type")  # "pan" or "aadhar"
    admin_id = request.GET.get("admin_id")  # getting admin_id from frontend

    if not all([customer_id, doc_type, admin_id]):
        return JsonResponse({"error": "Missing required fields"}, status=400)

   
    if not Admin.objects.filter(id=admin_id).exists():
        return JsonResponse({"error": "Invalid admin ID"}, status=401)
    if not CustomerRegister.objects.filter(id=customer_id).exists():
        return JsonResponse({"error": "Invalid customer ID"}, status=404)

    try:
        kyc = KYCDetails.objects.select_related("customer").get(customer__id=customer_id)

        file_path = ""
        if doc_type == "pan":
            file_path = kyc.pan_path
        elif doc_type == "aadhar":
            file_path = kyc.aadhar_path
        else:
            return JsonResponse({"error": "Invalid document type"}, status=400)

        if not file_path:
            return JsonResponse({"error": "Document not uploaded"}, status=404)

        presigned_url = generate_presigned_url(file_path, expires_in=300)
        return JsonResponse({"url": presigned_url})

    except KYCDetails.DoesNotExist:
        return JsonResponse({"error": "KYC details not found"}, status=404)
def format_kyc_data(kyc):
    # pan_url = generate_presigned_url(kyc.pan_path, expires_in=300) if kyc.pan_path else ""
    # aadhar_url = generate_presigned_url(kyc.aadhar_path, expires_in=300) if kyc.aadhar_path else ""
    """
    Instead of sending pre-signed S3 links directly in the response,
    we return a relative API endpoint like `/api/view-kyc-doc/?customer_id=...&type=pan`.

    Why?
      - Keeps S3 bucket details hidden from frontend
      - Ensures the document access is controlled via our Django logic
      - Allows only authorized admin/employee/customer to access S3 files
      - Prevents generation of unused signed URLs on every data load

    The frontend can call this endpoint on-demand (when user clicks "View") to get a fresh secure URL.
    """
    return {
        "customer_id": kyc.customer.id,
        "customer_fname": kyc.customer.first_name,
        "customer_lname": kyc.customer.last_name,
        "email": kyc.customer.email,
        "mobile": kyc.customer.mobile_no,
        "pan_number": kyc.pan_number,
        "pan_status": kyc.pan_status,
        "pan_path_db": kyc.pan_path,
        "pan_path": f"/api/view-kyc-doc/?customer_id={kyc.customer.id}&type=pan" if kyc.pan_path else "",
        # "pan_path": pan_url,
        "aadhar_number": kyc.aadhar_number,
        "aadhar_status": kyc.aadhar_status,
        "aadhar_path_db": kyc.aadhar_path,
        # "aadhar_path": aadhar_url,
        "aadhar_path": f"/api/view-kyc-doc/?customer_id={kyc.customer.id}&type=aadhar" if kyc.aadhar_path else "",
        "bank_account_number": kyc.banck_account_number,
        "ifsc_code": kyc.ifsc_code,
        "bank_status": kyc.bank_status,
        "created_at": kyc.created_at.strftime("%Y-%m-%d %H:%M:%S") if kyc.created_at else "",
    }

# def format_kyc_data(kyc):
#     s3_base_url = settings.AWS_S3_BUCKET_URL
#     return {
#         "customer_id": kyc.customer.id,
#         "customer_fname": kyc.customer.first_name,
#         "customer_lname": kyc.customer.last_name,
#         "email": kyc.customer.email,
#         "mobile": kyc.customer.mobile_no,
#         "pan_number": kyc.pan_number,
#         "pan_status": kyc.pan_status,
#         "pan_path": f"{s3_base_url}/{kyc.pan_path}" if kyc.pan_path else "",
#         "aadhar_number": kyc.aadhar_number,
#         "aadhar_status": kyc.aadhar_status,
#         "aadhar_path": f"{s3_base_url}/{kyc.aadhar_path}" if kyc.aadhar_path else "",
#         "bank_account_number": kyc.banck_account_number,
#         "ifsc_code": kyc.ifsc_code,
#         "bank_status": kyc.bank_status,
#         "created_at": kyc.created_at.strftime("%Y-%m-%d %H:%M:%S") if kyc.created_at else "",
#     }
@csrf_exempt
def admin_customer_kyc_details(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        action = data.get("action", "view")
        admin_id = data.get("admin_id")
        customer_id = data.get("customer_id")
        limit = int(data.get("limit", 10))
        offset = int(data.get("offset", 0))

        if not admin_id:
            return JsonResponse({"error": "admin_id is required"}, status=400)

        if action == "view":
            cache_key = f"kyc_list_ids_admin_{admin_id}_{offset}_{limit}"
            cached_ids = cache.get(cache_key)

            if cached_ids:
                kyc_records = KYCDetails.objects.select_related("customer").filter(id__in=cached_ids)
            else:
                kyc_records = (
                    KYCDetails.objects.select_related("customer")
                    .order_by("-created_at")[offset:offset + limit]
                )
                kyc_ids = list(kyc_records.values_list("id", flat=True))
                cache.set(cache_key, kyc_ids, timeout=300)

            # Always regenerate fresh presigned URLs
            kyc_list = [format_kyc_data(kyc) for kyc in kyc_records]
            total = KYCDetails.objects.count()

            response_data = {
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": total,
                "kyc_list": kyc_list
            }
            return JsonResponse(response_data, status=200)

        elif action == "view_more" and customer_id:
            try:
                kyc = KYCDetails.objects.select_related("customer").get(customer_id=customer_id)
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

            total = kyc_records.count()
            paginated_kyc = kyc_records.order_by("-created_at")[offset:offset + limit]
            kyc_list = [format_kyc_data(kyc) for kyc in paginated_kyc]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": total,
                "kyc_list": kyc_list
            }, status=200)

        return JsonResponse({"error": "Invalid action or missing customer_id"}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def format_nominee(n):
    s3_base_url = settings.AWS_S3_BUCKET_URL
    return {
        "nominee_id": n.id,
        "first_name": n.first_name,
        "last_name": n.last_name,
        "relation": n.relation,
        "dob": n.dob.strftime("%Y-%m-%d") if n.dob else None,
        "address_proof": n.address_proof,
        "address_proof_path": f"{s3_base_url}/{n.address_proof_path}" if n.address_proof_path else None,
        "id_proof": n.id_proof,
        "id_proof_path": f"{s3_base_url}/{n.id_proof_path}" if n.id_proof_path else None,
        "nominee_status": n.nominee_status,
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else None
    }


def group_nominees_by_customer(nominee_queryset):
    grouped = {}
    for nominee in nominee_queryset:
        cid = nominee.customer.id
        if cid not in grouped:
            grouped[cid] = {
                "customer_id": cid,
                "customer_name": f"{nominee.customer.first_name or ''} {nominee.customer.last_name or ''}".strip(),
                "customer_email": nominee.customer.email,
                "customer_mobile": nominee.customer.mobile_no,
                "nominees": [],
                "nominee_count": 0  # New field
            }
        grouped[cid]["nominees"].append(format_nominee(nominee))
        grouped[cid]["nominee_count"] += 1  # Increment count
    return list(grouped.values())



@csrf_exempt
def admin_nominee_details(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Only POST method is allowed."}, status=405)

    try:
        data = json.loads(request.body)
        action = data.get("action", "view")
        admin_id = data.get("admin_id")
        customer_id = data.get("customer_id")
        limit = int(data.get("limit", 10))
        offset = int(data.get("offset", 0))

        if not admin_id:
            return JsonResponse({"status": "error", "error": "admin_id is required"}, status=400)

        queryset = NomineeDetails.objects.select_related("customer").filter(admin_id=admin_id)

        if action == "view":
            cache_key = f"nominee_list_admin_{admin_id}{offset}{limit}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return JsonResponse(cached_data, status=200)

            total = queryset.count()
            nominees = queryset.order_by("-created_at")[offset:offset + limit]
            grouped_data = group_nominees_by_customer(nominees)

            response_data = {
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": total,
                "nominees": grouped_data
            }

            cache.set(cache_key, response_data, timeout=300)
            return JsonResponse(response_data, status=200)

        elif action == "view_more" and customer_id:
            nominees = queryset.filter(customer_id=customer_id).order_by("-created_at")
            if not nominees.exists():
                return JsonResponse({"status": "error", "error": "No nominee found for customer."}, status=404)

            grouped_data = group_nominees_by_customer(nominees)
            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "customer_id": customer_id,
                "nominees": grouped_data
            }, status=200)

        elif action == "search":
            name = data.get("name", "").strip()
            mobile = data.get("mobile_no", "").strip()
            min_nominee_count = int(data.get("min_nominee_count", 0))
            min_verified_nominee_count = int(data.get("min_verified_nominee_count", 0))

            filters = Q(admin_id=admin_id)

            if name:
                filters &= (
                    Q(customer__first_name__icontains=name) |
                    Q(customer__last_name__icontains=name) |
                    Q(first_name__icontains=name) |
                    Q(last_name__icontains=name)
                )

            if mobile:
                filters &= Q(customer__mobile_no__icontains=mobile)

            # Get nominee queryset after filtering
            nominees = queryset.filter(filters).order_by("-created_at")

            # Group nominees by customer
            grouped_data = group_nominees_by_customer(nominees)

            # Now apply nominee count filtering in-memory
            filtered_grouped_data = [
                group for group in grouped_data
                if group["nominee_count"] >= min_nominee_count and group["verified_nominee_count"] >= min_verified_nominee_count
            ]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": len(filtered_grouped_data),
                "nominees": filtered_grouped_data
            }, status=200)

        return JsonResponse({"status": "error", "error": "Invalid action or missing parameters."}, status=400)

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
def format_customer_data(customer, more):
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
        limit = int(data.get('limit', 20))
        offset = int(data.get('offset', 0))

        if not admin_id:
            return JsonResponse({'error': 'admin_id is required'}, status=400)

        # 🔁 Handle "view" with caching
        if action == "view":
            cache_key = f"admin_customers_{admin_id}{limit}{offset}"
            cached_result = cache.get(cache_key)
            if cached_result:
                return JsonResponse(cached_result, status=200)

            customers = CustomerRegister.objects.filter(admin_id=admin_id).order_by("-created_at")
            customer_ids = customers.values_list("id", flat=True)[offset:offset+limit]
            more_details_map = {
                more.customer_id: more
                for more in CustomerMoreDetails.objects.filter(customer_id__in=customer_ids)
            }

            paginated_customers = customers.filter(id__in=customer_ids)
            customer_details = [
                format_customer_data(customer, more_details_map.get(customer.id))
                for customer in paginated_customers
            ]

            response_data = {
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": customers.count(),
                "customers": customer_details
            }

            # ⏱️ Cache the result for 5 minutes
            cache.set(cache_key, response_data, timeout=300)
            return JsonResponse(response_data, status=200)

        # 🧾 Handle view_more
        elif action == "view_more" and customer_id:
            customer = CustomerRegister.objects.filter(id=customer_id, admin_id=admin_id).first()
            if not customer:
                return JsonResponse({"error": "Customer not found"}, status=404)

            more = CustomerMoreDetails.objects.filter(customer=customer).first()
            customer_data = format_customer_data(customer, more)

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "customer": customer_data
            }, status=200)

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
            customer_ids = customers.values_list("id", flat=True)[offset:offset+limit]
            more_details_map = {
                more.customer_id: more
                for more in CustomerMoreDetails.objects.filter(customer_id__in=customer_ids)
            }

            paginated_customers = customers.filter(id__in=customer_ids)
            customer_details = [
                format_customer_data(customer, more_details_map.get(customer.id))
                for customer in paginated_customers
            ]

            return JsonResponse({
                "status": "success",
                "status_code": 200,
                "admin_id": admin_id,
                "total_count": customers.count(),
                "customers": customer_details
            }, status=200)

        return JsonResponse({'error': 'Invalid action or missing customer_id'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def generate_presigned_url(file_key, expires_in=300):
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )
    mime_type, _ = mimetypes.guess_type(file_key)
    if not mime_type:
        mime_type = 'application/octet-stream'

    return s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
            'Key': file_key,
            'ResponseContentDisposition': 'inline',
            'ResponseContentType': mime_type
        },
        ExpiresIn=expires_in
    )

@csrf_exempt
def upload_drone_models(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        file = request.FILES.get('file')
        admin_id = request.POST.get('admin_id')

        if not file or not admin_id:
            return JsonResponse({"error": "Missing file or admin_id"}, status=400)
        
        try:
            admin = Admin.objects.get(id=admin_id, status=1)
        except Admin.DoesNotExist:
            return JsonResponse({'error': 'Admin not found'}, status=404)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            df = pd.read_excel(tmp_path)
        except ImportError:
            return JsonResponse({"error": "Missing optional dependency 'openpyxl'. Use pip install openpyxl."})
        except Exception as e:
            return JsonResponse({"error": f"Excel Read Error: {str(e)}"})

        folder_name, file_name = get_next_folder_and_filename()
        file_key = f"drone_uploads/{folder_name}/{file_name}"

        try:
            with open(tmp_path, 'rb') as f:
                upload_to_s3(f, file_key)
        except Exception as e:
            return JsonResponse({"error": f"S3 Upload Error: {str(e)}"})

        s3_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_key}"

        success_count = 0
        errors = []
        duplicate_serials = []
        duplicate_uins = []

        for index, row in df.iterrows():
            try:
                company_name = str(row.get('Company Name')).strip()
                model_name = str(row.get('Model Name')).strip()
                serial_number = str(row.get('Serial Number')).strip()
                uin_number = str(row.get('Uin')).strip()
                raw_date = row.get('Date of Model')

                if pd.isnull(raw_date):
                    raise ValueError("Date of Model is missing.")

                if isinstance(raw_date, str):
                    try:
                        date_of_model = datetime.strptime(raw_date, '%d-%m-%Y').date()
                    except ValueError:
                        date_of_model = datetime.strptime(raw_date, '%Y-%m-%d').date()
                else:
                    date_of_model = pd.to_datetime(raw_date).date()

                is_duplicate = False
                if CompanyDroneModelInfo.objects.filter(serial_number=serial_number).exists():
                    duplicate_serials.append(serial_number)
                    is_duplicate = True

                if CompanyDroneModelInfo.objects.filter(uin_number=uin_number).exists():
                    duplicate_uins.append(uin_number)
                    is_duplicate = True

                if is_duplicate:
                    errors.append(f"Row {index + 2}: Duplicate serial or UIN number")
                    continue

                CompanyDroneModelInfo.objects.create(
                    admin_id=admin.id,
                    company_name=company_name,
                    model_name=model_name,
                    serial_number=serial_number,
                    uin_number=uin_number,
                    date_of_model=date_of_model
                )
                success_count += 1

            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")

        if success_count > 0:
            response = {
                "message": f"{success_count} drone model(s) uploaded.",
                "s3_file_url": s3_url
            }

            if duplicate_serials or duplicate_uins:
                response["warning"] = "Some models already exist. Please try with different Serial Numbers and UINs."
                response["duplicate_serial_numbers"] = list(set(duplicate_serials))
                response["duplicate_uin_numbers"] = list(set(duplicate_uins))
                response["errors"] = errors

            return JsonResponse(response)

        else:
            return JsonResponse({
                "error": "All rows failed to upload. Possible duplicates or data issues.",
                "duplicate_serial_numbers": list(set(duplicate_serials)),
                "duplicate_uin_numbers": list(set(duplicate_uins)),
                "errors": errors
            }, status=400)

    except Exception as ex:
        return JsonResponse({"error": f"Unexpected error: {str(ex)}"}, status=500)
@csrf_exempt
def view_drone_models_by_admin(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')

        if not admin_id:
            return JsonResponse({"error": "Missing admin_id"}, status=400)

        drone_models = CompanyDroneModelInfo.objects.filter(admin_id=admin_id)

        if not drone_models.exists():
            return JsonResponse({"message": "No drone models found for this admin."})

        data = []
        for model in drone_models:
            data.append({
                "company_name": model.company_name,
                "model_name": model.model_name,
                "serial_number": model.serial_number,
                "uin_number": model.uin_number,
                "date_of_model": model.date_of_model.strftime('%d-%m-%Y'),
                "assign_drone_status":model.assign_status
            })

        return JsonResponse({"drone_models": data}, status=200)

    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
@csrf_exempt
def company_drone_status(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed"}, status=405)
    try:
        data = json.loads(request.body)
        admin_id = data.get('admin_id')
        role_id = data.get('role_id')
        uin_no = data.get('uin_no')
        update_type = data.get('update_type')

        if not uin_no:
            return JsonResponse({"error": "Missing uin_no"}, status=400)
        if not (admin_id or role_id):
            return JsonResponse({"error": "Either admin_id or role_id is required"}, status=400)
        if update_type not in ["request", "accept"]:
            return JsonResponse({"error": "update_type must be either 'request' or 'accept'"}, status=400)
        
        invoice_qs = InvoiceDetails.objects.filter(uin_no__icontains=uin_no)
        invoice = invoice_qs.first()
        if not invoice:
            return JsonResponse({"error": "No invoice found for given details"}, status=404)

        customer = invoice.customer
        if not customer:
            return JsonResponse({"error": "No customer linked with this invoice"}, status=404)

        drone_model_qs = CompanyDroneModelInfo.objects.filter(
            uin_number__iexact=uin_no.strip(),
            assign_status=1
        )
        drone_model_instance = drone_model_qs.first()
        if not drone_model_instance:
            return JsonResponse({"error": "No assigned drone model found for given details"}, status=404)
        agreement = AgreementDetails.objects.filter(drone_unique_code__icontains=uin_no).first()
        if not agreement:
            return JsonResponse({"error": "No agreement found for this UIN"}, status=404)
        
        admin = None
        if admin_id:
            admin = Admin.objects.filter(id=admin_id).first()
        if not admin:
            admin = Admin.objects.order_by("id").first()

        if not admin:
            return JsonResponse({"error": "No admin found in system"}, status=404)
        role=Role.objects.filter(id=role_id).first() if role_id else None
        if role:
            if update_type == "request" and role.company_name != "Pavaman Aviation":
                return JsonResponse({"error": "Only Pavaman Aviation role can request status"}, status=403)
            if update_type == "accept" and role.company_name != "Pavaman Agri Ventures":
                return JsonResponse({"error": "Only Pavaman Agri Ventures role can accept request"}, status=403)

        req, created = DroneOperation.objects.get_or_create(
            drone_model=drone_model_instance, 
            defaults={
                "customer": customer,
                "admin": admin,
                "role": role,    
                "agreement": agreement
            }
        )

        if update_type == "request":
            req.request_status = 1
            req.requested_on = timezone.now()
            req.save(update_fields=['request_status', 'requested_on'])

            return JsonResponse({
                "message": "Drone request status updated successfully.",
                "uin_no": uin_no,
                "request_status": req.request_status,
                "requested_on": req.requested_on,
                "agreement_id": req.agreement.id if req.agreement else None,
                "admin_id": req.admin.id if req.admin else None,
                "role_id": role.id if role else None,
                "customer": {
                    "id": customer.id,
                    "name": f"{customer.first_name} {customer.last_name}",
                    "email": customer.email
                }
            }, status=200)

        elif update_type == "accept":
            req.accept_status = 1
            req.accepted_on = timezone.now()
            req.save(update_fields=['accept_status', 'accepted_on'])

            return JsonResponse({
                "message": "Drone accept status updated successfully.",
                "uin_no": uin_no,
                "accept_status": req.accept_status,
                "accepted_on": req.accepted_on,
                "agreement_id": req.agreement.id if req.agreement else None,
                "role_id": req.role.id if req.role else None,
                "customer": {
                    "id": customer.id,
                    "name": f"{customer.first_name} {customer.last_name}",
                    "email": customer.email
                }
            }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def get_drone_status(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            admin_id= data.get('admin_id')
            role_id = data.get('role_id')
            if not (admin_id or role_id):
                return JsonResponse({"error": "Either admin_id or role_id is required"}, status=400)


            drone_operation = DroneOperation.objects.filter(admin_id).first()
            if not drone_operation:
                return JsonResponse({"error": "No drone operation found for this drone model"}, status=404)

            response_data = {
                "drone_model": {
                    "company_name": drone_operation.drone_model.company_name,
                    "model_name": drone_operation.drone_model.model_name,
                    "serial_number": drone_operation.drone_model.serial_number,
                    "uin_number": drone_operation.drone_model.uin_number,
                    "date_of_model": drone_operation.drone_model.date_of_model.strftime('%d-%m-%Y'),
                },
                "customer": {
                    "id": drone_operation.customer.id,
                    "name": f"{drone_operation.customer.first_name} {drone_operation.customer.last_name}",
                    "email": drone_operation.customer.email
                },
                "agreement_id": drone_operation.agreement.id if drone_operation.agreement else None,
                "request_status": drone_operation.request_status,
                "requested_on": drone_operation.requested_on.strftime('%Y-%m-%d %H:%M:%S') if drone_operation.requested_on else None,
                "accept_status": drone_operation.accept_status,
                "accepted_on": drone_operation.accepted_on.strftime('%Y-%m-%d %H:%M:%S') if drone_operation.accepted_on else None,
            }
            return JsonResponse(response_data, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)