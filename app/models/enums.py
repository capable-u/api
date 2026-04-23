from enum import Enum


class Direction(str, Enum):
    income = "income"
    expense = "expense"


class DuplicateStatus(str, Enum):
    unique = "unique"
    possible_duplicate = "possible_duplicate"
    duplicate_confirmed = "duplicate_confirmed"
