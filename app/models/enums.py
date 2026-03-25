from enum import Enum


class ImportJobStatus(str, Enum):
    uploaded = "uploaded"
    parsed_text = "parsed_text"
    parsed_transactions = "parsed_transactions"
    done = "done"
    needs_review = "needs_review"
    failed = "failed"
    llm_failed = "llm_failed"


class Direction(str, Enum):
    income = "income"
    expense = "expense"


class ReviewStatus(str, Enum):
    pending = "pending"
    reviewed = "reviewed"
    ignored = "ignored"


class DuplicateStatus(str, Enum):
    unique = "unique"
    possible_duplicate = "possible_duplicate"
    duplicate_confirmed = "duplicate_confirmed"