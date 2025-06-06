from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
# class Admin(models.Model):
#     name = models.CharField(max_length=50)
#     email = models.EmailField(max_length=50, unique=True)
#     mobile_no = models.CharField(max_length=15, unique=True)
#     otp = models.IntegerField(null=True, blank=True)
#     password = models.CharField(max_length=50)
#     # company_name = models.CharField(max_length=50)
#     status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
#     def __str__(self):
#         return self.name

# class Role(models.Model):
#     name = models.CharField(max_length=50)
#     email = models.EmailField(max_length=50, unique=True)
#     # employee_id = models.CharField(max_length=15, unique=True)
#     password = models.CharField(max_length=255)
#     mobile_no = models.CharField(max_length=15, unique=True)
#     company_name = models.CharField(max_length=50)
#     role_type = models.CharField(max_length=50)
#     created_at = models.DateTimeField(auto_now_add=True)
#     delete_status = models.BooleanField(default=False)  # Suggestion: False means not deleted
#     status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
#     admin = models.ForeignKey(Admin, null=True, blank=True, on_delete=models.SET_NULL)
    
#     def __str__(self):
#         return f"{self.name} ({self.role_type})"
class CustomerRegister(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50,unique=True)
    mobile_no = models.CharField(max_length=15, default='')
    created_at =  models.DateTimeField(auto_now_add=True)
    
    otp = models.IntegerField(null=True, blank=True)
    otp_send_type = models.CharField(max_length=50, null=True, blank=True)
    changed_on = models.DateTimeField(null=True, blank=True)
    register_type = models.CharField(max_length=20,default='Manual')

    register_status = models.IntegerField(default=0)
    account_status = models.IntegerField(default=0)
    status = models.IntegerField(default=1)  
    # admin = models.ForeignKey('Admin', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.email