from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pass_docs", "0003_package_request_status_building_failed"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="manual_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="ручные данные (корректировка)",
            ),
        ),
    ]
