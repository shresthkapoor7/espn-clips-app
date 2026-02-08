# Deploy to Railway

## Quick Deploy Steps

### 1. Initialize Git (if not already done)
```bash
git init
git add .
git commit -m "Initial commit"
```

### 2. Push to GitHub
```bash
# Create a new repo on GitHub, then:
git remote add origin <your-github-repo-url>
git branch -M main
git push -u origin main
```

### 3. Deploy on Railway
1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Choose "Deploy from GitHub repo"
4. Select your repository
5. Railway will auto-detect the configuration and deploy!

### 4. Add Environment Variables
In Railway dashboard:
- Go to your project → Variables
- Add these:
  - `SUPABASE_URL` = your Supabase URL
  - `SUPABASE_KEY` = your Supabase key
  - `GEMINI_API_KEY` = your Gemini API key

### 5. Wait for Deploy
- Railway will install ffmpeg automatically (via Aptfile)
- First deploy takes ~5 minutes (Whisper model download)
- You'll get a public URL like: `https://your-app.railway.app`

## Test Your Deployment
```bash
curl -X POST https://your-app.railway.app/auto-process
```

## Notes
- Railway free tier has 500 hours/month
- Processing videos is memory-intensive, may need paid plan ($5/month)
- Each request can take 5-10 minutes (be patient!)
