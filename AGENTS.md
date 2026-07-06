# AGENTS.md — managerGospodarstwa

## Project context

This is a Django web application for managing farm-related data, including ingredients, feed recipes, inventory, costs, sales, documents, and user-specific farm records.

The main goal is to keep the project stable, readable, maintainable, and safe for real user data. Prefer practical, production-oriented fixes over large rewrites.

Communicate with the user in Polish unless the user explicitly asks for English.

---

## Branch and Git rules

* Work only on the `develop` branch unless the user explicitly says otherwise.
* Do not modify `main`.
* Do not create risky or destructive changes without explaining them first.
* Keep commits and changes focused on the requested task.
* Do not remove existing features unless the task explicitly requires it.
* Do not delete migrations, settings files, environment examples, or production-related configuration without a clear reason.

---

## General coding rules

* Prefer simple, readable, maintainable code.
* Do not rewrite the whole project if a targeted fix is enough.
* Preserve the existing architecture, naming style, and app structure where possible.
* Avoid unnecessary dependencies.
* Ask before adding any new production dependency.
* Keep business logic out of templates when possible.
* Avoid duplicating logic across views, forms, templates, and services.
* Prefer reusable helpers, services, model methods, or template includes when the same logic appears in many places.
* Keep changes small enough to review.

---

## Django conventions

* Follow standard Django patterns.
* Use Django forms for validation.
* Use views for request handling, not for complex business calculations.
* Put repeated business calculations in services/helpers.
* Put repeated UI fragments in template includes.
* Use model methods only when the logic naturally belongs to the model.
* Create migrations whenever models change.
* Do not edit old migrations unless there is a very strong reason.
* Be careful with authentication, permissions, and user-specific data.

---

## Data safety and user isolation

* Never expose data from one user to another user.
* When adding queries, filters, exports, backups, reports, or dashboards, ensure they are scoped to the correct user/farm.
* Do not assume a global dataset unless the existing code clearly uses one.
* Be careful with admin-only features.
* Backup, export, and delete operations must be safe and clearly scoped.
* Do not log secrets, passwords, tokens, API keys, private email data, or production database credentials.

---

## Inventory, costs, and accounting logic

Inventory and cost calculations are business-critical.

When changing anything related to ingredients, feed, purchases, stock levels, production, sales, costs, or profit:

* Understand the current flow before editing.
* Do not change the accounting meaning accidentally.
* Be careful with unit conversions.
* Be careful with FIFO / purchase batches / historical prices if they exist.
* Do not average costs unless the task explicitly asks for it.
* Do not let buying ingredients on stock incorrectly inflate production cost or profit.
* Explain the business consequence of any calculation change.
* Add or update tests for cost and inventory logic where possible.

---

## Forms and validation

* Keep forms user-friendly and strict enough to prevent invalid data.
* Preserve existing required/optional field behavior unless the task says otherwise.
* If a form test fails, inspect whether the failure is caused by changed required fields, widgets, choices, or validation.
* Keep validation messages understandable.

---

## UI and UX rules

The user prefers a clean, modern, consistent interface.

When changing frontend code:

* Improve desktop, tablet, and mobile behavior.
* Keep layout consistent across pages.
* Keep UI patterns consistent across modules: forms, cards, page headers, tables, alerts, buttons, and action layouts should feel like one application.
* Use reusable template includes instead of duplicated HTML.
* Do not create one-off local styles when the same UI problem appears in several places. Prefer shared CSS classes, reusable Django template includes, and component-like template structure.
* Keep tables readable and responsive.
* Settings should be placed near the logout/user area if the task concerns navigation.
* Do not mix unrelated visual changes into one huge edit.
* Keep CSS modular where possible:

  * layout CSS,
  * table CSS,
  * form CSS,
  * navigation CSS,
  * theme/colors CSS,
  * responsive CSS.

Prefer improving existing templates and CSS instead of introducing a completely new frontend framework.

Forms must adapt to the content of their fields. Text, number, and date inputs should not look cramped; labels need readable line-height and spacing and must not overlap inputs or nearby text.

When working with numeric fields, account for Polish user formats: decimal comma, spaces or non-breaking spaces as thousand separators, and units such as kg, zł/kg, szt., %, gross/net values.

For UX changes, check desktop, tablet, and phone layouts.

---

## Tables

For tables:

* Make them readable on desktop.
* Make them usable on mobile.
* Avoid horizontal overflow where possible, but allow it when tables are too complex.
* Keep actions visually clear.
* Keep numeric values aligned and formatted consistently when possible.
* Do not hide important business data just to make the table smaller.

---

## PDF, import, export, and documents

When changing PDF parsing, imports, exports, backups, or document handling:

* Preserve existing parsed fields unless the task says otherwise.
* Do not break existing imports.
* Handle missing or malformed data safely.
* Validate dates and numbers carefully.
* Do not reject correctly visible PDF values only because they use decimal commas, spaces, non-breaking spaces, units, or non-standard separators.
* For sales PDFs, handle common units such as kg, zł, zł/kg, szt., and % without producing warnings when the cleaned value is valid.
* For sales PDFs, preserve document number parsing and parse sale/slaughter dates only when reliable.
* Explain what happens when a field cannot be parsed.
* Keep PDF import messages practical and compact. Prefer a short summary, smaller detailed list or disclosure, and row/field indicators where possible over many large repeated alerts.
* Do not expose files belonging to other users.

When changing PDF parsers, add or update tests using representative PDF text or fixtures. Include cases for Polish numeric formats and real invalid values that should still produce warnings.

---

## Tests and verification

After backend changes, run relevant tests.

Preferred commands:

```bash
python manage.py test
```

If the project uses a different command, inspect the repo and use the correct one.

For targeted changes, run the most relevant tests first, for example:

```bash
python manage.py test farms
```

If tests fail:

* Report which tests failed.
* Explain whether the failure appears related to the change.
* Fix related failures if possible.
* Do not hide failing tests.

When changing forms, models, services, or views, check whether tests need to be updated or added.

---

## Authentication and redirects

Be careful with login, logout, authentication decorators, middleware, redirects, and permissions.

If debugging login loops:

* Check redirects.
* Check login URL settings.
* Check middleware.
* Check user authentication state.
* Check permission checks.
* Check whether views redirect authenticated users back to login incorrectly.

Do not apply random fixes without identifying the cause.

---

## Deployment and production awareness

This project may be deployed with a production database.

* Do not assume local-only behavior.
* Be careful with migrations.
* Be careful with static files.
* Be careful with environment variables.
* Do not hardcode production secrets.
* Do not hardcode local paths.
* Keep deployment compatibility in mind.

---

## Preferred task workflow

For each task:

1. Inspect the relevant files first.
2. Identify the smallest safe change.
3. Make the change.
4. Run relevant tests or checks.
5. Summarize the result clearly.

Do not start with a large refactor unless the user explicitly asks for one.

---

## Final response format

At the end of every coding task, provide a concise summary in Polish:

```text
Zmieniono:
- ...

Pliki:
- ...

Testy:
- ...

Jak sprawdzić ręcznie:
- ...

Ryzyka / uwagi:
- ...
```

If tests were not run, say why.

If something could not be completed, say it directly and explain what remains.
