from abc import abstractmethod
from typing import TYPE_CHECKING, Any, override

from cosmo.rules.model import AbstractCondition

from .client import HubitatClient, HubitatDevice

if TYPE_CHECKING:
    from . import HubitatPlugin


class HubitatCondition(AbstractCondition):
    def __init__(self, plugin: "HubitatPlugin"):
        super().__init__()
        self._plugin = plugin

    @abstractmethod
    def on_device_event(self, device_id: int, attr_name: str, new_value: Any):
        """Invoked when an associated device encounters an event"""
        ...

    @abstractmethod
    def get_device_ids(self) -> list[int]:
        """Retrieves the list of device id's handled by this condition."""
        ...

    @override
    def initialize(self, _):
        # When initialized with the engine, register with the plugin
        self._plugin.register_condition(self)

    @override
    def removed(self):
        self._plugin.unregister_condition(self)


class AttributeChangeCondition(HubitatCondition):
    def __init__(self, plugin: "HubitatPlugin", device_id: int, attr_name: str):
        super().__init__(plugin)
        self._device_id = device_id
        self._attr_name = attr_name
        self._prev_value = None
        self._curr_value = None

    @property
    @override
    def identifier(self) -> str:
        return f"attribute_change(he_dev({self._device_id}:{self._attr_name}))"

    @override
    def on_device_event(self, device_id: int, attr_name: str, new_value: Any):
        if self._device_id == device_id and self._attr_name == attr_name:
            self._prev_value = self._curr_value
            self._curr_value = new_value

    @override
    def get_device_ids(self) -> list[int]:
        return [self._device_id]

    @override
    def evaluate(self) -> bool:
        return bool(self._prev_value != self._curr_value)


class DynamicDeviceAttributeCondition(HubitatCondition):
    """A condition for the comparison of a device attribute against another one"""

    def __init__(
        self,
        plugin: "HubitatPlugin",
        first: tuple[int, str],
        operator: str,
        second: tuple[int, str],
    ):
        super().__init__(plugin)
        self._left_device_id, self._left_attr_name = first
        self._right_device_id, self._right_attr_name = second
        self._operator = operator
        self._left_value: Any | None = None
        self._right_value: Any | None = None

    @property
    @override
    def identifier(self) -> str:
        return (
            f"device_condition(he_dev({self._left_device_id}:{self._left_attr_name}) "
            f"{self._operator} he_dev({self._right_device_id}:{self._right_attr_name}))"
        )

    @override
    def on_device_event(self, device_id: int, attr_name: str, new_value: Any):
        if device_id == self._left_device_id and attr_name == self._left_attr_name:
            self._left_value = new_value
        elif device_id == self._right_device_id and attr_name == self._right_attr_name:
            self._right_value = new_value

    @override
    def get_device_ids(self) -> list[int]:
        return [self._left_device_id, self._right_device_id]

    @override
    def evaluate(self) -> bool:
        match self._operator:
            case "=" | "==":
                return bool(self._left_value == self._right_value)
            case "!=" | "<>":
                return bool(self._left_value != self._right_value)
            case ">":
                # Handle None values - ordering comparisons with None are undefined
                if self._left_value is not None and self._right_value is not None:
                    return bool(self._left_value > self._right_value)
                return False
            case ">=":
                # Handle None values - ordering comparisons with None are undefined
                if self._left_value is not None and self._right_value is not None:
                    return bool(self._left_value >= self._right_value)
                return False
            case "<":
                # Handle None values - ordering comparisons with None are undefined
                if self._left_value is not None and self._right_value is not None:
                    return bool(self._left_value < self._right_value)
                return False
            case "<=":
                # Handle None values - ordering comparisons with None are undefined
                if self._left_value is not None and self._right_value is not None:
                    return bool(self._left_value <= self._right_value)
                return False
            case _:
                raise ValueError(f"Unknown operator: {self._operator}")


class StaticDeviceAttributeCondition(HubitatCondition):
    """A condition for the comparison of a device attribute against a static value"""

    def __init__(
        self,
        plugin: "HubitatPlugin",
        device_id: int,
        attr_name: str,
        operator: str,
        static_value: Any,
    ):
        super().__init__(plugin)
        self._device_id = device_id
        self._attr_name = attr_name
        self._device_value = None
        self._static_value = static_value
        self._operator = operator

    def _cast_value(self, value: Any) -> Any:
        """Cast the incoming value to match the model value type.

        Args:
            value: The value to cast

        Returns:
            The value cast to the appropriate type
        """
        if value is None:
            return None

        try:
            if isinstance(self._static_value, bool):
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on", "active", "open")
                return bool(value)
            elif isinstance(self._static_value, type(int)):
                return int(value)
            elif isinstance(self._static_value, type(float)):
                return float(value)
            elif isinstance(self._static_value, type(str)):
                return str(value)
            return value
        except (ValueError, TypeError):
            return value

    @property
    @override
    def identifier(self) -> str:
        return (
            f"device_condition(he_dev({self._device_id}:{self._attr_name}) "
            f"{self._operator} {self._static_value})"
        )

    @override
    def on_device_event(self, device_id: int, attr_name: str, new_value: Any):
        if device_id == self._device_id and self._attr_name == attr_name:
            self._device_value = self._cast_value(new_value)

    @override
    def get_device_ids(self) -> list[int]:
        return [self._device_id]

    @override
    def evaluate(self) -> bool:
        match self._operator:
            case "=" | "==":
                return bool(self._device_value == self._static_value)
            case "!=" | "<>":
                return bool(self._device_value != self._static_value)
            case ">":
                return bool(self._device_value > self._static_value)
            case ">=":
                return bool(self._device_value >= self._static_value)
            case "<":
                return bool(self._device_value < self._static_value)
            case "<=":
                return bool(self._device_value <= self._static_value)
            case _:
                raise ValueError(f"Unknown operator: {self._operator}")


class Attribute:
    def __init__(
        self,
        plugin: "HubitatPlugin",
        device_id: int,
        attr_name: str,
        he_client: HubitatClient,
    ):
        self._plugin = plugin
        self._device_id = device_id
        self._attr_name = attr_name
        self._he_client = he_client

    async def current_value(self) -> Any:
        """Reports the current value of this device attribute"""
        device = await self._he_client.get_device_by_id(self._device_id)
        return device.get_attr_value(self._attr_name)

    def changes(self) -> AbstractCondition:
        return AttributeChangeCondition(self._plugin, self._device_id, self._attr_name)

    def _compare(self, other: Any, op: str) -> AbstractCondition:
        """Helper method to handle all comparison operations.

        Args:
            other: Value to compare against
            op: Comparison operator to use
        Returns:
            Appropriate condition object for the comparison
        """
        if isinstance(other, Attribute):
            return DynamicDeviceAttributeCondition(
                self._plugin,
                (self._device_id, self._attr_name),
                op,
                (other._device_id, other._attr_name),
            )
        else:
            return StaticDeviceAttributeCondition(
                self._plugin, self._device_id, self._attr_name, op, other
            )

    def __gt__(self, other: Any) -> AbstractCondition:
        return self._compare(other, ">")

    def __ge__(self, other: Any) -> AbstractCondition:
        return self._compare(other, ">=")

    def __lt__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "<")

    def __le__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "<=")

    def __eq__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "=")

    def __ne__(self, other: Any) -> AbstractCondition:
        return self._compare(other, "!=")


class Command:
    def __init__(self, device_id: int, command_name: str, he_client: HubitatClient):
        self._device_id = device_id
        self._command_name = command_name
        self._he_client = he_client

    async def __call__(self, *args: Any, **_: Any) -> Any:
        await self._he_client.send_command(self._device_id, self._command_name, *args)


class Device:
    def __init__(
        self, plugin: "HubitatPlugin", he_client: HubitatClient, device: HubitatDevice
    ):
        self._plugin = plugin
        self._he_client = he_client
        self._device = device

    def __getattr__(self, attr_name: str) -> Attribute | Command:
        if self._device.has_attribute(attr_name):
            return Attribute(
                self._plugin, int(self._device.id), attr_name, self._he_client
            )
        elif self._device.has_command(attr_name):
            return Command(int(self._device.id), attr_name, self._he_client)
        else:
            raise AttributeError(
                f"Attribute or Command {attr_name} not found on device {self._device.id}"
            )


class HubitatUtility:
    def __init__(self, he_client: HubitatClient, plugin: "HubitatPlugin"):
        self._he_client = he_client
        self._plugin = plugin

    async def device(self, device_id: int) -> Device:
        return Device(
            self._plugin,
            self._he_client,
            await self._he_client.get_device_by_id(device_id),
        )
