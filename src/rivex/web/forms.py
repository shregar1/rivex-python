from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rivex.exceptions.http.exceptions import HTTPException


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
        """Render the field as an HTML ``<input>`` (or ``<select>``) element.

        When ``choices`` is configured, a ``<select>`` is emitted with
        one ``<option>`` per pair; otherwise a single ``<input>`` is
        produced using ``field_type`` for the ``type`` attribute. The
        current value (either ``value`` or ``self.default`` when
        ``value`` is ``None``) is HTML-escaped before interpolation.
        Any ``errors`` are rendered as a trailing ``<ul class="errors">``
        list.

        Args:
            value: Value to mark the control as selected/filled with.
                ``None`` falls back to ``self.default``.
            errors: Per-field validation messages to surface alongside
                the control. Empty / ``None`` produces no error markup.

        Returns:
            The raw HTML for this field, ready to be embedded in a
            form-rendering template.
        """
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
        """Populate ``self._fields`` from any :class:`FormField` class attributes.

        Walks the class ``__dict__`` (via :func:`dir`) and stores every
        attribute that is a :class:`FormField` instance, keyed by its
        attribute name on the class. Called once from ``__init__``;
        subclasses typically do not need to invoke it directly.
        """
        for attr_name in dir(self.__class__):
            val = getattr(self.__class__, attr_name)
            if isinstance(val, FormField):
                self._fields[attr_name] = val

    def fields(self) -> dict[str, FormField]:
        """Return a shallow copy of the registered field map.

        Returns:
            Mapping of field name → :class:`FormField` for every
            ``FormField`` declared on the form class.
        """
        return dict(self._fields)

    def is_valid(self) -> bool:
        """Run every field's validators and populate ``errors`` and ``cleaned_data``.

        Re-evaluates validation from scratch on every call: any
        previously-stored errors are cleared and ``cleaned_data`` is
        rebuilt from the bound input. Each field's ``validators`` are
        run in order; a raised :class:`ValueError` is recorded as a
        per-field error message. Required fields that resolve to
        ``None`` or the empty string are flagged with a default
        "This field is required." error.

        Returns:
            ``True`` when no errors were recorded, ``False`` otherwise.
            An unbound form (``is_bound`` is ``False``) short-circuits
            to ``False`` without running validators.
        """
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
        """Return a copy of the per-field validation errors.

        Returns:
            Mapping of field name → list of human-readable error
            messages. Empty when :meth:`is_valid` was last called and
            returned ``True``.
        """
        return dict(self._errors)

    @property
    def cleaned_data(self) -> dict[str, Any]:
        """Return a copy of the validated, transformed field values.

        Returns:
            Mapping of field name → cleaned value. Populated by
            :meth:`is_valid`; empty on an unbound form or one whose
            validation produced errors.
        """
        return dict(self._cleaned_data)

    def as_table(self) -> str:
        """Render the form as a ``<table>`` with one row per field.

        Each row contains a ``<label>`` and the field's rendered
        control; per-field errors are passed through to
        :meth:`FormField.render` and shown alongside the input.

        Returns:
            A ``<table>`` element with one ``<tr>`` per registered
            field, in the order they were discovered on the class.
        """
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
        """Render the form as a sequence of ``<p>`` blocks, one per field.

        Each block contains a ``<label>`` followed by the field's
        rendered control, suitable for default Bootstrap-style forms.

        Returns:
            Concatenated ``<p>`` elements, one per field.
        """
        parts: list[str] = []
        for name, field in self._fields.items():
            errs = self._errors.get(name, [])
            val = self._data.get(name)
            parts.append(f"<p><label for='id_{name}'>{field.label or name}</label> {field.render(val, errs)}</p>")
        return "".join(parts)

    def as_ul(self) -> str:
        """Render the form as a ``<ul>`` of labelled list items.

        Returns:
            A ``<ul>`` element whose ``<li>`` children each contain
            a ``<label>`` and the field's rendered control.
        """
        items: list[str] = []
        for name, field in self._fields.items():
            errs = self._errors.get(name, [])
            val = self._data.get(name)
            items.append(f"<li><label for='id_{name}'>{field.label or name}</label> {field.render(val, errs)}</li>")
        return f"<ul>{''.join(items)}</ul>"

    def hidden_fields(self) -> str:
        """Emit hidden ``<input>`` elements for every field whose ``field_type`` is ``"hidden"``.

        Iterates the registered fields once and concatenates a
        ``<input type="hidden" name="…" value="…">`` element for each
        matching field. Used by templates that place hidden state
        outside the visible form (CSRF tokens, redirect targets, …).

        Returns:
            Concatenated hidden ``<input>`` HTML. Empty when no hidden
            fields are registered.
        """
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
        """Coerce ``value`` to a string and require a literal ``"@"`` substring.

        A bare ``"@"`` check — sufficient for the common case of
        catching obviously-wrong inputs. Full RFC-5322 validation is
        intentionally out of scope; delegate to the email-sending
        backend for any deeper checks.

        Args:
            value: Candidate value, typically a string from the
                request data.

        Returns:
            ``value`` unchanged when it passes the check.

        Raises:
            ValueError: When ``value`` is not a string or has no
                ``"@"`` character.
        """
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
        """Coerce ``value`` to ``int`` using the built-in :func:`int` constructor.

        Args:
            value: Candidate value, typically a string from the
                request data.

        Returns:
            ``value`` converted to an :class:`int`.

        Raises:
            ValueError: When the conversion fails (non-numeric
                strings, ``None``, etc.).
        """
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
        """Confirm ``value`` matches one of the configured ``choices`` keys.

        Comparison is string-based: the candidate is stringified via
        :func:`str` before lookup, mirroring the value attribute used
        by the rendered ``<option>`` elements.

        Args:
            value: Candidate value, typically a string from the
                request data.

        Returns:
            ``str(value)`` when it matches a configured choice key.

        Raises:
            ValueError: When ``str(value)`` is not present in
                ``self.choices``.
        """
        valid = [k for k, _ in (self.choices or [])]
        if str(value) not in valid:
            raise ValueError(f"Select a valid choice. {value} is not one of the available choices.")
        return str(value)


class TextAreaField(FormField):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("field_type", "textarea")
        super().__init__(**kwargs)

    def render(self, value: Any = None, errors: list[str] | None = None) -> str:
        """Render a ``<textarea>`` element populated with the field's value.

        Overrides :meth:`FormField.render` because a textarea needs
        the value between the tags (not as a ``value="…"`` attribute)
        and has no concept of a ``field_type`` choice.

        Args:
            value: Value to populate the textarea with. ``None``
                falls back to ``self.default``.
            errors: Per-field validation messages to surface after
                the textarea. ``None`` produces no error markup.

        Returns:
            The raw HTML for the textarea element, including any
            trailing ``<ul class="errors">`` block.
        """
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
