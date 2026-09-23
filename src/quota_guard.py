"""
quota_guard.py

Provides detection, retry-suppression, and safe task-wrapping for API quota and spending cap exhaustion.
Prevents evaluation runners from getting stuck in multi-day retry loops when accounts hit monthly budget caps.
"""

from inspect_ai.model._model import Model, RetryDecision
from inspect_ai.solver import Generate, Solver, TaskState, solver

TERMINAL_QUOTA_PATTERNS = [
    "spending cap",
    "spend cap",
    "exceeded its monthly",
    "monthly spend",
    "insufficient_quota",
    "billing_hard_limit_reached",
    "account_deactivated",
    "credit balance is too low",
    "credit balance",
    "insufficient credits",
    "budget exceeded",
    "spending limit",
    "spend limit",
    "billing account",
    "unpaid balance",
]


def is_terminal_quota_error(ex: BaseException) -> bool:
    """Return True if exception represents hard billing/quota exhaustion rather than a transient rate limit."""
    err_str = str(ex).lower()
    return any(p in err_str for p in TERMINAL_QUOTA_PATTERNS)


def install_quota_retry_guard() -> None:
    """
    Monkeypatch Model and provider retry methods so that terminal quota/spend errors
    halt immediately instead of retrying with exponential backoff.
    """
    # Intercept base Model.should_retry
    try:
        _orig_model_should_retry = Model.should_retry

        def _patched_model_should_retry(self, ex: BaseException) -> bool:
            if is_terminal_quota_error(ex):
                return False
            return _orig_model_should_retry(self, ex)

        Model.should_retry = _patched_model_should_retry
    except Exception:
        pass

    # Intercept Google GenAI provider specifically
    try:
        from inspect_ai.model._providers.google import GoogleGenAIAPI

        _orig_google_should_retry = GoogleGenAIAPI.should_retry

        def _patched_google_should_retry(self, ex: BaseException):
            if is_terminal_quota_error(ex):
                return RetryDecision.no()
            return _orig_google_should_retry(self, ex)

        GoogleGenAIAPI.should_retry = _patched_google_should_retry
    except Exception:
        pass


# Automatically install guard upon import
install_quota_retry_guard()


@solver
def safe_agent_solver(base_solver: Solver) -> Solver:
    """
    Solver wrapper that intercepts terminal API quota / spending cap errors.
    Tags state.metadata with error details and re-raises so that with
    score_on_error=True and fail_on_error=True, Inspect AI marks the evaluation
    run status as 'error' (failed) while still proceeding to scoring.
    """
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        try:
            return await base_solver(state, generate)
        except Exception as ex:
            if is_terminal_quota_error(ex):
                state.metadata["is_spending_cap_error"] = True
                state.metadata["abort_reason"] = str(ex)
            raise

    return solve
