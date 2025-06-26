from invest_app.models import (CustomerRegister,Role,CustomerMoreDetails,
                               KYCDetails,Permission)
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.apps import apps
import json
from invest_app.views import MODEL_LABELS

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
