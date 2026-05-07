"""SQLAlchemy models — importing this module registers all tables on Base.metadata."""
from app.models.base import Base
from app.models.user import User, UserRole
from app.models.invite import Invite
from app.models.settings import AppSetting
from app.models.class_spec import GameClass, GameSpec, Role
from app.models.report import Report, ReportFight, ReportPlayer, ReportPlayerCast, ReportPlayerGear
from app.models.top_log import TopLog
from app.models.analysis import Analysis, AnalysisStatus

__all__ = [
    "Analysis",
    "AnalysisStatus",
    "AppSetting",
    "Base",
    "GameClass",
    "GameSpec",
    "Invite",
    "Report",
    "ReportFight",
    "ReportPlayer",
    "ReportPlayerCast",
    "ReportPlayerGear",
    "Role",
    "TopLog",
    "User",
    "UserRole",
]
