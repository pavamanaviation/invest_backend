"""
URL configuration for invest_proj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from invest_app.views import (add_role, view_kyc_doc,view_roles,delete_role,update_role,get_models_by_admin,assign_role_permissions,view_role_permissions_by_admin,
verify_otp,admin_customer_details,admin_customer_kyc_details,admin_nominee_details,)

# from invest_app.views import check_indian_time 
from invest_app.customer_views import (customer_register, get_pan_verification_status, match_selfie_with_s3_document, verify_aadhar_document,verify_customer_otp,customer_register_sec_phase,
customer_login,verify_pan_document,get_pan_source_verification_status,get_aadhar_verification_status,
bank_account_verification_view,customer_more_details,customer_profile_view,
upload_pdf_document,verify_and_save_nominee,create_drone_order,razorpay_callback,payment_status_check,
initiate_nominee_registration,preview_customer_details,verify_and_update_nominee
)

from invest_app.role_views import (get_model_names_by_role,get_model_data_by_role_and_model)
urlpatterns = [
    #admin urls
    path('admin/', admin.site.urls),
    path('verify-otp', verify_otp, name='verify_otp'),
    path('permission-data',get_models_by_admin,name="permission_data"),
    path('assign-role-permissions',assign_role_permissions,name='assign_role_permissions'),
    path('view-all-role-permissions',view_role_permissions_by_admin,name='view_role_permissions_by_admin'),
    path('add-role', add_role, name='add_role'),
    path('view-roles', view_roles,name='view_roles'), 
    path('delete-role', delete_role, name='delete_role'),
    path('update-role', update_role, name='update_role'),


    path('admin-customer-details',admin_customer_details,name='admin_customer_details'),
    path('admin-customer-kyc-details',admin_customer_kyc_details,name='admin_customer_kyc_details'),
    path('admin-nominee-details', admin_nominee_details, name='admin_nominee_details'),
    path("api/view-kyc-doc/", view_kyc_doc, name="view_kyc_doc"),
    #customer urls
    path('customer-register', customer_register, name='customer_register'),
    path('verify-customer-otp', verify_customer_otp, name='verify_customer_otp'),
    path('customer-register-sec-phase', customer_register_sec_phase, name='customer_register_sec_phase'),
    path('customer-login', customer_login, name='customer_login'),
    path('verify-pan', verify_pan_document,name='verify_pan_document'),
    path('get-pan-source-verification-status', get_pan_source_verification_status, name='get_pan_source_verification_status'),
    path('get-pan-verification-status', get_pan_verification_status, name='get_pan_verification_status'),
    
    path('verify-aadhar-document', verify_aadhar_document,name='verify_aadhar_document'),
    path('get-aadhar-verification-status', get_aadhar_verification_status, name='get_aadhar_verification_status'),
    # path('matchselfie_with_s3_document',match_selfie_with_s3_document, name='match_selfie_with_s3_document'),
    
    # path('verify-pan', pan_verification_request_view, name='verify_pan'),
    # path('verify-pan-result', pan_verification_result_view, name='verify_pan_result'),
    # path('verify-pandoc', pan_ocr_upload_view, name='pan_ocr_upload_view'),

    # path('verify-aadhar-lite', aadhar_lite_verification_view,name='aadhar_lite_verification'),
    path('verify-banck-account', bank_account_verification_view, name='bank_account_verification'),
    path('customer-more-details', customer_more_details, name='customer_more_details'),
    path('customer-profile', customer_profile_view, name='customer_profile'),
    path('upload-pdf-document', upload_pdf_document, name='upload_pdf_document'),
    path('add-nominee', verify_and_save_nominee, name='verify_and_save_nominee'),
    path('initiate-nominee',initiate_nominee_registration, name='initiate_nominee_registration'),

    # path('nominee-details', verify_and_save_nominee, name='verify_and_save_nominee'),
    # path('nominee-registration',initiate_nominee_registration, name='initiate_nominee_registration'),
    path('edit-nominee',verify_and_update_nominee, name='verify_and_update_nominee'),

    path('preview-customer-details',preview_customer_details,name='preview_customer_details'),
    
    path('create-drone-order', create_drone_order, name='create_drone_order'),
    path('razorpay-callback', razorpay_callback, name='razorpay_callback'),
    path('payment-status-check', payment_status_check, name='payment_status_check'),

    #role urls
    path('get-models-names',get_model_names_by_role,name='get_model_names_by_role'),
    path('get-details',get_model_data_by_role_and_model,name='get_model_data_by_role_and_model')

    
]
