"""Domain errors.

These subclass :class:`~app.core.errors.AppError`, so they are rendered by the
Stage 1 error envelope with no extra plumbing. Each error carries a stable
``code`` the frontend can branch on and a message written for a human.
"""

from __future__ import annotations

from app.core.errors import AppError


class DomainError(AppError):
    """Base class for expected domain failures."""


class NotFoundError(DomainError):
    """A requested entity does not exist (HTTP 404)."""

    code = "not_found"
    status_code = 404
    message = "The requested item was not found."


class ConflictError(DomainError):
    """The request is valid but conflicts with current state (HTTP 409)."""

    code = "conflict"
    status_code = 409
    message = "The request conflicts with the current state."


class InvalidConfigurationError(DomainError):
    """A product rule rejected the submitted configuration (HTTP 422)."""

    code = "invalid_configuration"
    status_code = 422
    message = "The submitted configuration is not valid."


# -- areas ------------------------------------------------------------------


class AreaNotFoundError(NotFoundError):
    code = "area_not_found"
    message = "That area does not exist."


class AreaNameConflictError(ConflictError):
    code = "area_name_conflict"
    message = "An active area with that name already exists."


class AreaHasActiveHabitsError(ConflictError):
    code = "area_has_active_habits"
    message = "This area still has active habits. Archive or move them first."


class AreaArchivedError(ConflictError):
    code = "area_archived"
    message = "This area is archived. Unarchive it before adding habits to it."


class InvalidAreaNameError(InvalidConfigurationError):
    code = "invalid_area_name"
    message = "The area name is not valid."


class InvalidAreaColorError(InvalidConfigurationError):
    code = "invalid_area_color"
    message = "The area color must be a hex value such as #4a7cc7."


# -- habits -----------------------------------------------------------------


class HabitNotFoundError(NotFoundError):
    code = "habit_not_found"
    message = "That habit does not exist."


class HabitConfigurationNotFoundError(NotFoundError):
    code = "configuration_not_found"
    message = "No configuration was effective for that habit on that date."


class InvalidHabitNameError(InvalidConfigurationError):
    code = "invalid_habit_name"
    message = "The habit name is not valid."


class InvalidWeightError(InvalidConfigurationError):
    code = "invalid_weight"
    message = "Habit weight must be 1 (normal), 2 (important) or 3 (key)."


class InvalidTrackingModeError(InvalidConfigurationError):
    code = "invalid_tracking_mode"
    message = "Unknown habit tracking mode."


class InvalidQuantityUnitError(InvalidConfigurationError):
    code = "invalid_quantity_unit"
    message = "A quantity unit is required for habits that track quantities."


class InvalidScheduleError(InvalidConfigurationError):
    code = "invalid_schedule"
    message = "The habit schedule is not valid."


class ConfigurationHistoryError(InvalidConfigurationError):
    code = "invalid_configuration_date"
    message = "The configuration change date is not valid."


# -- daily entries ----------------------------------------------------------


class DailyEntryNotFoundError(NotFoundError):
    code = "daily_entry_not_found"
    message = "There is no entry for that habit on that date."


class InvalidEntryStatusError(InvalidConfigurationError):
    code = "invalid_entry_status"
    message = "Unknown daily entry status."


class FutureEntryError(InvalidConfigurationError):
    """A future date only accepts a deliberately planned skip."""

    code = "future_entry_not_allowed"
    message = "Only a planned skip can be recorded for a future date."


class SkipReasonRequiredError(InvalidConfigurationError):
    code = "skip_reason_required"
    message = "Enter why the habit was skipped."


class SkipReasonNotAllowedError(InvalidConfigurationError):
    code = "skip_reason_not_allowed"
    message = "A skip reason only applies to a deliberately skipped entry."


class InvalidSkipReasonError(InvalidConfigurationError):
    code = "invalid_skip_reason"
    message = "The skip reason is not valid."


class InvalidNoteError(InvalidConfigurationError):
    code = "invalid_note"
    message = "The note is not valid."


class InvalidQuantityValueError(InvalidConfigurationError):
    code = "invalid_quantity"
    message = "The quantity is not valid."


class QuantityNotAllowedError(InvalidConfigurationError):
    code = "quantity_not_allowed"
    message = "This habit does not track a quantity."


class QuantityDecimalNotAllowedError(InvalidConfigurationError):
    code = "quantity_decimal_not_allowed"
    message = "This habit is configured for whole numbers only."
