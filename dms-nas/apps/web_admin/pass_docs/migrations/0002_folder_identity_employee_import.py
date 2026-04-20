# Идентичность сотрудника по полному имени папки импорта (import_key / source_folder_name).

from django.db import migrations, models


def populate_employee_identity(apps, schema_editor):
    Employee = apps.get_model("pass_docs", "Employee")
    for emp in Employee.objects.iterator():
        code = (emp.employee_code or "").strip()
        import_key = code
        if code == "__COMMON_ORG__":
            source_folder_name = ""
            source_prefix = ""
            source_label = ""
        elif "&" in code:
            source_folder_name = code
            left, _, right = code.partition("&")
            source_prefix = left.strip()
            source_label = right.strip()
        else:
            source_folder_name = code
            source_prefix = code
            source_label = ""

        Employee.objects.filter(pk=emp.pk).update(
            import_key=import_key,
            source_folder_name=source_folder_name,
            source_prefix=source_prefix,
            source_label=source_label,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pass_docs", "0001_align_models_and_folder_import"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="import_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Уникальный ключ: для личных папок — полное имя каталога (1&Фамилия); для служебной записи общих документов — __COMMON_ORG__.",
                max_length=512,
                null=True,
                verbose_name="ключ импорта",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="source_folder_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Как в ФС под корнем импорта, напр. 1&Гусев. Пусто только у служебной записи общих документов.",
                max_length=512,
                verbose_name="имя папки в источнике",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="source_prefix",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Часть до первого «&» в имени папки (информативно, не уникальна).",
                max_length=64,
                verbose_name="префикс до &",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="source_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Часть после первого «&» (ФИО/фамилия из имени папки).",
                max_length=512,
                verbose_name="подпись после &",
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="employee_code",
            field=models.CharField(
                blank=True,
                help_text="Устаревший короткий код; не использовать как единственный ключ импорта.",
                max_length=64,
                null=True,
                unique=True,
                verbose_name="код сотрудника (legacy)",
            ),
        ),
        migrations.RunPython(populate_employee_identity, noop_reverse),
        migrations.AlterField(
            model_name="employee",
            name="import_key",
            field=models.CharField(
                db_index=True,
                help_text="Уникальный ключ: для личных папок — полное имя каталога (1&Фамилия); для служебной записи общих документов — __COMMON_ORG__.",
                max_length=512,
                unique=True,
                verbose_name="ключ импорта",
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="source_folder_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Как в ФС под корнем импорта, напр. 1&Гусев. Пусто только у служебной записи общих документов.",
                max_length=512,
                unique=True,
                verbose_name="имя папки в источнике",
            ),
        ),
        migrations.AlterModelOptions(
            name="employee",
            options={
                "ordering": ["import_key"],
                "verbose_name": "сотрудник",
                "verbose_name_plural": "сотрудники",
            },
        ),
    ]
