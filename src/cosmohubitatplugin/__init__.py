import asyncio as aio
from collections.abc import AsyncGenerator
from typing import Any, Self, override

from cosmo.plugin import CosmoPlugin
from cosmo.plugin.model import AbstractCondition
from fastapi.routing import APIRouter

from .client import HubitatClient, HubitatDevice, HubitatDeviceEvent
from .misc import HUBITAT_ACCESS_TOKEN, HUBITAT_ADDRESS, HUBITAT_APP_ID, get_env
from .utility import HubitatCondition, HubitatUtility


class HubitatPlugin(CosmoPlugin):
    """Cosmo plugin for hubitat actions."""

    def __init__(self, he_client: HubitatClient, devices: dict[int, HubitatDevice]):
        self._he_client = he_client
        self._devices = devices

        # Async state tracking
        self._event_q: aio.Queue[tuple[int, str, Any]] = aio.Queue()
        self._conditions_for_device: dict[int, dict[int, HubitatCondition]] = {}

    @classmethod
    async def create(cls) -> Self:
        he_client = HubitatClient(
            get_env(HUBITAT_ADDRESS),
            get_env(HUBITAT_APP_ID),
            get_env(HUBITAT_ACCESS_TOKEN),
        )
        devices = await he_client.get_all_devices()
        return cls(he_client, devices)

    @override
    def configure_routes(self, router: APIRouter):
        router.post("/he_event")(self._on_device_event)

    @override
    async def run(self) -> AsyncGenerator[list[AbstractCondition], None]:
        while True:
            (device_id, attr_name, new_value) = await self._event_q.get()

            # Notify and store conditions that are impacted by this change
            conditions: list[AbstractCondition] = []
            for condition in self._conditions_for_device.get(device_id, {}).values():
                condition.on_device_event(device_id, attr_name, new_value)
                conditions.append(condition)

            # Let the rule engine know some conditions are changed
            if len(conditions) > 0:
                yield conditions

    @override
    def get_rule_utility(self) -> object | None:
        return HubitatUtility(self._he_client, self)

    def register_condition(self, condition: HubitatCondition):
        """Registers the condition with the plugin so we can notify of device events."""
        for device_id in condition.get_device_ids():
            if device_id not in self._conditions_for_device:
                self._conditions_for_device[device_id] = {}
            if condition.instance_id not in self._conditions_for_device[device_id]:
                self._conditions_for_device[device_id][condition.instance_id] = condition

    def unregister_condition(self, condition: HubitatCondition):
        """Removes the condition from tracking."""
        for device_id in condition.get_device_ids():
            if device_id in self._conditions_for_device:
                # Remove the condition from the device's condition map
                if condition.instance_id in self._conditions_for_device[device_id]:
                    del self._conditions_for_device[device_id][condition.instance_id]

                    # If no more conditions are tracking this device, remove it
                    if len(self._conditions_for_device[device_id]) == 0:
                        del self._conditions_for_device[device_id]

    async def _on_device_event(self, event: HubitatDeviceEvent) -> dict:
        """Invoked when we encounter a device event."""
        # Queue up the event for processing in the plugin task.
        await self._event_q.put((int(event.device_id), event.attribute, event.value))
        return {"result": "success"}
