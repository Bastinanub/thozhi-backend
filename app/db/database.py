from sqlmodel import SQLModel, create_engine, Session

# SQLite file (simple + perfect for research logging)
DATABASE_URL = "sqlite:///./thozhi.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

# Dependency for FastAPI routes
def get_db():
    with Session(engine) as session:
        yield session

# IMPORTANT → This creates tables automatically
def init_db():
    SQLModel.metadata.create_all(engine)