from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def currency_list(request):
    """Currency list view - To be fully implemented"""
    return render(request, 'reference_data/currency_list.html', {})

@login_required
def currency_detail(request, code):
    """Currency detail view - To be fully implemented"""
    return render(request, 'reference_data/currency_detail.html', {})

@login_required
def broker_list(request):
    """Broker list view - To be fully implemented"""
    return render(request, 'reference_data/broker_list.html', {})

@login_required
def broker_create(request):
    """Broker create view - To be fully implemented"""
    return render(request, 'reference_data/broker_form.html', {})

@login_required
def broker_detail(request, pk):
    """Broker detail view - To be fully implemented"""
    return render(request, 'reference_data/broker_detail.html', {})

@login_required
def broker_edit(request, pk):
    """Broker edit view - To be fully implemented"""
    return render(request, 'reference_data/broker_form.html', {})

@login_required
def calendar_list(request):
    """Trading calendar list view - To be fully implemented"""
    return render(request, 'reference_data/calendar_list.html', {})

@login_required
def client_list(request):
    """Client list view - To be fully implemented"""
    return render(request, 'reference_data/client_list.html', {})

@login_required
def client_create(request):
    """Client create view - To be fully implemented"""
    return render(request, 'reference_data/client_form.html', {})

@login_required
def client_detail(request, pk):
    """Client detail view - To be fully implemented"""
    return render(request, 'reference_data/client_detail.html', {})

@login_required
def client_edit(request, pk):
    """Client edit view - To be fully implemented"""
    return render(request, 'reference_data/client_form.html', {})
