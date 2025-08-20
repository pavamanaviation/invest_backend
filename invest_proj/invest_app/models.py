from django.db import models
from django.utils import timezone
from datetime import timedelta
class Admin(models.Model):
    name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True,db_index=True)
    mobile_no = models.CharField(max_length=15, unique=True,db_index=True)
    otp = models.IntegerField(null=True, blank=True)
    otp_send_type = models.CharField(max_length=50, null=True, blank=True)
    changed_on = models.DateTimeField(null=True, blank=True)
    # password = models.CharField(max_length=255)  # change from 50 to 255
    # company_name = models.CharField(max_length=50)
    status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
    def __str__(self):
        return self.name
    
class CompanyDroneModelInfo(models.Model):
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    company_name = models.CharField(max_length=150, default='Pavaman Aviation Private Limited')
    model_name = models.CharField(max_length=100, default='TEJAS')
    serial_number = models.CharField(max_length=100)
    uin_number = models.CharField(max_length=100)
    date_of_model = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(default=1)
    assign_status = models.IntegerField(default=0)#if once assign for agreement update as 1

    def __str__(self):
        return f"{self.model_name} - {self.serial_number}"


class Role(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True,db_index=True)
    # employee_id = models.CharField(max_length=15, unique=True)
    # password = models.CharField(max_length=255)
    mobile_no = models.CharField(max_length=15, unique=True,db_index=True)
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
    email = models.EmailField(max_length=50,unique=True,null=True, blank=True,db_index=True)
    mobile_no = models.CharField(max_length=15, default='',db_index=True)
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
    aadhar_gender= models.CharField(max_length=10, null=True, blank=True)  #
    bank_account_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    bank_name = models.CharField(max_length=50, null=True, blank=True)
    ifsc_code = models.CharField(max_length=11, null=True, blank=True)
    bank_task_id = models.CharField(max_length=100, null=True, blank=True)
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
    
    present_address = models.TextField(null=True, blank=True)
    present_district = models.CharField(max_length=50, null=True, blank=True)
    present_mandal = models.CharField(max_length=50, null=True, blank=True)
    present_city = models.CharField(max_length=50, null=True, blank=True)
    present_state = models.CharField(max_length=50, null=True, blank=True)
    present_country = models.CharField(max_length=50, null=True, blank=True)
    present_pincode = models.CharField(max_length=10, null=True, blank=True)
    same_address = models.BooleanField(default=False)  # True if present address is same as permanent address
    

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
    status=models.IntegerField(default=1)
    guardian_name = models.CharField(max_length=100, null=True, blank=True)
    guardian_relation = models.CharField(max_length=50, null=True, blank=True)

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
    status=models.IntegerField(default=1)
    share=models.FloatField(default=0.0)
    address=models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Nominee for {self.customer.email}" if self.customer else "Nominee Details"
    
class PaymentDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)    
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    payment_mode = models.CharField(max_length=40,default='unknown')
    part_number = models.IntegerField(default=1)  # 1, 2, or 3
    total_amount = models.DecimalField(max_digits=50, decimal_places=2,default=0.0)
    amount = models.DecimalField(max_digits=50, decimal_places=2,default=0.0)
    quantity= models.IntegerField(default=1)
    drone_order_id = models.CharField(max_length=50, null=True, blank=True) 
    payment_type = models.CharField(max_length=20, default='unknown')  # 'installment' or 'full'
    drone_payment_status = models.CharField(max_length=20, default='created')  # created, paid, failed
    created_at = models.DateTimeField(auto_now_add=True)
    payment_status= models.IntegerField(default=0)
    status=models.IntegerField(default=1)
    
from django.db.models import JSONField
class InvoiceDetails(models.Model):
    customer = models.ForeignKey(CustomerRegister, on_delete=models.CASCADE)
    customer_more = models.ForeignKey(CustomerMoreDetails, on_delete=models.CASCADE, null=True, blank=True)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    # role= models.ForeignKey('Role', on_delete=models.CASCADE, null=True, blank=True)
    drone_model_ids = models.JSONField(default=list, blank=True, null=True)

    payment= models.ForeignKey(PaymentDetails, on_delete=models.CASCADE, null=True, blank=True)   
    serial_no=models.IntegerField(default=1)
    invoice_number = models.CharField(max_length=50)
    uin_no = models.CharField(max_length=100, null=True, blank=True)  # UIN number of the drone 
    parts_quantity = models.IntegerField(default=1)
    hsn_sac_code = models.CharField(max_length=20, null=True, blank=True)
    uom = models.CharField(max_length=20, null=True, blank=True)  # Unit of Measure
    rate_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    cgst= models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    sgst= models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    igst= models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_taxable_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_invoice_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_invoice_amount_words = models.CharField(max_length=255,default="")
    address_type = models.CharField(
        max_length=10,
        choices=(
            ('permanent', 'Permanent Address'),
            ('present', 'Present Address'),
        ),
        default='permanent'
    )
    description = models.TextField(max_length=255, default='TEJA-S (UIN Drone)')
    invoice_type = models.CharField(choices=(('drone', 'Drone'),
                                              ('accessory', 'Accessory'),
                                              ('amc', 'AMC')
                                              ), max_length=20, default='drone')
    invoice_status=models.IntegerField(default=0) 
    total_invoice_status=models.IntegerField(default=0)
    status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} for {self.customer.email}" if self.customer else "Drone Invoice"
class Permission(models.Model):
    model_name = models.CharField(max_length=100)
    can_add = models.BooleanField(default=False)
    can_view = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    admin = models.ForeignKey(Admin, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class AgreementDetails(models.Model):
    agreement_no = models.CharField(max_length=100)
    agreement_date = models.DateField()
    agreement_day = models.CharField(max_length=50)
    agreement_month = models.CharField(max_length=50)
    agreement_year_full = models.IntegerField()
    agreement_year_short = models.CharField(max_length=50)
    from_date = models.DateField()
    to_date = models.DateField()
    drone_name = models.CharField(max_length=100)
    drone_unique_code = models.CharField(max_length=100)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    witness_leassor = models.CharField(max_length=100)
    witness_lessee = models.CharField(max_length=100)
    customer = models.ForeignKey('CustomerRegister', on_delete=models.CASCADE)
    customer_more = models.ForeignKey('CustomerMoreDetails', on_delete=models.CASCADE, null=True, blank=True)
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(default=1)  # 1 = Active, 0 = Inactive

    def __str__(self):
        return f"Agreement {self.agreement_no}"