from django.urls import path
from . import views

app_name = 'query_builder'

urlpatterns = [
    path('',                              views.builder,          name='builder'),
    path('run/',                          views.run_query,        name='run_query'),
    path('export/',                       views.export,           name='export'),
    path('saved/',                        views.saved_reports,    name='saved_reports'),
    path('saved/save/',                   views.save_template,    name='save_template'),
    path('saved/<int:template_id>/delete/', views.delete_template, name='delete_template'),
    path('sql-editor/',                   views.sql_editor,       name='sql_editor'),
    path('sql-editor/run/',               views.run_raw_sql,      name='run_raw_sql'),
    path('api/schema/',                   views.api_schema,       name='api_schema'),
    path('api/join-options/',             views.api_join_options, name='api_join_options'),
]
