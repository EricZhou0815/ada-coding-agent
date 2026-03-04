"""
Planning Service for Ada

Stateless service for managing planning sessions. Handles batch planning
with sequential or parallel execution and auto-queueing to execution.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from agents.planning_agent import PlanningAgent
from api.database import PlanningBatch, PlanningSession, StoryJob
from utils.logger import logger


class PlanningService:
    """
    Service layer for managing planning sessions and batches.
    
    Responsibilities:
    - Create and manage planning batches
    - Process planning session conversations
    - Auto-queue completed stories to execution
    - Handle sequential/parallel planning modes
    """
    
    COMPLETION_SIGNAL = "STORY_COMPLETE"
    
    def __init__(self, llm_client):
        """
        Initialize the planning service.
        
        Args:
            llm_client: LLM client for conversation
        """
        self.llm_client = llm_client
        self.planning_agent = PlanningAgent(llm_client)
    
    async def create_batch(
        self,
        db: Session,
        repo_url: str,
        inputs: List[Dict | str],
        planning_mode: str = "sequential",
        auto_execute: bool = True
    ) -> Tuple[PlanningBatch, List[str]]:
        """
        Create a planning batch from user inputs.
        
        Classifies each input as:
        - Complete story → Queue to execution immediately
        - Needs planning → Create planning session
        
        Args:
            db: Database session
            repo_url: Repository URL for execution
            inputs: List of user requests (natural language or partial stories)
            planning_mode: "sequential" or "parallel"
            auto_execute: Whether to auto-queue completed stories
            
        Returns:
            Tuple of (PlanningBatch, list of execution job_ids)
        """
        batch = PlanningBatch(
            id=f"batch-{uuid.uuid4().hex[:12]}",
            repo_url=repo_url,
            planning_mode=planning_mode,
            auto_execute=1 if auto_execute else 0
        )
        db.add(batch)
        
        execution_jobs = []
        first_session_activated = False
        
        for idx, user_input in enumerate(inputs):
            # Check if input is already a complete story
            if self._is_complete_story(user_input):
                # Queue directly to execution
                if auto_execute:
                    job_id = self._create_execution_job(db, repo_url, user_input)
                    execution_jobs.append(job_id)
                    logger.info("PlanningService", f"Story {idx + 1} already complete, queued to execution: {job_id}")
            else:
                # Needs planning - create session
                session_state = "pending"
                
                # In sequential mode, activate first session only
                if planning_mode == "sequential" and not first_session_activated:
                    session_state = "active"
                    first_session_activated = True
                # In parallel mode, activate all
                elif planning_mode == "parallel":
                    session_state = "active"
                
                session = self._create_planning_session(
                    db=db,
                    batch_id=batch.id,
                    user_input=self._input_to_string(user_input),
                    state=session_state
                )
                
                # If activated, generate initial question
                if session_state == "active":
                    await self._generate_initial_question(db, session)
        
        db.commit()
        logger.info("PlanningService", f"Created batch {batch.id} with {len(batch.sessions)} sessions, {len(execution_jobs)} immediate jobs")
        
        return batch, execution_jobs
    
    async def process_message(
        self,
        db: Session,
        session_id: str,
        message: str
    ) -> PlanningSession:
        """
        Process a user message in a planning session.
        
        Args:
            db: Database session
            session_id: Planning session ID
            message: User's message (answer to question)
            
        Returns:
            Updated PlanningSession
        """
        session = db.query(PlanningSession).filter(
            PlanningSession.id == session_id
        ).first()
        
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.state not in ["active", "pending"]:
            raise ValueError(f"Session {session_id} is in state '{session.state}' and cannot accept messages")
        
        # Activate if pending (shouldn't happen in normal flow but handle gracefully)
        if session.state == "pending":
            session.state = "active"
        
        # Add user message to conversation history
        if session.conversation_history is None:
            session.conversation_history = []
        session.conversation_history.append({"role": "user", "content": message})
        session.iteration += 1
        
        # Check iteration limit
        if session.iteration >= session.max_iterations:
            session.state = "error"
            session.error_message = f"Reached maximum iterations ({session.max_iterations})"
            db.commit()
            logger.warning("PlanningService", f"Session {session_id} hit max iterations")
            return session
        
        try:
            # Get LLM response
            # Reload conversation into LLM
            self.llm_client.reset_conversation()
            system_prompt = self.planning_agent._build_system_prompt()
            self.llm_client.conversation_history.append({"role": "system", "content": system_prompt})
            
            for msg in session.conversation_history:
                self.llm_client.conversation_history.append(msg)
            
            response = await self.llm_client.generate(message, tools=None)
            content = response.get("content", "") or ""
            
            # Add assistant response to history
            session.conversation_history.append({"role": "assistant", "content": content})
            
            logger.thought("PlanningAgent", content)
            
            # Check if complete
            if self.COMPLETION_SIGNAL in content:
                story = self.planning_agent._extract_story(content)
                
                if story:
                    # Add metadata
                    if "metadata" not in story:
                        story["metadata"] = {}
                    story["metadata"].update({
                        "source": "planning_agent",
                        "planning_agent_version": "1.0",
                        "questions_asked": session.questions_asked,
                        "planning_duration_seconds": int((datetime.now(timezone.utc) - session.created_at).total_seconds()),
                        "iterations": session.iteration
                    })
                    
                    # Auto-generate story_id if missing
                    if "story_id" not in story:
                        story["story_id"] = f"STORY-AUTO-{uuid.uuid4().hex[:8].upper()}"
                    
                    session.story_result = story
                    session.state = "complete"
                    session.completed_at = datetime.now(timezone.utc)
                    session.current_question = None
                    
                    logger.success("PlanningService", f"Session {session_id} complete: {story['title']}")
                    
                    # Auto-queue to execution if enabled
                    batch = session.batch
                    if batch and batch.auto_execute:
                        job_id = self._create_execution_job(db, batch.repo_url, story)
                        session.execution_job_id = job_id
                        logger.info("PlanningService", f"Auto-queued story to execution: {job_id}")
                    
                    # In sequential mode, activate next pending session
                    if batch and batch.planning_mode == "sequential":
                        await self._activate_next_session(db, batch.id)
                    
                else:
                    # Story extraction failed
                    session.current_question = "The story format was invalid. Please confirm the details are correct."
                    logger.warning("PlanningService", f"Session {session_id} - story extraction failed")
            else:
                # Check if this looks like a question
                if "?" in content or any(word in content.lower() for word in ["what", "how", "who", "when", "where", "which"]):
                    session.questions_asked += 1
                
                # Store current question
                session.current_question = content
            
            session.updated_at = datetime.now(timezone.utc)
            db.commit()
            
        except Exception as e:
            logger.error("PlanningService", f"Error processing message in session {session_id}: {e}")
            session.state = "error"
            session.error_message = str(e)
            db.commit()
        
        return session
    
    def get_session(self, db: Session, session_id: str) -> Optional[PlanningSession]:
        """Get a planning session by ID."""
        return db.query(PlanningSession).filter(
            PlanningSession.id == session_id
        ).first()
    
    def get_batch(self, db: Session, batch_id: str) -> Optional[PlanningBatch]:
        """Get a planning batch by ID."""
        return db.query(PlanningBatch).filter(
            PlanningBatch.id == batch_id
        ).first()
    
    def cancel_session(self, db: Session, session_id: str) -> bool:
        """Cancel a planning session."""
        session = self.get_session(db, session_id)
        if session and session.state in ["pending", "active"]:
            session.state = "cancelled"
            session.updated_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("PlanningService", f"Cancelled session {session_id}")
            return True
        return False
    
    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────
    
    def _is_complete_story(self, user_input: Dict | str) -> bool:
        """Check if input is already a complete user story."""
        if isinstance(user_input, dict):
            required_fields = ["title", "description", "acceptance_criteria"]
            return all(field in user_input for field in required_fields)
        return False
    
    def _input_to_string(self, user_input: Dict | str) -> str:
        """Convert user input to string format."""
        if isinstance(user_input, str):
            return user_input
        elif isinstance(user_input, dict):
            return json.dumps(user_input)
        return str(user_input)
    
    def _create_planning_session(
        self,
        db: Session,
        batch_id: str,
        user_input: str,
        state: str = "pending"
    ) -> PlanningSession:
        """Create a new planning session."""
        session = PlanningSession(
            id=f"session-{uuid.uuid4().hex[:12]}",
            batch_id=batch_id,
            user_input=user_input,
            state=state,
            conversation_history=[],
            iteration=0,
            questions_asked=0
        )
        db.add(session)
        return session
    
    async def _generate_initial_question(self, db: Session, session: PlanningSession):
        """Generate the initial question for a planning session."""
        try:
            # Use planning agent to generate first question
            system_prompt = self.planning_agent._build_system_prompt()
            initial_request = self.planning_agent._parse_input(session.user_input)
            
            self.llm_client.reset_conversation()
            self.llm_client.conversation_history.append({"role": "system", "content": system_prompt})
            
            response = await self.llm_client.generate(initial_request, tools=None)
            content = response.get("content", "") or ""
            
            # Add to history
            session.conversation_history = [
                {"role": "user", "content": initial_request},
                {"role": "assistant", "content": content}
            ]
            
            # Check if already complete (story was clear enough)
            if self.COMPLETION_SIGNAL in content:
                story = self.planning_agent._extract_story(content)
                if story:
                    if "story_id" not in story:
                        story["story_id"] = f"STORY-AUTO-{uuid.uuid4().hex[:8].upper()}"
                    
                    session.story_result = story
                    session.state = "complete"
                    session.completed_at = datetime.now(timezone.utc)
                    logger.success("PlanningService", f"Session {session.id} completed immediately (clear input)")
                    
                    # Auto-queue if enabled
                    batch = session.batch
                    if batch and batch.auto_execute:
                        job_id = self._create_execution_job(db, batch.repo_url, story)
                        session.execution_job_id = job_id
                    
                    # Activate next session in sequential mode
                    if batch and batch.planning_mode == "sequential":
                        await self._activate_next_session(db, batch.id)
                    return
            
            # Store the question
            session.current_question = content
            session.iteration = 1
            
            if "?" in content:
                session.questions_asked = 1
            
            logger.info("PlanningService", f"Generated initial question for session {session.id}")
            
        except Exception as e:
            logger.error("PlanningService", f"Failed to generate initial question for session {session.id}: {e}")
            session.state = "error"
            session.error_message = f"Failed to start planning: {str(e)}"
    
    def _create_execution_job(self, db: Session, repo_url: str, story: Dict) -> str:
        """Create an execution job for a completed story."""
        from worker.tasks import execute_sdlc_story
        
        job_id = str(uuid.uuid4())
        
        job = StoryJob(
            id=job_id,
            repo_url=repo_url,
            story_title=story.get("title", "Unknown"),
            status="PENDING",
            logs=json.dumps([{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Story queued from planning agent"
            }])
        )
        db.add(job)
        db.commit()
        
        # Dispatch to Celery
        execute_sdlc_story.delay(
            job_id=job_id,
            repo_url=repo_url,
            story=story,
            use_mock=False
        )
        
        return job_id
    
    async def _activate_next_session(self, db: Session, batch_id: str):
        """In sequential mode, activate the next pending session."""
        next_session = db.query(PlanningSession).filter(
            PlanningSession.batch_id == batch_id,
            PlanningSession.state == "pending"
        ).order_by(PlanningSession.created_at).first()
        
        if next_session:
            next_session.state = "active"
            await self._generate_initial_question(db, next_session)
            db.commit()
            logger.info("PlanningService", f"Activated next session: {next_session.id}")
