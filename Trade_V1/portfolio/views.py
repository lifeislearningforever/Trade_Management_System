from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def portfolio_list(request):
    """Portfolio list view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_list.html', {})

@login_required
def portfolio_create(request):
    """Portfolio create view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_form.html', {})

@login_required
def portfolio_detail(request, pk):
    """Portfolio detail view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_detail.html', {})

@login_required
def portfolio_edit(request, pk):
    """Portfolio edit view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_form.html', {})

@login_required
def portfolio_submit(request, pk):
    """Portfolio submit view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_detail.html', {})

@login_required
def portfolio_approve(request, pk):
    """Portfolio approve view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_detail.html', {})

@login_required
def portfolio_reject(request, pk):
    """Portfolio reject view - To be fully implemented"""
    return render(request, 'portfolio/portfolio_detail.html', {})
