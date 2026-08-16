class AppError(Exception):
    """Base class for expected application-level errors."""


class UserNotFoundError(AppError):
    pass


class InsufficientBalanceError(AppError):
    pass


class GenerationJobNotFoundError(AppError):
    pass


class FalSubmissionError(AppError):
    pass
