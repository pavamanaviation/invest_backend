from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
class Admin(models.Model):
    name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True)
    mobile_no = models.CharField(max_length=15, unique=True)
    otp = models.IntegerField(null=True, blank=True)
    otp_send_type = models.CharField(max_length=50, null=True, blank=True)
    changed_on = models.DateTimeField(null=True, blank=True)
    # password = models.CharField(max_length=255)  # change from 50 to 255
    # company_name = models.CharField(max_length=50)
    status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
    def __str__(self):
        return self.name

class Role(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True)
    # employee_id = models.CharField(max_length=15, unique=True)
    # password = models.CharField(max_length=255)
    mobile_no = models.CharField(max_length=15, unique=True)
    company_name = models.CharField(max_length=50)
    role_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    delete_status = models.BooleanField(default=False)  # Suggestion: False means not deleted
    otp = models.IntegerField(null=True, blank=True)
    otp_send_type = models.CharField(max_length=50, null=True, blank=True)
    changed_on = models.DateTimeField(null=True, blank=True)
    status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
    admin = models.ForeignKey(Admin, null=True, blank=True, on_delete=models.SET_NULL)
    
    def __str__(self):
        return f"{self.name} ({self.role_type})"
class CustomerRegister(models.Model):
    admin= models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)
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
    
    kyc_accept_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    payment_accept_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
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

    def __str__(self):
        return self.email
class KYCDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)    
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)
    pan_number = models.CharField(max_length=10, unique=True, null=True, blank=True)
    pan_request_id = models.CharField(max_length=100, null=True, blank=True)
    pan_group_id = models.CharField(max_length=100, null=True, blank=True)
    pan_name = models.CharField(max_length=100, null=True, blank=True)
    pan_dob = models.DateField(null=True, blank=True)
    pan_task_id = models.CharField(max_length=100, null=True, blank=True)
    idfy_pan_status = models.CharField(max_length=10, null=True, blank=True)
    pan_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    pan_path= models.CharField(max_length=250, null=True, blank=True)  # Path to the PAN document

    aadhar_number = models.CharField(max_length=12, unique=True, null=True, blank=True)
    aadhar_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    aadhar_task_id = models.CharField(max_length=100, blank=True, null=True)
    idfy_aadhar_status = models.CharField(max_length=10, null=True, blank=True)
    aadhar_path = models.CharField(max_length=250, null=True, blank=True)  # Path to the Aadhar document

    banck_account_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    banck_name = models.CharField(max_length=50, null=True, blank=True)
    ifsc_code = models.CharField(max_length=11, null=True, blank=True)
    banck_task_id = models.CharField(max_length=100, null=True, blank=True)
    idfy_bank_status = models.CharField(max_length=10, null=True, blank=True)
    bank_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    
    status = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"KYC for {self.customer.email}" if self.customer else "KYC Details"
class CustomerMoreDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    # customer_kyc = models.ForeignKey(KYCDetails, on_delete=models.CASCADE, null=True, blank=True)
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    district = models.CharField(max_length=50, null=True, blank=True)
    mandal = models.CharField(max_length=50, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=50, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)
    
    dob = models.DateField(null=True, blank  =True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    profession = models.CharField(max_length=50, null=True, blank=True)
    designation = models.CharField(max_length=50, null=True, blank=True)
    personal_status = models.IntegerField(default=0)  # 0 = Pending, 1 = Approved, 2 = Rejected
    selfie_path = models.CharField(max_length=250, null=True, blank=True)
    signature_path = models.CharField(max_length=250, null=True, blank=True)
    selfie_status=models.IntegerField(default=0)
    signature_status=models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"More Details for {self.customer.email}" if self.customer else "Customer More Details"

class NomineeDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)    
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    relation = models.CharField(max_length=50, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    address_proof= models.CharField(max_length=50, null=True, blank=True)  # e.g., "Aadhar", "PAN", etc.
    address_proof_path=models.CharField(max_length=250, null=True, blank=True)
    id_proof = models.CharField(max_length=50, null=True, blank=True)  # e.g., "Aadhar", "PAN", etc.
    id_proof_path = models.CharField(max_length=250, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    nominee_status= models.IntegerField(default=0)
    def __str__(self):
        return f"Nominee for {self.customer.email}" if self.customer else "Nominee Details"
class PaymentDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)    
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    payment_mode = models.CharField(max_length=40,default='card')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='created')  # created, paid, failed
    created_at = models.DateTimeField(auto_now_add=True)
