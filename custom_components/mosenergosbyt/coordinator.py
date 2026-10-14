"""DataUpdateCoordinator for Mosenergosbyt."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    AUTH_URL,
    REQUEST_URL,
    APP_VERSION,
    DEFAULT_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class MosenergosbytCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for fetching data from Mosenergosbyt."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.username = username
        self.password = password
        self._session: aiohttp.ClientSession | None = None
        self._session_id: str | None = None
        self._logged_in: bool = False

        self.account_id: int | None = None
        self.vl_provider: str | None = None
        self.plugin: str = "bytProxy"

    # ------------------------------------------------------------------ #
    # Session / login
    # ------------------------------------------------------------------ #

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(force_close=True)
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                connector=connector,
            )
        return self._session

    async def async_close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self._logged_in = False
        self._session_id = None

    async def _async_login(self) -> None:
        """Login, Init and fetch account list."""
        session = await self._get_session()

        # 1. GET /auth — reset cookies
        await session.get(AUTH_URL)

        # 2. POST login
        login_url = f"{REQUEST_URL}?action=auth&query=login"
        data = {
            "login": self.username,
            "psw": self.password,
            "remember": "true",
            "vl_device_info": (
                f'{{"appVer":"{APP_VERSION}","type":"browser",'
                f'"userAgent":"{DEFAULT_USER_AGENT}"}}'
            ),
        }
        async with session.post(login_url, data=data) as resp:
            result = await resp.json()
            info = result["data"][0]
            if info["kd_result"] not in (0, 1000):
                raise ConfigEntryAuthFailed(f"Login failed: {info.get('nm_result')}")
            self._session_id = info["session"]

        # 3. POST Init
        init_url = f"{REQUEST_URL}?action=sql&query=Init&session={self._session_id}"
        async with session.post(init_url) as resp:
            result = await resp.json()
            if not result.get("success"):
                self._session_id = None
                raise ConfigEntryAuthFailed("Init failed")

        # 4. POST LSList
        lslist_url = f"{REQUEST_URL}?action=sql&query=LSList&session={self._session_id}"
        async with session.post(lslist_url) as resp:
            result = await resp.json()
            accounts = result.get("data", [])
            if not accounts:
                raise UpdateFailed("No accounts found")
            acc = accounts[0]
            self.account_id = acc["id_service"]
            self.vl_provider = acc["vl_provider"]
            if acc.get("kd_provider", 1) == 1:
                self.plugin = "bytProxy"

        self._logged_in = True

    async def _async_fetch_proxy(self, proxyquery: str, **extra) -> Any:
        if not self._logged_in or self._session_id is None:
            await self._async_login()

        url = f"{REQUEST_URL}?action=sql&query={self.plugin}&session={self._session_id}"
        data = {
            "plugin": self.plugin,
            "proxyquery": proxyquery,
            "vl_provider": self.vl_provider,
            **extra,
        }

        session = await self._get_session()
        async with session.post(url, data=data) as resp:
            result = await resp.json()

        if not result.get("success"):
            err = result.get("err_text", "Unknown error")
            self._logged_in = False
            self._session_id = None
            raise UpdateFailed(f"API error: {err}")

        return result.get("data", [])

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if not self._logged_in:
                await self._async_login()

            # === LSInfo: абонент + текущие тарифы ===
            lsinfo = await self._async_fetch_proxy("LSInfo")
            info = lsinfo[0] if isinstance(lsinfo, list) else lsinfo

            tariff_current = {
                "t1": float(info.get("vl_t1_tariff") or 0),
                "t2": float(info.get("vl_t2_tariff") or 0),
                "t3": float(info.get("vl_t3_tariff") or 0),
            }

            # === Indications: последние показания ===
            now = datetime.now()
            dt_st = (now - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00+03:00")
            dt_en = now.strftime("%Y-%m-%dT23:59:59+03:00")

            indications = await self._async_fetch_proxy(
                "Indications", dt_st=dt_st, dt_en=dt_en
            )
            last_ind = indications[0] if indications else {}

            # === Invoice: начисления + долг + тарифы расчёта ===
            invoice = await self._async_fetch_proxy("Invoice", dt_st=dt_st, dt_en=dt_en)
            last_invoice = invoice[0] if invoice else {}

            pay_due = 0.0
            charged = 0.0
            debt_start = 0.0
            paid_amount = 0.0

            for cell in last_invoice.get("data_common", []):
                nm = (cell.get("nm_value") or "").lower()
                v = float(cell.get("vl_value") or 0)
                if "итого к оплате" in nm:
                    pay_due = v
                elif "начислено" in nm:
                    charged = v
                elif "задолженность" in nm:
                    debt_start = v
                elif "поступивших платежей" in nm:
                    paid_amount = v

            # data_detail: [[Пик: сумма, расход, тариф], [Ночь...], [П/пик...]]
            zones: dict[str, dict[str, float]] = {}
            for zone in last_invoice.get("data_detail") or []:
                if not zone or len(zone) < 3:
                    continue
                name = str(zone[0].get("nm_value") or "").lower().strip()
                zones[name] = {
                    "sum": float(zone[0].get("vl_value") or 0),
                    "consumption": float(zone[1].get("vl_value") or 0),
                    "tariff": float(zone[2].get("vl_value") or 0),
                }

            empty = {"sum": 0.0, "consumption": 0.0, "tariff": 0.0}
            zone_t1 = zones.get("пик", empty)
            zone_t2 = zones.get("ночь", empty)
            zone_t3 = zones.get("п/пик", zones.get("полупик", empty))

            tariff_calc = {
                "t1": zone_t1["tariff"],
                "t2": zone_t2["tariff"],
                "t3": zone_t3["tariff"],
            }
            consumption = {
                "t1": zone_t1["consumption"],
                "t2": zone_t2["consumption"],
                "t3": zone_t3["consumption"],
            }

            return {
                # абонент
                "nm_fio": info.get("nm_fio", ""),
                "nm_addr": info.get("nm_addr", ""),
                "nn_meter": info.get("nn_meter", ""),
                "vl_person": info.get("vl_person"),
                # показания
                "vl_t1": last_ind.get("vl_t1", 0),
                "vl_t2": last_ind.get("vl_t2", 0),
                "vl_t3": last_ind.get("vl_t3", 0),
                "dt_indication": last_ind.get("dt_indication", ""),
                # деньги
                "pay_due": pay_due,
                "charged": charged,
                "debt_start": debt_start,
                "paid_amount": paid_amount,
                "dt_period": last_invoice.get("dt_period", ""),
                # тарифы текущие
                "tariff_current_t1": tariff_current["t1"],
                "tariff_current_t2": tariff_current["t2"],
                "tariff_current_t3": tariff_current["t3"],
                # тарифы расчётные
                "tariff_calc_t1": tariff_calc["t1"],
                "tariff_calc_t2": tariff_calc["t2"],
                "tariff_calc_t3": tariff_calc["t3"],
                # расход за период
                "consumption_t1": consumption["t1"],
                "consumption_t2": consumption["t2"],
                "consumption_t3": consumption["t3"],
            }
        except ConfigEntryAuthFailed:
            raise
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Timeout") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
