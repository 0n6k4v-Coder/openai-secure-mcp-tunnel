from __future__ import annotations

import os
from starlette.responses import JSONResponse


def health_response(*, service_name: str, service_version: str, instance_id: str) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": service_name,
        "version": service_version,
        "instance_id": instance_id,
        "pid": os.getpid(),
    })
