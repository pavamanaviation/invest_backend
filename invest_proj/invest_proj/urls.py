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

# from invest_app.views import check_indian_time 
from invest_app.customer_views import (customer_register,verify_customer_otp,customer_register_sec_phase)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('customer-register', customer_register, name='customer_register'),
    path('verify-customer-otp', verify_customer_otp, name='verify_customer_otp'),
    path('customer-register-sec-phase', customer_register_sec_phase, name='customer_register_sec_phase'),
]
