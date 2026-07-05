import os
import sqlite3
import time
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")

class LearningModule:
    def __init__(self, logger, db_path: str = DB_PATH):
        self.logger = logger
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_experience (
                        task_type TEXT,
                        outcome TEXT,
                        friction REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            self.logger.error(f"LearningModule: DB init error: {e}")

    def record_experience(self, task_type: str, outcome: str, duration: float):
        """Log the outcome of a task to the experience database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO agent_experience (task_type, outcome, friction) VALUES (?, ?, ?)",
                    (task_type, outcome, duration)
                )
                conn.commit()
        except Exception as e:
            self.logger.warning(f"LearningModule: Write error: {e}")

    def get_friction_profile(self) -> Dict[str, float]:
        """Calculate average friction (latency/failure rate) per task type."""
        profile = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT task_type, AVG(friction) as avg_friction,
                    SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as failure_rate
                    FROM agent_experience
                    GROUP BY task_type
                """).fetchall()
                for row in rows:
                    # Friction score = avg_latency * (1 + failure_rate)
                    profile[row['task_type']] = row['avg_friction'] * (1 + row['failure_rate'])
        except Exception as e:
            self.logger.warning(f"LearningModule: Read error: {e}")
        return profile

class PlanningModule:
    def __init__(self, root_dir: str, learning_module: LearningModule, logger):
        self.root_dir = root_dir
        self.learner = learning_module
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

        # 3. Apply Learned Insights (Self-Learning Loop)
        friction_profile = self.learner.get_friction_profile()
        for obj in objectives:
            # If a task type has high friction (recurring failure/high latency), boost its priority
            # to address technical debt faster.
            friction = friction_profile.get(obj['type'], 0.0)
            if friction > 5.0: # Arbitrary threshold for "high friction"
                self.logger.info(f"PlanningModule: Boosting {obj['type']} priority due to learned friction ({friction:.2f})")
                obj['priority'] -= 1

        # Sort by priority
        objectives.sort(key=lambda x: (x['priority'], -friction_profile.get(x['type'], 0)))
        return objectives

class ExecutionModule:
    def __init__(self, orchestrator, protocol_service, logger):
        self.orch = orchestrator
        self.protocol = protocol_service
        self.logger = logger

    async def execute_task(self, objective: Dict[str, Any]) -> Dict[str, Any]:
        """Map objective types to system actions."""
        self.logger.info(f"Agent executing: {objective['task']}")
        start_time = time.time()

        try:
            success = False
            if objective['type'] == 'functional':
                # Example: If search task, maybe trigger a maintenance sync first
                # sync_repository is an async method
                await self.protocol.sync_repository()
                success = True

            elif objective['type'] == 'milestone':
                # Trigger roadmap extraction to update status
                await self.protocol.extract_roadmap()
                success = True

            elif objective['type'] == 'docs':
                self.logger.info("Agent: Analyzing documentation needs...")
                success = True

            duration = time.time() - start_time
            return {
                "success": success,
                "duration": duration,
                "type": objective['type']
            }
        except Exception as e:
            self.logger.error(f"Agent execution error: {e}")
            return {
                "success": False,
                "duration": time.time() - start_time,
                "type": objective['type']
            }

class AgentService:
    def __init__(self, orchestrator, protocol_service, logger, db_path: str = DB_PATH, root_dir: Optional[str] = None):
        self.logger = logger
        self.root_dir = root_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.learner = LearningModule(logger, db_path=db_path)
        self.planner = PlanningModule(self.root_dir, self.learner, logger)
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
                execution_result = await self.executor.execute_task(obj)
                results["tasks_executed"].append({
                    "task": obj["task"],
                    "success": execution_result["success"]
                })

                # 3. Learn (Self-Learning Loop)
                self.learner.record_experience(
                    task_type=execution_result["type"],
                    outcome="success" if execution_result["success"] else "failed",
                    duration=execution_result["duration"]
                )

            # 4. Review (Re-run protocol to update workspace state)
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
