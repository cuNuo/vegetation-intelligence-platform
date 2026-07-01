"""Nacos实例注册与心跳。"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import suppress

import httpx

from app.settings import settings


class NacosRegistration:
    def __init__(self) -> None:
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not settings.nacos_url:
            return
        await self._register()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
        if not settings.nacos_url:
            return
        with suppress(httpx.HTTPError):
            async with httpx.AsyncClient(timeout=5) as client:
                await client.delete(
                    f"{settings.nacos_url.rstrip('/')}/nacos/v1/ns/instance",
                    params=self._params(),
                )

    async def _register(self) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.nacos_url.rstrip('/')}/nacos/v1/ns/instance",
                params=self._params(),
            )
            response.raise_for_status()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(5)
            try:
                instance = self._params()
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.put(
                        f"{settings.nacos_url.rstrip('/')}/nacos/v1/ns/instance/beat",
                        params={
                            **instance,
                            "beat": json.dumps(
                                {
                                    "ip": instance["ip"],
                                    "port": settings.service_port,
                                    "serviceName": settings.service_name,
                                }
                            ),
                        },
                    )
            except httpx.HTTPError:
                with suppress(httpx.HTTPError):
                    await self._register()

    @staticmethod
    def _params() -> dict[str, str | int]:
        try:
            service_ip = socket.gethostbyname(settings.service_host)
        except socket.gaierror:
            service_ip = settings.service_host
        return {
            "serviceName": settings.service_name,
            "ip": service_ip,
            "port": settings.service_port,
            "healthy": "true",
            "enabled": "true",
            "ephemeral": "true",
        }


nacos_registration = NacosRegistration()
