from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Site / time
    site_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Load
    tower_load_kw: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    energy_consumption_kwh: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Solar
    solar_power_kw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    solar_irradiance: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Battery
    battery_soc: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    battery_health: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    battery_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    battery_voltage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    battery_current: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    battery_temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Grid
    grid_available: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    grid_power_kw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    grid_voltage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    grid_frequency_hz: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    electricity_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    tariff_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Generator
    generator_available: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    generator_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    generator_power_kw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    fuel_level: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    fuel_consumption_lph: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Environment
    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Current operation
    power_source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    equipment_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )