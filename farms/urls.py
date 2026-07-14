from django.urls import path

from farms.views import (
    audit_log_view,
    complete_today_tasks_view,
    export_csv_view,
    export_user_data_view,
    farm_settings_view,
    profitability_view,
    set_module_pin_view,
    task_center_view,
)


urlpatterns = [
    path(
        '',
        farm_settings_view,
        name='farm_settings',
    ),
    path(
        'eksport-danych/',
        export_user_data_view,
        name='export_user_data',
    ),
    path(
        'eksport-csv/',
        export_csv_view,
        name='export_csv',
    ),
    path(
        'historia-zmian/',
        audit_log_view,
        name='audit_log',
    ),
    path(
        'centrum-zadan/',
        task_center_view,
        name='task_center',
    ),
    path(
        'centrum-zadan/dzisiaj/wykonaj/',
        complete_today_tasks_view,
        name='complete_today_tasks',
    ),
    path(
        'analityka-oplacalnosci/',
        profitability_view,
        name='profitability',
    ),
    path(
        'moduly/przypnij/',
        set_module_pin_view,
        name='set_module_pin',
    ),
]
