"""Database models for ToneTrace AI.

Includes:
- SystemAuditLog (Phase 1 foundational operational audit)
- User, UserSession, UserProfile, SkinProfile, UserSensitivity,
  UserPreference, UserConsent (Phase 2 Auth & Profiles)

Follows strict database rules:
- UUID primary keys
- Timezone-aware UTC timestamps
- Foreign keys with ON DELETE CASCADE and explicit indexes
- Explicit uniqueness constraints
- Passwords stored strictly as Argon2id hashes
- Refresh tokens stored strictly as SHA-256 hashes
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Portable JSON column definition across PostgreSQL and SQLite
JsonType = JSON().with_variant(JSONB, "postgresql")


class SystemAuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Operational audit record for tracking system lifecycle events."""

    __tablename__ = "system_audit_logs"

    event_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Categorical name of the lifecycle event",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="system",
        index=True,
        comment="Subsystem emitting the event",
    )
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized diagnostic context or description",
    )

    __table_args__ = (
        Index("ix_system_audit_logs_event_name_created_at", "event_name", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SystemAuditLog id={self.id} event={self.event_name}>"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Core user account entity."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Normalized lowercase user email address",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Argon2id password hash",
    )
    account_status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
        index=True,
        comment="Account status: active, suspended, deactivated",
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Email verification status",
    )

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(UserSession.created_at)",
    )
    profile: Mapped["UserProfile | None"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    skin_profile: Mapped["SkinProfile | None"] = relationship(
        "SkinProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sensitivities: Mapped[list["UserSensitivity"]] = relationship(
        "UserSensitivity",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="UserSensitivity.ingredient_name",
    )
    preferences: Mapped["UserPreference | None"] = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    consents: Mapped[list["UserConsent"]] = relationship(
        "UserConsent",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(
        "MediaAsset",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    skin_scans: Mapped[list["SkinScan"]] = relationship(
        "SkinScan",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(SkinScan.created_at)",
    )
    skin_journal_entries: Mapped[list["SkinJournalEntry"]] = relationship(
        "SkinJournalEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(SkinJournalEntry.recorded_at)",
    )
    shelf_products: Mapped[list["UserProduct"]] = relationship(
        "UserProduct",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(UserProduct.created_at)",
    )
    product_reactions: Mapped[list["ProductReaction"]] = relationship(
        "ProductReaction",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(ProductReaction.observed_at)",
    )
    routines: Mapped[list["Routine"]] = relationship(
        "Routine",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(Routine.created_at)",
    )
    routine_completions: Mapped[list["RoutineCompletion"]] = relationship(
        "RoutineCompletion",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(RoutineCompletion.completed_at)",
    )
    reminder_preference: Mapped["ReminderPreference | None"] = relationship(
        "ReminderPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    reminder_deliveries: Mapped[list["ReminderDeliveryRecord"]] = relationship(
        "ReminderDeliveryRecord",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(ReminderDeliveryRecord.created_at)",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class UserSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Server-side authentication session and refresh token record."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Owning user reference",
    )
    hashed_refresh_token: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="SHA-256 digest of rotating refresh token",
    )
    device_label: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Optional client description or User-Agent summary",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
        comment="Refresh token absolute expiration timestamp",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Revocation timestamp (null if active)",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")

    @property
    def is_active(self) -> bool:
        """Evaluate if the session is currently valid and unexpired."""
        now = datetime.now(UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return self.revoked_at is None and expires_at > now

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user={self.user_id} active={self.is_active}>"


class UserProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """General user profile attributes (display name and timezone)."""

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
        comment="Associated user account (1:1)",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Public-facing display name",
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
        nullable=False,
        comment="User timezone preference for notifications and daily routines",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile id={self.id} user={self.user_id} display_name={self.display_name}>"


class SkinProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Self-reported skin attributes, concerns, and skincare goals."""

    __tablename__ = "skin_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
        comment="Associated user account (1:1)",
    )
    skin_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Self-reported skin type: dry, oily, combination, normal, sensitive",
    )
    skin_concerns: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="List of skin concerns (e.g. acne, redness, hyperpigmentation)",
    )
    skin_goals: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="List of skincare goals (e.g. hydration, barrier_support, brightening)",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="skin_profile")

    def __repr__(self) -> str:
        return f"<SkinProfile id={self.id} user={self.user_id} skin_type={self.skin_type}>"


class UserSensitivity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-reported cosmetic ingredient sensitivities or avoidances."""

    __tablename__ = "user_sensitivities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Associated user account",
    )
    ingredient_name: Mapped[str] = mapped_column(
        String(150),
        index=True,
        nullable=False,
        comment="Normalized ingredient name to avoid",
    )
    severity: Mapped[str] = mapped_column(
        String(30),
        default="moderate",
        nullable=False,
        comment="Reported sensitivity level: low, moderate, high, severe",
    )
    notes: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User-provided context or reaction description",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_name", name="uq_user_ingredient_sensitivity"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sensitivities")

    def __repr__(self) -> str:
        return f"<UserSensitivity user={self.user_id} ingredient={self.ingredient_name}>"


class UserPreference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User preferences for products, routines, and notifications."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
        comment="Associated user account (1:1)",
    )
    product_preferences: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="User preferences: cruelty_free, vegan, fragrance_free, organic, etc.",
    )
    routine_preferences: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Routine preferences: max_steps, preferred_texture, time_commitment",
    )
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Notification preferences: routine_reminders, weekly_summary",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreference id={self.id} user={self.user_id}>"


class UserConsent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User explicit consent records separated from general profile data."""

    __tablename__ = "user_consents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Associated user account",
    )
    purpose: Mapped[str] = mapped_column(
        String(80),
        index=True,
        nullable=False,
        comment="Consent domain (e.g. terms_of_service, privacy_policy, skin_data_processing)",
    )
    policy_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version identifier of policy consented to",
    )
    is_granted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether consent is currently active",
    )
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when consent was granted",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when consent was revoked",
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Sufficient audit evidence: IP address, user agent, choice timestamp",
    )

    __table_args__ = (UniqueConstraint("user_id", "purpose", name="uq_user_consent_purpose"),)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="consents")

    def __repr__(self) -> str:
        return f"<UserConsent user={self.user_id} purpose={self.purpose} granted={self.is_granted}>"


class Brand(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Manufacturer or brand entity."""

    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        comment="Brand name (e.g. CeraVe, The Ordinary)",
    )
    slug: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-friendly brand slug",
    )
    country_of_origin: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Country of brand origin or headquarters",
    )
    website: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Official brand website URL",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Brand philosophy and background summary",
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="brand_rel",
    )

    def __repr__(self) -> str:
        return f"<Brand id={self.id} name={self.name}>"


class DataSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Provenance data source registry (e.g. Open Beauty Facts, Channel3, manual)."""

    __tablename__ = "data_sources"

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Machine-readable source code (e.g. open_beauty_facts, channel3, manual)",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable source name",
    )
    attribution_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Upstream source URL for citation / attribution",
    )
    license_or_terms: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Data license or terms (e.g. ODbL 1.0, Proprietary API)",
    )

    # Relationships
    ingredient_lists: Mapped[list["ProductIngredientList"]] = relationship(
        "ProductIngredientList",
        back_populates="data_source",
    )
    offers: Mapped[list["ProductOffer"]] = relationship(
        "ProductOffer",
        back_populates="data_source",
    )

    def __repr__(self) -> str:
        return f"<DataSource id={self.id} code={self.code}>"


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative cosmetic product record in PostgreSQL."""

    __tablename__ = "products"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Commercial product name",
    )
    brand: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Manufacturer or brand name text representation",
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Structured Brand foreign key",
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Skincare product category: cleanser, moisturizer, serum, sunscreen, etc.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Product marketing or clinical description",
    )
    full_ingredient_list: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Raw INCI ingredient list as printed on packaging",
    )
    ean_or_upc: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
        comment="Barcode identifier",
    )
    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Product image asset URL",
    )

    # Relationships
    brand_rel: Mapped["Brand | None"] = relationship("Brand", back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    ingredient_lists: Mapped[list["ProductIngredientList"]] = relationship(
        "ProductIngredientList",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="desc(ProductIngredientList.created_at)",
    )
    product_ingredients: Mapped[list["ProductIngredient"]] = relationship(
        "ProductIngredient",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductIngredient.position",
    )
    offers: Mapped[list["ProductOffer"]] = relationship(
        "ProductOffer",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductOffer.price_minor_units",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} brand={self.brand} name={self.name}>"


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Specific commercial size, packaging, or regional SKU of a product."""

    __tablename__ = "product_variants"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent product identifier",
    )
    variant_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Variant descriptor (e.g. 50ml Pump, Travel Size, Fragrance-Free)",
    )
    barcode: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
        comment="EAN/UPC barcode identifier",
    )
    size_or_volume: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Standardized volume or weight (e.g. 50ml, 1.7 fl oz)",
    )
    sku: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Merchant or manufacturer SKU code",
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants")
    ingredient_lists: Mapped[list["ProductIngredientList"]] = relationship(
        "ProductIngredientList",
        back_populates="variant",
    )
    offers: Mapped[list["ProductOffer"]] = relationship(
        "ProductOffer",
        back_populates="variant",
    )

    def __repr__(self) -> str:
        return f"<ProductVariant id={self.id} product={self.product_id} name={self.variant_name}>"


class ProductIngredientList(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Provenance-tracked, versioned formulation of a cosmetic product.

    Preserves historical formula revisions rather than overwriting when reformulations occur.
    """

    __tablename__ = "product_ingredient_lists"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Target product identifier",
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional variant association",
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Data provider that supplied this formulation record",
    )
    formula_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="v1",
        index=True,
        comment="Formula version label (e.g. v1, 2024 reformulation, initial)",
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="True if this is the currently circulating commercial formula",
    )
    raw_ingredient_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Unparsed raw ingredient declaration string as provided by source",
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Timestamp when this formulation data was fetched",
    )

    __table_args__ = (
        Index("ix_product_ingredient_lists_prod_current", "product_id", "is_current"),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="ingredient_lists")
    variant: Mapped["ProductVariant | None"] = relationship(
        "ProductVariant", back_populates="ingredient_lists"
    )
    data_source: Mapped["DataSource | None"] = relationship(
        "DataSource", back_populates="ingredient_lists"
    )
    items: Mapped[list["ProductIngredient"]] = relationship(
        "ProductIngredient",
        back_populates="ingredient_list",
        cascade="all, delete-orphan",
        order_by="ProductIngredient.position",
    )

    def __repr__(self) -> str:
        return (
            f"<ProductIngredientList id={self.id} product={self.product_id} "
            f"version={self.formula_version} current={self.is_current}>"
        )


class Ingredient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Standardized cosmetic ingredient record in PostgreSQL."""

    __tablename__ = "ingredients"

    inci_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        comment="International Nomenclature of Cosmetic Ingredients (INCI) standard name",
    )
    common_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="Common vernacular name (e.g. Vitamin C, Niacinamide)",
    )
    aliases: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="Alternate naming conventions, chemical synonyms, or trade names",
    )
    function: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="Cosmetic purpose: humectant, surfactant, emollient, active, antioxidant",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Dermatological summary and mechanism of action",
    )
    safety_rating: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="safe",
        index=True,
        comment="Safety classification: safe, low_hazard, moderate_hazard, irritant, restricted",
    )

    # Relationships
    alias_records: Mapped[list["IngredientAlias"]] = relationship(
        "IngredientAlias",
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )
    product_associations: Mapped[list["ProductIngredient"]] = relationship(
        "ProductIngredient",
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )
    evidence_items: Mapped[list["IngredientEvidence"]] = relationship(
        "IngredientEvidence",
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Ingredient id={self.id} inci={self.inci_name}>"


class IngredientAlias(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Synonyms, trade names, or chemical identifiers for a standardized ingredient."""

    __tablename__ = "ingredient_aliases"

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Standardized ingredient reference",
    )
    alias_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
        comment="Alternative name, synonym, or trade name",
    )
    alias_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="synonym",
        index=True,
        comment="Category: synonym, trade_name, cas_number, chemical_name",
    )

    # Relationships
    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="alias_records")

    def __repr__(self) -> str:
        return f"<IngredientAlias id={self.id} alias={self.alias_name} type={self.alias_type}>"


class ProductIngredient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Many-to-many junction binding products (and formula lists) to standardized ingredients."""

    __tablename__ = "product_ingredients"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_ingredient_list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_ingredient_lists.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Specific formula version list this item belongs to",
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Ascending order in packaging ingredient declaration (indicates concentration)",
    )
    concentration_percentage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Exact concentration if verified by reliable source; otherwise null",
    )
    notes: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Provenance annotations (e.g. fragrance component, allergen)",
    )

    __table_args__ = (
        Index("ix_product_ingredients_list_pos", "product_ingredient_list_id", "position"),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="product_ingredients")
    ingredient_list: Mapped["ProductIngredientList | None"] = relationship(
        "ProductIngredientList", back_populates="items"
    )
    ingredient: Mapped["Ingredient"] = relationship(
        "Ingredient", back_populates="product_associations"
    )

    def __repr__(self) -> str:
        return (
            f"<ProductIngredient id={self.id} product={self.product_id} "
            f"ingredient={self.ingredient_id} pos={self.position}>"
        )


class ProductOffer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Commercial price and availability offer.

    Strictly separated from scientific formulation data.
    Prices are stored as exact integer minor units (e.g. 1999 for $19.99).
    """

    __tablename__ = "product_offers"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated product",
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated variant if pricing is SKU-specific",
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Source that supplied this commercial offer",
    )
    merchant_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Merchant or retailer name (e.g. Sephora, Ulta, Amazon)",
    )
    offer_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Direct link to purchase product on merchant store",
    )
    price_minor_units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Price in integer minor currency units (cents, pence, etc.)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        comment="ISO 4217 currency code (e.g. USD, EUR, GBP)",
    )
    is_in_stock: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Stock availability indicator",
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Timestamp when price and stock were observed",
    )

    __table_args__ = (Index("ix_product_offers_product_retrieved", "product_id", "retrieved_at"),)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="offers")
    variant: Mapped["ProductVariant | None"] = relationship(
        "ProductVariant", back_populates="offers"
    )
    data_source: Mapped["DataSource | None"] = relationship("DataSource", back_populates="offers")

    def __repr__(self) -> str:
        return (
            f"<ProductOffer id={self.id} merchant={self.merchant_name} "
            f"price={self.price_minor_units} {self.currency}>"
        )


class SearchOutbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Transactional Outbox table guaranteeing reliable sync between PostgreSQL and Elasticsearch.

    Every catalog mutation in PostgreSQL inserts a record here within the same transaction.
    A dedicated worker polls and bulk-syncs events with retry counts and backoff.
    """

    __tablename__ = "search_outbox"

    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Target domain entity: 'product' or 'ingredient'",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        index=True,
        nullable=False,
        comment="UUID of the changed entity",
    )
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Operation: 'index' or 'delete'",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Snapshot payload for indexing (empty for delete)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Event lifecycle: pending, processing, completed, failed",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of delivery attempts made to Elasticsearch",
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        comment="Maximum retry limit before dead-letter status",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error description from Elasticsearch bulk attempt",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp of successful synchronization",
    )

    __table_args__ = (
        Index("ix_search_outbox_status_created_at", "status", "created_at"),
        Index("ix_search_outbox_entity_lookup", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SearchOutbox id={self.id} entity={self.entity_type}:{self.entity_id} "
            f"action={self.action} status={self.status}>"
        )


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Uploaded user image asset stored privately in PostgreSQL BYTEA for the MVP.

    Uses deferred loading on `image_bytes` so ordinary metadata queries never return
    raw image bytes by default.
    """

    __tablename__ = "media_assets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user identifier",
    )
    storage_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="postgres",
        comment="Storage backend: 'postgres' (MVP BYTEA) or 'local'",
    )
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        index=True,
        comment="Random UUID-based private storage identifier",
    )
    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Sanitized original upload filename",
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME type (e.g. image/jpeg, image/png, image/webp)",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    image_width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Decoded pixel width",
    )
    image_height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Decoded pixel height",
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 digest of image content",
    )
    image_bytes: Mapped[bytes | None] = deferred(
        mapped_column(
            LargeBinary,
            nullable=True,
            comment="Validated raw image binary stored in PostgreSQL BYTEA; NULL when purged",
        )
    )
    retention_policy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ocr_retain_30d",
        comment="Retention rule (delete_after_ocr, ocr_retain_Nd, user_controlled_Nd)",
    )
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="UTC timestamp after which image_bytes are eligible for automatic purge",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="True once raw image_bytes have been deleted/purged",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when raw image_bytes were deleted/purged",
    )

    __table_args__ = (Index("ix_media_assets_user_created", "user_id", "created_at"),)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="media_assets")
    ocr_jobs: Mapped[list["OCRJob"]] = relationship(
        "OCRJob",
        back_populates="media_asset",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<MediaAsset id={self.id} user={self.user_id} "
            f"provider={self.storage_provider} deleted={self.is_deleted}>"
        )


class OCRJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """OCR analysis job extracting text from a MediaAsset."""

    __tablename__ = "ocr_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user identifier",
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated image media asset",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
        comment="Job status: pending, processing, succeeded, failed",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="OCR engine: ocr_space, tesseract, mock",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Deduplication key to avoid repeating identical scan jobs",
    )
    raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Raw untrusted OCR text extracted from image",
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Normalized provider confidence score (0.0 to 1.0)",
    )
    processing_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Execution duration in milliseconds",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Attempt count",
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum retry limit",
    )
    error_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Error classification: rate_limited, timeout, unreadable_image, upstream_error",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized diagnostic failure description",
    )

    __table_args__ = (Index("ix_ocr_jobs_user_status", "user_id", "status"),)

    # Relationships
    user: Mapped["User"] = relationship("User")
    media_asset: Mapped["MediaAsset"] = relationship("MediaAsset", back_populates="ocr_jobs")
    candidate_ingredients: Mapped[list["OCRCandidateIngredient"]] = relationship(
        "OCRCandidateIngredient",
        back_populates="ocr_job",
        cascade="all, delete-orphan",
        order_by="OCRCandidateIngredient.position",
    )

    def __repr__(self) -> str:
        return f"<OCRJob id={self.id} status={self.status} provider={self.provider}>"


class OCRCandidateIngredient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Candidate ingredient extracted from OCR raw text and matched against catalog."""

    __tablename__ = "ocr_candidate_ingredients"

    ocr_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent OCR scan job",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="1-based sequence order in packaging declaration",
    )
    raw_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Segmented raw string before normalization",
    )
    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Normalized candidate name",
    )
    matched_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Matched canonical Ingredient if verified against catalog",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Segment-level recognition confidence",
    )
    is_user_corrected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if modified by user in confirmation review",
    )
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if approved by user as valid packaging ingredient",
    )

    __table_args__ = (Index("ix_ocr_candidate_job_pos", "ocr_job_id", "position"),)

    # Relationships
    ocr_job: Mapped["OCRJob"] = relationship("OCRJob", back_populates="candidate_ingredients")
    matched_ingredient: Mapped["Ingredient | None"] = relationship("Ingredient")

    def __repr__(self) -> str:
        return (
            f"<OCRCandidateIngredient id={self.id} job={self.ocr_job_id} "
            f"pos={self.position} name={self.normalized_name}>"
        )


# ==============================================================================
# PHASE 6: INGREDIENT EVIDENCE AND RESEARCH RETRIEVAL MODELS
# ==============================================================================


class ResearchRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Deduplicated bibliographic article or regulatory reference monograph.

    Stores official PubMed E-utilities citations/abstracts and EC CosIng inventory entries.
    Never claims full-text possession when only metadata or abstracts were retrieved.
    """

    __tablename__ = "research_records"

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Source system identifier: pubmed, cosing, sccs, manual_curated",
    )
    external_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
        comment="External canonical ID (e.g. PMID '41319172' or CosIng Ref No '83218')",
    )
    doi: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="Digital Object Identifier when available",
    )
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Article title or official regulatory monograph heading",
    )
    authors: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="Ordered list of author names or authoring body",
    )
    journal_or_authority: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Journal name or regulatory authority (e.g. European Commission CosIng)",
    )
    publication_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Year of publication or regulatory inventory update",
    )
    publication_types: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment=(
            "Publication types (e.g. Randomized Controlled Trial, Review, Regulatory Monograph)"
        ),
    )
    study_type: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
        comment=(
            "Normalized design: rct, clinical_trial, meta_analysis, systematic_review, "
            "in_vitro, observational, review, regulatory_monograph, journal_article"
        ),
    )
    abstract_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Abstract text or regulatory chemical description; explicitly None when absent",
    )
    has_full_text: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Explicitly False when only bibliographic metadata or abstract was retrieved",
    )
    source_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Authoritative permalink to source record",
    )
    license_or_attribution: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Mandatory source attribution and terms of use notice",
    )
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Structured provenance metadata (CAS/EC numbers, MeSH terms, restrictions)",
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp when this record was retrieved from upstream",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "external_id",
            name="uq_research_records_source_external_id",
        ),
    )

    # Relationships
    source_links: Mapped[list["EvidenceSourceLink"]] = relationship(
        "EvidenceSourceLink",
        back_populates="research_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ResearchRecord id={self.id} source={self.source_type} ext_id={self.external_id}>"


class IngredientEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Auditable evidence assertion or record mapped to a canonical Ingredient.

    Strictly separates:
    1. identity_reference (Ingredient identity, CAS/EC, official CosIng functions & restrictions)
    2. published_research (Published scientific literature records)
    3. human_interpretation (Authored/reviewed dermatological interpretations)
    4. marketing_claim (Commercial product marketing claims, segregated from science)
    """

    __tablename__ = "ingredient_evidence"

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Canonical ingredient being described",
    )
    evidence_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment=(
            "One of: identity_reference, published_research, human_interpretation, marketing_claim"
        ),
    )
    topic_or_target: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment=(
            "Dermatological topic or regulatory scope "
            "(e.g. hyperpigmentation, skin_barrier, cosing_function)"
        ),
    )
    evidence_direction: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="neutral",
        comment="Direction: supportive, neutral, conflicting, insufficient, reference_only",
    )
    evidence_strength: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="preliminary",
        comment=(
            "Strength: strong, moderate, limited, preliminary, "
            "conflicting, insufficient, reference_only"
        ),
    )
    study_type: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
        comment=(
            "Study design when applicable "
            "(rct, clinical_trial, in_vitro, regulatory_monograph, etc.)"
        ),
    )
    population_or_context: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Study population, experimental model, or formulation context when known",
    )
    summary_statement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Provenance-backed summary statement; never treated as personal clinical diagnosis",
    )
    limitations_and_caveats: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Explicit limitations (abstract-only, unknown concentration, conflicting data, etc.)"
        ),
    )
    author_or_reviewer: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Originating importer or human reviewer identifier",
    )
    review_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="provisional",
        index=True,
        comment=(
            "Status: provisional, verified, conflicting_flagged, incorrect_match_flagged, rejected"
        ),
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp when evidence was retrieved or authored",
    )

    __table_args__ = (
        Index("ix_ing_evidence_ing_cat", "ingredient_id", "evidence_category"),
        Index("ix_ing_evidence_ing_status", "ingredient_id", "review_status"),
    )

    # Relationships
    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="evidence_items")
    source_links: Mapped[list["EvidenceSourceLink"]] = relationship(
        "EvidenceSourceLink",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    review_history: Mapped[list["EvidenceReviewStatus"]] = relationship(
        "EvidenceReviewStatus",
        back_populates="evidence",
        cascade="all, delete-orphan",
        order_by="EvidenceReviewStatus.reviewed_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<IngredientEvidence id={self.id} ing={self.ingredient_id} "
            f"cat={self.evidence_category} status={self.review_status}>"
        )


class EvidenceSourceLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Provenance bridge linking an IngredientEvidence entry to ResearchRecord and DataSource."""

    __tablename__ = "evidence_source_links"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredient_evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent ingredient evidence entry",
    )
    research_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Linked bibliographic or regulatory research record",
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Linked upstream DataSource provenance record",
    )
    is_exact_match: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment=(
            "False if article/monograph matched a derivative or lacked verified exact INCI match"
        ),
    )
    relevance_note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Explanation of how the source record relates to the ingredient",
    )
    quoted_excerpt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Relevant verbatim excerpt from abstract or regulatory restriction",
    )

    __table_args__ = (
        UniqueConstraint(
            "evidence_id",
            "research_record_id",
            name="uq_evidence_source_links_ev_rec",
        ),
    )

    # Relationships
    evidence: Mapped["IngredientEvidence"] = relationship(
        "IngredientEvidence", back_populates="source_links"
    )
    research_record: Mapped["ResearchRecord"] = relationship(
        "ResearchRecord", back_populates="source_links"
    )
    data_source: Mapped["DataSource | None"] = relationship("DataSource")

    def __repr__(self) -> str:
        return (
            f"<EvidenceSourceLink id={self.id} ev={self.evidence_id} rec={self.research_record_id}>"
        )


class EvidenceReviewStatus(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable audit log of review status transitions on an IngredientEvidence record."""

    __tablename__ = "evidence_review_status"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredient_evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reviewed evidence record",
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Authenticated user who performed the review (None if automated system check)",
    )
    previous_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Status prior to transition",
    )
    new_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment=(
            "New review status: provisional, verified, conflicting_flagged, "
            "incorrect_match_flagged, rejected"
        ),
    )
    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Justification, limitations noted, or reason for rejection/flagging",
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp of review action",
    )

    # Relationships
    evidence: Mapped["IngredientEvidence"] = relationship(
        "IngredientEvidence", back_populates="review_history"
    )
    reviewer: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<EvidenceReviewStatus id={self.id} ev={self.evidence_id} "
            f"{self.previous_status}->{self.new_status}>"
        )


# ==============================================================================
# PHASE 8: SKIN ANALYSIS AND SKIN STORY MODELS
# ==============================================================================


class AnalysisJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Shared asynchronous or synchronous external analysis job record.

    Tracks provider task execution, retries, timeouts, and failure categories
    independently of user-facing domain observations.
    """

    __tablename__ = "analysis_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user identifier",
    )
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="skin_analysis",
        index=True,
        comment="Analysis pipeline type (e.g. skin_analysis)",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="External or mock provider identifier (e.g. youcam, mock)",
    )
    provider_task_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="External provider asynchronous task identifier when applicable",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
        comment="Lifecycle status: pending, processing, succeeded, failed, cancelled",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
        comment="Optional client-supplied idempotency key",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of provider submission or polling attempts",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum allowed retry attempts",
    )
    error_category: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        comment="Normalized error category when failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized diagnostic failure message",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="UTC timestamp when job was initialized",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when job reached a terminal state",
    )

    __table_args__ = (
        Index("ix_analysis_jobs_user_status", "user_id", "status"),
        UniqueConstraint(
            "user_id",
            "job_type",
            "idempotency_key",
            name="uq_analysis_jobs_user_type_idempotency",
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    skin_scan: Mapped["SkinScan | None"] = relationship(
        "SkinScan",
        back_populates="analysis_job",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisJob id={self.id} type={self.job_type} "
            f"provider={self.provider} status={self.status}>"
        )


class SkinScan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-initiated facial skin analysis scan record.

    Records explicit consent linkage, provider provenance, model version,
    capture conditions, and lifecycle status. Never stores image bytes in PostgreSQL
    or retains unrestricted raw provider payloads without a retention policy.
    """

    __tablename__ = "skin_scans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_consents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Verified UserConsent record authorizing facial scan processing",
    )
    analysis_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated shared AnalysisJob execution record",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Skin analysis provider: youcam or mock",
    )
    provider_task_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="External provider task ID where applicable",
    )
    provider_model_version: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        comment="Provider/model version identifier (e.g. youcam-s2s-v2.0)",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
        comment="Scan status: pending, processing, succeeded, failed, deleted",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
        comment="Deduplication key to prevent duplicate scan creation on retry",
    )
    capture_conditions: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Self-reported lighting, camera angle, makeup/cosmetics state, and notes",
    )
    overall_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Optional composite display score (0-100) when reported by provider",
    )
    skin_type_observation: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        comment="Provider-observed visual skin surface type (e.g. combination, oily, dry, normal)",
    )
    error_category: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        comment=(
            "Failure category: provider_timeout, provider_unavailable, rate_limited, "
            "invalid_image, no_face_detected, authentication_error, upstream_error"
        ),
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized diagnostic error message",
    )
    raw_payload_retained: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Explicit flag confirming restricted raw provider responses are not retained",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when scan processing finished",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when user deleted scan media and observations",
    )

    __table_args__ = (
        Index("ix_skin_scans_user_created", "user_id", "created_at"),
        Index("ix_skin_scans_user_status", "user_id", "status"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_skin_scans_user_idempotency",
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="skin_scans")
    consent: Mapped["UserConsent | None"] = relationship("UserConsent")
    analysis_job: Mapped["AnalysisJob | None"] = relationship(
        "AnalysisJob",
        back_populates="skin_scan",
    )
    media_items: Mapped[list["ScanMedia"]] = relationship(
        "ScanMedia",
        back_populates="skin_scan",
        cascade="all, delete-orphan",
        order_by="ScanMedia.created_at",
    )
    observations: Mapped[list["SkinObservation"]] = relationship(
        "SkinObservation",
        back_populates="skin_scan",
        cascade="all, delete-orphan",
        order_by="SkinObservation.metric_code",
    )
    journal_entries: Mapped[list["SkinJournalEntry"]] = relationship(
        "SkinJournalEntry",
        back_populates="skin_scan",
    )

    def __repr__(self) -> str:
        return (
            f"<SkinScan id={self.id} user={self.user_id} "
            f"provider={self.provider} status={self.status}>"
        )


class ScanMedia(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Private object storage media reference and retention metadata for a SkinScan.

    Photos and masks are stored strictly in private object storage (never PostgreSQL)
    with explicit retention expiration and deletion tracking.
    """

    __tablename__ = "scan_media"

    skin_scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skin_scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent skin scan",
    )
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Linked MediaAsset record when uploaded by user",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier for direct ownership verification",
    )
    media_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="source_photo",
        comment="Asset role: source_photo or overlay_mask",
    )
    metric_code: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        comment="Associated metric code if media_role is overlay_mask",
    )
    storage_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="postgres",
        comment="Private storage provider ('postgres' MVP BYTEA or 'local')",
    )
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Private object storage key",
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Verified MIME type (image/jpeg, image/png, image/webp)",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Object size in bytes",
    )
    retention_policy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="user_controlled_90d",
        comment="Retention rule governing automatic or user-initiated purge",
    )
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="UTC timestamp after which object is eligible for retention purge",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="True once underlying private storage object has been purged",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when private object was deleted",
    )

    __table_args__ = (Index("ix_scan_media_user_deleted", "user_id", "is_deleted"),)

    # Relationships
    skin_scan: Mapped["SkinScan"] = relationship("SkinScan", back_populates="media_items")
    media_asset: Mapped["MediaAsset | None"] = relationship("MediaAsset")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<ScanMedia id={self.id} scan={self.skin_scan_id} "
            f"role={self.media_role} deleted={self.is_deleted}>"
        )


class SkinObservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Normalized visual skin metric observation extracted from a SkinScan.

    Stores normalized metric codes, raw values, display values, units, directionality,
    and interpretation versions separately from restricted raw provider responses.
    """

    __tablename__ = "skin_observations"

    skin_scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skin_scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent skin scan record",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier for longitudinal queries",
    )
    metric_code: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
        comment=(
            "Normalized metric code: spots, redness, texture, pores, wrinkles, "
            "acne, oiliness, moisture, radiance, firmness, dark_circles, eye_bags"
        ),
    )
    metric_label: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="User-visible non-diagnostic label for this visual observation",
    )
    raw_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Underlying raw score reported by the provider algorithm",
    )
    display_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Normalized display value (e.g. 0.0 to 100.0)",
    )
    unit: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="score_0_100",
        comment="Measurement unit or scale identifier (e.g. score_0_100)",
    )
    directionality: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="higher_is_better",
        comment="Scale direction: higher_is_better (e.g. YouCam UI score) or lower_is_better",
    )
    provider_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Provider that produced this observation (youcam, mock)",
    )
    provider_model_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="Exact provider/model version required for longitudinal comparability checks",
    )
    interpretation_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="tonetrace-obs-v1.0",
        comment="ToneTrace normalization and interpretation schema version",
    )
    facial_zone: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="full_face",
        comment="Evaluated facial region (e.g. full_face, forehead, cheeks, periorbital)",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Optional provider confidence (0.0 to 1.0) when available",
    )
    caveat_note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Explicit non-clinical caveat regarding lighting, camera, angle, and cosmetics impact"
        ),
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp when the visual observation was recorded",
    )

    __table_args__ = (
        Index("ix_skin_obs_user_metric_time", "user_id", "metric_code", "observed_at"),
        UniqueConstraint(
            "skin_scan_id",
            "metric_code",
            "facial_zone",
            name="uq_skin_obs_scan_metric_zone",
        ),
    )

    # Relationships
    skin_scan: Mapped["SkinScan"] = relationship("SkinScan", back_populates="observations")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<SkinObservation id={self.id} scan={self.skin_scan_id} "
            f"metric={self.metric_code} display={self.display_value}>"
        )


class SkinJournalEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-authored longitudinal skin story journal entry.

    Captures self-reported skin state, perceived visual changes, routine notes,
    and environmental/lighting context alongside optional scan links.
    """

    __tablename__ = "skin_journal_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    skin_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skin_scans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional SkinScan linked to this journal entry",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp of the journal observation",
    )
    perceived_skin_state: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="User's overall perceived skin state (e.g. calm, dry, balanced, irritated)",
    )
    self_reported_observations: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="List of user-observed surface notes (e.g. cheek redness, uneven tone)",
    )
    routine_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes on current morning/evening routine or active changes",
    )
    products_used: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="List of product names or IDs used around this entry",
    )
    environmental_or_lifestyle_factors: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Contextual factors (lighting, climate, UV exposure, cosmetics worn, sleep)",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional free-form user reflection",
    )

    __table_args__ = (Index("ix_skin_journal_user_recorded", "user_id", "recorded_at"),)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="skin_journal_entries")
    skin_scan: Mapped["SkinScan | None"] = relationship(
        "SkinScan",
        back_populates="journal_entries",
    )

    def __repr__(self) -> str:
        return (
            f"<SkinJournalEntry id={self.id} user={self.user_id} "
            f"state={self.perceived_skin_state} at={self.recorded_at}>"
        )


# ==============================================================================
# PHASE 9: MY SHELF AND PRODUCT DISCOVERY MODELS
# ==============================================================================


class UserProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-owned product item on their personal skincare shelf ('My Shelf').

    Supports both public catalogue-linked products (via product_id) and custom
    user-defined products (is_custom=True) that are not in the public catalogue.
    Personal notes and shelf items are strictly private to the owning user by default.
    """

    __tablename__ = "user_products"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Linked public catalogue Product ID when available; None for custom products",
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional linked ProductVariant SKU",
    )
    ocr_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional OCR scan job that supplied the custom ingredient declaration",
    )
    is_custom: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="True when item is a custom user entry not linked to a public catalogue record",
    )
    custom_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Custom product name (required when product_id is None)",
    )
    custom_brand: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Custom brand name when product_id is None",
    )
    custom_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Custom skincare category (e.g. cleanser, serum, sunscreen)",
    )
    custom_ingredient_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="User-entered or OCR-derived raw ingredient list for a custom product",
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="in_use",
        index=True,
        comment="Shelf status: in_use, wishlist, finished, paused, discontinued, avoided",
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional UTC timestamp when the product container was opened",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional UTC expiration or PAO (Period After Opening) target date",
    )
    purchase_price_minor_units: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Optional user-recorded purchase price in integer minor currency units",
    )
    purchase_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        comment="Optional ISO 4217 currency code for purchase_price_minor_units",
    )
    private_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Strictly private personal product notes; never shared publicly",
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Privacy flag; personal shelf items and notes are private (False) by default",
    )

    __table_args__ = (
        Index("ix_user_products_user_status", "user_id", "status"),
        Index("ix_user_products_user_product", "user_id", "product_id"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="shelf_products")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    ocr_job: Mapped["OCRJob | None"] = relationship("OCRJob")
    reactions: Mapped[list["ProductReaction"]] = relationship(
        "ProductReaction",
        back_populates="user_product",
        cascade="all, delete-orphan",
        order_by="desc(ProductReaction.observed_at)",
    )

    def __repr__(self) -> str:
        return (
            f"<UserProduct id={self.id} user={self.user_id} "
            f"product={self.product_id} custom={self.is_custom} status={self.status}>"
        )


class ProductReaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-reported skin reaction or tolerance log for a shelf or catalogue product.

    Used to track personal product tolerance and inform transparent rule-based
    suitability warnings without claiming clinical allergy diagnosis.
    """

    __tablename__ = "product_reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    user_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Optional associated shelf item",
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional linked public catalogue product ID",
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional routine context during which the reaction was observed",
    )
    reaction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment=(
            "Reaction category: well_tolerated, irritation, redness, breakout, "
            "dryness, stinging, allergic_suspect, no_visible_change"
        ),
    )
    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="none",
        comment="Perceived severity: none, mild, moderate, severe",
    )
    symptoms: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="User-reported visible or sensory symptoms (e.g. swelling, hives, burning)",
    )
    is_rapidly_worsening: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if the user reports a rapidly worsening or spreading reaction",
    )
    urgent_care_escalation_shown: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True when urgent-care guidance was surfaced instead of ordinary recommendations",
    )
    suspected_ingredient_names: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="Optional user-suspected ingredient names associated with this reaction",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Private user notes describing the reaction context",
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="UTC timestamp when reaction or tolerance was observed",
    )

    __table_args__ = (Index("ix_product_reactions_user_type", "user_id", "reaction_type"),)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="product_reactions")
    user_product: Mapped["UserProduct | None"] = relationship(
        "UserProduct",
        back_populates="reactions",
    )
    product: Mapped["Product | None"] = relationship("Product")
    routine: Mapped["Routine | None"] = relationship("Routine")

    def __repr__(self) -> str:
        return (
            f"<ProductReaction id={self.id} user_product={self.user_product_id} "
            f"type={self.reaction_type} severity={self.severity}>"
        )


# ==============================================================================
# PHASE 10: ROUTINES, REMINDERS AND REACTIONS MODELS
# ==============================================================================


class Routine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User skincare routine definition with ordered steps and scheduling metadata."""

    __tablename__ = "routines"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Routine title (e.g. Morning Brightening & SPF Routine)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional user description or goal notes for this routine",
    )
    time_of_day: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="morning",
        index=True,
        comment="Primary routine slot: morning, evening, midday, weekly, custom",
    )
    frequency: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="daily",
        comment="Schedule cadence: daily, every_other_day, weekly, custom_days",
    )
    days_of_week: Mapped[list[int]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="Optional ISO weekday numbers (0=Mon..6=Sun) when frequency=custom_days",
    )
    preferred_local_time: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
        comment="Optional preferred 24h local time (HH:MM) in the user's configured timezone",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether the routine is currently active",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonically increasing routine revision number",
    )

    __table_args__ = (Index("ix_routines_user_active_tod", "user_id", "is_active", "time_of_day"),)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="routines")
    steps: Mapped[list["RoutineStep"]] = relationship(
        "RoutineStep",
        back_populates="routine",
        cascade="all, delete-orphan",
        order_by="RoutineStep.step_order",
    )
    completions: Mapped[list["RoutineCompletion"]] = relationship(
        "RoutineCompletion",
        back_populates="routine",
        order_by="desc(RoutineCompletion.completed_at)",
    )

    def __repr__(self) -> str:
        return (
            f"<Routine id={self.id} user={self.user_id} name={self.name!r} "
            f"tod={self.time_of_day} v={self.version}>"
        )


class RoutineStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Ordered step within a user's Routine referencing a shelf item, product, or instruction."""

    __tablename__ = "routine_steps"

    routine_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent routine identifier",
    )
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-based execution order within the routine",
    )
    time_of_day: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="morning",
        comment="Step time-of-day slot: morning, evening, midday, any",
    )
    user_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional reference to an item on the user's personal shelf",
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional reference to a public catalogue product",
    )
    step_label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Resolved display label for the step or product",
    )
    custom_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Custom application instruction or non-product step description",
    )
    frequency: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="every_session",
        comment="Step frequency: every_session, daily, alternate_days, twice_weekly, weekly",
    )
    wait_time_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Optional wait duration in seconds after applying this step",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this step is currently active in the routine",
    )

    __table_args__ = (Index("ix_routine_steps_routine_order", "routine_id", "step_order"),)

    # Relationships
    routine: Mapped["Routine"] = relationship("Routine", back_populates="steps")
    user_product: Mapped["UserProduct | None"] = relationship("UserProduct")
    product: Mapped["Product | None"] = relationship("Product")

    def __repr__(self) -> str:
        return (
            f"<RoutineStep id={self.id} routine={self.routine_id} "
            f"order={self.step_order} label={self.step_label!r}>"
        )


class RoutineCompletion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable completion record separated from mutable routine definitions.

    Preserves a snapshot of the routine version, completed steps, UTC timestamp,
    and localized calendar date in the user's configured timezone so editing a
    routine never erases or corrupts historical completion logs.
    """

    __tablename__ = "routine_completions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user identifier",
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Routine reference (SET NULL on routine deletion to preserve history)",
    )
    routine_name_snapshot: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Routine name at the time of completion",
    )
    routine_version_snapshot: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Routine version number at the time of completion",
    )
    time_of_day_snapshot: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="morning",
        comment="Routine time-of-day slot at the time of completion",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="completed",
        index=True,
        comment="Completion status: completed, partial, skipped",
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="Timezone-aware UTC timestamp when the routine was completed",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UTC",
        comment="IANA timezone identifier used to compute local_date and local_time",
    )
    local_date: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        comment="Localized calendar date (YYYY-MM-DD) in user_timezone",
    )
    local_time: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="Localized wall-clock time (HH:MM:SS) in user_timezone",
    )
    completed_steps_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType,
        nullable=False,
        default=list,
        comment="Immutable snapshot of executed/skipped steps at completion time",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional user notes for this completion session",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
        comment="Optional client idempotency key to prevent duplicate completion logs",
    )

    __table_args__ = (
        Index("ix_routine_completions_user_routine_at", "user_id", "routine_id", "completed_at"),
        Index("ix_routine_completions_user_local_date", "user_id", "local_date"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="routine_completions")
    routine: Mapped["Routine | None"] = relationship("Routine", back_populates="completions")

    def __repr__(self) -> str:
        return (
            f"<RoutineCompletion id={self.id} routine={self.routine_id} "
            f"status={self.status} local_date={self.local_date}>"
        )


class ReminderPreference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-controlled reminder scheduling, quiet hours, timezone, and opt-out settings."""

    __tablename__ = "reminder_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        comment="Owning user identifier (1:1)",
    )
    reminders_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Master opt-in/opt-out toggle; when False, all reminders are suppressed",
    )
    preferred_channels: Mapped[list[str]] = mapped_column(
        JsonType,
        nullable=False,
        default=lambda: ["in_app"],
        comment="Enabled delivery channels: in_app, email, push",
    )
    morning_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether morning routine reminders are enabled",
    )
    morning_reminder_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="08:00",
        comment="24h local time (HH:MM) for morning reminders",
    )
    evening_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether evening routine reminders are enabled",
    )
    evening_reminder_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="21:00",
        comment="24h local time (HH:MM) for evening reminders",
    )
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether reminders are suppressed during quiet hours in user's timezone",
    )
    quiet_hours_start: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="22:30",
        comment="24h local start time (HH:MM) for quiet hours",
    )
    quiet_hours_end: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="07:00",
        comment="24h local end time (HH:MM) for quiet hours",
    )
    timezone_override: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Optional IANA timezone override (falls back to UserProfile.timezone)",
    )
    opted_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when the user most recently disabled reminders",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="reminder_preference")

    def __repr__(self) -> str:
        return (
            f"<ReminderPreference id={self.id} user={self.user_id} "
            f"enabled={self.reminders_enabled}>"
        )


class ReminderDeliveryRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Idempotency and audit record for routine reminder evaluation and delivery."""

    __tablename__ = "reminder_deliveries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Target user identifier",
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional associated routine identifier",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Deduplication key preventing duplicate reminder sends",
    )
    channel: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="in_app",
        comment="Notification channel: in_app, email, push",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Notification provider adapter name (e.g. local_test_recorder)",
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="True when recorded by local test adapter without external transmission",
    )
    actual_external_delivery: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True only when a verified external email/push provider confirmed delivery",
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
        comment=(
            "Outcome: recorded_local_not_sent, delivered_external, "
            "suppressed_opt_out, suppressed_quiet_hours, failed"
        ),
    )
    scheduled_for_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Reference UTC timestamp for the reminder evaluation",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Effective IANA timezone of the user at evaluation time",
    )
    user_local_time: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        comment="Formatted local date-time (YYYY-MM-DD HH:MM:SS) in user_timezone",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error or suppression details when delivery did not occur",
    )
    payload_summary: Mapped[dict[str, Any]] = mapped_column(
        JsonType,
        nullable=False,
        default=dict,
        comment="Recorded title, body, and metadata summary",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_reminder_deliveries_user_idempotency",
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="reminder_deliveries")
    routine: Mapped["Routine | None"] = relationship("Routine")

    def __repr__(self) -> str:
        return (
            f"<ReminderDeliveryRecord id={self.id} user={self.user_id} "
            f"key={self.idempotency_key!r} status={self.status}>"
        )
