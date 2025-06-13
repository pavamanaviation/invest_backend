from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
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
    email = models.EmailField(max_length=50,unique=True,null=True, blank=True)
    mobile_no = models.CharField(max_length=15, default='')
    created_at =  models.DateTimeField(auto_now_add=True)
    
    otp = models.IntegerField(null=True, blank=True)
    otp_send_type = models.CharField(max_length=50, null=True, blank=True)
    changed_on = models.DateTimeField(null=True, blank=True)
    register_type = models.CharField(max_length=20,default='Manual')

    register_status = models.IntegerField(default=0)
    account_status = models.IntegerField(default=0)
    status = models.IntegerField(default=1)
    def is_otp_valid(self):
        """Check if OTP is still valid (within 2 minutes)."""
        if self.changed_on:
            expiry_time = self.changed_on + timedelta(minutes=2)
            return timezone.now() < expiry_time
        return False

    def clear_expired_otp(self):
        """Set OTP to NULL if expired."""
        if not self.is_otp_valid():
            self.otp = None
            self.changed_on = None
            self.save()
    # admin = models.ForeignKey('Admin', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.email
class KYCDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    pan_number = models.CharField(max_length=10, unique=True, null=True, blank=True)
    pan_request_id = models.CharField(max_length=100, null=True, blank=True)
    pan_group_id = models.CharField(max_length=100, null=True, blank=True)
    pan_name = models.CharField(max_length=100, null=True, blank=True)
    pan_dob = models.DateField(null=True, blank=True)
    pan_task_id = models.CharField(max_length=100, null=True, blank=True)
    idfy_pan_status = models.CharField(max_length=10, null=True, blank=True)
    pan_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    

    aadhar_number = models.CharField(max_length=12, unique=True, null=True, blank=True)
    adhaar_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    banck_account_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    banck_name = models.CharField(max_length=50, null=True, blank=True)
    ifsc_code = models.CharField(max_length=11, null=True, blank=True)
    bank_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"KYC for {self.customer.email}" if self.customer else "KYC Details"