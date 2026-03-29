"""Daily automated runner for Tatvix AI Client Discovery System.

This module handles scheduled execution of the client discovery pipeline,
ensuring exactly 10 companies are added daily (Monday-Friday) with
Indian companies included.
"""

import asyncio
import schedule
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import pytz
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from database.models import LeadData, LeadStatus
from database.sheets_manager import SheetsManager
from utils.logger import get_logger
from utils.email_templates import generate_email_for_lead
from utils.website_validator import WebsiteValidator


logger = get_logger(__name__)


class DailyClientDiscovery:
    """Automated daily client discovery system."""
    
    def __init__(self):
        """Initialize daily discovery system."""
        self.settings = Settings()
        self.sheets_manager = None
        self.website_validator = WebsiteValidator(timeout=10, max_retries=1)
        
        # Target configuration
        self.target_companies_per_day = 10
        self.min_indian_companies = 3
        self.max_indian_companies = 4
        
        # IST timezone
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        
        self.logger = get_logger(__name__)
    
    async def initialize(self):
        """Initialize components."""
        self.sheets_manager = SheetsManager(self.settings)
        self.logger.info("Daily discovery system initialized")
    
    async def run_daily_discovery(self) -> Dict[str, Any]:
        """Run daily client discovery process.
        
        Returns:
            Dictionary with execution results
        """
        start_time = datetime.now(self.ist_timezone)
        self.logger.info(f"Starting daily discovery at {start_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
        
        try:
            # Get curated company list for the day
            companies = await self._get_daily_company_list()
            
            if len(companies) < self.target_companies_per_day:
                self.logger.warning(f"Only {len(companies)} companies available, target is {self.target_companies_per_day}")
            
            # Validate websites and generate emails
            validated_companies = await self._validate_and_prepare_companies(companies)
            
            # Ensure we have the right number of companies
            final_companies = self._select_final_companies(validated_companies)
            
            if not final_companies:
                self.logger.error("No valid companies found for today")
                return {
                    'success': False,
                    'companies_added': 0,
                    'error': 'No valid companies available'
                }
            
            # Insert into Google Sheets
            result = await self.sheets_manager.insert_leads(final_companies)
            
            # Log results
            indian_count = sum(1 for c in final_companies if c.country == 'IN')
            
            execution_summary = {
                'success': result.success,
                'companies_added': result.rows_affected,
                'indian_companies': indian_count,
                'international_companies': result.rows_affected - indian_count,
                'execution_time': start_time.strftime('%Y-%m-%d %H:%M:%S IST'),
                'companies': [{'name': c.company, 'country': c.country, 'industry': c.industry} for c in final_companies]
            }
            
            if result.success:
                self.logger.info(f"Daily discovery completed successfully: {result.rows_affected} companies added ({indian_count} Indian)")
            else:
                self.logger.error(f"Daily discovery failed: {result.error_message}")
            
            return execution_summary
            
        except Exception as e:
            self.logger.error(f"Daily discovery failed with exception: {e}")
            return {
                'success': False,
                'companies_added': 0,
                'error': str(e),
                'execution_time': start_time.strftime('%Y-%m-%d %H:%M:%S IST')
            }
    
    async def _get_daily_company_list(self) -> List[LeadData]:
        """Get curated list of companies for daily processing.
        
        Returns:
            List of LeadData objects for validation
        """
        # Mix of Indian and international companies
        # This would typically come from your discovery pipeline
        # For now, using a curated list of real companies
        
        indian_companies = [
            LeadData(
                company='Ather Energy',
                website='https://www.atherenergy.com',
                email='info@atherenergy.com',
                country='IN',
                industry='Electric Vehicles',
                score=8,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Byju\'s',
                website='https://byjus.com',
                email='info@byjus.com',
                country='IN',
                industry='EdTech',
                score=7,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Zomato',
                website='https://www.zomato.com',
                email='info@zomato.com',
                country='IN',
                industry='Food Tech',
                score=9,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Paytm',
                website='https://paytm.com',
                email='care@paytm.com',
                country='IN',
                industry='FinTech',
                score=8,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Flipkart',
                website='https://www.flipkart.com',
                email='support@flipkart.com',
                country='IN',
                industry='E-commerce',
                score=9,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Swiggy',
                website='https://www.swiggy.com',
                email='support@swiggy.in',
                country='IN',
                industry='Food Delivery',
                score=8,
                source='Daily Discovery - Indian',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            )
        ]
        
        international_companies = [
            LeadData(
                company='Stripe',
                website='https://stripe.com',
                email='info@stripe.com',
                country='US',
                industry='FinTech',
                score=9,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Shopify',
                website='https://www.shopify.com',
                email='support@shopify.com',
                country='CA',
                industry='E-commerce Platform',
                score=9,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Discord',
                website='https://discord.com',
                email='support@discord.com',
                country='US',
                industry='Communication',
                score=8,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Notion',
                website='https://www.notion.so',
                email='team@makenotion.com',
                country='US',
                industry='Productivity',
                score=8,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Figma',
                website='https://www.figma.com',
                email='support@figma.com',
                country='US',
                industry='Design Tools',
                score=8,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Canva',
                website='https://www.canva.com',
                email='support@canva.com',
                country='AU',
                industry='Design Platform',
                score=8,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Zoom',
                website='https://zoom.us',
                email='support@zoom.us',
                country='US',
                industry='Video Communication',
                score=9,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            ),
            LeadData(
                company='Slack',
                website='https://slack.com',
                email='feedback@slack.com',
                country='US',
                industry='Team Communication',
                score=9,
                source='Daily Discovery - International',
                status=LeadStatus.ANALYZED,
                personalized_email='',
                email_subject=''
            )
        ]
        
        # Combine and shuffle for variety
        all_companies = indian_companies + international_companies
        
        # Return more than needed so we have options after validation
        return all_companies[:20]  # Return 20 to have buffer for validation failures
    
    async def _validate_and_prepare_companies(self, companies: List[LeadData]) -> List[LeadData]:
        """Validate websites and prepare companies with enhanced emails.
        
        Args:
            companies: List of companies to validate
            
        Returns:
            List of validated companies with enhanced emails
        """
        self.logger.info(f"Validating {len(companies)} companies...")
        
        # Collect URLs for batch validation
        urls = [str(company.website) for company in companies]
        validation_results = await self.website_validator.validate_multiple_websites(urls)
        
        validated_companies = []
        
        for company in companies:
            url = str(company.website)
            validation_result = validation_results.get(url, {})
            
            if validation_result.get('is_valid') and validation_result.get('is_reachable'):
                # Generate enhanced email
                website_title = validation_result.get('title', '')
                email_content = generate_email_for_lead(company, website_title)
                
                company.personalized_email = email_content['body']
                company.email_subject = email_content['subject']
                
                validated_companies.append(company)
                self.logger.info(f"✓ {company.company} ({company.country}): Website validated")
            else:
                error = validation_result.get('error', 'Validation failed')
                self.logger.warning(f"✗ {company.company} ({company.country}): {error}")
        
        self.logger.info(f"Validation complete: {len(validated_companies)}/{len(companies)} companies passed")
        return validated_companies
    
    def _select_final_companies(self, validated_companies: List[LeadData]) -> List[LeadData]:
        """Select final 10 companies ensuring Indian representation.
        
        Args:
            validated_companies: List of validated companies
            
        Returns:
            Final list of exactly 10 companies
        """
        if len(validated_companies) < self.target_companies_per_day:
            self.logger.warning(f"Only {len(validated_companies)} validated companies available")
            return validated_companies
        
        # Separate Indian and international companies
        indian_companies = [c for c in validated_companies if c.country == 'IN']
        international_companies = [c for c in validated_companies if c.country != 'IN']
        
        # Ensure we have enough Indian companies
        indian_count = min(len(indian_companies), self.max_indian_companies)
        indian_count = max(indian_count, min(self.min_indian_companies, len(indian_companies)))
        
        # Calculate international companies needed
        international_count = self.target_companies_per_day - indian_count
        international_count = min(international_count, len(international_companies))
        
        # Select companies
        selected_indian = indian_companies[:indian_count]
        selected_international = international_companies[:international_count]
        
        final_companies = selected_indian + selected_international
        
        self.logger.info(f"Selected {len(final_companies)} companies: {len(selected_indian)} Indian, {len(selected_international)} International")
        
        return final_companies[:self.target_companies_per_day]  # Ensure exactly 10
    
    def is_weekday(self) -> bool:
        """Check if today is a weekday (Monday-Friday).
        
        Returns:
            True if today is Monday-Friday
        """
        now = datetime.now(self.ist_timezone)
        return now.weekday() < 5  # 0-4 are Monday-Friday
    
    async def scheduled_run(self):
        """Scheduled run wrapper with weekday check."""
        if not self.is_weekday():
            current_day = datetime.now(self.ist_timezone).strftime('%A')
            self.logger.info(f"Skipping execution - today is {current_day} (weekend)")
            return
        
        self.logger.info("Starting scheduled daily discovery...")
        
        try:
            await self.initialize()
            result = await self.run_daily_discovery()
            
            if result['success']:
                self.logger.info(f"Scheduled run completed successfully: {result['companies_added']} companies added")
            else:
                self.logger.error(f"Scheduled run failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.logger.error(f"Scheduled run failed with exception: {e}")


def setup_scheduler():
    """Setup the daily scheduler."""
    discovery = DailyClientDiscovery()
    
    # Schedule for 8:00 AM IST, Monday to Friday
    schedule.every().monday.at("08:00").do(lambda: asyncio.run(discovery.scheduled_run()))
    schedule.every().tuesday.at("08:00").do(lambda: asyncio.run(discovery.scheduled_run()))
    schedule.every().wednesday.at("08:00").do(lambda: asyncio.run(discovery.scheduled_run()))
    schedule.every().thursday.at("08:00").do(lambda: asyncio.run(discovery.scheduled_run()))
    schedule.every().friday.at("08:00").do(lambda: asyncio.run(discovery.scheduled_run()))
    
    logger.info("Scheduler configured for 8:00 AM IST, Monday-Friday")
    
    return discovery


def run_scheduler():
    """Run the scheduler continuously."""
    discovery = setup_scheduler()
    
    logger.info("Starting Tatvix Daily Client Discovery Scheduler...")
    logger.info("Schedule: Monday-Friday at 8:00 AM IST")
    logger.info("Target: 10 companies per day (3-4 Indian companies)")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Scheduler failed: {e}")


if __name__ == "__main__":
    # For testing - run immediately
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        async def test_run():
            discovery = DailyClientDiscovery()
            await discovery.initialize()
            result = await discovery.run_daily_discovery()
            print(f"Test run result: {result}")
        
        asyncio.run(test_run())
    else:
        # Run scheduler
        run_scheduler()