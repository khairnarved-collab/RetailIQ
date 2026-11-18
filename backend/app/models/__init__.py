"""Import every model so SQLAlchemy / Alembic can see the full schema."""
from app.models.customer import (  # noqa: F401
    Customer,
    CustomerSegment,
    CustomerTransaction,
)
from app.models.data import DataQualityReport, Dataset  # noqa: F401
from app.models.ml import Forecast, ForecastRun, ModelEvaluation  # noqa: F401
from app.models.retail import (  # noqa: F401
    CalendarDay,
    Category,
    InventoryItem,
    Price,
    Product,
    Sale,
    Store,
    Supplier,
)
from app.models.system import AppSetting, Notification, Report  # noqa: F401
from app.models.user import Role, User  # noqa: F401
