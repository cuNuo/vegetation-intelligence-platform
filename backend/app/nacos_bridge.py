# backend/app/nacos_bridge.py
# 文件说明：Nacos 到 Traefik 的动态路由同步桥。
# 主要职责：查询健康实例并原子生成 File Provider 配置。
# 对外入口：fetch_instances、render_configuration、sync_once。
# 依赖边界：只同步服务发现信息。

"""将Nacos健康实例同步为Traefik File Provider配置。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

NACOS_URL = os.getenv("VIP_NACOS_URL", "http://nacos:8848").rstrip("/")
OUTPUT_PATH = Path(os.getenv("TRAEFIK_DYNAMIC_PATH", "/dynamic/nacos.yml"))
SERVICES = {
    "vegetation-basic": "/api/basic",
    "vegetation-adjusted": "/api/adjusted",
    "vegetation-advanced": "/api/advanced",
}


def fetch_instances(service_name: str) -> list[str]:
    """执行 fetch_instances 对应的领域操作并返回结构化结果。"""
    query = urlencode({"serviceName": service_name, "healthyOnly": "true"})
    with urlopen(f"{NACOS_URL}/nacos/v1/ns/instance/list?{query}", timeout=5) as response:
        payload = json.load(response)
    return [
        f"http://{host['ip']}:{host['port']}"
        for host in payload.get("hosts", [])
        if host.get("healthy") and host.get("enabled", True)
    ]


def render_configuration(instances: dict[str, list[str]]) -> str:
    """执行 render_configuration 对应的领域操作并返回结构化结果。"""
    lines = ["http:", "  routers:"]
    for service_name, prefix in SERVICES.items():
        router_name = service_name.replace("vegetation-", "")
        lines.extend(
            [
                f"    {router_name}:",
                f'      rule: "PathPrefix(`{prefix}`)"',
                f"      service: {router_name}",
                "      middlewares:",
                "        - strip-service-prefix",
            ]
        )
    lines.extend(
        [
            "  middlewares:",
            "    strip-service-prefix:",
            "      stripPrefix:",
            "        prefixes:",
            *[f"          - {prefix}" for prefix in SERVICES.values()],
            "  services:",
        ]
    )
    for service_name in SERVICES:
        router_name = service_name.replace("vegetation-", "")
        lines.extend([f"    {router_name}:", "      loadBalancer:", "        servers:"])
        fallback_host = f"api-{router_name}"
        servers = instances.get(service_name) or [f"http://{fallback_host}:8000"]
        lines.extend(f'          - url: "{server}"' for server in servers)
    return "\n".join(lines) + "\n"


def sync_once() -> None:
    """执行 sync_once 对应的领域操作并返回结构化结果。"""
    instances: dict[str, list[str]] = {}
    for service_name in SERVICES:
        try:
            instances[service_name] = fetch_instances(service_name)
        except Exception:
            instances[service_name] = []
    content = render_configuration(instances)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


if __name__ == "__main__":
    while True:
        sync_once()
        time.sleep(10)
