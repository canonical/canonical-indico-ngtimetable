from indico.web.forms.base import IndicoForm
from indico.web.forms.widgets import SwitchWidget
from wtforms.fields import BooleanField, IntegerField, SelectField
from wtforms.widgets import NumberInput

from . import _, ngettext


class NGTimetableSettingsForm(IndicoForm):
    use_track_colors = BooleanField(
        _("Prefer Track Colors"),
        widget=SwitchWidget(),
        description=_(
            "Prefer the track's default session color in the timetable. Use this to assign colors by tracks instead of sessions. Make sure you DON'T assign contributions to a session if you want them to show up on the main schedule."
        ),
    )
    granularity = SelectField(
        _("Granularity"),
        coerce=int,
        choices=[
            (1, ngettext("%d Minute", "%d Minutes", 1) % 1),
            (5, ngettext("%d Minute", "%d Minutes", 5) % 5),
            (15, ngettext("%d Minute", "%d Minutes", 15) % 15),
            (30, ngettext("%d Minute", "%d Minutes", 30) % 30),
        ],
        description=_(
            "How granular is an hour slot? At 30 minutes, an hour slot can fit two contributions. This is used to maximize space in the timetable."
        ),
    )

    hours_per_screen = IntegerField(
        _("Hours on screen"),
        widget=NumberInput(min=1, max=24),
        description=_(
            "How many hours to show at once (desktop). Adjust this to account for longer titles, but setting it too low will make it hard to get a big picture."
        ),
    )
