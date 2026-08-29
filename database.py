import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent


def _database_url():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url

    db_path = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "product_hunter_v5.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


DATABASE_URL = _database_url()
IS_POSTGRES = DATABASE_URL.startswith("postgresql+")

engine_kwargs = {"pool_pre_ping": True, "future": True}
if DATABASE_URL.startswith("sqlite:"):
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


class SearchSession(Base):
    __tablename__ = "search_sessions"
    id = Column(String(36), primary_key=True)
    keyword = Column(String(180), default="")
    country = Column(String(8), default="SE", index=True)
    ads_pasted_count = Column(Integer, default=0)
    user_notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(String(36), primary_key=True)
    search_session_id = Column(String(36), ForeignKey("search_sessions.id"), nullable=True, index=True)
    status = Column(String(24), default="pending", index=True)
    total_chunks = Column(Integer, default=0)
    processed_chunks = Column(Integer, default=0)
    total_ads = Column(Integer, default=0)
    new_ads = Column(Integer, default=0)
    duplicate_ads = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class JobChunk(Base):
    __tablename__ = "job_chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    status = Column(String(24), default="pending", index=True)
    retry_count = Column(Integer, default=0)
    content_hash = Column(String(64), nullable=False)
    raw_text = Column(Text, nullable=False)
    error = Column(Text, default="")
    processed_at = Column(DateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_job_chunk_index"),
        UniqueConstraint("job_id", "content_hash", name="uq_job_chunk_hash"),
    )


class Ad(Base):
    __tablename__ = "ads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    library_id = Column(String(80), unique=True, nullable=True, index=True)
    fingerprint = Column(String(64), unique=True, nullable=False, index=True)
    company = Column(String(180), nullable=False, default="Okänt företag")
    company_normalized = Column(String(180), nullable=False, default="", index=True)
    product_name = Column(String(180), default="Fysisk produkt")
    category = Column(String(120), default="Övrig vardagsprodukt", index=True)
    problem_type = Column(String(120), default="Allmänt vardagsproblem", index=True)
    problem_summary = Column(Text, default="")
    country = Column(String(8), default="SE", index=True)
    keyword = Column(String(180), default="")
    search_session_id = Column(String(36), ForeignKey("search_sessions.id"), nullable=True, index=True)
    raw_text = Column(Text, nullable=False)
    ad_status = Column(String(24), default="unknown", index=True)
    ad_start_date = Column(String(32), default="")
    ad_end_date = Column(String(32), default="")
    ad_age_days = Column(Integer, nullable=True)
    simhash = Column(String(20), default="", index=True)
    data_quality = Column(Float, default=0.0)
    metrics_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class Cluster(Base):
    __tablename__ = "product_clusters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_key = Column(String(180), unique=True, nullable=False, index=True)
    name = Column(String(180), default="Fysisk produkt")
    category = Column(String(120), default="Övrig vardagsprodukt", index=True)
    problem_type = Column(String(120), default="Allmänt vardagsproblem", index=True)
    representative_ad_id = Column(Integer, ForeignKey("ads.id"), nullable=True)
    signature_json = Column(Text, default="{}")
    market_proof = Column(Float, default=0.0, index=True)
    opportunity_score = Column(Float, default=0.0, index=True)
    confidence = Column(Float, default=0.0)
    age_status = Column(String(24), default="UNKNOWN", index=True)
    data_quality = Column(Float, default=0.0)
    decision = Column(String(40), default="MER DATA")
    breakdown_json = Column(Text, default="{}")
    deep_review_json = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)


class ClusterMembership(Base):
    __tablename__ = "cluster_membership"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("product_clusters.id"), nullable=False, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), nullable=False, unique=True, index=True)
    similarity = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Top5Snapshot(Base):
    __tablename__ = "top5_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    cluster_id = Column(Integer, ForeignKey("product_clusters.id"), nullable=False, index=True)
    opportunity_score = Column(Float, default=0.0)
    evidence_delta_json = Column(Text, default="{}")


class TestResult(Base):
    __tablename__ = "test_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("product_clusters.id"), nullable=False, index=True)
    outcome = Column(String(24), default="INCONCLUSIVE")
    cpa = Column(Float, nullable=True)
    ctr = Column(Float, nullable=True)
    cpc = Column(Float, nullable=True)
    cvr = Column(Float, nullable=True)
    aov = Column(Float, nullable=True)
    roas = Column(Float, nullable=True)
    cogs = Column(Float, nullable=True)
    return_rate = Column(Float, nullable=True)
    execution_quality_rating = Column(Integer, nullable=True)
    execution_notes = Column(Text, default="")
    price_point = Column(Float, nullable=True)
    country_tested = Column(String(8), default="")
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db():
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def backend_name():
    return "postgres" if IS_POSTGRES else "sqlite"


def persistent_backend():
    return IS_POSTGRES
