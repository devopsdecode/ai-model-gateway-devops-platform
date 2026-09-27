from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.models.entities import User, ChatSession, ChatMessage, KnowledgeRecord
from app.services.model_service import model_service
from app.services.comparison_service import comparison_service

class ChatService:
    """Manages chat sessions, messages, multi-user retrieval, and database persistence."""

    async def get_or_create_user(self, db: AsyncSession, username: str, full_name: Optional[str] = None, role: str = "DevOps Engineer") -> User:
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            user = User(
                username=username,
                full_name=full_name or username.replace("_", " ").title(),
                role=role
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    async def list_users(self, db: AsyncSession) -> List[User]:
        stmt = select(User).order_by(User.created_at)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_user_sessions(self, db: AsyncSession, user_id: Optional[str] = None, username: Optional[str] = None) -> List[Dict[str, Any]]:
        stmt = select(ChatSession).options(selectinload(ChatSession.messages))
        
        if username:
            user = await self.get_or_create_user(db, username)
            stmt = stmt.where(ChatSession.user_id == user.id)
        elif user_id:
            stmt = stmt.where(ChatSession.user_id == user_id)
            
        stmt = stmt.order_by(desc(ChatSession.updated_at))
        result = await db.execute(stmt)
        sessions = result.scalars().all()

        output = []
        for s in sessions:
            msg_count = len(s.messages) if s.messages else 0
            last_msg = s.messages[-1].content if s.messages else None
            output.append({
                "id": s.id,
                "title": s.title,
                "user_id": s.user_id,
                "model_id": s.model_id,
                "is_pinned": s.is_pinned,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": msg_count,
                "last_message": (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else last_msg
            })
        return output

    async def get_session_details(self, db: AsyncSession, session_id: str) -> Optional[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def create_session(
        self,
        db: AsyncSession,
        title: str = "New Architecture Discussion",
        username: str = "devops_lead",
        model_id: str = "google-gemini-flash"
    ) -> ChatSession:
        user = await self.get_or_create_user(db, username)
        session = ChatSession(
            title=title,
            user_id=user.id,
            model_id=model_id
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def send_message_and_respond(
        self,
        db: AsyncSession,
        content: str,
        session_id: Optional[str] = None,
        username: str = "devops_lead",
        model_id: str = "google-gemini-flash",
        enable_comparison: bool = True,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Processes a user message:
        1. Ensures user and session exist.
        2. Compares input against database records (historical deduplication/matching).
        3. Saves user message to database.
        4. Invokes selected AI model module with context.
        5. Saves assistant response to database.
        6. Updates session title if it's the first message.
        """
        user = await self.get_or_create_user(db, username)

        # Retrieve or create session
        session = None
        if session_id:
            session = await self.get_session_details(db, session_id)
            
        if not session:
            # Generate short title from first prompt
            title = content.strip().split("\n")[0][:45]
            if len(content.strip().split("\n")[0]) > 45:
                title += "..."
            session = ChatSession(
                title=title,
                user_id=user.id,
                model_id=model_id
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)

        # 1. Run Data Comparison against historical database records
        comparison_res = None
        if enable_comparison:
            comparison_res = await comparison_service.compare_with_database(
                db=db,
                input_text=content,
                threshold=0.25,
                limit=3
            )

        # 2. Persist User Message in DB
        user_msg = ChatMessage(
            session_id=session.id,
            role="user",
            content=content,
            model_id=model_id,
            comparison_meta=comparison_res
        )
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)

        # 3. Explicitly load recent history asynchronously (excluding current user message)
        stmt_hist = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id, ChatMessage.id != user_msg.id)
            .order_by(desc(ChatMessage.created_at))
            .limit(8)
        )
        hist_result = await db.execute(stmt_hist)
        recent_messages = list(reversed(hist_result.scalars().all()))
        history_msgs = [{"role": m.role, "content": m.content} for m in recent_messages]

        # 4. Generate AI Model Response
        ai_res = await model_service.generate_response(
            prompt=content,
            model_id=model_id,
            chat_history=history_msgs,
            comparison_context=comparison_res,
            temperature=temperature
        )

        # 5. Persist Assistant Message in DB
        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=ai_res["content"],
            model_id=model_id,
            tokens_prompt=ai_res["tokens_prompt"],
            tokens_completion=ai_res["tokens_completion"],
            latency_ms=ai_res["latency_ms"],
            comparison_meta=comparison_res
        )
        db.add(assistant_msg)

        # 6. Update session model and timestamp
        session.model_id = model_id
        await db.commit()
        await db.refresh(assistant_msg)

        return {
            "session_id": session.id,
            "session_title": session.title,
            "user_message": user_msg,
            "assistant_message": assistant_msg,
            "comparison": comparison_res,
            "model_used": model_id
        }

    async def delete_session(self, db: AsyncSession, session_id: str) -> bool:
        stmt = select(ChatSession).where(ChatSession.id == session_id)
        result = await db.execute(stmt)
        session = result.scalars().first()
        if session:
            await db.delete(session)
            await db.commit()
            return True
        return False

chat_service = ChatService()
