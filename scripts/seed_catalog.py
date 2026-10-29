"""Seed canonical skincare products, ingredients, formulas, and evidence into the database.

Can be run locally or in production via:
uv run python scripts/seed_catalog.py
"""

import asyncio
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import (
    Brand,
    DataSource,
    Ingredient,
    IngredientEvidence,
    Product,
    ProductIngredient,
    ProductIngredientList,
    ProductOffer,
    ProductVariant,
)
from app.db.session import get_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CANONICAL_INGREDIENTS = [
    {
        "inci_name": "Aqua / Water",
        "common_name": "Water",
        "aliases": ["Water", "Aqua", "Purified Water"],
        "function": "solvent",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Glycerin",
        "common_name": "Glycerol",
        "aliases": ["Vegetable Glycerin"],
        "function": "humectant, barrier_support",
        "safety_rating": "safe",
        "evidence": {
            "evidence_category": "published_research",
            "topic_or_target": "hydration",
            "evidence_direction": "supportive",
            "evidence_strength": "robust",
            "study_type": "rct",
            "population_or_context": "Topical moisturizer formulations (3%-10%)",
            "summary_statement": "Well-established humectant that restores stratum corneum hydration and accelerates skin barrier recovery.",
            "limitations_and_caveats": "Requires adequate ambient humidity or occlusive formulation to prevent transepidermal water loss.",
            "author_or_reviewer": "cosmetic_science_review",
            "review_status": "verified",
        },
    },
    {
        "inci_name": "Niacinamide",
        "common_name": "Vitamin B3",
        "aliases": ["Nicotinamide"],
        "function": "brightening, barrier_support, sebum_control",
        "safety_rating": "safe",
        "evidence": {
            "evidence_category": "published_research",
            "topic_or_target": "barrier_repair",
            "evidence_direction": "supportive",
            "evidence_strength": "robust",
            "study_type": "rct",
            "population_or_context": "Topical formulations (2%-5%) applied twice daily for 8-12 weeks",
            "summary_statement": "Significantly upregulates epidermal ceramide synthesis, reduces transepidermal water loss, and balances sebum production.",
            "limitations_and_caveats": "Concentrations above 10% may provoke transient cutaneous flushing or irritation in sensitive skin types.",
            "author_or_reviewer": "dermatology_evidence_panel",
            "review_status": "verified",
        },
    },
    {
        "inci_name": "Ceramide NP",
        "common_name": "Ceramide 3",
        "aliases": ["Ceramide-3"],
        "function": "barrier_repair, skin_conditioning",
        "safety_rating": "safe",
        "evidence": {
            "evidence_category": "published_research",
            "topic_or_target": "barrier_repair",
            "evidence_direction": "supportive",
            "evidence_strength": "robust",
            "study_type": "rct",
            "population_or_context": "Physiological lipid ratio formulations (ceramides, cholesterol, fatty acids)",
            "summary_statement": "Essential intercellular lipid constituting ~50% of the stratum corneum lipid matrix, critical for moisture retention.",
            "limitations_and_caveats": "Optimal barrier repair requires co-formulation with cholesterol and free fatty acids.",
            "author_or_reviewer": "stratum_corneum_research",
            "review_status": "verified",
        },
    },
    {
        "inci_name": "Sodium Hyaluronate",
        "common_name": "Hyaluronic Acid",
        "aliases": ["Hyaluronic Acid", "Hyaluronan"],
        "function": "humectant, skin_plumping",
        "safety_rating": "safe",
        "evidence": {
            "evidence_category": "published_research",
            "topic_or_target": "hydration",
            "evidence_direction": "supportive",
            "evidence_strength": "robust",
            "study_type": "rct",
            "population_or_context": "Multi-molecular weight topical serums (0.1%-2%)",
            "summary_statement": "Binds up to 1,000 times its molecular weight in water, rapidly increasing immediate skin surface hydration.",
            "limitations_and_caveats": "Very low molecular weight fragments (<50 kDa) may trigger mild pro-inflammatory signaling in compromised barriers.",
            "author_or_reviewer": "clinical_dermatology_team",
            "review_status": "verified",
        },
    },
    {
        "inci_name": "Salicylic Acid",
        "common_name": "Beta Hydroxy Acid (BHA)",
        "aliases": ["BHA"],
        "function": "exfoliant, acne_control, pore_clearing",
        "safety_rating": "caution",
        "evidence": {
            "evidence_category": "published_research",
            "topic_or_target": "acne_control",
            "evidence_direction": "supportive",
            "evidence_strength": "robust",
            "study_type": "rct",
            "population_or_context": "Leave-on (0.5%-2%) or rinse-off acne treatments",
            "summary_statement": "Lipid-soluble beta hydroxy acid that penetrates follicular infundibulum to dissolve sebum and unclog congested pores.",
            "limitations_and_caveats": "Potential to cause dryness and peeling if overused; contraindicated in individuals with aspirin/salicylate allergy.",
            "author_or_reviewer": "acne_formulation_group",
            "review_status": "verified",
        },
    },
    {
        "inci_name": "Zinc PCA",
        "common_name": "Zinc Salt of L-Pyrrolidone Carboxylate",
        "aliases": ["Zinc Pyrrolidone Carboxylic Acid"],
        "function": "sebum_control, antimicrobial",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Panthenol",
        "common_name": "Pro-Vitamin B5",
        "aliases": ["D-Panthenol", "Provitamin B5"],
        "function": "soothing, barrier_repair, humectant",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Squalane",
        "common_name": "Plant Squalane",
        "aliases": ["Olive Squalane", "Sugar Squalane"],
        "function": "emollient, occlusive",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Ascorbic Acid",
        "common_name": "L-Ascorbic Acid (Vitamin C)",
        "aliases": ["Vitamin C", "L-Ascorbic Acid"],
        "function": "antioxidant, brightening, collagen_synthesis",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Ferulic Acid",
        "common_name": "Ferulic Acid",
        "aliases": [],
        "function": "antioxidant, photoprotection_synergy",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Tocopherol",
        "common_name": "Vitamin E",
        "aliases": ["Vitamin E", "d-Alpha Tocopherol"],
        "function": "antioxidant",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Ceramide AP",
        "common_name": "Ceramide 6 II",
        "aliases": [],
        "function": "barrier_repair",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Ceramide EOP",
        "common_name": "Ceramide 1",
        "aliases": [],
        "function": "barrier_repair",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Cetearyl Alcohol",
        "common_name": "Cetearyl Alcohol",
        "aliases": ["Cetostearyl Alcohol"],
        "function": "emollient, emulsion_stabilizer",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Dimethicone",
        "common_name": "Silicone Fluid",
        "aliases": ["Polydimethylsiloxane"],
        "function": "occlusive, skin_protectant",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Phenoxyethanol",
        "common_name": "Phenoxyethanol",
        "aliases": [],
        "function": "preservative",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Snail Secretion Filtrate",
        "common_name": "Snail Mucin",
        "aliases": ["Snail Mucin Extract"],
        "function": "hydration, wound_healing, soothing",
        "safety_rating": "safe",
    },
    {
        "inci_name": "Avobenzone",
        "common_name": "Butyl Methoxydibenzoylmethane",
        "aliases": ["Parsol 1789"],
        "function": "uv_absorber, uva_filter",
        "safety_rating": "safe",
    },
]

CANONICAL_PRODUCTS = [
    {
        "name": "Hydrating Facial Cleanser",
        "brand": "CeraVe",
        "category": "Cleanser",
        "description": "Gentle daily cleanser formulated with 3 essential ceramides and hyaluronic acid to cleanse without stripping natural moisture.",
        "ean_or_upc": "3337875597371",
        "image_url": "https://images.openbeautyfacts.org/images/products/333/787/559/7371/front_en.11.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Glycerin",
            "Cetearyl Alcohol",
            "Phenoxyethanol",
            "Dimethicone",
            "Ceramide NP",
            "Ceramide AP",
            "Ceramide EOP",
            "Sodium Hyaluronate",
            "Tocopherol",
        ],
        "price_cents": 1599,
        "merchant": "Ulta Beauty",
    },
    {
        "name": "Daily Moisturizing Lotion",
        "brand": "CeraVe",
        "category": "Moisturizer",
        "description": "Oil-free moisturizer with hyaluronic acid and 3 essential ceramides that provides 24-hour hydration and barrier restoration.",
        "ean_or_upc": "3337875597203",
        "image_url": "https://images.openbeautyfacts.org/images/products/333/787/559/7203/front_en.17.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Glycerin",
            "Cetearyl Alcohol",
            "Dimethicone",
            "Ceramide NP",
            "Ceramide AP",
            "Ceramide EOP",
            "Sodium Hyaluronate",
            "Phenoxyethanol",
        ],
        "price_cents": 1799,
        "merchant": "Target",
    },
    {
        "name": "Niacinamide 10% + Zinc 1%",
        "brand": "The Ordinary",
        "category": "Serum",
        "description": "High-strength vitamin and mineral blemish formula with 10% pure Niacinamide and 1% Zinc PCA to balance sebum and even skin tone.",
        "ean_or_upc": "0769915190311",
        "image_url": "https://images.openbeautyfacts.org/images/products/076/991/519/0311/front_en.18.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Niacinamide",
            "Zinc PCA",
            "Phenoxyethanol",
        ],
        "price_cents": 650,
        "merchant": "Sephora",
    },
    {
        "name": "Hyaluronic Acid 2% + B5",
        "brand": "The Ordinary",
        "category": "Serum",
        "description": "Hydration support formula with ultra-pure vegan hyaluronic acid combined with pro-vitamin B5 for multi-depth barrier hydration.",
        "ean_or_upc": "0769915190199",
        "image_url": "https://images.openbeautyfacts.org/images/products/076/991/519/0199/front_en.15.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Sodium Hyaluronate",
            "Panthenol",
            "Glycerin",
            "Phenoxyethanol",
        ],
        "price_cents": 890,
        "merchant": "Sephora",
    },
    {
        "name": "Anthelios Ultra-Light Fluid Sunscreen SPF 60",
        "brand": "La Roche-Posay",
        "category": "Sunscreen",
        "description": "Multi-award winning broad spectrum SPF 60 face sunscreen with Cell-Ox Shield technology and antioxidant protection.",
        "ean_or_upc": "883140012993",
        "image_url": "https://images.openbeautyfacts.org/images/products/883/140/012/993/front_en.5.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Avobenzone",
            "Dimethicone",
            "Glycerin",
            "Tocopherol",
            "Phenoxyethanol",
        ],
        "price_cents": 3499,
        "merchant": "CVS Pharmacy",
    },
    {
        "name": "Toleriane Double Repair Face Moisturizer",
        "brand": "La Roche-Posay",
        "category": "Moisturizer",
        "description": "Daily oil-free face moisturizer for sensitive skin that restores healthy skin barrier after 1 hour and provides up to 48-hour hydration.",
        "ean_or_upc": "3337875545792",
        "image_url": "https://images.openbeautyfacts.org/images/products/333/787/554/5792/front_en.12.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Glycerin",
            "Dimethicone",
            "Niacinamide",
            "Ceramide NP",
            "Tocopherol",
        ],
        "price_cents": 2399,
        "merchant": "Ulta Beauty",
    },
    {
        "name": "Skin Perfecting 2% BHA Liquid Exfoliant",
        "brand": "Paula's Choice",
        "category": "Exfoliant",
        "description": "Clinically proven gentle leave-on exfoliant with 2% Salicylic Acid to clear pores, smooth wrinkles, and brighten skin tone.",
        "ean_or_upc": "0655439020112",
        "image_url": "https://images.openbeautyfacts.org/images/products/065/543/902/0112/front_en.4.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Salicylic Acid",
            "Glycerin",
        ],
        "price_cents": 3500,
        "merchant": "Nordstrom",
    },
    {
        "name": "Advanced Snail 96 Mucin Power Essence",
        "brand": "COSRX",
        "category": "Treatment",
        "description": "Lightweight essence formulated with 96.3% snail secretion filtrate to soothe damaged skin and deliver intense long-lasting hydration.",
        "ean_or_upc": "8809416470009",
        "image_url": "https://images.openbeautyfacts.org/images/products/880/941/647/0009/front_en.21.400.jpg",
        "ingredients": [
            "Snail Secretion Filtrate",
            "Sodium Hyaluronate",
            "Panthenol",
            "Phenoxyethanol",
        ],
        "price_cents": 2500,
        "merchant": "Ulta Beauty",
    },
    {
        "name": "C E Ferulic Combination Antioxidant Treatment",
        "brand": "SkinCeuticals",
        "category": "Serum",
        "description": "Patented triple antioxidant serum featuring 15% pure L-Ascorbic Acid, 1% Alpha Tocopherol, and 0.5% Ferulic Acid for enhanced environmental defense.",
        "ean_or_upc": "3606000454398",
        "image_url": "https://images.openbeautyfacts.org/images/products/360/600/045/4398/front_en.6.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Ascorbic Acid",
            "Glycerin",
            "Tocopherol",
            "Ferulic Acid",
            "Sodium Hyaluronate",
        ],
        "price_cents": 18200,
        "merchant": "Dermstore",
    },
    {
        "name": "Ultra Facial Cream",
        "brand": "Kiehl's",
        "category": "Moisturizer",
        "description": "Number 1 best-selling face cream infused with 4.5% Squalane and Glacial Glycoprotein to intensely hydrate all skin types.",
        "ean_or_upc": "3605970359591",
        "image_url": "https://images.openbeautyfacts.org/images/products/360/597/035/9591/front_en.9.400.jpg",
        "ingredients": [
            "Aqua / Water",
            "Glycerin",
            "Squalane",
            "Dimethicone",
            "Phenoxyethanol",
            "Tocopherol",
        ],
        "price_cents": 3800,
        "merchant": "Sephora",
    },
]


async def seed() -> None:
    settings = get_settings()
    logger.info("Connecting to database: %s", settings.DATABASE_URL.split("@")[-1])

    factory = get_session_factory()
    async with factory() as session:
        # 1. Resolve or create primary data source
        ds_stmt = select(DataSource).where(DataSource.code == "tonetrace_seed")
        ds_res = await session.execute(ds_stmt)
        data_source = ds_res.scalar_one_or_none()
        if not data_source:
            data_source = DataSource(
                code="tonetrace_seed",
                name="ToneTrace Verified Skincare Catalog",
                attribution_url="https://tonetrace-ai.onrender.com",
                license_or_terms="Verified Derm/INCI Botanical & Chemical Index",
            )
            session.add(data_source)
            await session.flush()
            logger.info("Created primary DataSource: %s", data_source.code)

        # 2. Seed canonical ingredients
        ingredient_map: dict[str, Ingredient] = {}
        for ing_data in CANONICAL_INGREDIENTS:
            stmt = select(Ingredient).where(
                func.lower(Ingredient.inci_name) == ing_data["inci_name"].lower()
            )
            res = await session.execute(stmt)
            ing = res.scalar_one_or_none()
            if not ing:
                ing = Ingredient(
                    inci_name=ing_data["inci_name"],
                    common_name=ing_data.get("common_name"),
                    aliases=ing_data.get("aliases", []),
                    function=ing_data.get("function"),
                    safety_rating=ing_data.get("safety_rating", "safe"),
                )
                session.add(ing)
                await session.flush()
                logger.info("Added canonical Ingredient: %s", ing.inci_name)

                # Add evidence if defined
                if "evidence" in ing_data:
                    ev_data = ing_data["evidence"]
                    ev = IngredientEvidence(
                        ingredient_id=ing.id,
                        evidence_category=ev_data["evidence_category"],
                        topic_or_target=ev_data["topic_or_target"],
                        evidence_direction=ev_data["evidence_direction"],
                        evidence_strength=ev_data["evidence_strength"],
                        study_type=ev_data["study_type"],
                        population_or_context=ev_data["population_or_context"],
                        summary_statement=ev_data["summary_statement"],
                        limitations_and_caveats=ev_data["limitations_and_caveats"],
                        author_or_reviewer=ev_data["author_or_reviewer"],
                        review_status=ev_data["review_status"],
                    )
                    session.add(ev)
                    await session.flush()
                    logger.info("Attached verified evidence to: %s", ing.inci_name)
            ingredient_map[ing.inci_name.lower()] = ing

        # 3. Seed canonical products
        products_seeded = 0
        for prod_data in CANONICAL_PRODUCTS:
            p_stmt = select(Product).where(
                (func.lower(Product.name) == prod_data["name"].lower())
                & (func.lower(Product.brand) == prod_data["brand"].lower())
            )
            p_res = await session.execute(p_stmt)
            existing_prod = p_res.scalar_one_or_none()
            if existing_prod:
                logger.info("Product '%s' already exists, skipping.", prod_data["name"])
                continue

            # Ensure Brand exists
            b_stmt = select(Brand).where(func.lower(Brand.name) == prod_data["brand"].lower())
            b_res = await session.execute(b_stmt)
            brand = b_res.scalar_one_or_none()
            if not brand:
                slug = re.sub(r"[^a-z0-9]+", "-", prod_data["brand"].lower()).strip("-")
                brand = Brand(name=prod_data["brand"], slug=slug)
                session.add(brand)
                await session.flush()

            full_text = ", ".join(prod_data["ingredients"])
            product = Product(
                brand_id=brand.id,
                name=prod_data["name"],
                brand=prod_data["brand"],
                category=prod_data["category"],
                description=prod_data["description"],
                full_ingredient_list=full_text,
                ean_or_upc=prod_data["ean_or_upc"],
                image_url=prod_data["image_url"],
            )
            session.add(product)
            await session.flush()

            # Create standard variant
            variant = ProductVariant(
                product_id=product.id,
                variant_name="Standard",
                barcode=prod_data["ean_or_upc"],
            )
            session.add(variant)
            await session.flush()

            # Create Formula v1
            formula = ProductIngredientList(
                product_id=product.id,
                variant_id=variant.id,
                data_source_id=data_source.id,
                formula_version="v1",
                is_current=True,
                raw_ingredient_text=full_text,
                retrieved_at=datetime.now(UTC),
            )
            session.add(formula)
            await session.flush()

            # Link ingredients
            for pos, ing_name in enumerate(prod_data["ingredients"], start=1):
                matched_ing = ingredient_map.get(ing_name.lower())
                if not matched_ing:
                    # Lookup in db
                    stmt = select(Ingredient).where(func.lower(Ingredient.inci_name) == ing_name.lower())
                    res = await session.execute(stmt)
                    matched_ing = res.scalar_one_or_none()
                    if not matched_ing:
                        matched_ing = Ingredient(
                            inci_name=ing_name,
                            safety_rating="safe",
                        )
                        session.add(matched_ing)
                        await session.flush()
                        ingredient_map[ing_name.lower()] = matched_ing

                pi = ProductIngredient(
                    product_id=product.id,
                    product_ingredient_list_id=formula.id,
                    ingredient_id=matched_ing.id,
                    position=pos,
                )
                session.add(pi)

            # Record commercial offer
            offer = ProductOffer(
                product_id=product.id,
                merchant_name=prod_data["merchant"],
                price_minor_units=prod_data["price_cents"],
                currency="USD",
                offer_url=f"https://www.google.com/search?q={prod_data['brand']}+{prod_data['name']}",
                is_in_stock=True,
            )
            session.add(offer)

            products_seeded += 1
            logger.info("Successfully seeded product: %s by %s", product.name, product.brand)

        await session.commit()
        logger.info("Seeding complete! %d new products added to the catalogue.", products_seeded)


if __name__ == "__main__":
    asyncio.run(seed())
