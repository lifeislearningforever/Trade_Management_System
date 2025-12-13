from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def udf_type_list(request):
    """UDF Type list view - To be fully implemented"""
    return render(request, 'udf/udf_type_list.html', {})

@login_required
def udf_type_create(request):
    """UDF Type create view - To be fully implemented"""
    return render(request, 'udf/udf_type_form.html', {})

@login_required
def udf_type_edit(request, pk):
    """UDF Type edit view - To be fully implemented"""
    return render(request, 'udf/udf_type_form.html', {})
