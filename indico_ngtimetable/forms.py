from indico.web.forms.base import IndicoForm
from indico.web.forms.widgets import SwitchWidget
from markupsafe import Markup
from wtforms import Field
from wtforms.fields import BooleanField

from . import _


class HTMLDescriptionField(Field):
    def __init__(self, label="", validators=None, html="", **kwargs):
        super(HTMLDescriptionField, self).__init__(label, validators, **kwargs)
        self.html = html

    def __call__(self, **kwargs):
        return Markup(self.html)


class NGTimetableSettingsForm(IndicoForm):
    default_settings = {"timetable_use_track_colors": True, "description": None}

    description = HTMLDescriptionField(
        "Rules",
        html=_(
            """
        <p>This timetable is somewhat opinionated. It won't adapt to all situations. You should be aware of the following:</p>
        <ul>
          <li>Contributions should start at :00 or :30 of any given hour. They will be shown as multiples of :30 minutes to maximize space.</li>
          <li>Contributions less than 20 minutes will not show, unless they are in a session block (e.g. Lightning Talks)</li>
          <li>Each contribution needs a room assigned, your conference revolves around having sessions in a limited set of rooms.</li>
          <li>Your conference goes at most 7 days. More is ok, but weekday names are used to identify days.</li>
          <li>Make sure you set a room on all contributions and session blocks.</li>
        </ul>
    """
        ),
    )
    timetable_use_track_colors = BooleanField(
        _("Prefer Track Colors"),
        widget=SwitchWidget(),
        description=_(
            "Prefer the track's default session color in the timetable. Use this to assign colors by tracks instead of sessions. Make sure you DON'T assign contributions to a session if you want them to show up on the main schedule."
        ),
    )
