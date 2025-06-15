import uuid, datetime as dt
from sqlalchemy import String, Text, JSON, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship
from database import Base

# ─── RSS + LLM-кэш ────────────────────────────────────────────────────────
class RssPost(Base):
    __tablename__ = "rss_posts"
    post_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feed_url:  Mapped[str]       = mapped_column(String)
    title:     Mapped[str]       = mapped_column(Text)
    link:      Mapped[str]       = mapped_column(Text)
    content:   Mapped[str]       = mapped_column(Text)
    published: Mapped[dt.datetime] = mapped_column(DateTime)
    created_at:Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    llm_cache: Mapped["NewsLLMCache"] = relationship(back_populates="post", uselist=False, cascade="all, delete")

class NewsLLMCache(Base):
    __tablename__ = "news_llm_cache"
    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rss_posts.post_id", ondelete="CASCADE"), unique=True)
    asset:     Mapped[str]       = mapped_column(String(16), index=True)
    sentiment: Mapped[str]       = mapped_column(String(8))
    confidence:Mapped[float]     = mapped_column(Float)
    reason:    Mapped[str]       = mapped_column(Text)
    summary_md:Mapped[str]       = mapped_column(Text)
    llm_raw:   Mapped[dict]      = mapped_column(JSON)
    created_at:Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    post:      Mapped[RssPost]   = relationship(back_populates="llm_cache")

# ─── Trades (добавлена) ──────────────────────────────────────────────────
class Trade(Base):
    __tablename__ = "trades"
    id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts:       Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
    symbol:   Mapped[str]   = mapped_column(String(16), index=True)
    side:     Mapped[str]   = mapped_column(String(4))      # BUY / SELL
    qty:      Mapped[float] = mapped_column(Float)
    price:    Mapped[float] = mapped_column(Float)
    fee:      Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float)
