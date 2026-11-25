from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('clients', '0005_client_dimension_fallback_source')]

    operations = [
        migrations.AddField(
            model_name='client',
            name='cubic_dimension_confirmation_factor',
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal('10'),
                help_text=(
                    'Require Contact Center or Customer Service confirmation when the recorded '
                    'cubic volume differs from length × width × height by this factor or more.'
                ),
                max_digits=8,
                validators=[MinValueValidator(Decimal('1.001'))],
            ),
        ),
    ]
