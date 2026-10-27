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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
