from django.urls import path
from .views import (
    OfficeDashboardStatsView, MyDashboardStatsView,
    EmployeeReportView, TimeLogReportView, InactiveStaffTasksReportView,
    ClientWiseReportView, TaskTypeWiseReportView, TaskActivityReportView,
    DeletedTasksReportView, AssignmentChangesReportView,
    ServiceStaffGridView, IssuesReportView, PerformersReportView, AuditLogView,
)

urlpatterns = [
    path('dashboard/office/', OfficeDashboardStatsView.as_view(), name='report_office_dashboard'),
    path('dashboard/my/', MyDashboardStatsView.as_view(), name='report_my_dashboard'),
    path('employees/', EmployeeReportView.as_view(), name='report_employees'),
    path('timelogs/', TimeLogReportView.as_view(), name='report_timelogs'),
    path('inactive-staff-tasks/', InactiveStaffTasksReportView.as_view(), name='report_inactive_staff_tasks'),
    path('clients/', ClientWiseReportView.as_view(), name='report_clients'),
    path('task-types/', TaskTypeWiseReportView.as_view(), name='report_task_types'),
    path('activity/', TaskActivityReportView.as_view(), name='report_activity'),
    path('deleted/', DeletedTasksReportView.as_view(), name='report_deleted'),
    path('assignment-changes/', AssignmentChangesReportView.as_view(), name='report_assignment_changes'),
    path('service-staff/', ServiceStaffGridView.as_view(), name='report_service_staff'),
    path('issues/', IssuesReportView.as_view(), name='report_issues'),
    path('performers/', PerformersReportView.as_view(), name='report_performers'),
    path('audit-log/', AuditLogView.as_view(), name='report_audit_log'),
]
