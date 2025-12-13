"""
Order Forms for Create and Edit Operations
"""

from django import forms
from .models import Order, Stock
from reference_data.models import Client, Broker


class OrderForm(forms.ModelForm):
    """
    Form for creating and editing orders

    Excludes workflow fields (created_by, approved_by, status, etc.)
    which are managed programmatically
    """

    class Meta:
        model = Order
        fields = [
            'stock',
            'side',
            'order_type',
            'quantity',
            'price',
            'stop_price',
            'client',
            'broker',
            'validity',
            'notes',
        ]
        widgets = {
            'stock': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'side': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'order_type': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'required': True
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'stop_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            }),
            'client': forms.Select(attrs={
                'class': 'form-select'
            }),
            'broker': forms.Select(attrs={
                'class': 'form-select'
            }),
            'validity': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes about this order...'
            }),
        }
        help_texts = {
            'price': 'Required for LIMIT and STOP_LOSS_LIMIT orders',
            'stop_price': 'Required for STOP_LOSS and STOP_LOSS_LIMIT orders',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Make price and stop_price not required by default (validated in clean method)
        self.fields['price'].required = False
        self.fields['stop_price'].required = False

        # Filter active stocks only
        self.fields['stock'].queryset = Stock.objects.filter(is_active=True).order_by('symbol')

        # Filter active clients and brokers only
        self.fields['client'].queryset = Client.objects.filter(is_active=True).order_by('name')
        self.fields['broker'].queryset = Broker.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        order_type = cleaned_data.get('order_type')
        price = cleaned_data.get('price')
        stop_price = cleaned_data.get('stop_price')
        quantity = cleaned_data.get('quantity')

        # Validate price based on order type
        if order_type in ['LIMIT', 'STOP_LOSS_LIMIT']:
            if not price:
                self.add_error('price', f'Price is required for {order_type} orders')
            elif price <= 0:
                self.add_error('price', 'Price must be greater than 0')

        # Validate stop_price based on order type
        if order_type in ['STOP_LOSS', 'STOP_LOSS_LIMIT']:
            if not stop_price:
                self.add_error('stop_price', f'Stop price is required for {order_type} orders')
            elif stop_price <= 0:
                self.add_error('stop_price', 'Stop price must be greater than 0')

        # Validate quantity
        if quantity and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than 0')

        return cleaned_data


class OrderRejectForm(forms.Form):
    """
    Form for rejecting an order
    Requires rejection reason
    """
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Please provide a detailed reason for rejection...',
            'required': True
        }),
        help_text='Provide a clear explanation for why this order is being rejected',
        min_length=10,
        max_length=1000
    )

    def clean_rejection_reason(self):
        reason = self.cleaned_data.get('rejection_reason')
        if reason and len(reason.strip()) < 10:
            raise forms.ValidationError('Rejection reason must be at least 10 characters')
        return reason.strip()


class OrderFilterForm(forms.Form):
    """
    Form for filtering orders in list view
    """
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Order.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    side = forms.ChoiceField(
        choices=[('', 'All Sides')] + Order.SIDE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    order_type = forms.ChoiceField(
        choices=[('', 'All Types')] + Order.ORDER_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    stock = forms.ModelChoiceField(
        queryset=Stock.objects.filter(is_active=True).order_by('symbol'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='All Stocks'
    )
    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(is_active=True).order_by('name'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='All Clients'
    )
