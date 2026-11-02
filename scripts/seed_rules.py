"""
Seed script: Populate default fraud rules into database.
Handles idempotency - doesn't re-seed if rules exist.
"""

import sys
import os
from decimal import Decimal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo.database import Database
from app.db.database import close_db, get_database, initialize_database, insert_document
from app.models.fraud_rule import FraudRule
from app.services.fraud_engine import FraudEngine

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def seed_fraud_rules(db: Database) -> dict:
    """
    Seed default fraud rules into database.
    
    Returns:
        dict: Summary of seeding operation
    """
    stats = {
        "total_rules": 0,
        "created": 0,
        "skipped": 0,
        "errors": 0
    }
    
    logger.info("Starting fraud rules seeding...")
    
    try:
        # Get or create rules from DEFAULT_RULES
        for rule_id, rule_data in FraudEngine.DEFAULT_RULES.items():
            stats["total_rules"] += 1
            
            # Check if rule already exists
            existing = db["fraud_rules"].find_one({"rule_id": rule_id})
            
            if existing:
                logger.info(f"Rule {rule_id} already exists - skipping")
                stats["skipped"] += 1
                continue
            
            try:
                # Create new rule
                rule = FraudRule(
                    rule_id=rule_id,
                    name=rule_data["name"],
                    description=rule_data["description"],
                    rule_type=rule_data["rule_type"],
                    threshold_value=Decimal(str(rule_data.get("threshold", 0))),
                    threshold_unit=rule_data.get("threshold_unit", "amount"),
                    threshold_config=rule_data.get("config", {}),
                    severity=rule_data.get("severity", "medium"),
                    risk_weight=Decimal(str(rule_data["risk_weight"])),
                    required_fields=rule_data.get("required_fields", []),
                    applicable_transaction_types=rule_data.get(
                        "applicable_types", ["all"]
                    ),
                    is_enabled=True,
                    version=1,
                    notes=f"Default fraud detection rule: {rule_data['description']}"
                )
                
                inserted = insert_document(
                    db,
                    "fraud_rules",
                    rule.model_dump(exclude={"id", "created_at", "updated_at"}),
                )
                rule = FraudRule.model_validate(inserted)
                
                logger.info(
                    f"Created rule {rule_id}: {rule.name} "
                    f"(weight: {rule.risk_weight})"
                )
                stats["created"] += 1
            
            except Exception as e:
                logger.error(f"Failed to create rule {rule_id}: {e}")
                stats["errors"] += 1
        
        # Log summary
        logger.info("\n" + "="*60)
        logger.info("FRAUD RULES SEEDING SUMMARY")
        logger.info("="*60)
        logger.info(f"Total rules in catalog: {stats['total_rules']}")
        logger.info(f"Rules created:          {stats['created']}")
        logger.info(f"Rules skipped:          {stats['skipped']}")
        logger.info(f"Errors:                 {stats['errors']}")
        logger.info("="*60)
        
        return stats
    
    except Exception as e:
        logger.error(f"Fatal error during seeding: {e}")
        raise


def main():
    """Main entry point for seed script."""
    logger.info("Initializing database session...")
    
    try:
        db = get_database()
        initialize_database(db)
        
        # Seed rules
        stats = seed_fraud_rules(db)
        
        # Exit with appropriate code
        if stats["errors"] > 0:
            logger.warning(f"Seeding completed with {stats['errors']} errors")
            sys.exit(1)
        else:
            logger.info("Seeding completed successfully!")
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        sys.exit(1)
    
    finally:
        close_db()


if __name__ == "__main__":
    main()
