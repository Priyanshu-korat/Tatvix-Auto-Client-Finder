"""Google Sheets integration and data management for Tatvix AI Client Discovery System.

This module provides robust Google Sheets integration for lead storage, tracking,
and management with real-time synchronization, batch operations, and data integrity.
"""

import asyncio
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import backoff
from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import ValidationError

from config.settings import Settings
from database.models import LeadData, LeadStatus, SheetsOperationResult, BackupResult
from utils.exceptions import ConfigurationError, DataValidationError, ExternalServiceError
from utils.logger import get_logger


class SheetsManagerError(Exception):
    """Base exception for Google Sheets manager operations."""
    pass


class SheetsAuthenticationError(SheetsManagerError):
    """Exception raised for Google Sheets authentication failures."""
    pass


class SheetsAPIError(SheetsManagerError):
    """Exception raised for Google Sheets API errors."""
    pass


class SheetsDataError(SheetsManagerError):
    """Exception raised for Google Sheets data validation errors."""
    pass


class SheetsManager:
    """Google Sheets manager for lead data storage and synchronization.
    
    Provides comprehensive Google Sheets integration with authentication,
    CRUD operations, batch processing, backup functionality, and error handling.
    """
    
    # Google Sheets API scopes
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    # API quota limits (per 100 seconds)
    READ_REQUESTS_QUOTA = 100
    WRITE_REQUESTS_QUOTA = 100
    
    def __init__(self, config: Settings, credentials_path: Optional[str] = None):
        """Initialize Google Sheets manager.
        
        Args:
            config: Application configuration instance.
            credentials_path: Optional path to service account credentials file.
            
        Raises:
            SheetsAuthenticationError: If authentication setup fails.
            ConfigurationError: If required configuration is missing.
        """
        self.config = config
        self.logger = get_logger(__name__)
        
        # Configuration
        self.credentials_path = credentials_path or self.config.get_secure('google', 'sheets_credentials_path')
        self.spreadsheet_id = self.config.get_secure('google', 'sheets_id')
        self.worksheet_name = self.config.get('google', 'worksheet_name', fallback='Leads')
        
        # Performance settings
        self.batch_size = self.config.get_int('google', 'batch_size', fallback=100)
        self.timeout = self.config.get_int('google', 'sheets_timeout', fallback=30)
        self.retry_attempts = self.config.get_int('google', 'retry_attempts', fallback=3)
        
        # Backup settings
        self.backup_location = self.config.get('backup', 'directory', fallback='./backups')
        
        # Initialize service
        self.service = None
        self._initialize_service()
        
        # Request tracking for rate limiting
        self._read_requests = 0
        self._write_requests = 0
        self._last_reset_time = time.time()
        
        self.logger.info(
            "SheetsManager initialized",
            extra={
                "spreadsheet_id": self.spreadsheet_id,
                "worksheet_name": self.worksheet_name,
                "batch_size": self.batch_size
            }
        )
    
    def _initialize_service(self) -> None:
        """Initialize Google Sheets API service with authentication.
        
        Raises:
            SheetsAuthenticationError: If authentication fails.
            ConfigurationError: If credentials are not properly configured.
        """
        try:
            if not self.credentials_path:
                raise ConfigurationError("Google Sheets credentials path not configured")
            
            if not os.path.exists(self.credentials_path):
                raise ConfigurationError(f"Credentials file not found: {self.credentials_path}")
            
            if not self.spreadsheet_id:
                raise ConfigurationError("Google Sheets spreadsheet ID not configured")
            
            # Load service account credentials
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES
            )
            
            # Build the service
            self.service = build('sheets', 'v4', credentials=credentials)
            
            # Test authentication by accessing spreadsheet metadata
            self._test_authentication()
            
            self.logger.info("Google Sheets service initialized successfully")
            
        except GoogleAuthError as e:
            raise SheetsAuthenticationError(f"Google authentication failed: {e}")
        except Exception as e:
            raise SheetsAuthenticationError(f"Failed to initialize Google Sheets service: {e}")
    
    def _test_authentication(self) -> None:
        """Test Google Sheets authentication and access.
        
        Raises:
            SheetsAuthenticationError: If authentication test fails.
        """
        try:
            # Test by getting spreadsheet metadata
            result = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            
            self.logger.info(
                "Authentication test successful",
                extra={
                    "spreadsheet_title": result.get('properties', {}).get('title', 'Unknown'),
                    "sheet_count": len(result.get('sheets', []))
                }
            )
            
        except HttpError as e:
            if e.resp.status == 404:
                raise SheetsAuthenticationError(
                    f"Spreadsheet not found or access denied: {self.spreadsheet_id}"
                )
            elif e.resp.status == 403:
                raise SheetsAuthenticationError(
                    "Insufficient permissions to access spreadsheet"
                )
            else:
                raise SheetsAuthenticationError(f"Authentication test failed: {e}")
    
    def _check_rate_limits(self, operation_type: str) -> None:
        """Check and enforce API rate limits.
        
        Args:
            operation_type: Type of operation ('read' or 'write').
        """
        current_time = time.time()
        
        # Reset counters every 100 seconds
        if current_time - self._last_reset_time >= 100:
            self._read_requests = 0
            self._write_requests = 0
            self._last_reset_time = current_time
        
        # Check limits
        if operation_type == 'read' and self._read_requests >= self.READ_REQUESTS_QUOTA:
            sleep_time = 100 - (current_time - self._last_reset_time)
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)
                self._read_requests = 0
                self._write_requests = 0
                self._last_reset_time = time.time()
        
        elif operation_type == 'write' and self._write_requests >= self.WRITE_REQUESTS_QUOTA:
            sleep_time = 100 - (current_time - self._last_reset_time)
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)
                self._read_requests = 0
                self._write_requests = 0
                self._last_reset_time = time.time()
        
        # Increment counter
        if operation_type == 'read':
            self._read_requests += 1
        elif operation_type == 'write':
            self._write_requests += 1
    
    @backoff.on_exception(
        backoff.expo,
        (HttpError, ConnectionError, TimeoutError),
        max_tries=3,
        max_time=300,
        giveup=lambda e: isinstance(e, HttpError) and e.resp.status in [400, 401, 403, 404]
    )
    async def initialize_sheet(self, sheet_name: Optional[str] = None) -> str:
        """Initialize worksheet with proper headers.
        
        Creates the worksheet if it doesn't exist and ensures proper column headers
        are in place for lead data storage.
        
        Args:
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            Worksheet name that was initialized.
            
        Raises:
            SheetsAPIError: If sheet initialization fails.
        """
        start_time = time.time()
        sheet_name = sheet_name or self.worksheet_name
        
        try:
            self._check_rate_limits('read')
            
            # Get spreadsheet metadata
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Check if worksheet exists
            worksheet_exists = False
            for sheet in spreadsheet.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    worksheet_exists = True
                    break
            
            # Create worksheet if it doesn't exist
            if not worksheet_exists:
                self._check_rate_limits('write')
                
                request = {
                    'addSheet': {
                        'properties': {
                            'title': sheet_name,
                            'gridProperties': {
                                'rowCount': 1000,
                                'columnCount': 11
                            }
                        }
                    }
                }
                
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={'requests': [request]}
                ).execute()
                
                self.logger.info(f"Created new worksheet: {sheet_name}")
            
            # Check if headers exist
            self._check_rate_limits('read')
            
            range_name = f"{sheet_name}!A1:K1"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # Add headers if they don't exist or are incomplete
            expected_headers = LeadData.get_headers()
            if not values or len(values[0]) < len(expected_headers) or values[0] != expected_headers:
                self._check_rate_limits('write')
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': [expected_headers]}
                ).execute()
                
                self.logger.info(f"Updated headers in worksheet: {sheet_name}")
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Sheet initialization completed",
                extra={
                    "sheet_name": sheet_name,
                    "duration_ms": duration_ms,
                    "worksheet_existed": worksheet_exists
                }
            )
            
            return sheet_name
            
        except HttpError as e:
            raise SheetsAPIError(f"Failed to initialize sheet '{sheet_name}': {e}")
        except Exception as e:
            raise SheetsManagerError(f"Unexpected error during sheet initialization: {e}")
    
    @backoff.on_exception(
        backoff.expo,
        (HttpError, ConnectionError, TimeoutError),
        max_tries=3,
        max_time=300,
        giveup=lambda e: isinstance(e, HttpError) and e.resp.status in [400, 401, 403, 404]
    )
    async def insert_leads(self, leads: List[LeadData], sheet_name: Optional[str] = None) -> SheetsOperationResult:
        """Insert leads into Google Sheets with batch processing.
        
        Args:
            leads: List of LeadData instances to insert.
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            SheetsOperationResult with operation details.
            
        Raises:
            SheetsDataError: If lead data validation fails.
            SheetsAPIError: If insertion operation fails.
        """
        start_time = time.time()
        sheet_name = sheet_name or self.worksheet_name
        
        if not leads:
            return SheetsOperationResult(
                success=True,
                operation_type="insert_leads",
                rows_affected=0,
                duration_ms=0.0,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name
            )
        
        try:
            # Validate all leads first (data structure validation)
            validated_leads = []
            for i, lead in enumerate(leads):
                try:
                    if isinstance(lead, dict):
                        lead = LeadData(**lead)
                    elif not isinstance(lead, LeadData):
                        raise SheetsDataError(f"Invalid lead data type at index {i}")
                    
                    validated_leads.append(lead)
                except ValidationError as e:
                    raise SheetsDataError(f"Lead validation failed at index {i}: {e}")
            
            # Website validation - only include leads with valid, reachable websites
            self.logger.info(f"Validating websites for {len(validated_leads)} leads...")
            
            from utils.website_validator import WebsiteValidator
            website_validator = WebsiteValidator(timeout=10, max_retries=1)
            
            # Collect all URLs for batch validation
            urls_to_validate = [str(lead.website) for lead in validated_leads]
            validation_results = await website_validator.validate_multiple_websites(urls_to_validate)
            
            # Filter leads with valid websites only
            final_validated_leads = []
            for lead in validated_leads:
                url = str(lead.website)
                validation_result = validation_results.get(url, {})
                
                if validation_result.get('is_valid') and validation_result.get('is_reachable'):
                    # Generate enhanced personalized email with comprehensive service description
                    from utils.email_templates import generate_email_for_lead
                    
                    website_title = validation_result.get('title', '')
                    email_content = generate_email_for_lead(lead, website_title)
                    
                    # Update lead with enhanced email content
                    lead.personalized_email = email_content['body']
                    lead.email_subject = email_content['subject']
                    
                    final_validated_leads.append(lead)
                    self.logger.info(f"✅ {lead.company}: Website {url} is valid and reachable")
                else:
                    error = validation_result.get('error', 'Unknown validation error')
                    self.logger.warning(f"❌ {lead.company}: Website {url} validation failed - {error}")
            
            if not final_validated_leads:
                self.logger.warning("No leads have valid websites - nothing to insert")
                return SheetsOperationResult(
                    success=True,
                    operation_type="insert_leads",
                    rows_affected=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    spreadsheet_id=self.spreadsheet_id,
                    worksheet_name=sheet_name,
                    error_message=f"All {len(validated_leads)} leads failed website validation"
                )
            
            self.logger.info(f"Website validation complete: {len(final_validated_leads)}/{len(validated_leads)} leads have valid websites")
            validated_leads = final_validated_leads
            
            # Prepare data for insertion
            rows_to_insert = [lead.to_sheets_row() for lead in validated_leads]
            
            # Process in batches
            total_inserted = 0
            batch_count = 0
            
            for i in range(0, len(rows_to_insert), self.batch_size):
                batch = rows_to_insert[i:i + self.batch_size]
                batch_count += 1
                
                # Find next available row
                self._check_rate_limits('read')
                
                result = self.service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A:A"
                ).execute()
                
                existing_rows = len(result.get('values', []))
                next_row = existing_rows + 1
                
                # Insert batch
                range_name = f"{sheet_name}!A{next_row}:K{next_row + len(batch) - 1}"
                
                self._check_rate_limits('write')
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': batch}
                ).execute()
                
                total_inserted += len(batch)
                
                self.logger.debug(
                    f"Inserted batch {batch_count}",
                    extra={
                        "batch_size": len(batch),
                        "range": range_name,
                        "total_inserted": total_inserted
                    }
                )
                
                # Small delay between batches to avoid rate limiting
                if i + self.batch_size < len(rows_to_insert):
                    await asyncio.sleep(0.1)
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Lead insertion completed",
                extra={
                    "leads_inserted": total_inserted,
                    "batches_processed": batch_count,
                    "duration_ms": duration_ms,
                    "sheet_name": sheet_name
                }
            )
            
            return SheetsOperationResult(
                success=True,
                operation_type="insert_leads",
                rows_affected=total_inserted,
                duration_ms=duration_ms,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name,
                range_updated=f"A{existing_rows + 1}:K{existing_rows + total_inserted}"
            )
            
        except HttpError as e:
            error_msg = f"Failed to insert leads: {e}"
            self.logger.error(error_msg, extra={"leads_count": len(leads)})
            
            return SheetsOperationResult(
                success=False,
                operation_type="insert_leads",
                rows_affected=0,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=error_msg,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name
            )
        except Exception as e:
            error_msg = f"Unexpected error during lead insertion: {e}"
            self.logger.error(error_msg, extra={"leads_count": len(leads)})
            
            return SheetsOperationResult(
                success=False,
                operation_type="insert_leads",
                rows_affected=0,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=error_msg,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name
            )
    
    @backoff.on_exception(
        backoff.expo,
        (HttpError, ConnectionError, TimeoutError),
        max_tries=3,
        max_time=300,
        giveup=lambda e: isinstance(e, HttpError) and e.resp.status in [400, 401, 403, 404]
    )
    async def update_lead_status(
        self, 
        lead_id: str, 
        status: Union[LeadStatus, str], 
        sheet_name: Optional[str] = None
    ) -> SheetsOperationResult:
        """Update lead status by lead ID.
        
        Args:
            lead_id: Unique lead identifier.
            status: New status value.
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            SheetsOperationResult with operation details.
            
        Raises:
            SheetsAPIError: If update operation fails.
        """
        start_time = time.time()
        sheet_name = sheet_name or self.worksheet_name
        
        try:
            # Validate status
            if isinstance(status, str):
                status = LeadStatus(status)
            
            # Find the lead row
            self._check_rate_limits('read')
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:K"
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:  # Only headers or empty
                return SheetsOperationResult(
                    success=False,
                    operation_type="update_lead_status",
                    rows_affected=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    error_message=f"Lead not found: {lead_id}",
                    spreadsheet_id=self.spreadsheet_id,
                    worksheet_name=sheet_name
                )
            
            # Find lead by ID (column A)
            lead_row_index = None
            for i, row in enumerate(values[1:], start=2):  # Skip header row
                if len(row) > 0 and row[0] == lead_id:
                    lead_row_index = i
                    break
            
            if lead_row_index is None:
                return SheetsOperationResult(
                    success=False,
                    operation_type="update_lead_status",
                    rows_affected=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    error_message=f"Lead not found: {lead_id}",
                    spreadsheet_id=self.spreadsheet_id,
                    worksheet_name=sheet_name
                )
            
            # Update status (column H) and updated timestamp (column K)
            updates = [
                {
                    'range': f"{sheet_name}!H{lead_row_index}",
                    'values': [[status.value]]
                },
                {
                    'range': f"{sheet_name}!K{lead_row_index}",
                    'values': [[datetime.utcnow().isoformat()]]
                }
            ]
            
            self._check_rate_limits('write')
            
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    'valueInputOption': 'RAW',
                    'data': updates
                }
            ).execute()
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Lead status updated",
                extra={
                    "lead_id": lead_id,
                    "new_status": status.value,
                    "row_index": lead_row_index,
                    "duration_ms": duration_ms
                }
            )
            
            return SheetsOperationResult(
                success=True,
                operation_type="update_lead_status",
                rows_affected=1,
                duration_ms=duration_ms,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name,
                range_updated=f"H{lead_row_index},K{lead_row_index}"
            )
            
        except ValueError as e:
            error_msg = f"Invalid status value: {e}"
            return SheetsOperationResult(
                success=False,
                operation_type="update_lead_status",
                rows_affected=0,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=error_msg,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name
            )
        except HttpError as e:
            error_msg = f"Failed to update lead status: {e}"
            self.logger.error(error_msg, extra={"lead_id": lead_id})
            
            return SheetsOperationResult(
                success=False,
                operation_type="update_lead_status",
                rows_affected=0,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=error_msg,
                spreadsheet_id=self.spreadsheet_id,
                worksheet_name=sheet_name
            )
    
    @backoff.on_exception(
        backoff.expo,
        (HttpError, ConnectionError, TimeoutError),
        max_tries=3,
        max_time=300,
        giveup=lambda e: isinstance(e, HttpError) and e.resp.status in [400, 401, 403, 404]
    )
    async def get_existing_leads(
        self, 
        filters: Optional[Dict[str, Any]] = None,
        sheet_name: Optional[str] = None
    ) -> List[LeadData]:
        """Get existing leads with optional filtering.
        
        Args:
            filters: Optional filters to apply (e.g., {'status': 'new', 'country': 'US'}).
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            List of LeadData instances matching filters.
            
        Raises:
            SheetsAPIError: If retrieval operation fails.
        """
        start_time = time.time()
        sheet_name = sheet_name or self.worksheet_name
        filters = filters or {}
        
        try:
            self._check_rate_limits('read')
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:K"
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:  # Only headers or empty
                return []
            
            # Parse leads from rows
            leads = []
            for i, row in enumerate(values[1:], start=2):  # Skip header row
                try:
                    # Pad row to ensure all columns are present
                    padded_row = row + [''] * (11 - len(row))
                    lead = LeadData.from_sheets_row(padded_row)
                    
                    # Apply filters
                    if self._matches_filters(lead, filters):
                        leads.append(lead)
                        
                except (ValueError, ValidationError) as e:
                    self.logger.warning(
                        f"Skipping invalid row {i}",
                        extra={"row_data": row, "error": str(e)}
                    )
                    continue
            
            duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Retrieved existing leads",
                extra={
                    "total_rows": len(values) - 1,
                    "valid_leads": len(leads),
                    "filters_applied": bool(filters),
                    "duration_ms": duration_ms
                }
            )
            
            return leads
            
        except HttpError as e:
            self.logger.error(f"Failed to retrieve leads: {e}")
            raise SheetsAPIError(f"Failed to retrieve leads: {e}")
    
    def _matches_filters(self, lead: LeadData, filters: Dict[str, Any]) -> bool:
        """Check if lead matches the provided filters.
        
        Args:
            lead: LeadData instance to check.
            filters: Dictionary of field filters.
            
        Returns:
            True if lead matches all filters, False otherwise.
        """
        for field, value in filters.items():
            lead_value = getattr(lead, field, None)
            
            if lead_value is None:
                return False
            
            # Handle different comparison types
            if isinstance(value, str):
                if str(lead_value).lower() != value.lower():
                    return False
            elif isinstance(value, list):
                if lead_value not in value:
                    return False
            else:
                if lead_value != value:
                    return False
        
        return True
    
    async def backup_data(
        self, 
        backup_location: Optional[str] = None,
        format_type: str = 'csv',
        sheet_name: Optional[str] = None
    ) -> BackupResult:
        """Backup worksheet data to local file.
        
        Args:
            backup_location: Optional backup directory path.
            format_type: Backup format ('csv' or 'json').
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            BackupResult with backup operation details.
            
        Raises:
            SheetsManagerError: If backup operation fails.
        """
        start_time = time.time()
        sheet_name = sheet_name or self.worksheet_name
        backup_location = backup_location or self.backup_location
        
        try:
            # Ensure backup directory exists
            backup_dir = Path(backup_location)
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate backup filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"leads_backup_{timestamp}.{format_type}"
            backup_path = backup_dir / filename
            
            # Get all data
            leads = await self.get_existing_leads(sheet_name=sheet_name)
            
            if format_type.lower() == 'csv':
                # Export as CSV
                with open(backup_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Write headers
                    writer.writerow(LeadData.get_headers())
                    
                    # Write data
                    for lead in leads:
                        writer.writerow(lead.to_sheets_row())
            
            elif format_type.lower() == 'json':
                # Export as JSON
                leads_data = [lead.dict() for lead in leads]
                
                with open(backup_path, 'w', encoding='utf-8') as jsonfile:
                    json.dump({
                        'backup_timestamp': datetime.utcnow().isoformat(),
                        'spreadsheet_id': self.spreadsheet_id,
                        'worksheet_name': sheet_name,
                        'total_leads': len(leads),
                        'leads': leads_data
                    }, jsonfile, indent=2, default=str)
            
            else:
                raise ValueError(f"Unsupported backup format: {format_type}")
            
            # Get file size
            file_size = backup_path.stat().st_size
            duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Backup completed successfully",
                extra={
                    "backup_path": str(backup_path),
                    "format": format_type,
                    "rows_exported": len(leads),
                    "file_size_bytes": file_size,
                    "duration_ms": duration_ms
                }
            )
            
            return BackupResult(
                success=True,
                backup_path=str(backup_path),
                backup_format=format_type,
                rows_exported=len(leads),
                file_size_bytes=file_size,
                duration_ms=duration_ms
            )
            
        except Exception as e:
            error_msg = f"Backup operation failed: {e}"
            self.logger.error(error_msg)
            
            return BackupResult(
                success=False,
                backup_path="",
                backup_format=format_type,
                rows_exported=0,
                file_size_bytes=0,
                duration_ms=(time.time() - start_time) * 1000,
                error_message=error_msg
            )
    
    async def get_domains_for_duplicate_check(self, sheet_name: Optional[str] = None) -> List[str]:
        """Get list of existing domains for duplicate detection.
        
        This method is specifically designed for integration with the duplicate
        detection system to check for existing websites before insertion.
        
        Args:
            sheet_name: Optional worksheet name. Uses default if not provided.
            
        Returns:
            List of normalized domain strings.
        """
        try:
            leads = await self.get_existing_leads(sheet_name=sheet_name)
            
            domains = []
            for lead in leads:
                if lead.website:
                    # Extract domain from URL
                    domain = str(lead.website).replace('https://', '').replace('http://', '')
                    domain = domain.replace('www.', '').split('/')[0].lower()
                    domains.append(domain)
            
            # Remove duplicates and return
            unique_domains = list(set(domains))
            
            self.logger.debug(
                "Retrieved domains for duplicate check",
                extra={
                    "total_leads": len(leads),
                    "unique_domains": len(unique_domains)
                }
            )
            
            return unique_domains
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve domains for duplicate check: {e}")
            return []
    
    def __repr__(self) -> str:
        """String representation of SheetsManager."""
        return (
            f"SheetsManager(spreadsheet_id='{self.spreadsheet_id}', "
            f"worksheet='{self.worksheet_name}', batch_size={self.batch_size})"
        )