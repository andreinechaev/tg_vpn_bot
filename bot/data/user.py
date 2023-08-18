from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, Float
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import create_engine

engine = create_engine("sqlite://", echo=True, future=True)
Base = declarative_base()
Base.metadata.create_all(engine)

class User(Base):
    __tablename__ = "user_account"
    id = Column(Integer, primary_key=True)
    name = Column(String(64))
    fullname = Column(String)
    link = Column(String)
    invited = relationship(
        "Invitation", back_populates="users", cascade="all, delete-orphan")
    initial_space = Column(Float)
    current_space = Column(Float)

    def __repr__(self):
        return f"User(id={self.id!r}, name={self.name!r}, fullname={self.fullname!r})"


class Invitation(Base):
    __tablename__ = "invitation"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_account.id"), nullable=False)
    user = relationship("User", back_populates="invitations")

    def __repr__(self):
        return f"Invitation(id={self.id!r}, email_address={self.user.fullname!r})"
