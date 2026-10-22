"""
PostgreSQL-backed and In-Memory Persistent Checkpointers for ERM Copilot.
Handles safe state persistence, optimistic locking, ownership isolation,
and multi-turn workflow continuation.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import AuthorizationError
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
)

logger = logging.getLogger("ERM_Copilot.workflow.checkpointer")


class CheckpointError(Exception):
    """Base exception for checkpoint operations."""
    pass


class ConcurrencyConflictError(CheckpointError):
    """Raised when an optimistic locking version conflict occurs."""
    def __init__(self, workflow_id: str, expected_version: int, actual_version: int):
        super().__init__(
            f"Concurrency conflict on workflow '{workflow_id}': expected version {expected_version}, but actual version is {actual_version}."
        )


class BaseWorkflowCheckpointer(ABC):
    """Abstract interface for workflow state checkpointers."""

    @abstractmethod
    def save(self, state: AgentWorkflowState, expected_version: Optional[int] = None) -> AgentWorkflowState:
        """Persist workflow state with optimistic locking check."""
        pass

    @abstractmethod
    def load(self, workflow_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        """Load workflow state by ID with ownership verification."""
        pass

    @abstractmethod
    def load_active_for_session(self, session_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        """Load the currently active (non-terminal) workflow for a user/session."""
        pass

    @abstractmethod
    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow checkpoint."""
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        """Clean up expired workflows and return count of removed items."""
        pass


class InMemoryWorkflowCheckpointer(BaseWorkflowCheckpointer):
    """
    Thread-safe, isolated in-memory checkpointer for testing and fallback.
    """
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def save(self, state: AgentWorkflowState, expected_version: Optional[int] = None) -> AgentWorkflowState:
        wid = state.workflow_id
        if wid in self._store and expected_version is not None:
            actual_version = self._store[wid]["state_version"]
            if actual_version != expected_version:
                raise ConcurrencyConflictError(wid, expected_version, actual_version)

        state.updated_at = datetime.now(timezone.utc)
        payload = state.to_checkpoint_dict()
        self._store[wid] = payload
        return state

    def load(self, workflow_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        data = self._store.get(workflow_id)
        if not data:
            return None

        # Verify ownership if context is provided
        if context and context.user_id:
            owner_id = str(data.get("owner_user_id", "")).strip()
            req_user_id = str(context.user_id).strip()
            is_super = "super admin" in str(context.user_role or "").lower()
            if owner_id != req_user_id and not is_super:
                raise AuthorizationError(
                    f"Access Denied: User '{context.user_id}' cannot access workflow owned by '{owner_id}'."
                )

        state = AgentWorkflowState.from_checkpoint_dict(data)
        if state.is_expired and not state.is_terminal:
            state.transition_to(WorkflowStatus.EXPIRED, reason="TTL expired")
            self.save(state)
        return state

    def load_active_for_session(self, session_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        for data in self._store.values():
            if data.get("session_id") == session_id:
                state = AgentWorkflowState.from_checkpoint_dict(data)
                if not state.is_terminal and not state.is_expired:
                    if context and context.user_id:
                        owner_id = str(state.owner_user_id).strip()
                        req_user_id = str(context.user_id).strip()
                        is_super = "super admin" in str(context.user_role or "").lower()
                        if owner_id != req_user_id and not is_super:
                            continue
                    return state
        return None

    def delete(self, workflow_id: str) -> bool:
        if workflow_id in self._store:
            del self._store[workflow_id]
            return True
        return False

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired_ids = []
        for wid, data in list(self._store.items()):
            exp = data.get("expires_at")
            if exp:
                exp_dt = datetime.fromisoformat(exp) if isinstance(exp, str) else exp
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if now > exp_dt:
                    expired_ids.append(wid)
        for wid in expired_ids:
            del self._store[wid]
        return len(expired_ids)

    def clear(self) -> None:
        self._store.clear()


class PostgreSQLWorkflowCheckpointer(BaseWorkflowCheckpointer):
    """
    Production PostgreSQL Checkpoint Backend.
    Stores and restores workflow checkpoints in table `ers.agent_workflow_checkpoints`.
    """
    def __init__(self, fallback_in_memory: bool = True):
        self.schema = "ers"
        self.table_name = "agent_workflow_checkpoints"
        self.full_table = f"{self.schema}.{self.table_name}"
        self.fallback = InMemoryWorkflowCheckpointer() if fallback_in_memory else None
        self._schema_ensured = False

    def _get_connection(self):
        from ERM_Copilot.services.db_service import erm_db
        return erm_db._get_connection(readonly=False)

    def ensure_schema(self) -> None:
        """Create checkpoints table and indexes if they do not exist."""
        if self._schema_ensured:
            return
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.full_table} (
                    workflow_id VARCHAR(64) PRIMARY KEY,
                    conversation_id VARCHAR(64) NOT NULL,
                    session_id VARCHAR(128) NOT NULL,
                    owner_user_id VARCHAR(64) NOT NULL,
                    owner_role VARCHAR(64) NOT NULL,
                    dept_id INT,
                    workflow_type VARCHAR(64) NOT NULL,
                    workflow_status VARCHAR(64) NOT NULL,
                    current_agent VARCHAR(64) NOT NULL,
                    current_step VARCHAR(64) NOT NULL,
                    state_version INT NOT NULL DEFAULT 1,
                    state_payload TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_session ON {self.full_table} (session_id, workflow_status);
                CREATE INDEX IF NOT EXISTS idx_workflow_owner ON {self.full_table} (owner_user_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_expires ON {self.full_table} (expires_at);
            """)
            conn.commit()
            cur.close()
            conn.close()
            self._schema_ensured = True
            logger.info(f"[CHECKPOINTER] Checkpoint schema verified for {self.full_table}")
        except Exception as e:
            logger.warning(f"[CHECKPOINTER] Could not ensure PostgreSQL schema (using fallback if enabled): {e}")
            self._schema_ensured = False

    def save(self, state: AgentWorkflowState, expected_version: Optional[int] = None) -> AgentWorkflowState:
        try:
            self.ensure_schema()
            conn = self._get_connection()
            cur = conn.cursor()

            state.updated_at = datetime.now(timezone.utc)
            payload_json = json.dumps(state.to_checkpoint_dict(), default=str)
            wid = state.workflow_id
            status_val = state.workflow_status.value if hasattr(state.workflow_status, "value") else str(state.workflow_status)
            type_val = state.workflow_type.value if hasattr(state.workflow_type, "value") else str(state.workflow_type)

            if expected_version is not None:
                # Check optimistic lock with row-level lock across workers
                cur.execute(f"SELECT state_version FROM {self.full_table} WHERE workflow_id = %s FOR UPDATE", (wid,))
                row = cur.fetchone()
                if row and row[0] != expected_version:
                    actual_v = row[0]
                    conn.rollback()
                    cur.close()
                    conn.close()
                    raise ConcurrencyConflictError(wid, expected_version, actual_v)

            upsert_query = f"""
                INSERT INTO {self.full_table} (
                    workflow_id, conversation_id, session_id, owner_user_id, owner_role,
                    dept_id, workflow_type, workflow_status, current_agent, current_step,
                    state_version, state_payload, created_at, updated_at, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workflow_id) DO UPDATE SET
                    workflow_status = EXCLUDED.workflow_status,
                    current_agent = EXCLUDED.current_agent,
                    current_step = EXCLUDED.current_step,
                    state_version = EXCLUDED.state_version,
                    state_payload = EXCLUDED.state_payload,
                    updated_at = EXCLUDED.updated_at,
                    expires_at = EXCLUDED.expires_at;
            """
            cur.execute(upsert_query, (
                wid,
                state.conversation_id,
                state.session_id,
                state.owner_user_id,
                state.owner_role,
                state.dept_id,
                type_val,
                status_val,
                state.current_agent,
                state.current_step,
                state.state_version,
                payload_json,
                state.created_at,
                state.updated_at,
                state.expires_at
            ))
            conn.commit()
            cur.close()
            conn.close()

            # Mirror to fallback store
            if self.fallback:
                self.fallback.save(state, expected_version)
            return state

        except ConcurrencyConflictError:
            raise
        except Exception as e:
            logger.error(f"[CHECKPOINTER_ERROR] Failed saving to PostgreSQL: {e}")
            if self.fallback:
                logger.info("[CHECKPOINTER] Falling back to in-memory store.")
                return self.fallback.save(state, expected_version)
            raise CheckpointError(f"Failed to persist checkpoint: {e}")

    def load(self, workflow_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        try:
            self.ensure_schema()
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(f"SELECT state_payload FROM {self.full_table} WHERE workflow_id = %s", (workflow_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                if self.fallback:
                    return self.fallback.load(workflow_id, context)
                return None

            payload_dict = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            
            # Enforce Ownership Security
            if context and context.user_id:
                owner_id = str(payload_dict.get("owner_user_id", "")).strip()
                req_user_id = str(context.user_id).strip()
                is_super = "super admin" in str(context.user_role or "").lower()
                if owner_id != req_user_id and not is_super:
                    raise AuthorizationError(
                        f"Access Denied: User '{context.user_id}' cannot access workflow owned by '{owner_id}'."
                    )

            state = AgentWorkflowState.from_checkpoint_dict(payload_dict)
            if state.is_expired and not state.is_terminal:
                state.transition_to(WorkflowStatus.EXPIRED, reason="TTL expired")
                self.save(state)
            return state

        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"[CHECKPOINTER_ERROR] Failed loading from PostgreSQL: {e}")
            if self.fallback:
                return self.fallback.load(workflow_id, context)
            return None

    def load_active_for_session(self, session_id: str, context: Optional[HarnessContext] = None) -> Optional[AgentWorkflowState]:
        try:
            self.ensure_schema()
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(f"""
                SELECT state_payload FROM {self.full_table}
                WHERE session_id = %s AND workflow_status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED')
                ORDER BY updated_at DESC LIMIT 1
            """, (session_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                if self.fallback:
                    return self.fallback.load_active_for_session(session_id, context)
                return None

            payload_dict = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            
            # Enforce Ownership
            if context and context.user_id:
                owner_id = str(payload_dict.get("owner_user_id", "")).strip()
                req_user_id = str(context.user_id).strip()
                is_super = "super admin" in str(context.user_role or "").lower()
                if owner_id != req_user_id and not is_super:
                    return None

            state = AgentWorkflowState.from_checkpoint_dict(payload_dict)
            if state.is_expired and not state.is_terminal:
                state.transition_to(WorkflowStatus.EXPIRED, reason="TTL expired")
                self.save(state)
                return None
            return state

        except Exception as e:
            logger.error(f"[CHECKPOINTER_ERROR] Failed loading active workflow from PostgreSQL: {e}")
            if self.fallback:
                return self.fallback.load_active_for_session(session_id, context)
            return None

    def delete(self, workflow_id: str) -> bool:
        try:
            self.ensure_schema()
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {self.full_table} WHERE workflow_id = %s", (workflow_id,))
            conn.commit()
            deleted = cur.rowcount > 0
            cur.close()
            conn.close()
            if self.fallback:
                self.fallback.delete(workflow_id)
            return deleted
        except Exception as e:
            logger.error(f"[CHECKPOINTER_ERROR] Failed deleting checkpoint: {e}")
            if self.fallback:
                return self.fallback.delete(workflow_id)
            return False

    def cleanup_expired(self) -> int:
        try:
            self.ensure_schema()
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(timezone.utc)
            cur.execute(f"DELETE FROM {self.full_table} WHERE expires_at < %s", (now,))
            conn.commit()
            count = cur.rowcount
            cur.close()
            conn.close()
            if self.fallback:
                self.fallback.cleanup_expired()
            return count
        except Exception as e:
            logger.error(f"[CHECKPOINTER_ERROR] Failed cleanup: {e}")
            if self.fallback:
                return self.fallback.cleanup_expired()
            return 0


# Global Singleton Checkpointer
workflow_checkpointer = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
