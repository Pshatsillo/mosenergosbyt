"""Sensor platform for Mosenergosbyt."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MosenergosbytCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: MosenergosbytCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        # Деньги
        MosenergosbytBalanceSensor(coordinator, entry),
        MosenergosbytDebtSensor(coordinator, entry),
        MosenergosbytChargedSensor(coordinator, entry),
        # Тарифы — для Energy Dashboard
        MosenergosbytTariffSensor(coordinator, entry, "t1", "Пик"),
        MosenergosbytTariffSensor(coordinator, entry, "t2", "Ночь"),
        MosenergosbytTariffSensor(coordinator, entry, "t3", "Полупик"),
        # Показания — для Energy Dashboard
        MosenergosbytIndicationSensor(coordinator, entry, "t1", "Пик"),
        MosenergosbytIndicationSensor(coordinator, entry, "t2", "Ночь"),
        MosenergosbytIndicationSensor(coordinator, entry, "t3", "Полупик"),
    ]
    async_add_entities(entities)


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class MosenergosbytBaseSensor(
    CoordinatorEntity[MosenergosbytCoordinator], SensorEntity
):
    """Base sensor for Mosenergosbyt."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MosenergosbytCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Мосэнергосбыт {coordinator.username}",
            manufacturer="Мосэнергосбыт",
            model="Лицевой счёт",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


# --------------------------------------------------------------------------- #
# Деньги
# --------------------------------------------------------------------------- #


class MosenergosbytBalanceSensor(MosenergosbytBaseSensor):
    """Amount to pay + debt + calculated tariffs as attributes."""

    _attr_name = "К оплате"
    _attr_native_unit_of_measurement = "₽"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "balance")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("pay_due")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "задолженность_на_начало_периода": d.get("debt_start"),
            "начислено_за_период": d.get("charged"),
            "оплачено_за_период": d.get("paid_amount"),
            "расчётный_период": d.get("dt_period"),
            "тариф_расч_пик": d.get("tariff_calc_t1"),
            "тариф_расч_ночь": d.get("tariff_calc_t2"),
            "тариф_расч_полупик": d.get("tariff_calc_t3"),
            "расход_пик_кВтч": d.get("consumption_t1"),
            "расход_ночь_кВтч": d.get("consumption_t2"),
            "расход_полупик_кВтч": d.get("consumption_t3"),
            "номер_счётчика": d.get("nn_meter"),
            "ФИО": d.get("nm_fio"),
            "адрес": d.get("nm_addr"),
        }


class MosenergosbytDebtSensor(MosenergosbytBaseSensor):
    """Debt at the beginning of the period."""

    _attr_name = "Задолженность на начало"
    _attr_native_unit_of_measurement = "₽"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-minus"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "debt_start")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("debt_start")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {"расчётный_период": d.get("dt_period")}


class MosenergosbytChargedSensor(MosenergosbytBaseSensor):
    """Amount charged for the period."""

    _attr_name = "Начислено"
    _attr_native_unit_of_measurement = "₽"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "charged")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("charged")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {"расчётный_период": d.get("dt_period")}


# --------------------------------------------------------------------------- #
# Тарифы
# --------------------------------------------------------------------------- #


class MosenergosbytTariffSensor(MosenergosbytBaseSensor):
    """Current tariff (₽/kWh) per zone — used in Energy Dashboard."""

    _attr_native_unit_of_measurement = "₽/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-rub"

    def __init__(self, coordinator, entry, zone: str, name: str):
        super().__init__(coordinator, entry, f"tariff_{zone}")
        self._zone = zone
        self._attr_name = f"Тариф {name}"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(f"tariff_current_{self._zone}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "тариф_по_расчёту": d.get(f"tariff_calc_{self._zone}"),
            "расчётный_период": d.get("dt_period"),
            "зона": self._zone,
        }


# --------------------------------------------------------------------------- #
# Показания
# --------------------------------------------------------------------------- #


class MosenergosbytIndicationSensor(MosenergosbytBaseSensor):
    """Meter indication per zone — used in Energy Dashboard."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, entry, zone: str, name: str):
        super().__init__(coordinator, entry, f"indication_{zone}")
        self._zone = zone
        self._attr_name = f"Показания {name}"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(f"vl_{self._zone}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "дата_снятия": d.get("dt_indication"),
            "тариф_текущий": d.get(f"tariff_current_{self._zone}"),
            "тариф_по_расчёту": d.get(f"tariff_calc_{self._zone}"),
            "номер_счётчика": d.get("nn_meter"),
            "расчётный_период": d.get("dt_period"),
        }
