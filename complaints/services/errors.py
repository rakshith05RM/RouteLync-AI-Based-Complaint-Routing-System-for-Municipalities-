class WorkflowError(Exception):
    """A business rule was broken. The message is written for the user and may be shown as is."""
