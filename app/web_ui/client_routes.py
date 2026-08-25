# app/web_ui/client_routes.py
# GET /clients          — list all clients
# GET /clients/active   — active client profile
# POST /clients/active  — switch active client {"id": "chase_exotic"}

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.web_ui.client_manager import list_clients, get_active_client, get_active_id, set_active_client

router = APIRouter()


class SwitchRequest(BaseModel):
    id: str


@router.get("/clients")
async def clients_list():
    return list_clients()


@router.get("/clients/active")
async def clients_active():
    client = get_active_client()
    client["active_id"] = get_active_id()
    return client


@router.post("/clients/active")
async def clients_switch(body: SwitchRequest):
    if not set_active_client(body.id):
        raise HTTPException(status_code=404, detail=f"Client '{body.id}' not found")
    return {"ok": True, "active": body.id}
