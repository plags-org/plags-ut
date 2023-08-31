from typing import Dict

from django.forms import Form
from django.forms.fields import CharField, Field
from django.forms.widgets import HiddenInput, Textarea
from django.utils.html import conditional_escape
from django.utils.safestring import SafeText, mark_safe
from django.utils.translation import gettext_lazy as _
from typing_extensions import TypeAlias

_HtmlTemplate: TypeAlias = str


class ItemGroupPlaceholderField(Field):
    def __init__(self, heading: str) -> None:
        super().__init__(required=False, widget=HiddenInput())
        self.heading = heading


class LargeTextField(CharField):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("widget", Textarea(attrs={"style": "width: 100%;"}))
        super().__init__(*args, **kwargs)


class StructuredForm(Form):
    """「項目グループ」の概念を追加した Form"""

    required_css_class = "form_field_required"

    # copied from .venv/lib/python3.8/site-packages/django/forms/forms.py
    # VERSION = (3, 1, 13, 'final', 0)

    def _html_output(
        self,
        normal_row: _HtmlTemplate,
        error_row: _HtmlTemplate,
        row_ender: _HtmlTemplate,
        help_text_html: _HtmlTemplate,
        errors_on_separate_row: bool,
    ) -> SafeText:
        "Output HTML. Used by as_table(), as_ul(), as_p()."
        # Errors that should be displayed above all fields.
        top_errors = self.non_field_errors().copy()
        output, hidden_fields = [], []

        for name, field in self.fields.items():
            html_class_attr = ""
            bf = self[name]
            bf_errors = self.error_class(bf.errors)
            # ここでグループ名を格納する代替フィールドを処理する
            # error_row がたまたまこの用途にも使えそうなのでなるべく共用している
            if isinstance(field, ItemGroupPlaceholderField):
                heading_row_table: Dict[str, str] = {
                    # as_table
                    '<tr><td colspan="2">%s</td></tr>': '<tr><td class="table_form_group" colspan="2">%s</td></tr>',
                }
                heading_row = heading_row_table.get(error_row, error_row)
                output.append(
                    heading_row
                    % f'<h4 class="table_form_group_heading">{field.heading}</h4>'
                )
            elif bf.is_hidden:
                if bf_errors:
                    top_errors.extend(
                        [
                            _("(Hidden field %(name)s) %(error)s")
                            % {"name": name, "error": str(e)}
                            for e in bf_errors
                        ]
                    )
                hidden_fields.append(str(bf))
            else:
                # Create a 'class="..."' attribute if the row should have any
                # CSS classes applied.
                css_classes = bf.css_classes()
                if css_classes:
                    html_class_attr = ' class="%s"' % css_classes

                if errors_on_separate_row and bf_errors:
                    output.append(error_row % str(bf_errors))

                if bf.label:
                    label = conditional_escape(bf.label)
                    label = bf.label_tag(label) or ""
                else:
                    label = ""

                if field.help_text:
                    help_text = help_text_html % field.help_text
                else:
                    help_text = ""

                output.append(
                    normal_row
                    % {
                        "errors": bf_errors,
                        "label": label,
                        "field": bf,
                        "help_text": help_text,
                        "html_class_attr": html_class_attr,
                        "css_classes": css_classes,
                        "field_name": bf.html_name,
                    }
                )

        if top_errors:
            output.insert(0, error_row % top_errors)

        if hidden_fields:  # Insert any hidden fields in the last row.
            str_hidden = "".join(hidden_fields)
            if output:
                last_row = output[-1]
                # Chop off the trailing row_ender (e.g. '</td></tr>') and
                # insert the hidden fields.
                if not last_row.endswith(row_ender):
                    # This can happen in the as_p() case (and possibly others
                    # that users write): if there are only top errors, we may
                    # not be able to conscript the last row for our purposes,
                    # so insert a new, empty row.
                    last_row = normal_row % {
                        "errors": "",
                        "label": "",
                        "field": "",
                        "help_text": "",
                        "html_class_attr": html_class_attr,
                        "css_classes": "",
                        "field_name": "",
                    }
                    output.append(last_row)
                output[-1] = last_row[: -len(row_ender)] + str_hidden + row_ender
            else:
                # If there aren't any rows in the output, just append the
                # hidden fields.
                output.append(str_hidden)
        return mark_safe("\n".join(output))
