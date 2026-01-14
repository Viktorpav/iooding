from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='semantic_summary',
            field=models.TextField(blank=True, help_text='AI-generated semantic map of the post'),
        ),
    ]
