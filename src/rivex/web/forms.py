from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.core.exceptions import HTTPException


class ValidationError(HTTPException):
    def __init__(self, errors: dict[str, list[str]]):
        self.errors = errors
        super().__init__(422, detail={"errors": errors})


@dataclass
class FormField:
    name: str
    label: str = ""
    field_type: str = "text"
    required: bool = True
    default: Any = None
    choices: list[tuple[str, str]] | None = None
    placeholder: str = ""
    help_text: str = ""
    validators: list[Callable] = field(default_factory=list)
    widget: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)

    def render(self, value: Any = None, errors: list[str] | None = None) -> str:
        from html import escape
        current = value if value is not None else self.default
        val = escape(str(current)) if current is not None else ""
        err_html = ""
        if errors:
            err_html = "".join(f'<li>{escape(e)}</li>' for e in errors)
            err_html = f'<ul class="errors">{err_html}</ul>'
        if self.choices:
            opts = "".join(
                f'<option value="{escape(k)}"{" selected" if str(k)==str(current) else ""}>{escape(v)}</option>'
                for k, v in self.choices
            )
            return f'<select name="{escape(self.name)}" id="id_{escape(self.name)}">{opts}</select>{err_html}'
        attrs_str = "".join(f' {k}="{escape(v)}"' for k, v in self.attrs.items())
        return (
            f'<input type="{escape(self.field_type)}" name="{escape(self.name)}"'
            f' id="id_{escape(self.name)}" value="{val}"{attrs_str}>'
            f'{err_html}'
        )


Callable = Any


class Form:
    """Base class for HTML forms with validation.

    Usage::

        class LoginForm(Form):
            username = CharField(label="Username", max_length=100)
            password = CharField(label="Password", widget="password")

        @app.post("/login")
        async def login(form: LoginForm = Depends(LoginForm)):
            if form.is_valid():
                ...
    """

    def __init__(self, data: dict[str, Any] | None = None, files: dict[str, Any] | None = None):
        self._data = data or {}
        self._files = files or {}
        self._errors: dict[str, list[str]] = {}
        self._cleaned_data: dict[str, Any] = {}
        self._fields: dict[str, FormField] = {}
        self.is_bound = data is not None
        self._build_fields()

    def _build_fields(self) -> None:
        for attr_name in dir(self.__class__):
            val = getattr(self.__class__, attr_name)
            if isinstance(val, FormField):
                self._fields[attr_name] = val

    def fields(self) -> dict[str, FormField]:
        return dict(self._fields)

    def is_valid(self) -> bool:
        if not self.is_bound:
            return False
        self._errors = {}
        self._cleaned_data = {}
        for name, field in self._fields.items():
            raw = self._data.get(name, field.default)
            cleaned = raw
            for validator in field.validators:
                try:
                    cleaned = validator(cleaned)
                except ValueError as e:
                    self._errors.setdefault(name, []).append(str(e))
            if field.required and (cleaned is None or cleaned == ""):
                self._errors.setdefault(name, []).append("This field is required.")
                continue
            if cleaned is not None:
                self._cleaned_data[name] = cleaned
        return len(self._errors) == 0

    @property
    def errors(self) -> dict[str, list[str]]:
        return dict(self._errors)

    @property
    def cleaned_data(self) -> dict[str, Any]:
        return dict(self._cleaned_data)

    def as_table(self) -> str:
        rows: list[str] = []
        for name, field in self._fields.items():
            errs = self._errors.get(name, [])
            val = self._data.get(name)
            rows.append(
                f"<tr><th><label for='id_{name}'>{field.label or name}</label></th>"
                f"<td>{field.render(val, errs)}</td></tr>"
            )
        return f"<table>{''.join(rows)}</table>"

    def as_p(self) -> str:
        parts: list[str] = []
        for name, field in self._fields.items():
            errs = self._errors.get(name, [])
            val = self._data.get(name)
            parts.append(f"<p><label for='id_{name}'>{field.label or name}</label> {field.render(val, errs)}</p>")
        return "".join(parts)

    def as_ul(self) -> str:
        items: list[str] = []
        for name, field in self._fields.items():
            errs = self._errors.get(name, [])
            val = self._data.get(name)
            items.append(f"<li><label for='id_{name}'>{field.label or name}</label> {field.render(val, errs)}</li>")
        return f"<ul>{''.join(items)}</ul>"

    def hidden_fields(self) -> str:
        parts: list[str] = []
        for name, field in self._fields.items():
            if field.field_type == "hidden":
                val = self._data.get(name, field.default)
                parts.append(f'<input type="hidden" name="{name}" value="{val or ""}">')
        return "".join(parts)


class CharField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "text")
        super().__init__(**kwargs)


class EmailField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "email")
        super().__init__(**kwargs)
        self.validators.append(self._validate_email)

    def _validate_email(self, value: Any) -> str:
        if not isinstance(value, str) or "@" not in value:
            raise ValueError("Enter a valid email address.")
        return value


class PasswordField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "password")
        kwargs.setdefault("widget", "password")
        super().__init__(**kwargs)


class IntegerField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "number")
        super().__init__(**kwargs)
        self.validators.append(self._validate_int)

    def _validate_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("Enter a valid integer.")


class BooleanField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "checkbox")
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)


class SelectField(FormField):
    def __init__(self, choices: list[tuple[str, str]], **kwargs: Any):
        kwargs.setdefault("field_type", "select")
        super().__init__(choices=choices, **kwargs)
        self.validators.append(self._validate_choice)

    def _validate_choice(self, value: Any) -> str:
        valid = [k for k, _ in (self.choices or [])]
        if str(value) not in valid:
            raise ValueError(f"Select a valid choice. {value} is not one of the available choices.")
        return str(value)


class TextAreaField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "textarea")
        super().__init__(**kwargs)

    def render(self, value: Any = None, errors: list[str] | None = None) -> str:
        from html import escape
        current = value if value is not None else self.default
        val = escape(str(current)) if current is not None else ""
        err_html = ""
        if errors:
            err_html = "".join(f'<li>{escape(e)}</li>' for e in errors)
            err_html = f'<ul class="errors">{err_html}</ul>'
        return (
            f'<textarea name="{escape(self.name)}" id="id_{escape(self.name)}">'
            f'{val}</textarea>{err_html}'
        )
