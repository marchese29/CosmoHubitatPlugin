import os

HUBITAT_ADDRESS = "HE_ADDRESS"
HUBITAT_APP_ID = "HE_APP_ID"
HUBITAT_ACCESS_TOKEN = "HE_ACCESS_TOKEN"


def get_env(name: str) -> str:
    """
    Retrieve the value of an environment variable.

    Args:
        name: The name of the environment variable to retrieve.

    Returns:
        The value of the environment variable as a string.

    Raises:
        ValueError: If the environment variable is not set or is None.
    """
    result = os.getenv(name)
    if result is None:
        raise ValueError(f"'{name}' was not set on the environment")
    return result
