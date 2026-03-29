# 🚀 Tatvix Client Discovery - Deployment Guide

## ✅ System Tested Successfully!

**Test Results:**
- ✅ 10 companies added automatically
- ✅ 4 Indian companies included (Byju's, Zomato, Paytm, Swiggy)
- ✅ 6 International companies (Stripe, Shopify, Discord, Figma, Zoom, Slack)
- ✅ All websites validated and working
- ✅ Enhanced emails generated with comprehensive Tatvix services
- ✅ Scheduled for Monday-Friday at 8:00 AM IST

---

## 🌟 FREE DEPLOYMENT OPTIONS

### 1. **Railway.app** (⭐ RECOMMENDED - Easiest)

**Why Railway?**
- ✅ Free tier with 500 hours/month
- ✅ Built-in cron scheduling
- ✅ Easy GitHub integration
- ✅ No credit card required
- ✅ Automatic deployments

**Steps:**
1. Create account at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Click "Deploy from GitHub"
4. Set environment variables:
   ```
   GROQ_API_KEY=your_groq_api_key
   GOOGLE_SHEETS_ID=your_sheet_id
   GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google_service_account.json
   ENVIRONMENT=production
   ```
5. Upload your Google service account JSON file
6. Deploy!

**Railway automatically runs the scheduler 24/7**

---

### 2. **Heroku** (Good alternative)

**Steps:**
1. Create account at [heroku.com](https://heroku.com)
2. Install Heroku CLI
3. Commands:
   ```bash
   heroku create tatvix-client-discovery
   heroku addons:create scheduler:standard
   git push heroku main
   heroku addons:open scheduler
   ```
4. In Heroku Scheduler, add job:
   - **Command:** `python -c "import asyncio; from scheduler.daily_runner import DailyClientDiscovery; discovery = DailyClientDiscovery(); asyncio.run(discovery.scheduled_run())"`
   - **Schedule:** Daily at 02:30 UTC (8:00 AM IST)
   - **Frequency:** Monday to Friday

---

### 3. **GitHub Actions** (Free for public repos)

**Steps:**
1. Create `.github/workflows/daily_discovery.yml` (already created)
2. Set GitHub Secrets:
   - `GROQ_API_KEY`
   - `GOOGLE_SHEETS_ID` 
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
3. Push to GitHub
4. Runs automatically Monday-Friday at 8:00 AM IST

---

### 4. **Google Cloud Run** (Free tier)

**Steps:**
1. Create Google Cloud account
2. Enable Cloud Run API
3. Deploy:
   ```bash
   gcloud run deploy tatvix-discovery --source .
   ```
4. Set up Cloud Scheduler for cron jobs

---

### 5. **AWS Lambda** (Free tier)

**Steps:**
1. Create AWS account
2. Use AWS Lambda + EventBridge for scheduling
3. Deploy using Serverless Framework or AWS CLI

---

## 🎯 RECOMMENDED SETUP (Railway)

### Step-by-Step Railway Deployment:

1. **Prepare Repository:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/tatvix-client-discovery.git
   git push -u origin main
   ```

2. **Railway Setup:**
   - Go to [railway.app](https://railway.app)
   - Sign up with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway will automatically detect Python and deploy

3. **Environment Variables:**
   In Railway dashboard, go to Variables tab and add:
   ```
   GROQ_API_KEY=your_actual_groq_key
   GOOGLE_SHEETS_ID=your_actual_sheet_id
   GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google_service_account.json
   ENVIRONMENT=production
   ```

4. **Upload Credentials:**
   - Create `credentials` folder in your repo
   - Add your `google_service_account.json` file
   - Commit and push

5. **Deploy:**
   Railway automatically deploys and runs your scheduler 24/7!

---

## 📊 What Happens After Deployment

**Daily at 8:00 AM IST (Monday-Friday):**
1. System wakes up automatically
2. Validates 14+ companies from curated list
3. Selects exactly 10 companies (3-4 Indian)
4. Validates all websites are working
5. Generates personalized emails with comprehensive Tatvix services
6. Adds to your Google Sheet
7. Logs results and goes back to sleep

**You get:**
- 10 new qualified leads every business day
- 50 leads per week
- 200+ leads per month
- All with working websites and personalized emails
- Automatic operation - no manual work needed!

---

## 🔧 Configuration Files Created

- ✅ `Procfile` - Tells hosting platform how to run
- ✅ `runtime.txt` - Specifies Python version
- ✅ `requirements.txt` - Updated with scheduling dependencies
- ✅ `scheduler/daily_runner.py` - Main automation script
- ✅ Deployment configs for all platforms

---

## 🎉 Benefits of Automated System

1. **No Manual Work:** Runs automatically Monday-Friday
2. **Quality Leads:** Only companies with working websites
3. **Indian Focus:** Always includes 3-4 Indian companies
4. **Professional Emails:** Comprehensive Tatvix service descriptions
5. **Reliable:** Hosted on professional cloud platforms
6. **Free:** All recommended platforms have generous free tiers
7. **Scalable:** Easy to modify company targets or schedule

---

## 🚨 Important Notes

1. **Keep API Keys Secret:** Never commit them to GitHub
2. **Monitor Usage:** Check your Google Sheets API quotas
3. **Update Company Lists:** Periodically refresh the company database
4. **Check Logs:** Monitor deployment logs for any issues

---

## 📞 Support

If you need help with deployment:
1. Check platform documentation
2. Review logs for error messages
3. Verify all environment variables are set correctly
4. Ensure Google service account has proper permissions

**Your system is ready to run 24/7 and generate leads automatically! 🎯**