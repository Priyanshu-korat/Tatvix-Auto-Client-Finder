"""Email template generation utilities for Tatvix AI Client Discovery System.

This module provides comprehensive email template generation with personalized
content based on company information and industry focus.
"""

from typing import Dict, Any, Optional
from database.models import LeadData


class EmailTemplateGenerator:
    """Generate personalized email templates for different industries and company types."""
    
    # Comprehensive Tatvix service description
    TATVIX_SERVICES = (
        "At Tatvix Technologies, we specialize in embedded systems and industrial IoT development, "
        "supporting companies across multiple domains such as firmware development, hardware design, "
        "wireless communication (BLE, Wi-Fi, LoRa), cloud integration, and end-to-end product development."
    )
    
    # Industry-specific service highlights (avoiding repetition with main services)
    INDUSTRY_SERVICES = {
        'IoT': {
            'services': 'sensor integration, device management, and IoT platform connectivity',
            'focus': 'connected device solutions and IoT ecosystem integration'
        },
        'Hardware': {
            'services': 'PCB design, prototyping, and manufacturing support',
            'focus': 'hardware design and product development'
        },
        'Industrial': {
            'services': 'industrial automation, monitoring systems, SCADA integration, and ruggedized solutions',
            'focus': 'industrial IoT and automation systems'
        },
        'Firmware': {
            'services': 'bootloader design, RTOS implementation, and device driver development',
            'focus': 'embedded software and system optimization'
        },
        'Wireless': {
            'services': 'RF design, protocol optimization, and connectivity solutions',
            'focus': 'wireless communication and network integration'
        },
        'Startup': {
            'services': 'MVP development, prototype design, and technical consulting',
            'focus': 'accelerated product development and market entry'
        },
        'Platform': {
            'services': 'API development, system architecture, and data processing',
            'focus': 'platform integration and ecosystem development'
        },
        'Default': {
            'services': 'system integration, technical consulting, and product development',
            'focus': 'comprehensive technology solutions'
        }
    }
    
    @classmethod
    def generate_personalized_email(
        cls,
        company_name: str,
        website_title: Optional[str] = None,
        industry: Optional[str] = None,
        company_description: Optional[str] = None,
        lead_score: Optional[int] = None
    ) -> Dict[str, str]:
        """Generate a personalized email for a company.
        
        Args:
            company_name: Name of the target company
            website_title: Title extracted from company website
            industry: Company's industry/sector
            company_description: Brief description of what the company does
            lead_score: Lead quality score (1-10)
            
        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        
        # Determine industry category for service customization
        industry_key = cls._determine_industry_category(industry, company_description, website_title)
        industry_info = cls.INDUSTRY_SERVICES.get(industry_key, cls.INDUSTRY_SERVICES['Default'])
        
        # Generate opening line based on available information
        opening = cls._generate_opening_line(company_name, website_title, company_description)
        
        # Generate company-specific value proposition
        value_prop = cls._generate_value_proposition(company_name, industry_key, industry_info)
        
        # Generate call to action based on lead score and industry
        cta = cls._generate_call_to_action(industry_key, lead_score)
        
        # Construct email body
        email_body = f"""Hello,

{opening}

{cls.TATVIX_SERVICES}

{value_prop}

{cta}

Best regards,
Tatvix Technologies Team"""

        # Generate subject line
        subject = cls._generate_subject_line(company_name, industry_key)
        
        return {
            'subject': subject,
            'body': email_body
        }
    
    @classmethod
    def _determine_industry_category(
        cls,
        industry: Optional[str],
        description: Optional[str],
        title: Optional[str]
    ) -> str:
        """Determine the most appropriate industry category for service customization."""
        
        # Combine all available text for analysis
        text_to_analyze = ' '.join(filter(None, [industry or '', description or '', title or ''])).lower()
        
        # Industry keyword mapping
        industry_keywords = {
            'IoT': ['iot', 'internet of things', 'connected', 'smart device', 'sensor', 'connectivity'],
            'Hardware': ['hardware', 'pcb', 'circuit', 'electronic', 'component', 'manufacturing'],
            'Industrial': ['industrial', 'automation', 'manufacturing', 'scada', 'monitoring', 'control'],
            'Firmware': ['firmware', 'embedded', 'microcontroller', 'bootloader', 'rtos', 'driver'],
            'Wireless': ['wireless', 'bluetooth', 'wifi', 'lora', 'zigbee', 'rf', 'communication'],
            'Startup': ['startup', 'early stage', 'seed', 'series a', 'mvp', 'prototype', 'funding'],
            'Platform': ['platform', 'api', 'cloud', 'saas', 'service', 'integration', 'ecosystem']
        }
        
        # Score each category based on keyword matches
        category_scores = {}
        for category, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_to_analyze)
            if score > 0:
                category_scores[category] = score
        
        # Return the highest scoring category, or Default if no matches
        if category_scores:
            return max(category_scores.items(), key=lambda x: x[1])[0]
        
        return 'Default'
    
    @classmethod
    def _generate_opening_line(
        cls,
        company_name: str,
        website_title: Optional[str],
        description: Optional[str]
    ) -> str:
        """Generate a personalized opening line."""
        
        if website_title and len(website_title) > 10:
            # Use website title if available and meaningful
            return f"I discovered {company_name} and your work with {website_title}. Your innovative approach caught our attention."
        elif description:
            # Use company description if available
            return f"I came across {company_name} and your {description}. Your technology solutions show great potential."
        else:
            # Generic but professional opening
            return f"I discovered {company_name} and your technology solutions. Your company's innovative approach aligns well with current market needs."
    
    @classmethod
    def _generate_value_proposition(
        cls,
        company_name: str,
        industry_key: str,
        industry_info: Dict[str, str]
    ) -> str:
        """Generate industry-specific value proposition."""
        
        services = industry_info['services']
        focus = industry_info['focus']
        
        if industry_key == 'Startup':
            return f"We understand the unique challenges startups face and help early-stage companies like {company_name} accelerate development. Our additional expertise in {services} enables us to support your {focus} from concept to market."
        
        elif industry_key == 'Industrial':
            return f"Given your industrial focus, our specialized experience in {services} could be valuable for {company_name}. We help companies build robust, reliable systems for {focus} in demanding environments."
        
        elif industry_key == 'Platform':
            return f"Understanding that platform companies like {company_name} need reliable technical partners, our specialized capabilities in {services} could help enhance your {focus} or support your ecosystem partners."
        
        else:
            return f"Our specialized expertise in {services} positions us well to support companies like {company_name} with {focus}, helping bridge the gap between innovative ideas and market-ready products."
    
    @classmethod
    def _generate_call_to_action(cls, industry_key: str, lead_score: Optional[int]) -> str:
        """Generate appropriate call to action based on industry and lead quality."""
        
        # High-value leads get more direct approach
        if lead_score and lead_score >= 8:
            return "Would you be interested in a brief call to discuss how we could support your current technical initiatives? I'd be happy to share some relevant case studies from similar projects."
        
        # Platform/ecosystem companies
        elif industry_key == 'Platform':
            return "Would you be interested in exploring partnership opportunities or discussing how we could support companies building on your platform?"
        
        # Startups get growth-focused CTA
        elif industry_key == 'Startup':
            return "Would you be interested in discussing how we could help accelerate your technical development and reduce time-to-market?"
        
        # Default professional CTA
        else:
            return "Would you be interested in discussing potential collaboration opportunities or how we could support your technical development needs?"
    
    @classmethod
    def _generate_subject_line(cls, company_name: str, industry_key: str) -> str:
        """Generate compelling subject line."""
        
        subject_templates = {
            'IoT': f"IoT Development Partnership - {company_name}",
            'Hardware': f"Hardware Development Support - {company_name}",
            'Industrial': f"Industrial IoT Partnership - {company_name}",
            'Firmware': f"Embedded Development Partnership - {company_name}",
            'Wireless': f"Wireless Technology Partnership - {company_name}",
            'Startup': f"Technical Development Support - {company_name}",
            'Platform': f"Platform Integration Partnership - {company_name}",
            'Default': f"Technical Partnership Opportunity - {company_name}"
        }
        
        return subject_templates.get(industry_key, subject_templates['Default'])


def generate_email_for_lead(lead: LeadData, website_title: Optional[str] = None) -> Dict[str, str]:
    """Generate personalized email for a LeadData instance.
    
    Args:
        lead: LeadData instance containing company information
        website_title: Optional website title from validation
        
    Returns:
        Dictionary with 'subject' and 'body' keys
    """
    return EmailTemplateGenerator.generate_personalized_email(
        company_name=lead.company,
        website_title=website_title,
        industry=lead.industry,
        company_description=getattr(lead, 'description', None),
        lead_score=lead.score
    )