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


class InvalidImportanceError(InvalidConfigurationError):
    """Importance must be ``low``, ``normal`` or ``high``."""

    code = "invalid_importance"
    message = "Habit importance must be low, normal or high."


class InvalidTrackingModeError(InvalidConfigurationError):
    code = "invalid_tracking_mode"
    message = "Unknown habit tracking mode."


class InvalidQuantityUnitError(InvalidConfigurationError):
    code = "invalid_quantity_unit"
    message = "A quantity unit is required for habits that track quantities."


class IncompatibleTrackingError(InvalidConfigurationError):
    """A quantity and a value scale were requested for the same habit."""

    code = "incompatible_tracking"
    message = (
        "A habit cannot track a quantity and a value scale at the same time."
    )


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


# -- insights (Stage 8) -----------------------------------------------------


class InsightRequestError(DomainError):
    """An insight request that is not a valid description of a hypothesis space."""

    code = "invalid_insight_request"
    status_code = 422
    message = "The insight request is not valid."


class InsightTooLargeError(InsightRequestError):
    """The requested sweep would exceed the bounded hypothesis budget."""

    code = "insight_request_too_large"
    message = "Too many hypotheses for one insight sweep."


class InsightIdentityMismatchError(InsightRequestError):
    """A fingerprint that does not describe the requested hypothesis."""

    code = "insight_identity_mismatch"
    message = "The insight identity does not match the requested hypothesis."


class InsightNotFoundError(NotFoundError):
    """No insight or history exists for that fingerprint."""

    code = "insight_not_found"
    message = "That insight does not exist."


# -- habit value scales ------------------------------------------------------
#
# A habit is answered either as completion (done / missed / skipped) or as a
# value on a small scale. These errors describe the value side only; the
# completion side keeps the errors above.


class InvalidValueTypeError(InvalidConfigurationError):
    code = "invalid_value_type"
    message = "Unknown habit value type."


class InvalidDirectionError(InvalidConfigurationError):
    code = "invalid_direction"
    message = "Unknown habit direction."


class InvalidValueLabelsError(InvalidConfigurationError):
    code = "invalid_value_labels"
    message = "A value scale needs exactly one label per value."


class InvalidHabitValueError(InvalidConfigurationError):
    code = "invalid_habit_value"
    message = "The habit value is not valid for its scale."


class ValueNotAllowedError(InvalidConfigurationError):
    """A value was submitted for a habit that tracks completion instead."""

    code = "value_not_allowed"
    message = "This habit does not track a value."


class ValueRequiredError(InvalidConfigurationError):
    """A value-tracked habit cannot be recorded without an answer."""

    code = "value_required"
    message = "This habit needs a value (0 is a valid answer)."


# -- experiments (Stage 10) -------------------------------------------------


class ExperimentNotFoundError(NotFoundError):
    """No experiment exists with that id."""

    code = "experiment_not_found"
    message = "That experiment does not exist."


class InvalidExperimentError(InvalidConfigurationError):
    """A product rule rejected the submitted experiment fields (HTTP 422)."""

    code = "invalid_experiment"
    message = "The experiment data is not valid."


class ExperimentStateError(ConflictError):
    """The requested change is not allowed in the experiment's current state."""

    code = "experiment_state_conflict"
    message = "That change is not allowed for this experiment's current state."
