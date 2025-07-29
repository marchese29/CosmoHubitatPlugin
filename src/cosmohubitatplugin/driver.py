import json
from pathlib import Path

from pydantic import BaseModel


class CapabilityAttribute(BaseModel):
    """Represents an attribute of a Hubitat device capability.

    Attributes are read-only properties that represent the current state
    of a device, such as temperature, switch state, or battery level.

    Attributes:
        name: The attribute name
        value_type: The data type of the attribute value
        notes: Optional notes about the attribute, including valid values or units
    """

    name: str
    value_type: str
    notes: str | None = None


class CapabilityCommandArgument(BaseModel):
    """Represents an argument for a Hubitat device capability command.

    Command arguments define the parameters that can be passed to a device
    command method, including their data types and constraints.

    Attributes:
        name: The argument name
        value_type: The data type expected
        notes: Optional notes about the argument, including valid ranges or units
    """

    name: str
    value_type: str
    notes: str | None = None


class CapabilityCommand(BaseModel):
    """Represents a command (method) of a Hubitat device capability.

    Commands are actions that can be performed on a device, such as
    turning on/off, setting a level, or playing a sound.

    Attributes:
        name: The command name
        arguments: List of arguments that the command accepts
    """

    name: str
    arguments: list[CapabilityCommandArgument] = []


class DeviceCapability(BaseModel):
    """Represents a complete Hubitat device capability.

    A capability defines a standard interface for device functionality,
    including the attributes (state) and commands (actions) available.

    Attributes:
        name: The capability name
        attributes: List of attributes this capability provides
        commands: List of commands this capability supports
    """

    name: str
    attributes: list[CapabilityAttribute]
    commands: list[CapabilityCommand]


class HubitatCapabilities(BaseModel):
    """Container for all Hubitat device capabilities.

    This class represents the complete collection of device capabilities
    supported by Hubitat, loaded from the capabilities JSON file.

    Attributes:
        capabilities: List of all available device capabilities
    """

    capabilities: list[DeviceCapability]


def load_hubitat_capabilities() -> dict[str, DeviceCapability]:
    """Load Hubitat capabilities from the JSON data file.

    Returns:
        HubitatCapabilities: Parsed capabilities data

    Raises:
        FileNotFoundError: If the capabilities JSON file is not found
        json.JSONDecodeError: If the JSON file is malformed
    """
    current_dir = Path(__file__).parent
    capabilities_file = current_dir / "data" / "hubitat_capabilities.json"

    if not capabilities_file.exists():
        raise FileNotFoundError(f"Capabilities file not found: {capabilities_file}")

    with open(capabilities_file, encoding="utf-8") as f:
        data = json.load(f)

    return {cap.name: cap for cap in HubitatCapabilities(**data).capabilities}
