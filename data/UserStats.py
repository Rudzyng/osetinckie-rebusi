import sqlalchemy
from .db_session import SqlAlchemyBase


class UserStats(SqlAlchemyBase):
    __tablename__ = 'user_stats'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('users.id'), unique=True, nullable=False)
    puzzles_solved = sqlalchemy.Column(sqlalchemy.Integer, default=0, nullable=False)
    word_solved = sqlalchemy.Column(sqlalchemy.Integer, default=0, nullable=False)

    user = sqlalchemy.orm.relationship("User", back_populates="stats")

    def __repr__(self):
        return f"<UserStats> user_id={self.user_id}, puzzles_solved={self.puzzles_solved}"