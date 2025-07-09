from invest_app.utils.shared_imports import *

from invest_app.models import (CustomerRegister,Role,CustomerMoreDetails,
                               KYCDetails,Permission)
from invest_app.views import MODEL_LABELS


@csrf_exempt
def get_all_models_by_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')

        if not role_id:
            return JsonResponse({'error': 'role_id is required'}, status=400)

        # Validate and get the active role
        try:
            role = Role.objects.get(id=role_id, status=1)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found or inactive'}, status=404)


        return JsonResponse({
            "role_id": role_id,
            "role_name":role.first_name+" "+role.last_name,
            "role_type": role.role_type,
            "role_company": role.company_name,
            "model_names": MODEL_LABELS
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

ALLOWED_ROLE_TYPES = ['Marketing Executive', 'Financial Executive']
ALLOWED_COMPANIES = ['Pavaman Aviation', 'Pavaman Agriventure']

def get_kyc_details(role):
    if role.role_type in ALLOWED_ROLE_TYPES and role.company_name in ALLOWED_COMPANIES:
        queryset = KYCDetails.objects.select_related('customer').all()
        data = []

        for obj in queryset:
            record = {
                "customer_name": f"{obj.customer.first_name} {obj.customer.last_name}",
                "pan_name": "",
                "pan_number": "",
                "pan_status": obj.pan_status,
                "pan_verify_status": "",
                "aadhar_number": "",
                "aadhar_status": obj.aadhar_status,
                "aadhar_verify_status": "",
                "bank_account_number": "",
                "bank_ifsc_code": "",
                "bank_name": ""
            }

            if obj.pan_status == 1 and obj.idfy_pan_status == "completed":
                record["pan_name"] = obj.pan_name or ""
                record["pan_number"] = obj.pan_number or ""
                record["pan_verify_status"] = obj.idfy_pan_status or ""

            if obj.aadhar_status == 1 and obj.idfy_aadhar_status == "completed":
                record["aadhar_number"] = obj.aadhar_number or ""
                record["aadhar_verify_status"] = obj.idfy_aadhar_status or ""

            if role.role_type == "Financial Executive":
                if obj.bank_status == 1 and obj.idfy_bank_status == "completed":
                    record["bank_account_number"] = obj.bank_account_number or ""
                    record["bank_ifsc_code"] = obj.ifsc_code or ""
                    record["bank_name"] = obj.bank_name or ""

            data.append(record)

        return data
    return None


def get_customer_more_details(role):
    if role.role_type in ALLOWED_ROLE_TYPES and role.company_name in ALLOWED_COMPANIES:
        queryset = CustomerMoreDetails.objects.select_related('customer').filter(status=1)
        data = []

        for obj in queryset:
            record = {
                "customer_name": f"{obj.customer.first_name} {obj.customer.last_name}",
                "email": obj.customer.email,
                # "phone": obj.customer.phone_number,
                "address": obj.address or "",
                "district": obj.district or "",
                "mandal": obj.mandal or "",
                "city": obj.city or "",
                "state": obj.state or "",
                "country": obj.country or "",
                "pincode": obj.pincode or "",
                "dob": obj.dob.strftime('%Y-%m-%d') if obj.dob else "",
                "gender": obj.gender or "",
                "profession": obj.profession or "",
                "designation": obj.designation or "",
                "personal_status": obj.personal_status,
                "selfie_path": obj.selfie_path or "",
                "signature_path": obj.signature_path or "",
                "selfie_status": obj.selfie_status,
                "signature_status": obj.signature_status,
                "created_at": obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            data.append(record)

        return data
    return None


@csrf_exempt
def get_models_data_by_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')
        model_name = data.get('model_name')

        if not role_id or not model_name:
            return JsonResponse({'error': 'role_id and model_name are required'}, status=400)

        try:
            role = Role.objects.get(id=role_id, status=1)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)

        if model_name not in MODEL_LABELS:
            return JsonResponse({'error': f'Model "{model_name}" not recognized.'}, status=400)

        if model_name == 'KYCDetails':
            result = get_kyc_details(role)
        elif model_name == 'CustomerMoreDetails':
            result = get_customer_more_details(role)
        else:
            return JsonResponse({'error': 'This model is not handled yet.'}, status=400)

        if result is not None:
            return JsonResponse({
                'model': model_name,
                'label': MODEL_LABELS[model_name],
                'data': result
            }, status=200)
        else:
            return JsonResponse({
                'error': 'Permission denied: Role type or company not allowed to view this data.'
            }, status=403)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


#keep it for backup
"""
@csrf_exempt
def get_model_names_by_role(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')

        if not role_id:
            return JsonResponse({'error': 'role_id is required'}, status=400)

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)

        model_names = Permission.objects.filter(role=role).values_list('model_name', flat=True).distinct()

        return JsonResponse({
            "role_id": role_id,
            "model_names": list(model_names)
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
#keep it for backup    
@csrf_exempt
def get_model_data_by_role_and_model(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        role_id = data.get('role_id')
        model_name = data.get('model_name')

        if not role_id or not model_name:
            return JsonResponse({'error': 'role_id and model_name are required'}, status=400)

        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return JsonResponse({'error': 'Role not found'}, status=404)

        try:
            permission = Permission.objects.get(role=role, model_name=model_name)
        except Permission.DoesNotExist:
            return JsonResponse({'error': 'No permissions found for this model and role'}, status=403)

        try:
            model_class = apps.get_model('invest_app', model_name)
        except LookupError:
            return JsonResponse({'error': f'Model "{model_name}" not found'}, status=404)

        data_list = []
        if permission.can_view:
            data_list = list(model_class.objects.all().values())

        return JsonResponse({
            "role_id": role_id,
            "model_name": model_name,
            "can_add": permission.can_add,
            "can_view": permission.can_view,
            "can_edit":permission.can_edit,
            "can_delete": permission.can_delete,
            "data": data_list if permission.can_view else []
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    


# @csrf_exempt
# def get_model_data_by_role(request):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Only POST method allowed'}, status=405)

#     try:
#         data = json.loads(request.body)
#         role_id = data.get('role_id')

#         if not role_id:
#             return JsonResponse({'error': 'role_id is required'}, status=400)

#         # Get role and its permissions
#         try:
#             role = Role.objects.get(id=role_id)
#         except Role.DoesNotExist:
#             return JsonResponse({'error': 'Role not found'}, status=404)

#         permissions = Permission.objects.filter(role=role, can_view=True)
#         if not permissions:
#             return JsonResponse({'message': 'No viewable model data for this role'}, status=200)

#         model_data = {}

#         for perm in permissions:
#             model_name = perm.model_name

#             try:
#                 model = apps.get_model('invest_app', model_name)
#                 # Get all objects from the model and convert to list of dicts
#                 model_objects = list(model.objects.all().values())

#                 model_data[model_name] = {
#                     "label": MODEL_LABELS.get(model_name, model_name),
#                     "records": model_objects
#                 }

#             except LookupError:
#                 continue  # Skip if model not found

#         return JsonResponse({"model_data": model_data}, status=200)

#     except json.JSONDecodeError:
#         return JsonResponse({'error': 'Invalid JSON format'}, status=400)
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)
"""