"""Enum-like constants used across models and schemas.

Kept as plain str subclasses so they serialize cleanly to JSON and compare
naturally with strings coming from the DB / AI.
"""
from enum import Enum


class UserRole(str, Enum):
    customer = "customer"
    agent = "agent"


class TicketStatus(str, Enum):
    new = "new"
    processing = "processing"
    triaged = "triaged"
    failed = "failed"
    closed = "closed"       # agent resolved / closed the ticket


class TicketCategory(str, Enum):
    billing = "billing"
    bug = "bug"
    refund = "refund"
    account = "account"
    other = "other"


class AIEventType(str, Enum):
    classified = "classified"
    cache_hit = "cache_hit"
    retry = "retry"
    failed = "failed"
