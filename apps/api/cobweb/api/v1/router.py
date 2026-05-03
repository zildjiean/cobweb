from fastapi import APIRouter

from cobweb.api.v1 import (
    audit, auth, llm, notifications, projects, reports, scans, schedules, tokens,
    vulnerabilities, ws,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(scans.router)
api_router.include_router(schedules.router)
api_router.include_router(vulnerabilities.router)
api_router.include_router(reports.router)
api_router.include_router(audit.router)
api_router.include_router(tokens.router)
api_router.include_router(notifications.router)
api_router.include_router(llm.router)
api_router.include_router(ws.router)
