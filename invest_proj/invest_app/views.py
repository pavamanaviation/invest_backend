from datetime import timedelta
import random
import pytz
import json

from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import Admin, CustomerRegister,Role
from .sms_utils import send_otp_sms
from django.contrib.auth.hashers import check_password

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

