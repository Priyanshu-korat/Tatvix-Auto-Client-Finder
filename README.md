# 🚀 Tatvix AI Client Discovery System

**Automated client discovery system that finds, validates, and adds potential clients to Google Sheets with personalized emails.**

## ✨ Features

- **🎯 Automated Discovery:** Runs Monday-Friday at 8:00 AM IST
- **🌐 Website Validation:** Only adds companies with working, reachable websites  
- **📧 Enhanced Emails:** Personalized emails highlighting comprehensive Tatvix services
- **🇮🇳 Indian Focus:** Guarantees 3-4 Indian companies per day for better conversion
- **📊 Google Sheets Integration:** Automatically adds validated leads to spreadsheet
- **🔄 Real-time Monitoring:** Web interface for manual triggers and status monitoring

## 📈 Daily Results

- **Target:** 10 companies per day
- **Weekly:** 50 validated leads  
- **Monthly:** 200+ high-quality prospects
- **Quality:** 100% working websites with personalized outreach emails

## 🛠️ System Architecture

### Core Components

- **Daily Runner:** Automated scheduling and execution
- **Website Validator:** Comprehensive URL validation and connectivity testing
- **Email Templates:** Industry-specific personalized email generation
- **Google Sheets Manager:** Batch processing and data storage
- **Web Interface:** Gradio-based dashboard for monitoring and control

### Technology Stack

- **Python 3.11+** with asyncio for concurrent processing
- **Gradio** for web interface and Hugging Face Spaces deployment
- **Google Sheets API** for data storage and management
- **Groq AI** for intelligent company analysis and email generation
- **Advanced website validation** with DNS resolution and HTTP testing

## 🎯 Target Companies

### Indian Companies (3-4 per day)
- Startups and growing tech companies
- E-commerce and fintech platforms  
- IoT and hardware development firms
- SaaS and platform companies

### International Companies (6-7 per day)
- Technology startups and scale-ups
- IoT and embedded systems companies
- Hardware and firmware development firms
- Platform and infrastructure companies

## 📧 Email Features

Each generated email includes:

- **Personalized opening** based on company website content
- **Comprehensive Tatvix services:** firmware development, hardware design, wireless communication (BLE, Wi-Fi, LoRa), cloud integration, end-to-end product development
- **Industry-specific value propositions** tailored to company focus
- **Professional call-to-action** appropriate for lead quality score

## 🔧 Configuration

### Environment Variables

```bash
GROQ_API_KEY=your_groq_api_key
GOOGLE_SHEETS_ID=your_google_sheets_id
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google_service_account.json
ENVIRONMENT=production
```

### Google Sheets Setup

1. Create a Google Service Account
2. Download credentials JSON file
3. Share your Google Sheet with the service account email
4. Add credentials to `credentials/google_service_account.json`

## 🚀 Deployment on Hugging Face Spaces

### Quick Start

1. **Create Space:** Go to [huggingface.co/spaces](https://huggingface.co/spaces)
2. **Choose Gradio SDK:** Select Gradio as the Space SDK
3. **Upload Code:** Push this repository to your Space
4. **Set Variables:** Add environment variables in Space settings
5. **Deploy:** Space automatically builds and runs!

### Space Configuration

- **SDK:** Gradio
- **Python Version:** 3.11+
- **Hardware:** CPU Basic (free tier sufficient)
- **Persistent Storage:** Not required (stateless operation)

## 📊 Monitoring & Control

### Web Interface Features

- **📋 System Status:** Current time, schedule, last execution results
- **🚀 Manual Trigger:** Run discovery process immediately for testing
- **⏰ Next Run Time:** See when the next scheduled execution will occur
- **📈 Real-time Logs:** Monitor execution progress and results

### Automated Schedule

- **Monday-Friday:** 8:00 AM IST (2:30 AM UTC)
- **Weekends:** Automatically skipped
- **Execution Time:** ~2-3 minutes per run
- **Error Handling:** Automatic retries and graceful failure recovery

## 🎯 Business Impact

### Lead Quality
- **100% validated websites** - No broken links or fake companies
- **Personalized outreach** - Higher response rates with tailored messaging
- **Indian market focus** - Better conversion rates for Tatvix's target market
- **Comprehensive service showcase** - No missed opportunities

### Operational Efficiency  
- **Fully automated** - No manual lead research required
- **Consistent pipeline** - 50 new leads every week
- **Professional presentation** - Enhanced brand credibility
- **Scalable system** - Easy to adjust targets and criteria

## 🔒 Security & Privacy

- **Secure API handling** with proper error handling and rate limiting
- **Environment variable protection** for sensitive credentials
- **HTTPS-only communication** with external APIs
- **Minimal data retention** - focuses on lead generation, not storage

## 📞 Support

For technical support or customization requests:
- **Company:** Tatvix Technologies
- **Focus:** Embedded systems and IoT development
- **Services:** Firmware, hardware, wireless communication, cloud integration

---

**Powered by Tatvix Technologies | Deployed on Hugging Face Spaces**