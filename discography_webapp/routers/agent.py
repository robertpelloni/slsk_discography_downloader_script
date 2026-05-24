from fastapi import APIRouter, BackgroundTasks, Request, Depends
from services.agent import AgentService
from services.protocol import ProtocolService
from dependencies import get_orchestrator

router = APIRouter()

def get_agent_service(request: Request):
    orch = get_orchestrator(request.app.state.event_bus)
    protocol = ProtocolService(orch.logger)
    return AgentService(orch, protocol, orch.logger)

@router.post("/api/agent/cycle")
async def run_agent_cycle(background_tasks: BackgroundTasks, agent: AgentService = Depends(get_agent_service)):
    background_tasks.add_task(agent.run_cycle)
    return {"message": "Autonomous Agent cycle started in background"}

@router.get("/api/agent/status")
async def get_agent_status(agent: AgentService = Depends(get_agent_service)):
    return {"is_busy": agent.is_busy}
