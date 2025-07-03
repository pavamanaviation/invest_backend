from invest_app.utils.shared_imports import *
from invest_app.utils.s3_helper import generate_presigned_url
from .models import (Admin, CustomerRegister, KYCDetails, CustomerMoreDetails,
                      NomineeDetails, PaymentDetails, Permission, Role)

MODEL_LABELS = {
                "CustomerRegister": "Customer Registration Details",
                "KYCDetails": "KYC Details",
                "CustomerMoreDetails": "Customer More Details",
                "NomineeDetails": "Nominee Details",
                "PaymentDetails": "Payment Details"
            }

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

    return None  # OTP is valid


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

        # Define user models and session mappings
        user_types = [
            {
                "model": CustomerRegister,
                "session_key": "customer_id",
                "extra_check": lambda u: u.register_status == 1 and u.account_status == 1,
                "error": "Account is not active or verified."
            },
            {"model": Admin, "session_key": "admin_id"},
            {"model": Role, "session_key": "role_id"}
        ]

        for user_type in user_types:
            model = user_type["model"]
            user = model.objects.filter(
                Q(email=email) | Q(mobile_no=mobile_no)
            ).first()

            if user:
                # Validate OTP
                error = validate_otp_and_expiry(user, otp)
                if error:
                    return JsonResponse({"error": error}, status=400)

                # Extra user-type specific validation
                if "extra_check" in user_type and not user_type["extra_check"](user):
                    return JsonResponse({"error": user_type["error"]}, status=403)

                # OTP is valid, clear it and update session
                user.otp = None
                user.save(update_fields=["otp"])

                request.session[user_type["session_key"]] = user.id
                request.session.save()

                # Construct response
                response = {
                    "message": f"OTP verified and login successful ({user_type['session_key'].split('_')[0].capitalize()}).",
                    user_type["session_key"]: user.id,
                    "email": user.email,
                    "session_id": request.session.session_key
                }

                if user_type["session_key"] == "customer_id":
                    response["register_status"] = user.register_status
                    response["account_status"] = user.account_status

                return JsonResponse(response, status=200)

        return JsonResponse({"error": "Account not found."}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format."}, status=400)
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
        "bank_account_number": kyc.bank_account_number,
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
#         "bank_account_number": kyc.bank_account_number,
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
                kyc_records = kyc_records.filter(bank_account_number__icontains=bank_no)

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
