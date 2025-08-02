import logging
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from .driver import DeviceCapability, load_hubitat_capabilities

logger = logging.getLogger(__name__)


class HubitatDeviceEvent(BaseModel):
    """Represents an event from a Hubitat device."""

    device_id: str = Field(alias="deviceId")
    attribute: str = Field(alias="name")
    value: Any | None = None


class DeviceAttribute(BaseModel):
    name: str
    current_value: Any
    data_type: str | None = None
    values: list[str] | None = None


class HubitatDevice(BaseModel):
    id: str
    name: str
    date: str | None = None
    label: str
    type: str
    room: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    attributes: list[DeviceAttribute]
    capabilities: dict[str, DeviceCapability]

    @classmethod
    def from_api_data(
        cls, device_data: dict, capabilities_map: dict[str, DeviceCapability]
    ) -> "HubitatDevice":
        """Create a HubitatDevice from API response data.

        Args:
            device_data: Raw device data from Hubitat API
            capabilities_map: Mapping of capability names to DeviceCapability objects

        Returns:
            HubitatDevice instance with transformed data
        """
        transformed_data = {
            **device_data,  # Direct field mapping for id, name, label, type, room, etc.
            "attributes": cls._parse_attributes(device_data.get("attributes", {})),
            "capabilities": cls._parse_capabilities(
                device_data.get("capabilities", []), capabilities_map
            ),
        }
        # Remove API fields that don't belong to our model
        transformed_data.pop("commands", None)
        return cls(**transformed_data)

    @classmethod
    def _parse_attributes(cls, api_attributes: dict) -> list[DeviceAttribute]:
        """Parse API attributes dict into list of DeviceAttribute objects.

        Args:
            api_attributes: Raw attributes dict from API

        Returns:
            List of DeviceAttribute objects
        """
        attributes = []
        metadata_fields = {"dataType", "values"}

        for attr_name, value in api_attributes.items():
            if attr_name not in metadata_fields:
                attributes.append(
                    DeviceAttribute(
                        name=attr_name,
                        current_value=value,
                        data_type=api_attributes.get("dataType"),
                        values=api_attributes.get("values"),
                    )
                )
        return attributes

    @classmethod
    def _parse_capabilities(
        cls, capability_names: list[str], capabilities_map: dict[str, DeviceCapability]
    ) -> dict[str, DeviceCapability]:
        """Parse capability names into DeviceCapability objects.

        Args:
            capability_names: List of capability names from API
            capabilities_map: Mapping of capability names to DeviceCapability objects

        Returns:
            Dict mapping capability names to DeviceCapability objects
        """
        capabilities = {}
        for name in capability_names:
            if name in capabilities_map:
                capabilities[name] = capabilities_map[name]
            else:
                logger.warning(f"Unknown capability '{name}' - skipping")
        return capabilities

    def has_attribute(self, attr_name: str) -> bool:
        """Check if the device has an attribute with the given name.

        Args:
            attr_name: The name of the attribute to check for

        Returns:
            True if the device has the attribute, False otherwise
        """
        return any(attr.name == attr_name for attr in self.attributes)

    def has_command(self, command_name: str) -> bool:
        """Check if the device has a command with the given name.

        Args:
            command_name: The name of the command to check for

        Returns:
            True if the device has the command, False otherwise
        """
        for capability in self.capabilities.values():
            if any(cmd.name == command_name for cmd in capability.commands):
                return True
        return False

    def get_attr_value(self, attr_name: str) -> Any:
        """Get the current value of an attribute by name.

        Args:
            attr_name: The name of the attribute to get the value for

        Returns:
            The current value of the attribute

        Raises:
            AttributeError: If the attribute is not found on the device
        """
        for attr in self.attributes:
            if attr.name == attr_name:
                return attr.current_value
        raise AttributeError(f"Attribute '{attr_name}' not found on device {self.id}")


class HubitatClient:
    """Wrapper around Hubitat functionalities."""

    def __init__(self, address: str, app_id: str, access_token: str):
        """Initialize the Hubitat client with connection details."""
        self._address = f"http://{address}/apps/api/{app_id}"
        self._token = access_token
        self._capabilities = load_hubitat_capabilities()

    async def _make_request(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params={"access_token": self._token})
            except httpx.HTTPStatusError as error:
                raise Exception(
                    f"HE Client returned '{error.response.status_code}' "
                    f"status: {error.response.text}"
                ) from error
            except Exception as error:
                logger.error(f"HE Client returned error: {error}", exc_info=True)
                raise

        if resp.status_code != 200:
            raise Exception(
                f"HE Client returned '{resp.status_code}' status: {resp.text}"
            )

        return resp

    async def send_command(
        self, device_id: int, command: str, arguments: list[Any] | None = None
    ):
        """Send a command with optional arguments to a device.

        Args:
            device_id: The ID of the device to send the command to
            command: The command to send
            arguments: Optional list of arguments for the command
        """
        url = f"{self._address}/devices/{device_id}/{command}"
        if arguments is not None and len(arguments) > 0:
            url += f"/{','.join(str(arg) for arg in arguments)}"

        await self._make_request(url)

    async def get_all_devices(self) -> dict[int, HubitatDevice]:
        """Get all devices from the Hubitat hub.

        Returns:
            List of HubitatDevice objects representing all devices on the hub

        Raises:
            Exception: If the API request fails or returns an error status
        """
        url = f"{self._address}/devices/all"
        response = await self._make_request(url)

        try:
            devices_data = response.json()
        except ValueError as error:
            raise Exception(
                f"Failed to parse device response as JSON: {error}"
            ) from error

        devices = []
        for device_data in devices_data:
            try:
                device = HubitatDevice.from_api_data(device_data, self._capabilities)
                devices.append(device)
            except Exception as error:
                logger.error(
                    f"Failed to transform device {device_data.get('id', 'unknown')}",
                    exc_info=True,
                )
                # Continue processing other devices instead of failing completely
                raise error

        return {int(d.id): d for d in devices}

    async def get_device_by_id(self, device_id: int) -> HubitatDevice:
        """Get a specific device by its ID from the Hubitat hub.

        Args:
            device_id: The ID of the device to retrieve

        Returns:
            HubitatDevice object representing the requested device

        Raises:
            Exception: If the device ID is not found
        """
        devices = await self.get_all_devices()

        if device_id not in devices:
            raise Exception(f"Device with ID {device_id} not found")

        return devices[device_id]

    async def subscribe_to_events(self, webhook_url: str) -> None:
        """Subscribe to Hubitat events by registering a webhook URL.

        Args:
            webhook_url: The URL where Hubitat should send event notifications

        Raises:
            Exception: If the API request fails or returns an error status
        """
        # URL encode the webhook URL as required by the Hubitat API
        encoded_url = quote(webhook_url, safe="")

        # Build the postURL endpoint with the encoded webhook URL
        url = f"{self._address}/postURL/{encoded_url}"

        logger.debug(f"Registering webhook URL with Hubitat: '{webhook_url}'")

        try:
            await self._make_request(url)
            logger.info(f"Successfully registered webhook URL: {webhook_url}")
        except Exception as error:
            logger.error(f"Failed to register webhook URL: {webhook_url}", exc_info=True)
            raise Exception(f"Failed to register webhook URL: {error}") from error
