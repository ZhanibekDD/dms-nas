import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pass_docs", "0004_employee_manual_data"),
    ]

    operations = [
        # 1. Новая модель TrainingJournal
        migrations.CreateModel(
            name="TrainingJournal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=512, verbose_name="название")),
                ("code", models.CharField(max_length=64, unique=True, verbose_name="код")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="порядок")),
            ],
            options={
                "verbose_name": "журнал обучения",
                "verbose_name_plural": "журналы обучения",
                "ordering": ["sort_order", "name"],
            },
        ),
        # 2. Новые поля в DocumentType
        migrations.AddField(
            model_name="documenttype",
            name="is_other",
            field=models.BooleanField(
                default=False,
                help_text="Документ показывается в разделе «Прочие документы» карточки сотрудника.",
                verbose_name="прочий документ",
            ),
        ),
        migrations.AddField(
            model_name="documenttype",
            name="training_journal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="document_types",
                to="pass_docs.trainingjournal",
                verbose_name="журнал обучения",
                help_text="При загрузке протокола автоматически создаётся запись в этом журнале.",
            ),
        ),
        # 3. Новая модель JournalEntry
        migrations.CreateModel(
            name="JournalEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("protocol_number", models.CharField(blank=True, max_length=128, verbose_name="номер протокола")),
                ("protocol_date", models.DateField(blank=True, null=True, verbose_name="дата протокола")),
                ("commission_member_1", models.CharField(blank=True, max_length=255, verbose_name="член комиссии 1")),
                ("commission_member_2", models.CharField(blank=True, max_length=255, verbose_name="член комиссии 2")),
                ("commission_member_3", models.CharField(blank=True, max_length=255, verbose_name="член комиссии 3")),
                ("training_center", models.CharField(blank=True, max_length=512, verbose_name="учебный центр")),
                ("is_auto", models.BooleanField(default=True, verbose_name="создано автоматически")),
                ("notes", models.TextField(blank=True, verbose_name="заметки")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "journal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="pass_docs.trainingjournal",
                        verbose_name="журнал",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="journal_entries",
                        to="pass_docs.employee",
                        verbose_name="сотрудник",
                    ),
                ),
                (
                    "employee_document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journal_entries",
                        to="pass_docs.employeedocument",
                        verbose_name="документ",
                    ),
                ),
            ],
            options={
                "verbose_name": "запись журнала",
                "verbose_name_plural": "записи журнала",
                "ordering": ["-protocol_date", "employee__full_name"],
            },
        ),
    ]
