import asyncio
import os
import re
from typing import List, Dict, Any, Optional

class PlanningModule:
    def __init__(self, root_dir: str, logger):
        self.root_dir = root_dir
        self.logger = logger

    def prioritize_objectives(self) -> List[Dict[str, Any]]:
        """Analyze TODO.md and ROADMAP.md to determine next actions."""
        objectives = []

        # 1. Parse TODOs
        todo_path = os.path.join(self.root_dir, "TODO.md")
        if os.path.exists(todo_path):
            with open(todo_path, "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.strip().startswith("- ["):
                        # Priority 1: Functional Tasks
                        if "[Search]" in line or "[Library]" in line:
                            objectives.append({"task": line.strip(), "priority": 1, "type": "functional"})
                        # Priority 2: Documentation
                        elif "[Documentation]" in line:
                            objectives.append({"task": line.strip(), "priority": 2, "type": "docs"})

        # 2. Parse Roadmap (Focus on unfinished phases)
        roadmap_path = os.path.join(self.root_dir, "ROADMAP.md")
        if os.path.exists(roadmap_path):
            with open(roadmap_path, "r") as f:
                for line in f:
                    if "- [ ]" in line:
                        objectives.append({"task": f"Roadmap: {line.strip()[6:]}", "priority": 3, "type": "milestone"})

        # Sort by priority
        objectives.sort(key=lambda x: x['priority'])
        return objectives

class ExecutionModule:
    def __init__(self, orchestrator, protocol_service, logger):
        self.orch = orchestrator
        self.protocol = protocol_service
        self.logger = logger

    async def execute_task(self, objective: Dict[str, Any]) -> bool:
        """Map objective types to system actions."""
        self.logger.info(f"Agent executing: {objective['task']}")

        try:
            if objective['type'] == 'functional':
                # Example: If search task, maybe trigger a maintenance sync first
                # sync_repository is an async method
                await self.protocol.sync_repository()
                return True

            elif objective['type'] == 'milestone':
                # Trigger roadmap extraction to update status
                await self.protocol.extract_roadmap()
                return True

            elif objective['type'] == 'docs':
                self.logger.info("Agent: Analyzing documentation needs...")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Agent execution error: {e}")
            return False

class AgentService:
    def __init__(self, orchestrator, protocol_service, logger):
        self.logger = logger
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.planner = PlanningModule(self.root_dir, logger)
        self.executor = ExecutionModule(orchestrator, protocol_service, logger)
        self.is_busy = False

    async def run_cycle(self) -> Dict[str, Any]:
        """Perform a single autonomous cycle: Plan -> Execute -> Review."""
        if self.is_busy:
            return {"status": "skipped", "reason": "Agent is already busy"}

        self.is_busy = True
        results = {"status": "completed", "tasks_executed": []}

        try:
            self.logger.info("--- Starting Autonomous Agent Cycle ---")

            # 1. Plan
            objectives = self.planner.prioritize_objectives()
            self.logger.info(f"Agent identified {len(objectives)} objectives.")

            # 2. Execute (Handle top 2 for now to prevent runaway loops)
            for obj in objectives[:2]:
                success = await self.executor.execute_task(obj)
                results["tasks_executed"].append({"task": obj["task"], "success": success})

            # 3. Review (Re-run protocol to update workspace state)
            self.logger.info("Agent cycle review: updating technical debt...")
            await self.protocol_review()

            self.logger.info("--- Autonomous Agent Cycle Complete ---")

        except Exception as e:
            self.logger.error(f"Agent cycle failure: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
        finally:
            self.is_busy = False

        return results

    async def protocol_review(self):
        """Review the current state of the repository."""
        await self.executor.protocol.extract_roadmap()
        # In a real v1.0, this would also run tests and report health
