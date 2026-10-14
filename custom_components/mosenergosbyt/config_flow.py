"""Config flow for Mosenergosbyt."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, AUTH_URL, REQUEST_URL, APP_VERSION, DEFAULT_USER_AGENT

_LOGGER = logging.getLogger(__name__)


class MosenergosbytConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mosenergosbyt."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._test_credentials(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except ValueError as err:
                _LOGGER.error("Auth failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _test_credentials(self, username: str, password: str) -> None:
        """Test if credentials are valid."""
        connector = aiohttp.TCPConnector(force_close=True)
        async with aiohttp.ClientSession(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            connector=connector,
        ) as session:
            # 1. GET /auth — reset cookies
            await session.get(AUTH_URL)

            # 2. POST login
            login_url = f"{REQUEST_URL}?action=auth&query=login"
            data = {
                "login": username,
                "psw": password,
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
                    raise ValueError(f"Auth failed: {info.get('nm_result')}")
