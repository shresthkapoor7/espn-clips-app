# main.py
import os
import asyncio
import subprocess
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from yt_dlp import YoutubeDL
import dotenv
from faster_whisper import WhisperModel
import google.generativeai as genai

dotenv.load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase init
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a local video to Supabase"""
    try:
        contents = await file.read()

        # Upload to Supabase
        response = supabase.storage.from_('videos').upload(
            f'test/{file.filename}',
            contents
        )

        return {
            "status": "success",
            "filename": file.filename,
            "message": "Video uploaded successfully"
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/fetch-clips")
async def fetch_clips():
    """Fetch last 1 clip from ESPN NFL, skip if already downloaded"""
    try:
        print("\n🔍 Checking existing videos in Supabase...")
        # Get existing videos in originals folder
        existing_files = supabase.storage.from_('videos').list(path='originals')
        existing_ids = set()

        if existing_files:
            for file in existing_files:
                video_id = file['name'].split('.')[0]
                existing_ids.add(video_id)
            print(f"📦 Found {len(existing_ids)} existing videos in storage")
        else:
            print("📦 No existing videos found")

        # Get last 1 video from ESPN NFL
        print("\n🎥 Fetching latest ESPN NFL video...")
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': 'in_playlist',
            'playlistend': 1,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                "https://www.youtube.com/@ESPNNFL/videos",
                download=False
            )

        clips = []
        new_clips = []

        print(f"\n📋 Processing {len(info['entries'][:1])} video...")
        for video in info['entries'][:1]:
            video_id = video['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            clip_data = {
                "title": video['title'],
                "url": video_url,
                "id": video_id
            }
            clips.append(clip_data)

            # Only queue for download if not already stored
            if video_id not in existing_ids:
                print(f"  ✨ NEW: {video['title']}")
                new_clips.append(clip_data)
            else:
                print(f"  ⏭️  SKIP: {video['title']} (already exists)")

        # Download only new clips
        if new_clips:
            print(f"\n⬇️  Downloading {len(new_clips)} new clip(s)...")
            await upload_clips_to_supabase(new_clips)
        else:
            print("\n✅ All clips already downloaded, nothing to do!")

        print(f"\n✅ Done! New: {len(new_clips)}, Skipped: {len(clips) - len(new_clips)}\n")

        return {
            "status": "success",
            "total_found": len(clips),
            "new_downloaded": len(new_clips),
            "already_exists": len(clips) - len(new_clips),
            "clips": clips
        }

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}\n")
        return {"status": "error", "message": str(e)}


@app.post("/auto-process")
async def auto_process():
    """Fetch latest ESPN NFL video, download it, and process into reels - all in one call"""
    try:
        print("\n🚀 AUTO-PROCESS: Fetch + Process in one go!\n")

        # Step 1: Fetch latest video
        print("🔍 Checking existing videos in Supabase...")
        existing_files = supabase.storage.from_('videos').list(path='originals')
        existing_ids = set()

        if existing_files:
            for file in existing_files:
                video_id = file['name'].split('.')[0]
                existing_ids.add(video_id)
            print(f"📦 Found {len(existing_ids)} existing videos in storage")
        else:
            print("📦 No existing videos found")

        # Get latest video from ESPN NFL
        print("\n🎥 Fetching latest ESPN NFL video...")
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': 'in_playlist',
            'playlistend': 1,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                "https://www.youtube.com/@ESPNNFL/videos",
                download=False
            )

        video = info['entries'][0]
        video_id = video['id']
        video_title = video['title']
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"📹 Found: {video_title}")
        print(f"   ID: {video_id}")

        # Step 2: Download if new
        if video_id in existing_ids:
            print(f"\n⚠️  Video already exists, processing existing one...")
        else:
            print(f"\n⬇️  Downloading new video...")
            ydl_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': f'/tmp/{video_id}.mp4',
                'quiet': True,
                'no_warnings': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip,deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls', 'dash', 'translated_subs']
                    }
                }
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Upload to Supabase
            print(f"📤 Uploading to Supabase...")
            file_path = f'/tmp/{video_id}.mp4'
            with open(file_path, 'rb') as f:
                supabase.storage.from_('videos').upload(
                    f'originals/{video_id}.mp4',
                    f.read()
                )
            print(f"✅ Uploaded to originals folder")

        # Step 3: Process video into reels
        print(f"\n🎬 Processing video into reels...\n")
        result = await process_video_internal(video_id)

        return {
            "status": "success",
            "video_id": video_id,
            "video_title": video_title,
            "was_new": video_id not in existing_ids,
            "processing_result": result
        }

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}\n")
        return {"status": "error", "message": str(e)}


@app.post("/process-video")
async def process_video(video_id: str):
    """Transcribe video, find highlights with Gemini, cut into reels"""
    result = await process_video_internal(video_id)
    return result


async def process_video_internal(video_id: str):
    """Internal function to process a video - used by both /process-video and /auto-process"""
    try:
        print(f"🎬 Processing video: {video_id}")

        # Download video from Supabase
        print("📥 Downloading video from Supabase...")
        video_path = f'/tmp/{video_id}.mp4'
        video_data = supabase.storage.from_('videos').download(f'originals/{video_id}.mp4')
        with open(video_path, 'wb') as f:
            f.write(video_data)
        print(f"✅ Downloaded to {video_path}")

        # Transcribe with Whisper
        print("\n🎤 Transcribing video with Whisper...")
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments_generator, info = model.transcribe(video_path)
        segments = list(segments_generator)
        transcript = " ".join([seg.text for seg in segments])
        print(f"✅ Transcription complete ({len(segments)} segments)")

        # Format transcript with timestamps for Gemini
        transcript_with_times = ""
        for seg in segments:
            start_time = f"{int(seg.start // 60)}:{int(seg.start % 60):02d}"
            transcript_with_times += f"[{start_time}] {seg.text}\n"

        print("\n🤖 Asking Gemini for best highlights...")

        # Call Gemini to get 5 highlight timestamps
        model = genai.GenerativeModel('gemini-3-flash-preview')
        prompt = f"""You are analyzing a sports video transcript to find the 5 most exciting and engaging moments for short-form content (reels/shorts).

Transcript with timestamps:
{transcript_with_times}

Find the 5 BEST moments that would make great 15-30 second reels. Look for:
- Exciting plays or action
- Key moments or highlights
- Memorable quotes or reactions
- Viral-worthy content

For each moment, provide:
1. Start time in seconds
2. End time in seconds (15-30 seconds after start)
3. Brief description

Return your response as a JSON array ONLY (no other text) in this exact format:
[
  {{"start": 45, "end": 70, "description": "Amazing touchdown play"}},
  {{"start": 120, "end": 145, "description": "Coach reaction to penalty"}},
  ...
]"""

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Extract JSON from response (in case there's extra text)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        highlights = json.loads(response_text)
        print(f"✅ Found {len(highlights)} highlights")

        # Cut videos using ffmpeg
        print("\n✂️  Cutting videos into reels...")
        reel_paths = []

        for i, highlight in enumerate(highlights, 1):
            try:
                start = highlight['start']
                end = highlight['end']
                duration = end - start

                reel_filename = f"{video_id}_reel_{i}.mp4"
                reel_path = f"/tmp/{reel_filename}"

                print(f"  [{i}/{len(highlights)}] Cutting {start}s to {end}s: {highlight['description']}")

                # Use ffmpeg to cut the video
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-ss', str(start),
                    '-t', str(duration),
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-y',  # Overwrite output file
                    reel_path
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"  ⚠️  ffmpeg error: {result.stderr}")
                    continue
                    
                reel_paths.append((reel_filename, reel_path, highlight['description']))
                print(f"  ✅ Cut reel {i}")
            except Exception as e:
                print(f"  ❌ Failed to cut reel {i}: {str(e)}")
                continue

        # Upload reels to Supabase
        print(f"\n📤 Uploading {len(reel_paths)} reels to Supabase...")
        uploaded_reels = []

        for filename, path, description in reel_paths:
            try:
                with open(path, 'rb') as f:
                    supabase.storage.from_('videos').upload(
                        f'reels/{filename}',
                        f.read()
                    )
                uploaded_reels.append({
                    "filename": filename,
                    "description": description
                })
                print(f"  ✅ Uploaded {filename}")
                os.remove(path)
            except Exception as e:
                print(f"  ❌ Failed to upload {filename}: {str(e)}")

        # Cleanup
        os.remove(video_path)

        print(f"\n✅ Processing complete! Generated {len(uploaded_reels)} reels\n")

        return {
            "status": "success",
            "video_id": video_id,
            "transcript": transcript[:500] + "...",  # First 500 chars
            "highlights": highlights,
            "reels": uploaded_reels
        }

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}\n")
        return {"status": "error", "message": str(e)}


async def upload_clips_to_supabase(clips):
    """Download clips from YouTube and upload to originals folder"""
    for i, clip in enumerate(clips, 1):
        try:
            print(f"  [{i}/{len(clips)}] Downloading: {clip['title']}")
            ydl_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': f'/tmp/{clip["id"]}.mp4',
                'quiet': True,
                'no_warnings': True,
                # Add headers to bypass YouTube restrictions
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip,deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls', 'dash', 'translated_subs']
                    }
                }
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([clip['url']])

            # Upload to originals folder
            print(f"  [{i}/{len(clips)}] Uploading to Supabase...")
            file_path = f'/tmp/{clip["id"]}.mp4'
            with open(file_path, 'rb') as f:
                supabase.storage.from_('videos').upload(
                    f'originals/{clip["id"]}.mp4',
                    f.read()
                )

            print(f"  [{i}/{len(clips)}] ✅ Uploaded {clip['title']}\n")
            os.remove(file_path)

        except Exception as e:
            print(f"  [{i}/{len(clips)}] ❌ Failed {clip['title']}: {str(e)}\n")


@app.get("/")
def health():
    return {"status": "ok"}